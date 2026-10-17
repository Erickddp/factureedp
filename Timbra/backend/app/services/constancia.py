"""Constancia de Situación Fiscal (CSF): leer el PDF que da el SAT, compararlo con el emisor y guardarlo.

Reglas de oro (iguales a la importación de clientes):
  · Nunca se pisan en silencio los datos del emisor (nombre, régimen, CP): se muestra «la constancia dice X, tú tienes Y» y decide la persona.
  · Si el PDF no trae texto (escaneado o foto) no se adivina: se pide el PDF original del SAT.
  · El RFC de la constancia debe ser el del emisor.
  · No se valida el sello digital del SAT: la constancia se lee tal cual; para validarla está el código QR del propio PDF.
"""
import io
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import ConstanciaFiscal, Emisor
from .validacion import nombre_sin_societario, quitar_acentos, tipo_persona

MAX_PDF = 2 * 1024 * 1024  # una constancia pesa unos 100 KB


class ConstanciaError(Exception):
    pass


MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"], 1)}

# Descripción del régimen en la constancia → clave del catálogo c_RegimenFiscal. El orden importa (lo más específico primero).
REGIMENES = [
    ("sueldos y salarios", "605"), ("simplificado de confianza", "626"), ("actividades empresariales y profesionales", "612"),
    ("incorporacion fiscal", "621"), ("arrendamiento", "606"), ("general de ley personas morales", "601"),
    ("fines no lucrativos", "603"), ("enajenacion o adquisicion de bienes", "607"), ("demas ingresos", "608"),
    ("residentes en el extranjero", "610"), ("dividendos", "611"), ("intereses", "614"), ("premios", "615"),
    ("sin obligaciones fiscales", "616"), ("sociedades cooperativas de produccion", "620"),
    ("agricolas, ganaderas, silvicolas y pesqueras", "622"), ("opcional para grupos de sociedades", "623"), ("coordinados", "624"),
    ("plataformas tecnologicas", "625"), ("hidrocarburos", "628"),
]
# Regímenes en los que un contribuyente puede EMITIR facturas (605 y similares sólo reciben sueldos o ingresos sin factura)
EMITEN = {"601", "603", "606", "612", "620", "621", "622", "623", "624", "625", "626", "607", "610"}


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def clave_regimen(descripcion: str) -> str | None:
    d = _norm(descripcion)
    for frag, clave in REGIMENES:
        if frag in d:
            return clave
    return None


def texto_pdf(datos: bytes) -> str:
    if not datos or not datos.startswith(b"%PDF"):
        raise ConstanciaError("Ese archivo no es un PDF. Sube la constancia tal como la baja del SAT.")
    if len(datos) > MAX_PDF:
        raise ConstanciaError("El PDF pesa más de 2 MB; una constancia del SAT pesa menos. ¿Es el archivo correcto?")
    try:
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(datos))
        if lector.is_encrypted:
            raise ConstanciaError("El PDF está protegido con contraseña. Descárgalo otra vez del SAT sin protegerlo.")
        texto = "\n".join((p.extract_text() or "") for p in lector.pages)
    except ConstanciaError:
        raise
    except Exception:
        raise ConstanciaError("No pude abrir el PDF. Descarga la constancia de nuevo desde el portal del SAT.")
    if len(texto.strip()) < 80:
        raise ConstanciaError("El PDF no trae texto (parece una foto o un escaneo). Sube el PDF original que descargas del SAT.")
    return texto


ETIQUETAS = [
    "RFC:", "CURP:", "Nombre (s):", "Primer Apellido:", "Segundo Apellido:", "Denominación/Razón Social:", "Régimen Capital:",
    "Fecha inicio de operaciones:", "Estatus en el padrón:", "Fecha de último cambio de estado:", "Nombre Comercial:",
    "Código Postal:", "Tipo de Vialidad:", "Nombre de Vialidad:", "Número Exterior:", "Número Interior:", "Nombre de la Colonia:",
    "Nombre de la Localidad:", "Nombre del Municipio o Demarcación Territorial:", "Nombre de la Entidad Federativa:", "Entre Calle:",
    "Y Calle:", "Actividades Económicas:", "Regímenes:", "Obligaciones:", "Sus datos personales",
]


def _campo(plano: str, etiqueta: str) -> str:
    """Lo que hay entre `etiqueta` y la siguiente etiqueta conocida (el texto del PDF viene en una sola línea larga)."""
    m = re.search(re.escape(etiqueta) + r"\s*", plano)
    if not m:
        return ""
    resto = plano[m.end():]
    corte = len(resto)
    for otra in ETIQUETAS:
        if otra == etiqueta:
            continue
        i = resto.find(otra)
        if 0 <= i < corte:
            corte = i
    return resto[:corte].strip()


def _fecha(txt: str) -> str | None:
    """«16 DE MARZO DE 2026» o «16/03/2026» → 2026-03-16."""
    m = re.search(r"(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚ]+)\s+DE\s+(\d{4})", txt.upper().replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U"))
    if m and m.group(2).lower() in MESES:
        return f"{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _iso(d: str | None) -> str | None:
    return f"{d[6:]}-{d[3:5]}-{d[:2]}" if d else None


def leer(datos: bytes) -> dict:
    """PDF de la constancia → datos estructurados. Lanza ConstanciaError con un mensaje que se le puede mostrar al usuario."""
    plano = re.sub(r"\s+", " ", texto_pdf(datos))
    if "constancia de situacion fiscal" not in _norm(plano):
        raise ConstanciaError("Ese PDF no parece una Constancia de Situación Fiscal del SAT.")
    rfc = _campo(plano, "RFC:").split(" ")[0].upper()
    if not re.fullmatch(r"[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}", rfc):
        raise ConstanciaError("No encontré el RFC en la constancia. ¿Es el PDF original del SAT?")
    moral = len(rfc) == 12
    if moral:
        nombre = _campo(plano, "Denominación/Razón Social:")
    else:
        nombre = " ".join(x for x in (_campo(plano, "Nombre (s):"), _campo(plano, "Primer Apellido:"), _campo(plano, "Segundo Apellido:")) if x)
    cp = re.sub(r"\D", "", _campo(plano, "Código Postal:"))[:5]
    if len(cp) != 5:
        raise ConstanciaError("No encontré el código postal del domicilio fiscal en la constancia.")
    dom = {"vialidad": " ".join(x for x in (_campo(plano, "Tipo de Vialidad:"), _campo(plano, "Nombre de Vialidad:")) if x),
           "exterior": _campo(plano, "Número Exterior:"), "interior": _campo(plano, "Número Interior:"),
           "colonia": _campo(plano, "Nombre de la Colonia:"), "localidad": _campo(plano, "Nombre de la Localidad:"),
           "municipio": _campo(plano, "Nombre del Municipio o Demarcación Territorial:"), "estado": _campo(plano, "Nombre de la Entidad Federativa:")}

    # Regímenes y actividades: son tablas; se leen por sus fechas (dd/mm/aaaa) porque cada renglón termina en una o dos
    regs_txt = plano[plano.find("Regímenes:"):] if "Regímenes:" in plano else ""
    regs_txt = regs_txt.split("Obligaciones:")[0].replace("Regímenes:", "").replace("Régimen Fecha Inicio Fecha Fin", "")
    regimenes = []
    for m in re.finditer(r"([^\d]+?)\s+(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}/\d{2}/\d{4}))?", regs_txt):
        desc = m.group(1).strip()
        regimenes.append({"clave": clave_regimen(desc), "nombre": desc, "desde": _iso(m.group(2)), "hasta": _iso(m.group(3))})
    acts_txt = plano[plano.find("Actividades Económicas:"):] if "Actividades Económicas:" in plano else ""
    acts_txt = acts_txt.split("Regímenes:")[0].replace("Actividades Económicas:", "")
    acts_txt = re.sub(r"Orden Actividad Económica Porcentaje Fecha Inicio Fecha Fin", "", acts_txt)
    actividades = []
    for m in re.finditer(r"(\d{1,2})\s+(.+?)\s+(\d{1,3})\s+(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}/\d{2}/\d{4}))?", acts_txt):
        actividades.append({"orden": int(m.group(1)), "nombre": m.group(2).strip(), "porcentaje": int(m.group(3)),
                            "desde": _iso(m.group(4)), "hasta": _iso(m.group(5))})
    actividades.sort(key=lambda a: a["orden"])
    obl_txt = plano.split("Obligaciones:", 1)[1].split("Sus datos personales")[0] if "Obligaciones:" in plano else ""
    obligaciones = sorted({m.group(0).strip() for m in re.finditer(
        r"(Pago (?:provisional|definitivo) mensual de (?:ISR|IVA)|Ajuste anual de ISR|Declaraci[oó]n anual|Declaraci[oó]n informativa)", obl_txt)})
    if not regimenes:
        raise ConstanciaError("No encontré los regímenes en la constancia. ¿Es el PDF original del SAT?")
    emision = re.search(r"Lugar y Fecha de Emisi[oó]n\s*(.{0,140}?\d{4})", plano)
    cif = re.search(r"idCIF:\s*(\d{6,})", plano)
    curp = _campo(plano, "CURP:").split(" ")[0].upper() or None
    return {
        "rfc": rfc, "persona": "moral" if moral else "fisica", "nombre": nombre, "curp": curp if not moral else None, "cp": cp,
        "id_cif": cif.group(1) if cif else None, "emitida_el": _fecha(emision.group(1)) if emision else _fecha(plano),
        "estatus": _campo(plano, "Estatus en el padrón:") or None, "inicio_operaciones": _fecha(_campo(plano, "Fecha inicio de operaciones:")),
        "domicilio": dom, "regimenes": regimenes, "actividades": actividades, "obligaciones": obligaciones,
    }


# ---------------------------------------------------------------- lo que se le sugiere al dar de alta el emisor
def vigentes(regimenes: list[dict]) -> list[dict]:
    return [r for r in regimenes if not r.get("hasta")]


def emisor_sugerido(c: dict) -> dict:
    """Datos listos para llenar el alta del emisor. El régimen es una SUGERENCIA: entre varios vigentes se prefiere el que
    sirve para facturar (605 «sueldos» no factura) y, de ésos, el más reciente."""
    vig = vigentes(c["regimenes"]) or c["regimenes"]
    emiten = [r for r in vig if r.get("clave") in EMITEN]
    elegido = (sorted(emiten, key=lambda r: r.get("desde") or "")[-1] if emiten else (vig[0] if vig else None)) or {}
    nombre = quitar_acentos(nombre_sin_societario(c["nombre"])).upper()
    return {"rfc": c["rfc"], "nombre": nombre, "regimen_fiscal": elegido.get("clave") or "", "lugar_expedicion": c["cp"],
            "regimenes": [{**r, "emite": r.get("clave") in EMITEN} for r in vig],
            "avisos": avisos(c, elegido.get("clave"))}


def avisos(c: dict, elegido: str | None) -> list[str]:
    out = []
    if (c.get("estatus") or "").upper() not in ("ACTIVO", ""):
        out.append(f"En el padrón del SAT aparece como {c['estatus']}: con ese estatus no se puede facturar.")
    vig = vigentes(c["regimenes"])
    if vig and not any(r.get("clave") in EMITEN for r in vig):
        out.append("Ninguno de sus regímenes vigentes sirve para emitir facturas (sólo sueldos u otros ingresos). Revisa con tu contador.")
    if len(vig) > 1:
        out.append("Tiene más de un régimen vigente: elige con el que vas a facturar.")
    if any(r.get("clave") is None for r in c["regimenes"]):
        out.append("Algún régimen no se pudo ligar al catálogo del SAT: captúralo a mano.")
    if c.get("emitida_el"):
        try:
            meses = (date.today().year - int(c["emitida_el"][:4])) * 12 + date.today().month - int(c["emitida_el"][5:7])
            if meses >= 3:
                out.append(f"La constancia tiene {meses} meses: si cambiaste de régimen o de domicilio, sube una nueva.")
        except ValueError:
            pass
    return out


def diferencias(c: dict, emisor: Emisor) -> list[dict]:
    """Lo que la constancia dice distinto a lo que tiene el emisor. Nunca se aplica solo."""
    out = []
    sug = emisor_sugerido(c)
    claves = [r["clave"] for r in vigentes(c["regimenes"]) if r.get("clave")]
    if emisor.regimen_fiscal not in claves:
        out.append({"campo": "regimen_fiscal", "constancia": ", ".join(claves) or sug["regimen_fiscal"], "emisor": emisor.regimen_fiscal,
                    "sugerido": sug["regimen_fiscal"], "texto": f"La constancia dice régimen {', '.join(claves)}; el emisor tiene {emisor.regimen_fiscal}."})
    if (emisor.lugar_expedicion or "") != c["cp"]:
        out.append({"campo": "lugar_expedicion", "constancia": c["cp"], "emisor": emisor.lugar_expedicion, "sugerido": c["cp"],
                    "texto": f"La constancia dice CP {c['cp']}; el lugar de expedición del emisor es {emisor.lugar_expedicion}. "
                             "(Puede ser distinto a propósito si expides desde otra sucursal.)"})
    if quitar_acentos(nombre_sin_societario(c["nombre"])).upper() != quitar_acentos(nombre_sin_societario(emisor.nombre or "")).upper():
        out.append({"campo": "nombre", "constancia": sug["nombre"], "emisor": emisor.nombre, "sugerido": sug["nombre"],
                    "texto": f"La constancia dice «{sug['nombre']}»; el emisor está como «{emisor.nombre}»."})
    return out


# ---------------------------------------------------------------- guardar
def guardar(db: Session, emisor: Emisor, datos_pdf: bytes, c: dict, usuario_id: int | None) -> ConstanciaFiscal:
    if c["rfc"] != (emisor.rfc or "").upper():
        raise ConstanciaError(f"La constancia es del RFC {c['rfc']} y este emisor es {emisor.rfc}. Sube la constancia de este emisor.")
    carpeta = Path(settings.data_dir) / "csf" / str(emisor.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{datetime.now():%Y%m%d%H%M%S}_{c.get('id_cif') or 'csf'}.pdf"
    ruta.write_bytes(datos_pdf)
    fila = ConstanciaFiscal(emisor_id=emisor.id, rfc=c["rfc"], nombre=c["nombre"], curp=c.get("curp"), cp=c["cp"], id_cif=c.get("id_cif"),
                            emitida_el=c.get("emitida_el"), regimenes=c["regimenes"], actividades=c["actividades"],
                            obligaciones=c["obligaciones"], domicilio=c["domicilio"], archivo=ruta.name, subida_por=usuario_id)
    db.add(fila)
    db.commit()
    return fila


def vigente(db: Session, emisor_id: int) -> ConstanciaFiscal | None:
    return (db.query(ConstanciaFiscal).filter(ConstanciaFiscal.emisor_id == emisor_id)
            .order_by(ConstanciaFiscal.id.desc()).first())


def a_dict(f: ConstanciaFiscal) -> dict:
    return {"id": f.id, "rfc": f.rfc, "persona": tipo_persona(f.rfc), "nombre": f.nombre, "curp": f.curp, "cp": f.cp, "id_cif": f.id_cif,
            "emitida_el": f.emitida_el, "regimenes": f.regimenes or [], "actividades": f.actividades or [], "obligaciones": f.obligaciones or [],
            "domicilio": f.domicilio or {}, "subida": f.creado.isoformat() if f.creado else None}
