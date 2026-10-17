"""Facturas en lote desde una tabla (pegada de Excel/Sheets, CSV o XLSX).

Flujo: perfil de importación → leer tabla → resolver cada fila (cliente, folio, conceptos, centavo, validaciones SAT)
→ vista previa → timbrar (en segundo plano, fila por fila, sin duplicar) → registro / ZIP.

Reglas que NO se negocian:
- El total del CFDI debe ser IGUAL al monto cobrado. Se puede mover hasta `ajuste_centavos` por concepto para lograrlo
  (el ajuste queda visible en la vista previa); si no cuadra, la fila no se timbra.
- Una fila con error NO frena el lote: queda en "pendientes de corrección" con su folio APARTADO, y se rescata
  corrigiendo el dato y reintentando (mismo folio).
- Nunca se timbra dos veces la misma fila (referencia + folio + estados).
"""
import ast
import csv
import io
import operator
import os
import re
import threading
import zipfile
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import product

from sqlalchemy.orm import Session

from ..config import EN_WEB
from ..db import SessionLocal
from ..logs import log
from ..models import Cliente, Emisor, Factura, Lote, LoteFila
from ..schemas import ConceptoIn, FacturaIn, ReceptorIn
from . import facturacion, folios, importar, pac as pac_svc, pdf as pdf_svc, validacion

CENT, SEIS = Decimal("0.01"), Decimal("0.000001")
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE",
         "NOVIEMBRE", "DICIEMBRE"]
IVA16 = [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]


TOKENS_CARPETA = ("AAAA", "MM", "Mes", "MES", "RFC")


class ErrorFila(Exception):
    """Problema de una fila (se muestra al usuario tal cual)."""


# ---------------------------------------------------------------- perfil de ejemplo
PERFIL_EJEMPLO = {
    "serie": "C",
    "folio_modo": "hoja",  # hoja = el folio es el de tu tabla (C-30 → serie C, folio 30) · consecutivo = Timbra asigna
    "uso_cfdi": "D01",
    "metodo_pago": "PUE",
    "regimen_default": "605",
    # posición (0 = primera columna) de cada dato en tu tabla. Si pegas con encabezados, se buscan por nombre.
    "columnas": {"folio": 0, "nombre": 1, "rfc": 2, "cp": 3, "fecha": 4, "monto": 5, "servicio": 6, "forma": 10,
                 "regimen": 11, "direccion": 13, "correo": 14},
    "nombres_columnas": {"folio": "NO. FACTURA", "nombre": "NOMBRE", "rfc": "RFC", "cp": "CP",
                         "fecha": "FECHA DE PAGO", "monto": "MONTO", "servicio": "IVA 0%", "forma": "FORMA DE PAGO",
                         "regimen": "REGIMEN FISCAL", "direccion": "DIRECCION", "correo": "CORREO/CONTACTO"},
    "forma_map": {"TDC": "04", "TDD": "28", "TRANSF": "03", "EFE": "01", "EFECT": "01"},
    # Cada concepto: valor = fórmula con las columnas (servicio / 1.16 → precio sin IVA a 6 decimales)
    "conceptos": [
        {"descripcion": "SERVICIOS MÉDICOS DE CONTROL Y SEGUIMIENTO CLÍNICO DE SALUD Y CONTROL DE PESO DENTRO DEL "
                        "PROGRAMA DE TRATAMIENTO CLÍNICO DEL PACIENTE. CORRESPONDIENTE AL DÍA {DD} DE {MES} DE {AAAA}.",
         "clave_prod_serv": "85121503", "clave_unidad": "E48", "no_identificacion": "CED PROF 13868869",
         "cantidad": "1", "valor": "servicio / 1.16", "impuestos": IVA16},
        {"descripcion": "VITAMINAS Y MINERALES (SUPLEMENTO VITAMÍNICO) SUMINISTRADOS AL PACIENTE DENTRO DEL "
                        "TRATAMIENTO CLÍNICO. CORRESPONDIENTE AL DÍA {DD} DE {MES} DE {AAAA}.",
         "clave_prod_serv": "51191905", "clave_unidad": "H87", "no_identificacion": "",
         "cantidad": "1", "valor": "(monto - servicio) / 1.16", "impuestos": IVA16},
    ],
    "iva_permitido": ["0.16"],  # tasas de IVA que este perfil puede usar ("exento" y "0" bloqueados)
    "claves_bloqueadas": ["51191903", "51191908", "51191910"],  # medicamentos: nunca como suplemento
    "ajuste_centavos": 1,
    # Sólo con Timbra instalado en tu PC: al terminar el lote deja ahí el PDF y el XML de cada factura ({folio}_{UUID}).
    # Acepta {AAAA} {MM} {Mes} {MES} {RFC}; ej. G:\\Mi unidad\\Facturas\\{MM} {Mes}\\Clientes Emitidas
    "carpeta": "",
}


# ---------------------------------------------------------------- fórmulas (seguras, en Decimal)
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def evaluar(expr: str, valores: dict[str, Decimal]) -> Decimal:
    """Aritmética con + - * / paréntesis y los nombres de tus columnas. Nada más (no se ejecuta código)."""
    try:
        arbol = ast.parse(str(expr).strip(), mode="eval")
    except SyntaxError as e:
        raise ErrorFila(f"Fórmula inválida «{expr}»") from e

    def ev(n) -> Decimal:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return Decimal(str(n.value))
        if isinstance(n, ast.Name):
            if n.id not in valores:
                raise ErrorFila(f"La fórmula usa «{n.id}» y esa columna viene vacía o no es un número")
            return valores[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Div) and b == 0:
                raise ErrorFila(f"División entre cero en «{expr}»")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        raise ErrorFila(f"Fórmula no permitida «{expr}»: sólo + − × ÷, paréntesis, números y nombres de columna")

    return ev(arbol)


# ---------------------------------------------------------------- lectura de la tabla
def _num(s) -> Decimal | None:
    t = re.sub(r"[\s$]", "", str(s or "")).replace(",", "")
    if not t:
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def _monto_txt(m: Decimal | None) -> str:
    """El monto como texto comparable: 750, 750.00 y $750.00 son el mismo cobro."""
    return str(m.quantize(CENT)) if m is not None else ""


def _fecha(s) -> date | None:
    t = str(s or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(t[:10] if fmt == "%Y-%m-%d" else t, fmt).date()
        except ValueError:
            continue
    return None


def leer_filas(cfg: dict, texto: str | None = None, contenido: bytes | None = None,
               nombre_archivo: str | None = None) -> list[dict]:
    """Tabla → lista de {llave: celda}. Detecta si trae encabezados (si MONTO no es número)."""
    filas = importar.leer_tabla(nombre_archivo, contenido, texto)
    if not filas:
        return []
    cols = dict(cfg.get("columnas") or {})
    if "monto" not in cols:
        raise ErrorFila("El perfil no dice en qué columna va el MONTO.")
    idx = {k: int(v) for k, v in cols.items()}
    primera = filas[0]
    im = idx["monto"]
    if im < len(primera) and _num(primera[im]) is None and any(c.strip() for c in primera):
        nombres = {importar._norm(h): i for i, h in enumerate(primera)}
        for k, h in (cfg.get("nombres_columnas") or {}).items():
            n = importar._norm(h)
            if n in nombres:
                idx[k] = nombres[n]
        filas = filas[1:]
    out = []
    for fila in filas:
        if not any(str(c).strip() for c in fila):
            continue
        d = {k: (str(fila[i]).strip() if i < len(fila) else "") for k, i in idx.items()}
        if not d.get("monto") and not d.get("folio"):
            continue
        out.append(d)
    return out


def _folio(txt: str, serie_default: str | None) -> tuple[str | None, str]:
    m = re.match(r"^\s*([A-Za-z]*)\s*[-_ ]?\s*0*(\d+)\s*$", str(txt or ""))
    if not m:
        raise ErrorFila(f"No entiendo el folio «{txt}» (usa algo como C-30)")
    return (m.group(1).upper() or serie_default), str(int(m.group(2)))


def _mayus(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).upper()


# ---------------------------------------------------------------- validación del perfil
def validar_perfil(cfg: dict) -> list[str]:
    e = []
    if not isinstance(cfg, dict):
        return ["Perfil inválido."]
    cols = cfg.get("columnas") or {}
    if "monto" not in cols:
        e.append("Falta la columna MONTO.")
    for req in ("nombre", "rfc", "cp"):
        if req not in cols:
            e.append(f"Falta la columna {req.upper()}.")
    for k, v in cols.items():
        if not re.match(r"^[a-z_][a-z0-9_]*$", k):
            e.append(f"El nombre de columna «{k}» debe ir en minúsculas, sin espacios ni acentos (ej. servicio_iva).")
        if not str(v).isdigit():
            e.append(f"La posición de «{k}» debe ser un número (0 = primera columna).")
    if cfg.get("folio_modo", "hoja") == "hoja" and "folio" not in cols:
        e.append("Con folio de la hoja necesitas la columna FOLIO.")
    if not cfg.get("conceptos"):
        e.append("Agrega al menos un concepto.")
    carpeta = str(cfg.get("carpeta") or "").strip()
    if carpeta:
        if EN_WEB:
            e.append("La carpeta de entrega sólo existe con Timbra instalado en tu PC. En la web descarga el ZIP.")
        elif not os.path.isabs(carpeta.split("{")[0] or carpeta):
            e.append("La carpeta de entrega debe ser una ruta completa (ej. G:\\Mi unidad\\Facturas\\{MM} {Mes}).")
        for tok in re.findall(r"\{(\w+)\}", carpeta):
            if tok not in TOKENS_CARPETA:
                e.append(f"La carpeta usa {{{tok}}} y sólo se aceptan {', '.join('{' + t + '}' for t in TOKENS_CARPETA)}.")
    ficticios = {k: Decimal(1) for k in cols}
    for i, c in enumerate(cfg.get("conceptos") or [], start=1):
        try:
            evaluar(c.get("valor", ""), ficticios)
            evaluar(c.get("cantidad", "1") or "1", ficticios)
        except ErrorFila as x:
            e.append(f"Concepto {i}: {x}")
        for tok in re.findall(r"\{(\w+)\}", c.get("descripcion", "")):
            if tok not in ("DD", "MES", "mes", "AAAA", "año") and tok not in cols:
                e.append(f"Concepto {i}: la descripción usa {{{tok}}} y no existe esa columna.")
        if not c.get("descripcion", "").strip():
            e.append(f"Concepto {i}: falta la descripción.")
        try:
            ConceptoIn(clave_prod_serv=c.get("clave_prod_serv", ""), clave_unidad=c.get("clave_unidad", ""),
                       descripcion="x", valor_unitario=1, impuestos=c.get("impuestos") or [])
        except Exception as x:
            e.append(f"Concepto {i}: impuestos inválidos ({str(x)[:80]})")
        if validacion.select("C756_c_ClaveProdServ", c.get("clave_prod_serv", "")) is None:
            e.append(f"Concepto {i}: la clave SAT {c.get('clave_prod_serv') or '(vacía)'} no existe.")
        if validacion.select("C756_c_ClaveUnidad", c.get("clave_unidad", "")) is None:
            e.append(f"Concepto {i}: la unidad {c.get('clave_unidad') or '(vacía)'} no existe.")
    return e


# ---------------------------------------------------------------- centavo
def _total_cfdi(emisor: Emisor, conceptos: list[ConceptoIn], metodo: str, forma: str) -> Decimal:
    from . import cfdi as cfdi_svc
    d = FacturaIn(emisor_id=emisor.id or 0, tipo="I", metodo_pago=metodo, forma_pago=forma, conceptos=conceptos,
                  receptor=ReceptorIn(rfc="AAA010101AAA", nombre="X", regimen_fiscal="601",
                                      codigo_postal=emisor.lugar_expedicion, guardar=False))
    return Decimal(str(cfdi_svc.construir(emisor, d, None, "X", "1")["Total"]))


def cuadrar(emisor: Emisor, conceptos: list[dict], monto: Decimal, metodo: str, forma: str,
            tolerancia: int) -> tuple[list[Decimal], str | None]:
    """Devuelve los precios unitarios con los que el total del CFDI es EXACTAMENTE `monto`.
    Primero intenta tal cual (6 decimales); si no cuadra, mueve hasta `tolerancia` centavos por concepto
    (el menor movimiento posible) y lo describe."""
    def armar(vus):
        return [ConceptoIn(clave_prod_serv=c["clave_prod_serv"], clave_unidad=c["clave_unidad"],
                           descripcion=c["descripcion"], cantidad=c["cantidad"], valor_unitario=v,
                           impuestos=c["impuestos"]) for c, v in zip(conceptos, vus)]

    def total(vus):
        return _total_cfdi(emisor, armar(vus), metodo, forma)

    vus0 = [c["vu"] for c in conceptos]
    t0 = total(vus0)
    if t0 == monto:
        return vus0, None
    if tolerancia <= 0:
        raise ErrorFila(f"El total del CFDI sale {t0} y cobraste {monto}; el ajuste de centavos está apagado.")
    imps0 = [(c["cantidad"] * v).quantize(CENT, ROUND_HALF_UP) for c, v in zip(conceptos, vus0)]
    rango = range(-tolerancia, tolerancia + 1)
    mejor = None
    for ds in product(rango, repeat=min(len(conceptos), 6)):
        ds = ds + (0,) * (len(conceptos) - len(ds))
        if not any(ds):
            continue
        vus = []
        for c, imp, k, v0 in zip(conceptos, imps0, ds, vus0):
            vus.append(((imp + CENT * k) / c["cantidad"]).quantize(SEIS, ROUND_HALF_UP) if k else v0)
        if any(v <= 0 for v in vus):
            continue
        if total(vus) == monto:
            score = (sum(abs(k) for k in ds), -sum(imps0[i] for i, k in enumerate(ds) if k))
            if mejor is None or score < mejor[0]:
                mejor = (score, vus, ds)
    if mejor is None:
        raise ErrorFila(f"No se pudo cuadrar el total al centavo: el CFDI sale {t0} y cobraste {monto} "
                        f"(con hasta {tolerancia} centavo(s) de ajuste por concepto).")
    _, vus, ds = mejor
    det = []
    for i, (c, imp, k) in enumerate(zip(conceptos, imps0, ds), start=1):
        if k:
            det.append(f"concepto {i}: {imp:,.2f} → {imp + CENT * k:,.2f}")
    return vus, "Ajuste de centavo para que el total sea " + f"{monto:,.2f}" + " (" + "; ".join(det) + ")"


# ---------------------------------------------------------------- una fila
def _vigente(db: Session, emisor_id: int, referencia: str | None) -> Factura | None:
    """La factura timbrada y NO cancelada que ya existe para ese renglón de la hoja (es la que impide duplicar)."""
    if not referencia:
        return None
    return (db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.referencia == referencia,
                                     Factura.uuid.isnot(None), Factura.estado != "cancelada").order_by(Factura.id.desc()).first())


def _tokens(texto: str, datos: dict, fecha: date | None) -> str:
    def rep(m):
        t = m.group(1)
        if t in ("DD", "MES", "mes", "AAAA", "año"):
            if fecha is None:
                raise ErrorFila("Falta la fecha de pago (la descripción usa el día/mes/año)")
            return {"DD": f"{fecha.day:02d}", "MES": MESES[fecha.month - 1], "mes": MESES[fecha.month - 1].lower(),
                    "AAAA": str(fecha.year), "año": str(fecha.year)}[t]
        return str(datos.get(t, ""))
    return re.sub(r"\{(\w+)\}", rep, texto)


def resolver(db: Session, emisor: Emisor, cfg: dict, datos: dict, fila_id: int | None = None,
             ctx: dict | None = None) -> dict:
    """Una fila de la tabla → todo lo necesario para timbrarla (o por qué no se puede). No timbra ni guarda."""
    ctx = ctx or {}
    errores: list[str] = []
    avisos: list[dict] = []
    resumen: dict = {}
    out = {"serie": None, "folio": None, "referencia": None, "payload": {}}

    def aviso(t, nivel="aviso"):
        avisos.append({"nivel": nivel, "texto": t})

    d = {k: str(v or "").strip() for k, v in datos.items()}
    nombre, rfc = _mayus(d.get("nombre")), re.sub(r"\s", "", d.get("rfc", "")).upper()
    cp = re.sub(r"\D", "", d.get("cp", ""))
    cp = cp.zfill(5) if len(cp) == 4 else cp  # Excel le quita el cero a los CP
    monto = _num(d.get("monto"))
    fecha = _fecha(d.get("fecha"))
    resumen.update(nombre=nombre, rfc=rfc, monto=str(monto) if monto is not None else d.get("monto", ""))

    # ---- datos mínimos
    if not nombre:
        errores.append("Falta el nombre.")
    if not rfc:
        errores.append("Falta el RFC.")
    if not re.match(r"^\d{5}$", cp):
        errores.append(f"El CP «{d.get('cp', '')}» debe tener 5 dígitos.")
    if monto is None or monto <= 0:
        errores.append(f"El monto «{d.get('monto', '')}» no es un número mayor a 0.")
    if d.get("fecha") and fecha is None:
        errores.append(f"La fecha «{d['fecha']}» no se entiende (usa día/mes/año).")
    if fecha:
        resumen["fecha"] = fecha.isoformat()
        prev = ctx.get("fecha_anterior")
        if prev and fecha < prev:
            aviso(f"La fecha ({fecha:%d/%m/%Y}) es anterior a la de la fila de arriba ({prev:%d/%m/%Y}).")

    # ---- ¿ya se timbró esta fila? (puedes volver a pegar la hoja completa sin duplicar nada)
    serie_default = cfg.get("serie") or None
    referencia = d.get("folio", "").strip() or None
    out["referencia"] = referencia
    if referencia:
        ya = _vigente(db, emisor.id, referencia)
        if ya:
            resumen["ya_timbrada"] = ya.id
            return {**out, "estado": "omitida", "etapa": None, "resumen": resumen, "errores": [],
                    "avisos": [{"nivel": "info", "texto": f"Ya estaba timbrada: factura {ya.serie or ''}{ya.folio}"}],
                    "error": None}
        cancelada = (db.query(Factura).filter(Factura.emisor_id == emisor.id, Factura.referencia == referencia,
                                              Factura.estado == "cancelada").order_by(Factura.id.desc()).first())
        if cancelada:  # se timbró y se canceló: no se omite en silencio, se vuelve a emitir
            resumen["reexpide"] = cancelada.id
            if cfg.get("folio_modo", "hoja") == "hoja":
                aviso(f"{referencia} ya se timbró y está cancelada ({cancelada.serie or ''}{cancelada.folio}). "
                      "Para emitirla de nuevo ponle un folio nuevo.")
            else:
                aviso(f"{referencia} ya se timbró y está cancelada ({cancelada.serie or ''}{cancelada.folio}): se emite de nuevo.")

    # ---- folio
    if cfg.get("folio_modo", "hoja") == "hoja":
        if not serie_default:
            errores.append("El perfil necesita la serie (ej. C) para usar el folio de la hoja.")
        try:
            serie, folio = _folio(d.get("folio", ""), serie_default)
            vistos = ctx.get("folios", {})
            otro = folios.usado_por(db, emisor.id, serie, folio, excepto_fila=fila_id)
            if (serie, folio) in vistos:
                errores.append(f"El folio {serie or ''}{folio} está repetido en la fila {vistos[(serie, folio)]} de esta tabla.")
            elif otro:
                errores.append(f"El folio {serie or ''}{folio} ya lo tiene {otro}.")
            else:
                out["serie"], out["folio"] = serie, folio  # folio válido y libre: queda APARTADO para esta fila
        except ErrorFila as e:
            errores.append(str(e))
    else:
        out["serie"] = serie_default
    # ---- cliente
    cli = db.query(Cliente).filter_by(emisor_id=emisor.id, rfc=rfc).order_by(Cliente.id).first() if rfc else None
    texto_regimen = d.get("regimen", "")
    regimen = importar.regimen_a_clave(texto_regimen) if texto_regimen else None
    if texto_regimen and not regimen:
        errores.append(f"No reconozco el régimen «{texto_regimen}». Pon la clave (ej. 605).")
    regimen = regimen or (cli.regimen_fiscal if cli else None) or cfg.get("regimen_default")
    if not regimen:
        errores.append("Falta el régimen fiscal del cliente.")
    # El uso lo manda la hoja, luego el perfil; el guardado en el cliente sólo si ninguno lo dice
    uso = _mayus(d.get("uso")) or cfg.get("uso_cfdi") or (cli.uso_cfdi if cli else None) or "G03"
    resumen["regimen"], resumen["uso"] = regimen, uso
    cliente_id = None
    if cli is None:
        resumen["cliente"] = "nuevo"
        aviso("Cliente nuevo: se dará de alta al timbrar.", "info")
    else:
        difs = []
        if _mayus(cli.nombre) != nombre:
            difs.append(f"nombre ({cli.nombre} → {nombre})")
        if cli.codigo_postal != cp:
            difs.append(f"CP ({cli.codigo_postal} → {cp})")
        if regimen and cli.regimen_fiscal != regimen:
            difs.append(f"régimen ({cli.regimen_fiscal} → {regimen})")
        if difs:
            resumen["cliente"] = "datos_distintos"
            aviso("La hoja trae datos distintos a los del cliente guardado: " + ", ".join(difs) +
                  ". Se usan los de la hoja y se actualiza el cliente al timbrar.")
        else:
            resumen["cliente"], cliente_id = "existe", cli.id
    if cp and emisor.lugar_expedicion and cp[:2] != emisor.lugar_expedicion[:2]:
        aviso(f"El CP {cp} es de otra zona que el emisor ({emisor.lugar_expedicion}). Confírmalo con su constancia.")
    clave_dup = (rfc, _monto_txt(monto), fecha.isoformat() if fecha else d.get("fecha"))
    if rfc and clave_dup in ctx.get("duplicados", {}):
        aviso(f"Mismo cliente, monto y fecha que la fila {ctx['duplicados'][clave_dup]}: ¿cobro repetido?")

    # ---- forma de pago
    forma = None
    ftxt = _mayus(d.get("forma"))
    if not ftxt:
        errores.append("Falta la forma de pago.")
    else:
        fm = {_mayus(k): v for k, v in (cfg.get("forma_map") or {}).items()}
        forma = fm.get(ftxt) or (ftxt if re.match(r"^\d{2}$", ftxt) else None)
        if not forma:
            errores.append(f"Forma de pago «{ftxt}» desconocida: agrégala al perfil (TDC→04, TDD→28, TRANSF→03, EFE→01).")
    metodo = cfg.get("metodo_pago") or "PUE"

    # ---- conceptos (fórmulas + tokens + políticas)
    valores = {k: n for k in (cfg.get("columnas") or {}) if (n := _num(d.get(k))) is not None}
    if monto is not None:
        valores["monto"] = monto
    conceptos = []
    permitido = {str(x).lower() for x in (cfg.get("iva_permitido") or [])}
    for i, c in enumerate(cfg.get("conceptos") or [], start=1):
        try:
            vu = evaluar(c["valor"], valores).quantize(SEIS, ROUND_HALF_UP)
            cant = evaluar(c.get("cantidad") or "1", valores)
            if vu <= 0 or cant <= 0:
                raise ErrorFila(f"el precio o la cantidad sale 0 o negativo")
            conceptos.append({"clave_prod_serv": c["clave_prod_serv"], "clave_unidad": c["clave_unidad"],
                              "descripcion": _tokens(c["descripcion"], d, fecha),
                              "no_identificacion": c.get("no_identificacion") or None,
                              "cantidad": cant, "vu": vu, "impuestos": c.get("impuestos") or []})
        except ErrorFila as e:
            errores.append(f"Concepto {i}: {e}")
        if c.get("clave_prod_serv") in (cfg.get("claves_bloqueadas") or []):
            errores.append(f"⛔ La clave {c['clave_prod_serv']} es de un medicamento: no puede facturarse como "
                           "suplemento. Revísala con la médica antes de timbrar.")
            resumen["bloqueo"] = True
        if permitido:
            for imp in c.get("impuestos") or []:
                if imp.get("impuesto") == "002" and imp.get("tipo") == "traslado":
                    tasa = "exento" if imp.get("factor") == "Exento" else str(Decimal(str(imp.get("tasa") or 0)).normalize())
                    if tasa not in permitido:
                        errores.append(f"Concepto {i}: IVA {tasa} no está permitido en este perfil "
                                       f"(sólo {', '.join(sorted(permitido))}).")

    # ---- cuadrar el total y armar el CFDI
    total = None
    if conceptos and monto is not None and forma and not any(e.startswith("Concepto") for e in errores):
        try:
            vus, ajuste = cuadrar(emisor, conceptos, monto, metodo, forma, int(cfg.get("ajuste_centavos", 1)))
            for c, v in zip(conceptos, vus):
                c["vu"] = v
            if ajuste:
                resumen["ajuste"] = ajuste
                aviso(ajuste, "info")
        except ErrorFila as e:
            errores.append(str(e))
    if conceptos and not errores:
        receptor = ReceptorIn(rfc=rfc, nombre=nombre, regimen_fiscal=regimen, codigo_postal=cp, uso_cfdi=uso,
                              guardar=False)
        data = FacturaIn(
            emisor_id=emisor.id, tipo="I", serie=out["serie"], folio=out["folio"], referencia=referencia,
            metodo_pago=metodo, forma_pago=forma, cliente_id=cliente_id, receptor=None if cliente_id else receptor,
            uso_cfdi=uso,  # el cliente guardado puede traer otro uso: en el lote manda el del perfil
            conceptos=[ConceptoIn(clave_prod_serv=c["clave_prod_serv"], clave_unidad=c["clave_unidad"],
                                  descripcion=c["descripcion"], no_identificacion=c["no_identificacion"],
                                  cantidad=c["cantidad"], valor_unitario=c["vu"], impuestos=c["impuestos"])
                       for c in conceptos])
        prev = facturacion.previsualizar(db, data)
        for v in prev["errores"]:
            errores.append(v["mensaje"])
        for v in prev["avisos"]:
            # lo del emisor (CSD, PAC) y la familia 51 del perfil se muestran UNA vez arriba del lote, no en cada fila
            if str(v.get("campo", "")).startswith("emisor") or "familia de medicamentos" in v["mensaje"]:
                continue
            aviso(v["mensaje"])
        total = Decimal(str(prev["total"]))
        if not prev["errores"] and total != monto:
            errores.append(f"El total del CFDI sale {total:,.2f} y cobraste {monto:,.2f}.")
        resumen["total"] = str(total)
        resumen["subtotal"] = str(prev["subtotal"])
        resumen["conceptos"] = [{"descripcion": c["descripcion"][:90], "clave": c["clave_prod_serv"],
                                 "unidad": c["clave_unidad"], "cantidad": str(c["cantidad"]),
                                 "valor_unitario": str(c["vu"]),
                                 "importe": str((c["cantidad"] * c["vu"]).quantize(CENT, ROUND_HALF_UP))}
                                for c in conceptos]
        out["payload"] = data.model_dump(mode="json")

    ctx.setdefault("duplicados", {}).setdefault(clave_dup, ctx.get("n"))
    if out["folio"]:
        ctx.setdefault("folios", {}).setdefault((out["serie"], out["folio"]), ctx.get("n"))
    if fecha:
        ctx["fecha_anterior"] = fecha
    estado = "error" if errores else "listo"
    return {**out, "estado": estado, "etapa": "validacion" if errores else None, "resumen": resumen,
            "errores": errores, "avisos": avisos, "error": "; ".join(errores) or None}


# ---------------------------------------------------------------- lote: crear / editar / consultar
def _aplicar(fila: LoteFila, r: dict):
    fila.estado, fila.etapa = r["estado"], r["etapa"]
    fila.serie, fila.folio, fila.referencia = r["serie"], r["folio"], r["referencia"]
    fila.payload, fila.resumen = r["payload"], r["resumen"]
    fila.errores, fila.avisos, fila.error = r["errores"], r["avisos"], r["error"]
    fila.actualizado = datetime.now()


def crear_lote(db: Session, emisor: Emisor, nombre: str, cfg: dict, perfil_id: int | None, filas: list[dict]) -> Lote:
    lote = Lote(emisor_id=emisor.id, perfil_id=perfil_id, nombre=nombre, config=cfg, estado="borrador")
    db.add(lote)
    db.flush()
    ctx: dict = {}
    for n, datos in enumerate(filas, start=1):
        ctx["n"] = n
        fila = LoteFila(lote_id=lote.id, emisor_id=emisor.id, n=n, datos=datos)
        db.add(fila)
        db.flush()
        _aplicar(fila, resolver(db, emisor, cfg, datos, fila.id, ctx))
        db.flush()  # el folio apartado ya cuenta para las filas siguientes
    db.commit()
    return lote


def _contexto(db: Session, lote: Lote, excepto: LoteFila) -> dict:
    ctx: dict = {"n": excepto.n, "folios": {}, "duplicados": {}}
    previas = db.query(LoteFila).filter(LoteFila.lote_id == lote.id, LoteFila.id != excepto.id).order_by(LoteFila.n)
    for o in previas:
        if o.folio and o.estado not in ("omitida",):
            ctx["folios"].setdefault((o.serie, o.folio), o.n)
        if o.n < excepto.n and o.resumen.get("fecha"):
            ctx["fecha_anterior"] = date.fromisoformat(o.resumen["fecha"])
        if o.n < excepto.n:
            ctx["duplicados"].setdefault((o.resumen.get("rfc"), _monto_txt(_num(o.resumen.get("monto"))),
                                          o.resumen.get("fecha") or o.datos.get("fecha")), o.n)
    return ctx


def actualizar_fila(db: Session, lote: Lote, fila: LoteFila, cambios: dict) -> LoteFila:
    """Corrige datos de una fila y la vuelve a validar. Conserva su folio apartado."""
    if fila.estado in ("timbrada", "timbrando"):
        raise ErrorFila("Esa fila ya se timbró: no se puede cambiar.")
    emisor = db.get(Emisor, lote.emisor_id)
    fila.datos = {**fila.datos, **{k: str(v) for k, v in cambios.items()}}
    _aplicar(fila, resolver(db, emisor, lote.config, fila.datos, fila.id, _contexto(db, lote, fila)))
    db.commit()
    return fila


def omitir_fila(db: Session, fila: LoteFila):
    if fila.estado in ("timbrada", "timbrando"):
        raise ErrorFila("Esa fila ya se timbró.")
    fila.estado, fila.actualizado = "omitida", datetime.now()  # libera su folio
    db.commit()


def descartar_lote(db: Session, lote: Lote) -> int:
    """Omite todas las filas que aún no se timbran y libera sus folios (revisar filas los aparta). Devuelve cuántas liberó."""
    if en_ejecucion(lote.id):
        raise ErrorFila("El lote se está timbrando: detenlo primero.")
    n = 0
    for fila in db.query(LoteFila).filter(LoteFila.lote_id == lote.id, LoteFila.estado.in_(("listo", "error"))).all():
        fila.estado, fila.actualizado = "omitida", datetime.now()
        n += 1
    db.commit()
    return n


# ---------------------------------------------------------------- ejecución
_EJECUTANDO: set[int] = set()
_DETENER: set[int] = set()
_GUARDANDO: set[int] = set()  # lotes que ya timbraron y están dejando sus PDF/XML en la carpeta de entrega
_LOCK = threading.Lock()


def en_ejecucion(lote_id: int) -> bool:
    return lote_id in _EJECUTANDO


def detener(lote_id: int):
    _DETENER.add(lote_id)


class _Alto(Exception):
    pass


def _cliente_despues(db: Session, emisor: Emisor, fila: LoteFila, f: Factura):
    """Tras timbrar: alta o actualización del cliente con los datos de la hoja y liga con la factura."""
    p = fila.payload
    if p.get("cliente_id"):
        f.cliente_id = p["cliente_id"]
        return
    r = p.get("receptor") or {}
    c = db.query(Cliente).filter_by(emisor_id=emisor.id, rfc=r["rfc"]).order_by(Cliente.id).first()
    emails, tel = importar._separar_contacto(fila.datos.get("correo", ""))
    if c is None:
        c = Cliente(emisor_id=emisor.id, rfc=r["rfc"], nombre=r["nombre"], regimen_fiscal=r["regimen_fiscal"],
                    codigo_postal=r["codigo_postal"], uso_cfdi=r.get("uso_cfdi") or "G03", emails=emails, telefono=tel,
                    direccion=fila.datos.get("direccion") or None)
        db.add(c)
        db.flush()
    else:
        c.nombre, c.regimen_fiscal, c.codigo_postal = r["nombre"], r["regimen_fiscal"], r["codigo_postal"]
        if emails and not c.emails:
            c.emails = emails
    f.cliente_id = c.id


def _timbrar_fila(db: Session, lote: Lote, fila: LoteFila):
    emisor = db.get(Emisor, lote.emisor_id)
    # Idempotencia: si por referencia o folio ya hay una factura timbrada para esta fila, no se vuelve a timbrar
    ya = _vigente(db, emisor.id, fila.referencia)
    if ya is None and fila.folio:
        ya = db.query(Factura).filter(Factura.emisor_id == emisor.id, Factura.serie == fila.serie,
                                      Factura.folio == fila.folio, Factura.uuid.isnot(None)).first()
    if ya:
        fila.estado, fila.factura_id, fila.error, fila.etapa = "timbrada", ya.id, None, None
        db.commit()
        return
    fila.estado, fila.etapa, fila.error = "timbrando", None, None
    fila.intentos = (fila.intentos or 0) + 1
    db.commit()  # el folio sigue apartado mientras se timbra
    data = FacturaIn.model_validate(fila.payload)
    try:
        f = facturacion.emitir(db, data, fila_id=fila.id)
    except facturacion.TimbradoSinGuardar as e:
        db.rollback()
        fila = db.get(LoteFila, fila.id)
        fila.estado, fila.etapa, fila.error = "error", "timbrado", str(e)
        fila.resumen = {**fila.resumen, "critico": True}
        db.commit()
        raise _Alto() from e
    except Exception as e:  # el PAC o el SAT rechazaron: la fila se aparta con su folio y se rescata después
        db.rollback()
        fila = db.get(LoteFila, fila.id)
        diag = getattr(e, "diag", None)
        fila.estado, fila.etapa = "error", "timbrado"
        fila.error = str(e)
        fila.errores = [str(e)]
        fila.resumen = {**fila.resumen, "diagnostico": diag.clave if diag else None}
        db.commit()
        log.warning("Lote %s fila %s no se timbró: %s", lote.id, fila.n, e)
        return
    fila = db.get(LoteFila, fila.id)
    fila.estado, fila.factura_id, fila.error, fila.etapa, fila.errores = "timbrada", f.id, None, None, []
    try:
        _cliente_despues(db, emisor, fila, f)
    except Exception:
        db.rollback()
        log.exception("Lote %s fila %s: timbrada pero no se pudo ligar el cliente", lote.id, fila.n)
        fila = db.get(LoteFila, fila.id)
        fila.estado, fila.factura_id = "timbrada", f.id
    db.commit()


def seleccionar(db: Session, lote: Lote, ids: list[int] | None, primeras: int | None) -> list[int]:
    q = db.query(LoteFila).filter(LoteFila.lote_id == lote.id, LoteFila.estado == "listo")
    if ids:
        q = q.filter(LoteFila.id.in_(ids))
    sel = [f.id for f in q.order_by(LoteFila.n)]
    return sel[:primeras] if primeras else sel


def _correr(lote_id: int, ids: list[int], detener_en_error: bool):
    try:
        with SessionLocal() as db:
            lote = db.get(Lote, lote_id)
            lote.estado = "en_proceso"
            db.commit()
            for fid in ids:
                if lote_id in _DETENER:
                    break
                fila = db.get(LoteFila, fid)
                if fila is None or fila.estado != "listo":
                    continue
                try:
                    _timbrar_fila(db, lote, fila)
                except _Alto:
                    break
                db.refresh(fila)
                if detener_en_error and fila.estado == "error":
                    break
            lote = db.get(Lote, lote_id)
            queda = db.query(LoteFila).filter(LoteFila.lote_id == lote_id, LoteFila.estado.in_(("listo", "error"))).count()
            lote.estado = "detenido" if lote_id in _DETENER else ("borrador" if queda else "terminado")
            db.commit()
            if carpeta_activa(lote.config):  # lo timbrado ya está a salvo en la base; la copia a tu carpeta nunca lo afecta
                _GUARDANDO.add(lote_id)
                try:
                    r = guardar_en_carpeta(db, lote)
                    if r["errores"]:
                        log.warning("Lote %s: no todo llegó a la carpeta: %s", lote_id, "; ".join(r["errores"][:3]))
                except Exception:
                    log.exception("Lote %s: no se pudo guardar en la carpeta de entrega", lote_id)
    except Exception:
        log.exception("El lote %s se interrumpió", lote_id)
    finally:
        with _LOCK:
            _EJECUTANDO.discard(lote_id)
            _DETENER.discard(lote_id)
            _GUARDANDO.discard(lote_id)


def iniciar(db: Session, lote: Lote, ids: list[int] | None = None, primeras: int | None = None,
            detener_en_error: bool = False, esperar: bool = False) -> int:
    """Arranca el timbrado en segundo plano. Devuelve cuántas filas va a procesar."""
    sel = seleccionar(db, lote, ids, primeras)
    if not sel:
        return 0
    with _LOCK:
        if lote.id in _EJECUTANDO:
            raise ErrorFila("Este lote ya se está timbrando.")
        _EJECUTANDO.add(lote.id)
    hilo = threading.Thread(target=_correr, args=(lote.id, sel, detener_en_error), daemon=True, name=f"lote-{lote.id}")
    hilo.start()
    if esperar:
        hilo.join()
    return len(sel)


def recuperar_interrumpidas(db: Session) -> int:
    """Al arrancar: filas que quedaron 'timbrando' por un cierre inesperado. Si ya existe la factura se ligan;
    si no, vuelven a 'error' para revisarlas a mano (nunca se reintentan solas: podrían estar timbradas en el PAC)."""
    n = 0
    for fila in db.query(LoteFila).filter(LoteFila.estado == "timbrando"):
        ya = _vigente(db, fila.emisor_id, fila.referencia)
        if ya:
            fila.estado, fila.factura_id = "timbrada", ya.id
        else:
            fila.estado, fila.etapa = "error", "timbrado"
            fila.error = ("El programa se cerró mientras se timbraba esta fila. Revisa en Facturas si se emitió "
                          "(también Facturas → Recuperar) antes de reintentar.")
        n += 1
    for lote in db.query(Lote).filter(Lote.estado == "en_proceso"):
        lote.estado = "detenido"
    db.commit()
    return n


# ---------------------------------------------------------------- salidas
def alertas_lote(db: Session, lote: Lote) -> list[dict]:
    """Lo que aplica a TODO el lote (no se repite fila por fila): CSD, modo de pruebas y claves de la familia 51."""
    e = db.get(Emisor, lote.emisor_id)
    out = []
    if not e.cer:
        out.append({"nivel": "error", "texto": f"{e.rfc} no tiene CSD cargado: no se puede timbrar. Súbelo en Emisores y CSD."})
    elif e.csd_vence and e.csd_vence < datetime.now():
        prueba = e.pac is None or e.pac.proveedor == "demo" or e.pac.pruebas
        out.append({"nivel": "aviso" if prueba else "error",
                    "texto": f"El CSD de {e.rfc} venció el {e.csd_vence:%d/%m/%Y}." + (" (en pruebas se permite)" if prueba else " Renuévalo antes de timbrar.")})
    if e.pac is None or e.pac.proveedor == "demo":
        out.append({"nivel": "aviso", "texto": "Modo demo: se sella pero NO se timbra ante el SAT."})
    elif e.pac.pruebas:
        out.append({"nivel": "aviso", "texto": f"{e.pac.nombre} está en ambiente de pruebas: los CFDI no tienen validez fiscal."})
    bloq = set((lote.config.get("claves_bloqueadas") or [])) | {str(x) for x in ((e.config_facturar or {}).get("claves_bloqueadas") or [])}
    for c in lote.config.get("conceptos") or []:
        k = str(c.get("clave_prod_serv", ""))
        if k.startswith("51") and k not in bloq:
            out.append({"nivel": "info", "texto": f"El perfil usa la clave {k} (familia de medicamentos y productos farmacéuticos): "
                                                   "confirma que sea lo que vendes. Las claves bloqueadas sí detienen la fila."})
    return out


def resumen_lote(db: Session, lote: Lote) -> dict:
    cuentas = {k: 0 for k in ("listo", "error", "timbrando", "timbrada", "omitida")}
    suma_cobrado = suma_listo = Decimal(0)
    for f in db.query(LoteFila).filter(LoteFila.lote_id == lote.id):
        cuentas[f.estado] = cuentas.get(f.estado, 0) + 1
        m = _num(f.resumen.get("monto"))
        if m is not None and f.estado == "timbrada":
            suma_cobrado += m
        if m is not None and f.estado == "listo":
            suma_listo += m
    return {"id": lote.id, "nombre": lote.nombre, "estado": "en_proceso" if en_ejecucion(lote.id) else lote.estado,
            "creado": lote.creado, "perfil_id": lote.perfil_id, "cuentas": cuentas,
            "total_timbrado": str(suma_cobrado), "total_listo": str(suma_listo), "ejecutando": en_ejecucion(lote.id),
            "guardando": lote.id in _GUARDANDO, "entrega": entrega(db, lote)}


def registro_csv(db: Session, lote: Lote) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Folio hoja", "Folio Timbra", "Cliente", "RFC", "UUID", "Total", "Estado", "Error"])
    for f in db.query(LoteFila).filter(LoteFila.lote_id == lote.id).order_by(LoteFila.n):
        fac = db.get(Factura, f.factura_id) if f.factura_id else None
        w.writerow([f.referencia or "", f"{(fac.serie or '') if fac else (f.serie or '')}{(fac.folio or '') if fac else (f.folio or '')}",
                    f.resumen.get("nombre", ""), f.resumen.get("rfc", ""), fac.uuid if fac else "",
                    f.resumen.get("total") or f.resumen.get("monto", ""),
                    {"timbrada": "Timbrada", "error": "Pendiente de corrección", "listo": "Lista",
                     "omitida": "Omitida", "timbrando": "Timbrando"}.get(f.estado, f.estado),
                    f.error or ""])
    return ("﻿" + out.getvalue()).encode("utf-8")


def _limpio(s: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", s or "").strip("_")


def _timbradas(db: Session, lote: Lote) -> list[tuple[str, Factura]]:
    """(nombre de archivo sin extensión, factura) de cada fila timbrada: {folio de la hoja}_{UUID}."""
    facs = []
    for f in db.query(LoteFila).filter(LoteFila.lote_id == lote.id, LoteFila.estado == "timbrada").order_by(LoteFila.n):
        fac = db.get(Factura, f.factura_id)
        if fac and fac.xml:
            facs.append((f"{_limpio(f.referencia or (fac.serie or '') + (fac.folio or ''))}_{fac.uuid}", fac))
    return facs


# ---------------------------------------------------------------- carpeta de entrega (Timbra instalado en tu PC)
def carpeta_activa(cfg: dict) -> bool:
    return bool(str(cfg.get("carpeta") or "").strip()) and not EN_WEB


def carpeta_de(cfg: dict, emisor: Emisor, cuando: datetime | None) -> str:
    """La carpeta de esa factura: los {tokens} salen de su fecha de emisión (cada mes cae en su carpeta)."""
    cuando = cuando or datetime.now()
    rep = {"AAAA": f"{cuando:%Y}", "MM": f"{cuando:%m}", "Mes": MESES[cuando.month - 1].capitalize(),
           "MES": MESES[cuando.month - 1], "RFC": emisor.rfc}
    return os.path.normpath(re.sub(r"\{(\w+)\}", lambda m: rep.get(m.group(1), m.group(0)), str(cfg["carpeta"]).strip()))


def entrega(db: Session, lote: Lote) -> dict | None:
    """Cuántas facturas del lote ya tienen su PDF y XML en la carpeta. Se mira el disco: no se confía en una marca."""
    if not carpeta_activa(lote.config):
        return None
    emisor = db.get(Emisor, lote.emisor_id)
    facs = _timbradas(db, lote)
    carpetas, completas = [], 0
    for base, fac in facs:
        d = carpeta_de(lote.config, emisor, fac.fecha)
        if d not in carpetas:
            carpetas.append(d)
        completas += os.path.isfile(os.path.join(d, base + ".xml")) and os.path.isfile(os.path.join(d, base + ".pdf"))
    return {"carpetas": carpetas or [carpeta_de(lote.config, emisor, None)], "guardadas": completas, "timbradas": len(facs)}


def _escribir(ruta: str, datos: bytes):
    tmp = ruta + ".parcial"  # Drive no debe sincronizar un archivo a medias
    with open(tmp, "wb") as fh:
        fh.write(datos if isinstance(datos, bytes) else str(datos).encode("utf-8"))
    os.replace(tmp, ruta)


def guardar_en_carpeta(db: Session, lote: Lote) -> dict:
    """Deja en la carpeta de entrega el XML y el PDF de cada factura timbrada que aún no esté ahí. No pisa archivos."""
    if EN_WEB:
        raise ErrorFila("La carpeta de entrega sólo existe con Timbra instalado en tu PC. Aquí descarga el ZIP.")
    if not carpeta_activa(lote.config):
        raise ErrorFila("El perfil de este lote no tiene carpeta de entrega. Agrégala en el perfil.")
    emisor = db.get(Emisor, lote.emisor_id)
    nuevos, errores, sin_pdf, hechas = 0, [], [], set()
    for base, fac in _timbradas(db, lote):
        d = carpeta_de(lote.config, emisor, fac.fecha)
        ruta = os.path.join(d, base)
        try:
            if d not in hechas:
                os.makedirs(d, exist_ok=True)
                hechas.add(d)
            if not os.path.isfile(ruta + ".xml"):
                _escribir(ruta + ".xml", fac.xml)
                nuevos += 1
            if not os.path.isfile(ruta + ".pdf"):
                sin_pdf.append((ruta, fac))
        except OSError as e:
            errores.append(f"{base.split('_')[0]}: no se pudo escribir en {d} ({e.strerror or e})")
    if sin_pdf:
        pdfs = pdf_svc.pdf_varios([(fac.xml, fac.emisor) for _, fac in sin_pdf])  # en paralelo
        for (ruta, fac), datos in zip(sin_pdf, pdfs):
            try:
                if not datos:
                    raise OSError("no se pudo generar el PDF")
                _escribir(ruta + ".pdf", datos)
                nuevos += 1
            except OSError as e:
                errores.append(f"{os.path.basename(ruta).split('_')[0]}: PDF sin guardar ({e.strerror or e})")
    return {**(entrega(db, lote) or {}), "archivos_nuevos": nuevos, "errores": errores}


def zip_cfdi(db: Session, lote: Lote) -> bytes:
    """PDF y XML de cada factura timbrada, nombrados {folio de la hoja}_{UUID}."""
    facs = _timbradas(db, lote)
    pdfs = pdf_svc.pdf_varios([(fac.xml, fac.emisor) for _, fac in facs])  # en paralelo: cada PDF tarda unos segundos
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for (base, fac), data in zip(facs, pdfs):
            z.writestr(f"{base}.xml", fac.xml)
            if data:
                z.writestr(f"{base}.pdf", data)
            else:
                z.writestr(f"{base}.html", pdf_svc.html(fac.xml, emisor=fac.emisor))
    return buf.getvalue()
