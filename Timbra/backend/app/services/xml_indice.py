"""Los XML bajados del SAT o leídos de una carpeta: dónde viven, cómo se indexan y cómo se consultan.

El XML se guarda en disco, dentro de la carpeta de datos (datos/xml/{emisor}/{AAAAMM} {RFC4}/{emitidos|recibidos}/UUID.xml,
la misma estructura de la app de escritorio), y la tabla `xml_cfdi` es su índice: un registro por comprobante con sus
renglones ya leídos en el formato maestro (un pago trae un renglón por documento pagado).
Aquí no hay criterio fiscal: sólo hechos del XML y lo que el SAT dice de su estatus.
"""
import io
import shutil
import zipfile
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import CfdiSat, Emisor, Factura, XmlCfdi
from ..xmlsat import inteligencia, lector
from ..xmlsat.almacen import Almacen
from ..xmlsat.lector import COLUMNAS_COPIADO, Renglon

# El formato maestro EDDP: las columnas de «Copiar tabla», en este orden. La hoja maestra del despacho depende de él.
FORMATO_EDDP = list(COLUMNAS_COPIADO)
MAX_XML = 5 * 1024 * 1024  # un CFDI real pesa kilobytes; más que esto no es un CFDI
CLASES = "IGNPET"


def carpeta_xml(emisor_id: int) -> Path:
    return Path(settings.data_dir) / "xml" / str(emisor_id)


def carpeta_estado() -> Path:
    p = Path(settings.data_dir) / "xml_estado"
    p.mkdir(parents=True, exist_ok=True)
    return p


def carpeta_tmp() -> Path:
    p = Path(settings.data_dir) / "tmp"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- guardar
def _busca(d: dict) -> str:
    t = " ".join(str(d.get(k) or "") for k in (
        "UUID", "Serie", "Folio", "RFC Emisor", "Nombre Emisor", "RFC Receptor", "Nombre Receptor", "Descripción", "Total"))
    return f"{t} {d.get('Serie', '')}{d.get('Folio', '')} {d.get('Serie', '')}-{d.get('Folio', '')}".lower()


TIPO_PERCEPCION = {"001": "Sueldos y salarios", "002": "Aguinaldo", "003": "PTU", "005": "Fondo de ahorro", "010": "Premios por puntualidad",
                   "019": "Horas extra", "020": "Prima dominical", "021": "Prima vacacional", "022": "Prima por antigüedad",
                   "023": "Pagos por separación", "025": "Indemnizaciones", "028": "Comisiones", "029": "Vales de despensa",
                   "038": "Otros ingresos por salarios", "039": "Jubilaciones y pensiones", "046": "Asimilados a salarios",
                   "047": "Alimentación", "049": "Premios por asistencia", "050": "Viáticos"}
TIPO_DEDUCCION = {"001": "Seguridad social (IMSS)", "002": "ISR", "003": "Retiro, cesantía y vejez", "004": "Otros",
                  "005": "Fondo de vivienda", "006": "Incapacidad", "007": "Pensión alimenticia", "010": "Crédito de vivienda (Infonavit)",
                  "011": "Infonacot", "017": "Ajuste en PTU", "019": "Cuotas sindicales", "020": "Ausentismo", "021": "Cuotas obrero patronales",
                  "101": "ISR retenido de ejercicio anterior", "107": "Ajuste al subsidio causado"}


def leer_nomina(ruta: Path) -> dict | None:
    """Lo que dice el complemento de nómina de un recibo: percepciones (gravado y exento), deducciones (ISR, IMSS…),
    otros pagos y a qué periodo corresponde. None si el XML no trae nómina. No toca el formato maestro."""
    root = lector._raiz(Path(ruta))
    if root is None:
        return None
    nom = next((n for n in lector._buscar_todos(root, "Nomina")), None)
    if nom is None:
        return None
    f = lector._f

    def partes(contenedor: str, hijo: str, tipo: str, catalogo: dict) -> list[dict]:
        out = []
        for c in lector._buscar_todos(nom, contenedor):
            for x in lector._hijos(c, hijo):
                clave = x.get(tipo) or ""
                out.append({"tipo": clave, "concepto": (x.get("Concepto") or catalogo.get(clave) or clave).strip()[:80],
                            "nombre": catalogo.get(clave, ""), "gravado": f(x.get("ImporteGravado")), "exento": f(x.get("ImporteExento")),
                            "importe": f(x.get("Importe"))})
        return out

    per = partes("Percepciones", "Percepcion", "TipoPercepcion", TIPO_PERCEPCION)
    ded = partes("Deducciones", "Deduccion", "TipoDeduccion", TIPO_DEDUCCION)
    otros = partes("OtrosPagos", "OtroPago", "TipoOtroPago", {"002": "Subsidio para el empleo", "001": "Reintegro de ISR", "003": "Viáticos"})
    receptor = next(iter(lector._buscar_todos(nom, "Receptor")), None)
    emisor = next(iter(lector._buscar_todos(nom, "Emisor")), None)
    gravado, exento = sum(p["gravado"] for p in per), sum(p["exento"] for p in per)
    isr = sum(d["importe"] for d in ded if d["tipo"] in ("002", "101"))
    imss = sum(d["importe"] for d in ded if d["tipo"] in ("001", "003", "021"))
    total_ded = f(nom.get("TotalDeducciones")) or sum(d["importe"] for d in ded)
    return {
        "tipo": {"O": "Ordinaria", "E": "Extraordinaria"}.get(nom.get("TipoNomina") or "", nom.get("TipoNomina") or ""),
        "fecha_pago": nom.get("FechaPago") or "", "desde": nom.get("FechaInicialPago") or "", "hasta": nom.get("FechaFinalPago") or "",
        "dias": f(nom.get("NumDiasPagados")),
        "percepciones": round(f(nom.get("TotalPercepciones")) or gravado + exento, 2), "gravado": round(gravado, 2), "exento": round(exento, 2),
        "deducciones": round(total_ded, 2), "isr": round(isr, 2), "imss": round(imss, 2), "otras_deducciones": round(total_ded - isr - imss, 2),
        "otros_pagos": round(f(nom.get("TotalOtrosPagos")) or sum(o["importe"] for o in otros), 2),
        "subsidio": round(sum(o["importe"] for o in otros if o["tipo"] == "002"), 2),
        "puesto": (receptor.get("Puesto") or "") if receptor is not None else "",
        "num_empleado": (receptor.get("NumEmpleado") or "") if receptor is not None else "",
        "periodicidad": (receptor.get("PeriodicidadPago") or "") if receptor is not None else "",
        "registro_patronal": (emisor.get("RegistroPatronal") or "") if emisor is not None else "",
        "det_percepciones": per, "det_deducciones": ded, "det_otros": otros,
    }


def completar_nomina(db: Session) -> int:
    """Los recibos de nómina indexados antes de leer su complemento se completan desde su XML (una sola vez cada uno)."""
    n = 0
    for x in db.query(XmlCfdi).filter(XmlCfdi.clase == "N", XmlCfdi.archivo != ""):
        if not x.filas or "_nomina" in x.filas[0]:
            continue
        det = leer_nomina(carpeta_xml(x.emisor_id) / x.archivo)
        x.filas = [{**x.filas[0], "_nomina": det or {}}, *x.filas[1:]]
        n += 1
    if n:
        db.commit()
    return n


def indexar(db: Session, emisor_id: int, ruta: Path, tipo: str = "", origen: str = "sat") -> bool:
    """Lee un XML ya guardado y lo anota en el índice. False si no es CFDI o ya estaba."""
    ruta = Path(ruta)
    filas = lector.leer_xml_filas(ruta, tipo or lector._tipo_por_ruta(ruta))
    if not filas:
        return False
    rel = ruta.relative_to(carpeta_xml(emisor_id)).as_posix()
    datos = []
    for f in filas:
        f.datos["Archivo"] = rel
        datos.append(f.datos)
    d = datos[0]
    if d.get("Clase") == "N":
        d["_nomina"] = leer_nomina(ruta) or {}   # va aparte de las 65 columnas: no cambia lo que se copia
    uuid = (d.get("UUID") or ruta.stem).upper()
    ya = db.query(XmlCfdi).filter_by(emisor_id=emisor_id, uuid=uuid, tipo=d["Tipo"]).first()
    if ya is not None:
        if ya.origen != "aviso":
            return False
        db.delete(ya)  # sólo se sabía que existía (lo avisó el SAT): ahora sí está el XML; conserva su estatus
        db.flush()
    db.add(XmlCfdi(
        emisor_id=emisor_id, uuid=uuid, tipo=d["Tipo"], fecha=d.get("Fecha") or "", clase=d.get("Clase") or "",
        comprobante=d.get("Comprobante") or "", serie=str(d.get("Serie") or "")[:40], folio=str(d.get("Folio") or "")[:60],
        rfc_emisor=str(d.get("RFC Emisor") or "")[:13], nombre_emisor=str(d.get("Nombre Emisor") or "")[:300],
        rfc_receptor=str(d.get("RFC Receptor") or "")[:13], nombre_receptor=str(d.get("Nombre Receptor") or "")[:300],
        subtotal=float(d.get("SubTotal") or 0), iva=float(d.get("IVA Trasladado") or 0), total=float(d.get("Total") or 0),
        moneda=str(d.get("Moneda") or "")[:3], metodo=str(d.get("Método Pago") or "")[:3],
        estatus=ya.estatus if ya is not None else "Vigente", cancelado_el=ya.cancelado_el if ya is not None else None,
        origen=origen, archivo=rel, filas=datos, busca=_busca(d)))
    db.flush()
    return True


def _xml_sueltos(archivos: list[tuple[str, bytes]]):
    """(nombre, contenido) de cada XML; los ZIP se abren aquí mismo."""
    for nombre, datos in archivos:
        if nombre.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(datos)) as z:
                    for info in z.infolist():
                        if not info.is_dir() and info.filename.lower().endswith(".xml") and info.file_size <= MAX_XML:
                            yield info.filename, z.read(info)
            except zipfile.BadZipFile:
                yield nombre, b""
        else:
            yield nombre, datos if len(datos) <= MAX_XML else b""


def _rfcs(root) -> tuple[str, str]:
    emisor, receptor = lector._hijo(root, "Emisor"), lector._hijo(root, "Receptor")
    de = ((emisor.get("Rfc") or emisor.get("rfc") or "") if emisor is not None else "").upper()
    para = ((receptor.get("Rfc") or receptor.get("rfc") or "") if receptor is not None else "").upper()
    return de, para


def guardar_subidos(db: Session, emisor: Emisor, archivos: list[tuple[str, bytes]]) -> dict:
    """XML que el usuario ya tenía: se guardan como emitidos o recibidos según el papel del RFC en cada uno.
    Los que no son de este RFC no entran (se cuentan como ajenos)."""
    alm = Almacen(str(carpeta_xml(emisor.id)), emisor.rfc)
    rfc = emisor.rfc.upper()
    res = {"nuevos": 0, "repetidos": 0, "ajenos": 0, "invalidos": 0}
    for nombre, datos in _xml_sueltos(archivos):
        if not datos or b"<!DOCTYPE" in datos[:4096] or b"<!ENTITY" in datos[:4096]:  # un CFDI nunca trae DTD ni entidades
            res["invalidos"] += 1
            continue
        root = lector._raiz(Path(nombre), datos)
        if root is None or lector.etree.QName(root).localname != "Comprobante":
            res["invalidos"] += 1
            continue
        de, para = _rfcs(root)
        if rfc not in (de, para):
            res["ajenos"] += 1
            continue
        ruta, _ = alm.guardar(datos, "emitidos" if de == rfc else "recibidos", Path(nombre).name)
        res["nuevos" if indexar(db, emisor.id, ruta, origen="subido") else "repetidos"] += 1
    db.commit()
    return res


def candidatos_a_dueno(archivos: list[tuple[str, bytes]]) -> list[dict]:
    """De quién puede ser una carpeta de XML, del más al menos probable: el contribuyente aparece en todos sus
    comprobantes; sus clientes y proveedores, sólo en algunos. Cada candidato trae sus datos tal como vienen en los XML."""
    veces: dict[str, int] = {}
    datos: dict[str, dict] = {}
    for nombre, contenido in _xml_sueltos(archivos):
        if not contenido or b"<!DOCTYPE" in contenido[:4096] or b"<!ENTITY" in contenido[:4096]:
            continue
        root = lector._raiz(Path(nombre), contenido)
        if root is None or lector.etree.QName(root).localname != "Comprobante":
            continue
        emisor, receptor = lector._hijo(root, "Emisor"), lector._hijo(root, "Receptor")
        for nodo, regimen, cp in ((emisor, "RegimenFiscal", root.get("LugarExpedicion")),
                                  (receptor, "RegimenFiscalReceptor", receptor.get("DomicilioFiscalReceptor") if receptor is not None else None)):
            if nodo is None:
                continue
            rfc = (nodo.get("Rfc") or nodo.get("rfc") or "").upper().strip()
            if len(rfc) not in (12, 13) or rfc in ("XAXX010101000", "XEXX010101000"):
                continue
            veces[rfc] = veces.get(rfc, 0) + 1
            d = datos.setdefault(rfc, {"rfc": rfc, "nombre": "", "regimen": "", "cp": ""})
            d["nombre"] = d["nombre"] or (nodo.get("Nombre") or nodo.get("nombre") or "").strip()
            d["regimen"] = d["regimen"] or (nodo.get(regimen) or "").strip()
            d["cp"] = d["cp"] or (cp or "").strip()
    return [{**datos[rfc], "veces": n} for rfc, n in sorted(veces.items(), key=lambda kv: -kv[1])][:6]


def importar_heredados(db: Session) -> int:
    """Una sola vez: los XML que guardó el módulo SAT anterior (tabla cfdi_sat) pasan al índice nuevo. No borra nada."""
    n = 0
    for emisor in db.query(Emisor):
        viejos = db.query(CfdiSat).filter(CfdiSat.emisor_id == emisor.id, CfdiSat.xml.isnot(None))
        if not viejos.count() or db.query(XmlCfdi).filter_by(emisor_id=emisor.id).count():
            continue
        r = guardar_subidos(db, emisor, [(f"{c.uuid}.xml", c.xml) for c in viejos])
        n += r["nuevos"]
    return n


def al_dia_con_timbra(db: Session, emisor_id: int) -> int:
    """Lo que Timbra mismo canceló ante el SAT ya se sabe cancelado, sin esperar a la lista del SAT."""
    cancelados = select(func.upper(Factura.uuid)).where(Factura.emisor_id == emisor_id, Factura.estado == "cancelada",
                                                         Factura.uuid.isnot(None))
    n = (db.query(XmlCfdi).filter(XmlCfdi.emisor_id == emisor_id, XmlCfdi.tipo == "Emitido", XmlCfdi.estatus != "Cancelado",
                                  XmlCfdi.uuid.in_(cancelados))
         .update({XmlCfdi.estatus: "Cancelado"}, synchronize_session=False))
    if n:
        db.commit()
    return n


# ---------------------------------------------------------------- lo que el SAT dice del estatus (Metadata)
def aplicar_metadata(db: Session, emisor: Emisor, tipo: str, texto: str) -> dict:
    """`texto`: el .txt de Metadata del SAT (campos separados por ~). Marca cancelados y cuenta lo que aún no se tiene.
    tipo: Emitido | Recibido."""
    lineas = [x for x in texto.replace("\r", "").split("\n") if x.strip()]
    res = {"revisados": 0, "cancelados": 0, "nuevos_cancelados": 0, "sin_xml": 0}
    if not lineas:
        return res
    cab = [c.strip().lower() for c in lineas[0].split("~")]
    if "uuid" not in cab:
        return res
    pos = {c: i for i, c in enumerate(cab)}

    def dato(campos: list[str], nombre: str) -> str:
        i = pos.get(nombre)
        return campos[i].strip() if i is not None and i < len(campos) else ""

    for linea in lineas[1:]:
        campos = linea.split("~")
        uuid = dato(campos, "uuid").upper()
        if len(uuid) != 36:
            continue
        res["revisados"] += 1
        cancelado = dato(campos, "estatus") == "0"
        x = db.query(XmlCfdi).filter_by(emisor_id=emisor.id, uuid=uuid, tipo=tipo).first()
        if x is None:
            if not cancelado:
                res["sin_xml"] += 1
                continue
            # Cancelado del que nunca se bajó el XML: se anota que existe, con lo poco que dice el SAT
            efecto = {"I": "Ingreso", "E": "Egreso", "P": "Pago", "N": "Nómina", "T": "Traslado"}.get(dato(campos, "efectocomprobante").upper(), "")
            fecha = dato(campos, "fechaemision").replace("T", " ")[:19]
            try:
                monto = float(dato(campos, "monto") or 0)
            except ValueError:
                monto = 0.0
            cod = {"Ingreso": "I", "Egreso": "E", "Pago": "P", "Nómina": "N", "Traslado": "T"}.get(efecto, "")
            d = {"Tipo": tipo, "Fecha": fecha, "Año": fecha[0:4], "Mes": fecha[5:7], "Día": fecha[8:10], "Hora": fecha[11:16],
                 "Comprobante": efecto, "RFC Emisor": dato(campos, "rfcemisor"), "Nombre Emisor": dato(campos, "nombreemisor"),
                 "RFC Receptor": dato(campos, "rfcreceptor"), "Nombre Receptor": dato(campos, "nombrereceptor"),
                 "Total": monto, "UUID": uuid, "Fecha Timbrado": dato(campos, "fechacertificacionsat"),
                 "RFC PAC": dato(campos, "rfcpac") or dato(campos, "paccertifico"), "Clase": lector.clase_de(cod, tipo), "Archivo": ""}
            x = XmlCfdi(emisor_id=emisor.id, uuid=uuid, tipo=tipo, fecha=fecha, clase=d["Clase"], comprobante=efecto,
                        rfc_emisor=d["RFC Emisor"][:13], nombre_emisor=d["Nombre Emisor"][:300], rfc_receptor=d["RFC Receptor"][:13],
                        nombre_receptor=d["Nombre Receptor"][:300], total=monto, origen="aviso", filas=[d], busca=_busca(d))
            db.add(x)
            res["nuevos_cancelados"] += 1
        if cancelado:
            res["cancelados"] += 1
            if x.estatus != "Cancelado":
                x.estatus = "Cancelado"
                x.cancelado_el = dato(campos, "fechacancelacion").replace("T", " ")[:19] or None
        elif x.estatus == "Cancelado" and x.origen != "aviso":
            x.estatus, x.cancelado_el = "Vigente", None  # el SAT dice que sigue vigente
    db.commit()
    return res


# ---------------------------------------------------------------- consultar
class Filtros(BaseModel):
    emisor_id: int
    mes: str = ""       # "2026-09", "2026" (todo el año) o "" (todo)
    tipo: str = ""      # "Emitido" | "Recibido" | ""
    clase: str = ""     # letras juntas: "IG" = ingresos y gastos
    estatus: str = ""   # "" (todos, como la app de escritorio) | "Vigente" | "Cancelado"
    q: str = ""
    ids: list[int] = []  # comprobantes marcados; vacío = todo lo filtrado


def limpios(f: Filtros) -> Filtros:
    f.tipo = f.tipo if f.tipo in ("Emitido", "Recibido") else ""
    f.clase = "".join(x for x in f.clase.upper() if x in CLASES)
    f.mes = f.mes if len(f.mes) in (4, 7) and f.mes.replace("-", "").isdigit() else ""
    f.estatus = f.estatus if f.estatus in ("Vigente", "Cancelado") else ""
    f.ids = f.ids[:5000]
    return f


def consulta(db: Session, f: Filtros, con_clase: bool = True, con_estatus: bool = True):
    q = db.query(XmlCfdi).filter(XmlCfdi.emisor_id == f.emisor_id)
    if f.ids:
        return q.filter(XmlCfdi.id.in_(f.ids))
    if f.mes:
        q = q.filter(XmlCfdi.fecha.like(f"{f.mes}%"))
    if f.tipo:
        q = q.filter(XmlCfdi.tipo == f.tipo)
    if con_clase and f.clase:
        q = q.filter(XmlCfdi.clase.in_(list(f.clase)))
    if con_estatus and f.estatus:
        q = q.filter(XmlCfdi.estatus == f.estatus)
    for palabra in f.q.lower().split()[:6]:
        esc = palabra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        q = q.filter(XmlCfdi.busca.like(f"%{esc}%", escape="\\"))
    return q


def renglones(db: Session, f: Filtros) -> list[Renglon]:
    """Los renglones de lo filtrado, del más antiguo al más nuevo (un pago da un renglón por documento)."""
    return [Renglon(dict(d)) for (filas,) in consulta(db, f).order_by(XmlCfdi.fecha, XmlCfdi.uuid).with_entities(XmlCfdi.filas)
            for d in filas]


def con_inteligencia(db: Session, emisor_id: int, filas: list[Renglon]) -> dict:
    """Llena Estatus Pago, Pagado REP, Saldo Pendiente… de `filas` cruzándolas con TODOS los pagos y notas de crédito
    vigentes del emisor (aunque no estén en lo filtrado). Devuelve el resumen de inteligencia.relacionar."""
    propios = {((f.datos.get("UUID") or "").upper(), f.datos.get("Tipo")) for f in filas}
    resto = []
    q = (db.query(XmlCfdi.uuid, XmlCfdi.tipo, XmlCfdi.comprobante, XmlCfdi.total, XmlCfdi.metodo, XmlCfdi.filas)
         .filter(XmlCfdi.emisor_id == emisor_id, XmlCfdi.estatus == "Vigente", XmlCfdi.comprobante.in_(("Ingreso", "Pago", "Egreso"))))
    for uuid, tipo, comprobante, total, metodo, fs in q:
        if (uuid, tipo) in propios:
            continue
        if comprobante == "Ingreso":  # de las demás facturas sólo importa que existen
            resto.append(Renglon({"Comprobante": "Ingreso", "UUID": uuid, "Total": total, "Método Pago": metodo}))
        else:
            resto += [Renglon(dict(d)) for d in fs]
    return inteligencia.relacionar(filas + resto)


def seguimiento(d: dict, resumen: dict) -> dict | None:
    """Seguimiento de pago de una factura para el PDF (igual que el visor de escritorio)."""
    if not d.get("Estatus Pago") or d.get("Comprobante") != "Ingreso":
        return None
    pagos = resumen.get("pagos_por_factura", {}).get((d.get("UUID") or "").upper(), [])
    return {"estatus": d["Estatus Pago"], "pagado_rep": d.get("Pagado REP", 0), "nc_aplicadas": d.get("NC Aplicadas", 0),
            "saldo_pendiente": d.get("Saldo Pendiente", 0), "pagos": pagos}


def meses(db: Session, emisor_id: int) -> list[dict]:
    m = func.substr(XmlCfdi.fecha, 1, 7)
    return [{"mes": mes, "n": n} for mes, n in db.query(m, func.count()).filter(XmlCfdi.emisor_id == emisor_id, XmlCfdi.fecha != "")
            .group_by(m).order_by(m.desc())]


# ---------------------------------------------------------------- estadísticas (sólo hechos del XML)
def _r(v) -> float:
    return round(float(v or 0), 2)


def resumen(db: Session, f: Filtros) -> dict:
    """Números para las gráficas: por clase, por mes, impuestos, a quién más se le vende y se le compra.
    Cuenta sólo vigentes; los cancelados van aparte. Los pagos (REP) no se suman a ingresos ni gastos."""
    base = consulta(db, f, con_clase=False, con_estatus=False)
    clases = {c: {"n": 0, "subtotal": 0.0, "iva": 0.0, "total": 0.0} for c in CLASES}
    por_mes: dict[str, dict] = {}
    imp = {k: 0.0 for k in ("iva_trasladado", "iva_acreditable", "ieps_trasladado", "ieps_pagado", "iva_retenido_a_mi", "isr_retenido_a_mi",
                            "iva_retenido_por_mi", "isr_retenido_por_mi", "base_16", "base_8", "base_0", "base_exento")}
    clientes: dict[str, list] = {}
    proveedores: dict[str, list] = {}
    cancel = {"n": 0, "total": 0.0}
    metodos = {"PUE": 0.0, "PPD": 0.0}
    n_total = 0
    CAMPOS_N = ("percepciones", "gravado", "exento", "deducciones", "isr", "imss", "otras_deducciones", "otros_pagos", "subsidio", "neto")
    nomina = {lado: {"recibos": 0, **{k: 0.0 for k in CAMPOS_N}, "por_quien": {}, "por_mes": {}, "percepciones_det": {}, "deducciones_det": {}}
              for lado in ("recibida", "pagada")}
    for x in base.with_entities(XmlCfdi.clase, XmlCfdi.fecha, XmlCfdi.tipo, XmlCfdi.estatus, XmlCfdi.subtotal, XmlCfdi.iva, XmlCfdi.total,
                                XmlCfdi.rfc_emisor, XmlCfdi.nombre_emisor, XmlCfdi.rfc_receptor, XmlCfdi.nombre_receptor,
                                XmlCfdi.metodo, XmlCfdi.filas):
        n_total += 1
        if x.estatus == "Cancelado":
            cancel["n"] += 1
            cancel["total"] += x.total or 0
            continue
        c = x.clase if x.clase in clases else ""
        if not c:
            continue
        signo = 1
        clases[c]["n"] += 1
        clases[c]["subtotal"] += x.subtotal or 0
        clases[c]["iva"] += x.iva or 0
        clases[c]["total"] += x.total or 0
        d = x.filas[0] if x.filas else {}
        mes = (x.fecha or "")[:7]
        m = por_mes.setdefault(mes, {"mes": mes, "ingresos": 0.0, "gastos": 0.0, "notas_emitidas": 0.0, "notas_recibidas": 0.0,
                                     "nomina": 0.0, "cobrado": 0.0, "pagado": 0.0, "n": 0})
        m["n"] += 1
        if c == "I":
            m["ingresos"] += x.subtotal or 0
            imp["iva_trasladado"] += x.iva or 0
            imp["ieps_trasladado"] += float(d.get("IEPS Trasladado") or 0)
            imp["iva_retenido_a_mi"] += float(d.get("IVA Retenido") or 0)
            imp["isr_retenido_a_mi"] += float(d.get("ISR Retenido") or 0)
            k = clientes.setdefault(x.rfc_receptor, [x.nombre_receptor, 0.0, 0])
            k[1] += x.total or 0
            k[2] += 1
            if x.metodo in metodos:
                metodos[x.metodo] += x.total or 0
        elif c == "G":
            m["gastos"] += x.subtotal or 0
            imp["iva_acreditable"] += x.iva or 0
            imp["ieps_pagado"] += float(d.get("IEPS Trasladado") or 0)
            imp["iva_retenido_por_mi"] += float(d.get("IVA Retenido") or 0)
            imp["isr_retenido_por_mi"] += float(d.get("ISR Retenido") or 0)
            k = proveedores.setdefault(x.rfc_emisor, [x.nombre_emisor, 0.0, 0])
            k[1] += x.total or 0
            k[2] += 1
        elif c == "E":
            emitida = x.tipo == "Emitido"
            m["notas_emitidas" if emitida else "notas_recibidas"] += x.subtotal or 0
            imp["iva_trasladado" if emitida else "iva_acreditable"] -= x.iva or 0
            signo = -1
        elif c == "N":
            m["nomina"] += x.total or 0
            # Recibida: el contribuyente es el trabajador (sus sueldos). Pagada: él es el patrón.
            nd = d.get("_nomina") or {}
            lado = nomina["recibida" if x.tipo == "Recibido" else "pagada"]
            valores = {k: float(nd.get(k) or 0) for k in CAMPOS_N if k != "neto"}
            valores["neto"] = x.total or 0
            if not nd:  # recibo sin complemento legible: al menos lo que dice el comprobante
                valores["percepciones"] = x.subtotal or 0
            lado["recibos"] += 1
            otro = (x.rfc_emisor, x.nombre_emisor) if x.tipo == "Recibido" else (x.rfc_receptor, x.nombre_receptor)
            q = lado["por_quien"].setdefault(otro[0], {"rfc": otro[0], "nombre": otro[1], "recibos": 0, **{k: 0.0 for k in CAMPOS_N}})
            pm = lado["por_mes"].setdefault(mes, {"mes": mes, "recibos": 0, **{k: 0.0 for k in CAMPOS_N}})
            for destino in (lado, q, pm):
                for k, v in valores.items():
                    destino[k] += v
            q["recibos"] += 1
            pm["recibos"] += 1
            for p in nd.get("det_percepciones") or []:
                a = lado["percepciones_det"].setdefault(p["concepto"].upper(), {"concepto": p["concepto"], "tipo": p.get("nombre") or "", "gravado": 0.0, "exento": 0.0})
                a["gravado"] += p["gravado"]
                a["exento"] += p["exento"]
            for p in nd.get("det_deducciones") or []:
                a = lado["deducciones_det"].setdefault(p["concepto"].upper(), {"concepto": p["concepto"], "tipo": p.get("nombre") or "", "importe": 0.0})
                a["importe"] += p["importe"]
        elif c == "P":
            pagado = sum(float(r.get("Imp Pagado") or 0) for r in (x.filas or []))
            m["cobrado" if x.tipo == "Emitido" else "pagado"] += pagado
        if c in ("I", "G", "E"):
            for k_imp, col in (("base_16", "Base IVA 16"), ("base_8", "Base IVA 8"), ("base_0", "Base IVA 0"), ("base_exento", "Base Exento")):
                if c == "I" or (c == "E" and x.tipo == "Emitido"):
                    imp[k_imp] += signo * float(d.get(col) or 0)

    def top(dic: dict) -> list[dict]:
        orden = sorted(dic.items(), key=lambda kv: -kv[1][1])[:8]
        return [{"rfc": rfc, "nombre": v[0], "total": _r(v[1]), "n": v[2]} for rfc, v in orden]

    def redondo(dic: dict) -> dict:
        return {k: (_r(v) if isinstance(v, float) else v) for k, v in dic.items()}

    def lado_listo(lado: dict) -> dict:
        return {**{k: (_r(v) if isinstance(v, float) else v) for k, v in lado.items() if not isinstance(v, dict)},
                "por_quien": [redondo(v) for v in sorted(lado["por_quien"].values(), key=lambda v: -v["percepciones"])[:12]],
                "por_mes": [redondo(v) for _, v in sorted(lado["por_mes"].items())],
                "percepciones_det": [redondo(v) for v in sorted(lado["percepciones_det"].values(), key=lambda v: -(v["gravado"] + v["exento"]))[:15]],
                "deducciones_det": [redondo(v) for v in sorted(lado["deducciones_det"].values(), key=lambda v: -v["importe"])[:15]]}

    ingresos = clases["I"]["subtotal"] - sum(m["notas_emitidas"] for m in por_mes.values())
    gastos = clases["G"]["subtotal"] - sum(m["notas_recibidas"] for m in por_mes.values())
    return {
        "comprobantes": n_total,
        "ingresos": _r(ingresos), "gastos": _r(gastos), "diferencia": _r(ingresos - gastos),
        "clases": {c: {k: (v if k == "n" else _r(v)) for k, v in d.items()} for c, d in clases.items()},
        "por_mes": [{k: (v if k in ("mes", "n") else _r(v)) for k, v in m.items()} for _, m in sorted(por_mes.items())],
        "impuestos": {k: _r(v) for k, v in imp.items()},
        "iva_a_cargo": _r(imp["iva_trasladado"] - imp["iva_acreditable"] - imp["iva_retenido_a_mi"]),
        "clientes": top(clientes), "proveedores": top(proveedores),
        "cancelados": {"n": cancel["n"], "total": _r(cancel["total"])},
        "metodos": {k: _r(v) for k, v in metodos.items()},
        "nomina": {lado: lado_listo(v) for lado, v in nomina.items()},
    }


# ---------------------------------------------------------------- borrar
def borrar(db: Session, f: Filtros) -> int:
    """Quita del índice y del disco lo filtrado. Los XML se pueden volver a bajar del SAT o a leer de la carpeta."""
    base = carpeta_xml(f.emisor_id)
    n = 0
    for x in consulta(db, f).all():
        if x.archivo:
            try:
                (base / x.archivo).unlink(missing_ok=True)
            except OSError:
                pass
        db.delete(x)
        n += 1
    db.commit()
    return n


def borrar_emisor(emisor_id: int) -> None:
    """Al eliminar un emisor: sus XML en disco y su historial de solicitudes al SAT."""
    shutil.rmtree(carpeta_xml(emisor_id), ignore_errors=True)
    for f in carpeta_estado().glob(f"*_{emisor_id}.json"):
        f.unlink(missing_ok=True)

