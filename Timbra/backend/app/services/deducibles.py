"""Gastos deducibles: sugerir si cada CFDI RECIBIDO es deducible según el régimen y la actividad de la constancia (CSF),
y aprender de lo que la persona decide.

Es ORIENTACIÓN, no asesoría fiscal: la sugerencia nunca es definitiva. Una persona la confirma o la cambia; queda quién y cuándo.
La sugerencia se calcula al leerla (no se guarda): así siempre refleja la constancia y lo aprendido más recientes. Lo que sí se guarda
es la DECISIÓN de la persona (xml_deduccion) y lo aprendido (pref_deduccion). Recalcular jamás toca una decisión.

Orden de las reglas: 1) lo que descarta, 2) lo que limita, 3) lo aprendido de esta cuenta, 4) familia del producto y actividad.
"""
import re
import threading
import time
import unicodedata
from datetime import datetime
from functools import lru_cache

from sqlalchemy.orm import Session

from ..logs import log
from ..models import Emisor, PrefDeduccion, XmlCfdi, XmlDeduccion
from . import constancia as csf
from .validacion import tipo_persona

GRUPOS = ("deducible", "no_deducible", "revisar", "personal")
DECISIONES = ("deducible", "no_deducible")

# Regímenes en los que el contribuyente tiene una actividad de la que puede restar gastos (o acreditar IVA)
GASTO_PERMITIDO = {"601", "603", "606", "612", "620", "621", "622", "623", "624", "625", "626", "628", "607", "610"}
ISR_SIN_DEDUCCIONES = {"626"}  # RESICO persona física: el ISR se paga sobre ingresos; el gasto sólo sirve para acreditar IVA

# Primeros 2 dígitos de la clave de producto/servicio (segmento del catálogo del SAT)
SEG_GENERAL = {"43", "44", "45", "72", "73", "76", "77", "78", "80", "81", "82", "83", "84", "86", "92"}  # oficina, TI, servicios profesionales, telecom, transporte…
SEG_DUDOSO = {"49", "50", "51", "52", "53", "54", "55", "56", "60", "85"}  # alimentos, ropa, hogar, regalos, salud: pueden ser del negocio o personales
EFECTIVO_TOPE = 2000  # art. 27 fr. III LISR: pagos en efectivo de más de $2,000 no se deducen
RESTAURANTE = "9010"
COMBUSTIBLE = "1510"
VEHICULOS = ("2510", "7811")  # automóviles y su arrendamiento: con tope (art. 36 LISR)
PARCIAL_RESTAURANTE = 8.5

APRENDE_RFC = (1, 0.66)     # (mínimo de decisiones, proporción) para que un proveedor mande
APRENDE_CLAVE = (2, 0.75)   # un tipo de producto necesita más evidencia

STOP = {"servicios", "servicio", "otros", "relacionados", "para", "con", "los", "las", "del", "por", "una", "uno", "que", "venta", "compra",
        "comercio", "menor", "mayor", "actividades", "general", "productos", "asalariado"}


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def _tokens(texto: str) -> set[str]:
    return {t[:5] for t in re.findall(r"[a-z]{4,}", _norm(texto)) if t not in STOP}


@lru_cache(maxsize=4096)
def _descripcion_clave(clave: str) -> str:
    try:
        from satcfdi.catalogs import select
        r = select("C756_c_ClaveProdServ", clave)
        return str(r[0]) if r else ""
    except Exception:
        return ""


# ---------------------------------------------------------------- lista 69-B (en segundo plano: nunca frena la pantalla)
_L69B: dict = {"datos": None, "hora": 0.0, "buscando": False}


def lista_69b() -> dict[str, str] | None:
    """RFC → situación, si ya se bajó. La primera vez se pide en un hilo y se devuelve None; la siguiente consulta ya la tiene."""
    if _L69B["datos"] is not None and time.time() - _L69B["hora"] < 12 * 3600:
        return _L69B["datos"]
    if not _L69B["buscando"]:
        _L69B["buscando"] = True

        def bajar():
            try:
                from .clientes_io import listado_69b
                _L69B["datos"], _L69B["hora"] = listado_69b(), time.time()
            except Exception as e:  # sin internet: se sigue sin esa regla
                log.info("Deducibles: lista 69-B no disponible (%s)", e)
            finally:
                _L69B["buscando"] = False
        threading.Thread(target=bajar, name="lista-69b", daemon=True).start()
    return _L69B["datos"]


# ---------------------------------------------------------------- contexto de una cuenta
class Contexto:
    def __init__(self, db: Session, emisor: Emisor, con_69b: bool = True):
        self.emisor = emisor
        self.rfc = (emisor.rfc or "").upper()
        c = csf.vigente(db, emisor.id)
        self.constancia = csf.a_dict(c) if c else None
        regs = {r["clave"] for r in csf.vigentes(c.regimenes)} if c else set()
        regs = {r for r in regs if r} or {emisor.regimen_fiscal}
        self.regs = regs
        self.persona = tipo_persona(self.rfc)
        self.permitido = bool(regs & GASTO_PERMITIDO)
        self.solo_iva = self.persona == "fisica" and bool(regs & ISR_SIN_DEDUCCIONES) and not (regs & {"612", "606", "621", "625"})
        acts = [a for a in (c.actividades if c else []) if not a.get("hasta")]
        self.actividades = [a["nombre"] for a in acts if _norm(a["nombre"]) != "asalariado"]
        self.tokens_actividad = set().union(*[_tokens(a) for a in self.actividades]) if self.actividades else set()
        self.prefs = {(p.tipo, p.valor): (p.si, p.no) for p in db.query(PrefDeduccion).filter(PrefDeduccion.emisor_id == emisor.id)}
        self.l69b = lista_69b() if con_69b else None


def _fila(x: XmlCfdi) -> dict:
    return (x.filas or [{}])[0] if x.filas else {}


def _claves(fila: dict) -> list[str]:
    return re.findall(r"\d{8}", str(fila.get("Claves ProdServ") or ""))


def _forma(fila: dict) -> str:
    m = re.match(r"\s*(\d{2})", str(fila.get("Forma Pago") or ""))
    return m.group(1) if m else ""


def _pref(ctx: Contexto, tipo: str, valor: str, minimo: int, proporcion: float) -> tuple[str, int, int] | None:
    si, no = ctx.prefs.get((tipo, valor), (0, 0))
    n = si + no
    if n < minimo:
        return None
    if si / n >= proporcion:
        return "deducible", si, no
    if no / n >= proporcion:
        return "no_deducible", si, no
    return None


# ---------------------------------------------------------------- el motor
def clasificar(x: XmlCfdi, ctx: Contexto) -> dict:
    """{sugerencia, porcentaje, motivos[{regla, texto, peso}], efecto}. Una persona siempre puede cambiarlo."""
    f = _fila(x)
    motivos: list[dict] = []

    def m(regla: str, texto: str, peso: str):
        motivos.append({"regla": regla, "texto": texto, "peso": peso})

    uso = str(f.get("Uso CFDI") or "")[:4].strip()
    claves = _claves(f)
    forma = _forma(f)
    seg4 = sorted({c[:4] for c in claves})
    descripcion = str(f.get("Descripción") or f.get("Descripci�n") or "")
    bloqueo = False

    # 1) lo que descarta
    if x.estatus == "Cancelado":
        m("cancelado", "El SAT lo marca como cancelado.", "bloqueo"); bloqueo = True
    if x.clase == "N":
        m("nomina", "Es un recibo de nómina que recibiste: es tu ingreso, no un gasto.", "bloqueo"); bloqueo = True
    elif x.clase == "P":
        m("pago", "Es un complemento de pago: sólo liquida otra factura, no es un gasto por sí mismo.", "bloqueo"); bloqueo = True
    elif x.clase == "T":
        m("traslado", "Es un CFDI de traslado: no es un gasto.", "bloqueo"); bloqueo = True
    elif x.clase == "E":
        m("nota", "Es una nota de crédito: reduce un gasto anterior; revísala junto con esa factura.", "duda")
    if x.rfc_receptor and x.rfc_receptor.upper() != ctx.rfc:
        m("receptor", f"La factura está a nombre de {x.rfc_receptor}, no de {ctx.rfc}.", "bloqueo"); bloqueo = True
    if uso == "S01":
        m("uso_s01", "El uso del CFDI es S01 «sin efectos fiscales».", "bloqueo"); bloqueo = True
    if forma == "01" and (x.total or 0) > EFECTIVO_TOPE:
        m("efectivo", f"Se pagó en efectivo y pasa de ${EFECTIVO_TOPE:,} (art. 27 fr. III LISR).", "bloqueo"); bloqueo = True
    if forma == "01" and COMBUSTIBLE in seg4:
        m("combustible_efectivo", "Combustible pagado en efectivo no se deduce, sea cual sea el monto.", "bloqueo"); bloqueo = True
    estado69 = (ctx.l69b or {}).get((x.rfc_emisor or "").upper())
    if estado69:
        e = str(estado69).strip().lower()
        if e.startswith("definitivo"):
            m("69b", "El proveedor está en la lista 69-B del SAT como DEFINITIVO (operaciones inexistentes).", "bloqueo"); bloqueo = True
        elif e.startswith("presunto"):
            m("69b", "El proveedor está en la lista 69-B del SAT como PRESUNTO: revisa antes de deducir.", "duda")
    if not x.filas:
        m("sin_xml", "Sólo se sabe que existe en el SAT (falta el XML): descárgalo para clasificarlo bien.", "duda")
    if bloqueo:
        return _salida("no_deducible", None, motivos, ctx)

    # deducciones personales (D01–D10): van aparte, no se mezclan con los gastos del negocio
    if re.fullmatch(r"D(0[1-9]|10)", uso):
        m("personal", f"Uso {uso}: es una deducción personal (se aplica en la declaración anual), no un gasto del negocio.", "info")
        return _salida("personal", None, motivos, ctx)

    # 2) lo que limita
    if not ctx.permitido:
        m("regimen", "Tus regímenes vigentes no tienen una actividad de la que se resten gastos: sólo cuentan las deducciones personales de la anual.", "bloqueo")
        return _salida("no_deducible", None, motivos, ctx)
    porcentaje = None
    if RESTAURANTE in seg4:
        porcentaje = PARCIAL_RESTAURANTE
        m("restaurante", f"Consumo en restaurante: sólo se deduce {PARCIAL_RESTAURANTE}% (art. 28 fr. XX LISR).", "info")
    if any(s in seg4 for s in VEHICULOS):
        m("vehiculo", "Automóviles y su arrendamiento se deducen con tope (art. 36 LISR): revisa el monto.", "duda")
    if (x.metodo or "") == "PPD":
        m("ppd", "Es PPD: en flujo de efectivo se deduce hasta que lo pagas (necesitas el complemento de pago).", "info")
    if forma == "99" and (x.metodo or "") != "PPD":
        m("forma99", "Forma de pago «por definir» (99) sin ser PPD: revisa cómo se pagó.", "duda")

    # 3) lo aprendido de las decisiones de esta cuenta
    aprendido = _pref(ctx, "rfc", (x.rfc_emisor or "").upper(), *APRENDE_RFC)
    if aprendido:
        dec, si, no = aprendido
        m("aprendido_proveedor", f"Antes marcaste a este proveedor como {'deducible' if dec == 'deducible' else 'no deducible'} "
                                 f"({max(si, no)} de {si + no} veces).", "aprendido")
        return _salida(dec, porcentaje if dec == "deducible" else None, motivos, ctx)
    for s in seg4:
        aprendido = _pref(ctx, "clave", s, *APRENDE_CLAVE)
        if aprendido:
            dec, si, no = aprendido
            m("aprendido_clave", f"Antes marcaste este tipo de producto o servicio ({s}…) como {'deducible' if dec == 'deducible' else 'no deducible'} "
                                 f"({max(si, no)} de {si + no} veces).", "aprendido")
            return _salida(dec, porcentaje if dec == "deducible" else None, motivos, ctx)

    # 4) familia del producto y actividad
    textos = f"{descripcion} " + " ".join(_descripcion_clave(c) for c in claves[:3])
    relacion = ctx.tokens_actividad & _tokens(textos)
    duda = any(mo["peso"] == "duda" for mo in motivos)
    if relacion:
        m("actividad", "Se relaciona con tu actividad: " + ", ".join(ctx.actividades[:2]) + ".", "ayuda")
    segmentos = {c[:2] for c in claves}
    if segmentos & SEG_DUDOSO and not relacion:
        m("familia", "Este tipo de compra puede ser del negocio o personal: dime cuál es.", "duda")
        return _salida("revisar", porcentaje, motivos, ctx)
    if duda:
        return _salida("revisar", porcentaje, motivos, ctx)
    if porcentaje is not None and not duda:  # restaurante: deducible sólo en parte
        return _salida("deducible", porcentaje, motivos, ctx)
    if relacion or (segmentos & SEG_GENERAL):
        if not relacion:
            m("general", "Gasto operativo común (servicios, oficina, tecnología, telecomunicaciones…): suele ser deducible si es estrictamente indispensable.", "ayuda")
        return _salida("deducible", porcentaje, motivos, ctx)
    m("desconocido", "No pude ligarlo a tu actividad: confírmalo tú.", "duda")
    return _salida("revisar", porcentaje, motivos, ctx)


def _salida(sug: str, porcentaje: float | None, motivos: list[dict], ctx: Contexto) -> dict:
    efecto = "ninguno" if sug in ("no_deducible", "personal") else ("solo_iva" if ctx.solo_iva else "isr_iva")
    if ctx.solo_iva and sug == "deducible":
        motivos.append({"regla": "resico", "peso": "info", "texto": "En RESICO persona física el ISR no admite deducciones: este gasto te sirve para acreditar el IVA."})
    return {"sugerencia": sug, "porcentaje": porcentaje, "motivos": motivos, "efecto": efecto}


# ---------------------------------------------------------------- decisiones y aprendizaje
def _mueve(db: Session, emisor_id: int, tipo: str, valor: str, decision: str, delta: int):
    if not valor:
        return
    p = db.query(PrefDeduccion).filter(PrefDeduccion.emisor_id == emisor_id, PrefDeduccion.tipo == tipo, PrefDeduccion.valor == valor).first()
    if p is None:
        if delta < 0:
            return
        p = PrefDeduccion(emisor_id=emisor_id, tipo=tipo, valor=valor, si=0, no=0)
        db.add(p)
    campo = "si" if decision == "deducible" else "no"
    setattr(p, campo, max(0, (getattr(p, campo) or 0) + delta))
    if (p.si or 0) == 0 and (p.no or 0) == 0:
        db.delete(p)
    db.flush()  # la sesión no hace autoflush: sin esto, dos CFDI del mismo lote con la misma clave insertarían la preferencia dos veces


def _aprender(db: Session, d: XmlDeduccion, delta: int):
    _mueve(db, d.emisor_id, "rfc", (d.rfc_proveedor or "").upper(), d.decision, delta)
    for s in (d.claves or "").split(","):
        _mueve(db, d.emisor_id, "clave", s.strip(), d.decision, delta)


def decidir(db: Session, emisor: Emisor, usuario_id: int | None, uuids: list[str], decision: str, porcentaje: float | None = None,
            nota: str | None = None, aprender: bool = True) -> int:
    if decision not in DECISIONES:
        raise ValueError("La decisión es «deducible» o «no deducible».")
    hechos = 0
    for uuid in dict.fromkeys(u.upper() for u in uuids):
        x = db.query(XmlCfdi).filter(XmlCfdi.emisor_id == emisor.id, XmlCfdi.uuid == uuid, XmlCfdi.tipo == "Recibido").first()
        if x is None:
            continue
        d = db.query(XmlDeduccion).filter(XmlDeduccion.emisor_id == emisor.id, XmlDeduccion.uuid == uuid).first()
        if d is not None and d.aprendida:
            _aprender(db, d, -1)  # lo que había contado antes se corrige
        if d is None:
            d = XmlDeduccion(emisor_id=emisor.id, uuid=uuid)
            db.add(d)
        d.decision, d.porcentaje, d.nota = decision, (porcentaje if decision == "deducible" else None), (nota or None)
        d.rfc_proveedor = (x.rfc_emisor or "").upper()
        d.claves = ",".join(sorted({c[:4] for c in _claves(_fila(x))}))
        d.decidido_por, d.decidido_el, d.aprendida = usuario_id, datetime.now(), bool(aprender)
        if aprender:
            _aprender(db, d, +1)
        hechos += 1
    db.commit()
    return hechos


def deshacer(db: Session, emisor: Emisor, uuids: list[str]) -> int:
    n = 0
    for uuid in dict.fromkeys(u.upper() for u in uuids):
        d = db.query(XmlDeduccion).filter(XmlDeduccion.emisor_id == emisor.id, XmlDeduccion.uuid == uuid).first()
        if d is None:
            continue
        if d.aprendida:
            _aprender(db, d, -1)
        db.delete(d)
        n += 1
    db.commit()
    return n


# ---------------------------------------------------------------- lista para la pantalla
def listar(db: Session, emisor: Emisor, desde: str | None = None, hasta: str | None = None, grupo: str | None = None,
           q: str | None = None, limite: int = 200, desplazar: int = 0) -> dict:
    ctx = Contexto(db, emisor)
    qs = db.query(XmlCfdi).filter(XmlCfdi.emisor_id == emisor.id, XmlCfdi.tipo == "Recibido")
    if desde:
        qs = qs.filter(XmlCfdi.fecha >= desde)
    if hasta:
        qs = qs.filter(XmlCfdi.fecha <= f"{hasta} 23:59:59")
    decisiones = {d.uuid: d for d in db.query(XmlDeduccion).filter(XmlDeduccion.emisor_id == emisor.id)}
    filas, totales, meses = [], {g: {"n": 0, "total": 0.0, "iva": 0.0} for g in GRUPOS}, {}
    busca = _norm(q or "")
    for x in qs.order_by(XmlCfdi.fecha.desc()).limit(20000):
        r = clasificar(x, ctx)
        d = decisiones.get(x.uuid.upper()) or decisiones.get(x.uuid)
        final = d.decision if d else r["sugerencia"]
        pct = (d.porcentaje if d else r["porcentaje"])
        total = float(x.total or 0)
        t = totales[final]
        t["n"] += 1
        t["total"] += total
        t["iva"] += float(x.iva or 0) * ((pct or 100) / 100 if final == "deducible" else 1)
        mes = (x.fecha or "")[:7]
        mm = meses.setdefault(mes, {g: 0.0 for g in GRUPOS})
        mm[final] += total
        if grupo and final != grupo:
            continue
        if busca and busca not in _norm(f"{x.nombre_emisor} {x.rfc_emisor} {x.uuid} {x.serie}{x.folio} {x.busca}"):
            continue
        f = _fila(x)
        filas.append({
            "uuid": x.uuid, "fecha": x.fecha, "comprobante": x.comprobante, "serie": x.serie, "folio": x.folio,
            "proveedor": x.nombre_emisor, "rfc": x.rfc_emisor, "total": total, "iva": float(x.iva or 0), "moneda": x.moneda,
            "uso": str(f.get("Uso CFDI") or "")[:4].strip(), "forma": _forma(f), "metodo": x.metodo, "estatus": x.estatus,
            "descripcion": str(f.get("Descripción") or "")[:160], "sugerencia": r["sugerencia"], "porcentaje_sug": r["porcentaje"],
            "motivos": r["motivos"], "efecto": r["efecto"], "decision": d.decision if d else None, "porcentaje": pct if d else None,
            "nota": d.nota if d else None, "final": final, "decidido_el": d.decidido_el.isoformat() if d else None,
        })
    for t in totales.values():
        t["total"], t["iva"] = round(t["total"], 2), round(t["iva"], 2)
    return {
        "filas": filas[desplazar:desplazar + limite], "coinciden": len(filas), "totales": totales,
        "meses": [{"mes": k, **{g: round(v, 2) for g, v in vals.items()}} for k, vals in sorted(meses.items())],
        "constancia": ({"rfc": ctx.constancia["rfc"], "emitida_el": ctx.constancia["emitida_el"], "regimenes": sorted(ctx.regs),
                        "actividades": ctx.actividades} if ctx.constancia else None),
        "regimenes": sorted(ctx.regs), "solo_iva": ctx.solo_iva, "permitido": ctx.permitido, "lista_69b": ctx.l69b is not None,
    }


def aprendido(db: Session, emisor_id: int) -> list[dict]:
    out = []
    for p in db.query(PrefDeduccion).filter(PrefDeduccion.emisor_id == emisor_id).order_by(PrefDeduccion.si + PrefDeduccion.no.desc()):
        out.append({"id": p.id, "tipo": p.tipo, "valor": p.valor, "si": p.si, "no": p.no,
                    "manda": ("deducible" if p.si / max(1, p.si + p.no) >= 0.66 else "no_deducible" if p.no / max(1, p.si + p.no) >= 0.66 else None)})
    return out
