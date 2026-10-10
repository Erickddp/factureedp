"""Catálogo de productos y servicios: catálogos sugeridos por giro e importación desde tabla (Excel/CSV/pegado)."""
import re
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from ..models import Emisor, Producto
from . import claves, importar
from .semillas import EXENTO, HON_PM, IVA16, PACKS, a_frontera

IVA8 = [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.08"}]
IVA0 = [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.000000"}]
RESICO = IVA16 + [{"tipo": "retencion", "impuesto": "001", "factor": "Tasa", "tasa": "0.012500"},
                  {"tipo": "retencion", "impuesto": "002", "factor": "Tasa", "tasa": "0.106667"}]

COLUMNAS = {
    "descripcion": {"DESCRIPCION", "PRODUCTO", "CONCEPTO", "NOMBRE", "PRODUCTO O SERVICIO", "SERVICIO"},
    "clave": {"CLAVE", "CLAVE SAT", "CLAVE PROD SERV", "CLAVEPRODSERV", "CLAVE PRODUCTO", "CLAVE PRODUCTO SERVICIO"},
    "unidad": {"UNIDAD", "CLAVE UNIDAD", "CLAVEUNIDAD"},
    "precio": {"PRECIO", "PRECIO UNITARIO", "VALOR UNITARIO", "COSTO", "IMPORTE"},
    "impuesto": {"IMPUESTO", "IMPUESTOS", "IVA", "TASA"},
    "sku": {"SKU", "NO IDENTIFICACION", "CODIGO", "NUMERO DE IDENTIFICACION"},
}


def impuestos_de_texto(txt: str, frontera: bool) -> tuple[list[dict], str] | None:
    """'16', 'IVA 16%', 'exento', 'honorarios', 'resico', 'ninguno'… → (lista de impuestos, objeto_imp)."""
    t = importar._norm(txt).lower()  # _norm devuelve MAYÚSCULAS
    if not t:
        return (a_frontera(IVA16) if frontera else IVA16), "02"
    n = re.sub(r"\s+", "", t.replace("iva", "").replace("%", ""))
    if n in ("16", "016", "160000"):
        return IVA16, "02"
    if n in ("8", "08"):
        return IVA8, "02"
    if n in ("0", "00", "tasa0"):
        return IVA0, "02"
    if "exento" in t:
        return EXENTO, "02"
    if "resico" in t:
        return RESICO, "02"
    if "honorario" in t or t.startswith("hon") or "retenc" in t:
        return HON_PM, "02"
    if t in ("ninguno", "no objeto", "sin impuestos", "no", "n a"):
        return [], "01"
    return None


def packs() -> list[dict]:
    return [{"id": p["id"], "nombre": p["nombre"], "descripcion": p["descripcion"], "nota": p.get("nota"),
             "productos": [{"descripcion": d, "clave": c, "unidad": u, "impuestos": etiqueta}
                           for d, c, u, imps, etiqueta in p["productos"]]} for p in PACKS]


def aplicar_pack(db: Session, emisor: Emisor, pack_id: str) -> dict:
    p = next((x for x in PACKS if x["id"] == pack_id), None)
    if p is None:
        raise ValueError("Ese catálogo sugerido no existe.")
    existentes = {(x.descripcion.strip().lower(), x.clave_prod_serv) for x in db.query(Producto).filter_by(emisor_id=emisor.id)}
    nuevos = ya = 0
    for desc, clave, unidad, imps, _ in p["productos"]:
        if claves.descripcion(clave) is None:
            continue
        if (desc.strip().lower(), clave) in existentes:
            ya += 1
            continue
        db.add(Producto(emisor_id=emisor.id, descripcion=desc, clave_prod_serv=clave, clave_unidad=unidad, precio=0,
                        objeto_imp="02" if imps else "01", impuestos=a_frontera(imps) if emisor.region_fronteriza else imps))
        nuevos += 1
    db.commit()
    return {"agregados": nuevos, "ya_estaban": ya}


def _col(encabezados: list[str]) -> dict[int, str]:
    mapa: dict[int, str] = {}
    for i, h in enumerate(encabezados):
        n = importar._norm(h)
        for campo, alias in COLUMNAS.items():
            if n in alias and campo not in mapa.values():
                mapa[i] = campo
                break
    return mapa


def previsualizar(db: Session, emisor: Emisor, filas: list[list[str]]) -> dict:
    """Primera fila = encabezados. Cada fila: nuevo | actualiza | sugerida (clave propuesta) | error."""
    if len(filas) < 2:
        return {"filas": [], "resumen": {}, "error": "Pega los encabezados (descripción, clave, unidad, precio, impuesto) y al menos una fila."}
    mapa = _col(filas[0])
    if "descripcion" not in mapa.values():
        return {"filas": [], "resumen": {}, "error": "No encontré la columna DESCRIPCION (también vale PRODUCTO o CONCEPTO)."}
    existentes = {x.descripcion.strip().lower(): x.id for x in db.query(Producto).filter_by(emisor_id=emisor.id)}
    vistos: set[str] = set()
    out = []
    for n, fila in enumerate(filas[1:], start=2):
        d = {campo: (fila[i].strip() if i < len(fila) else "") for i, campo in mapa.items()}
        if not any(d.values()):
            continue
        errores, avisos = [], []
        desc = re.sub(r"\s+", " ", d.get("descripcion", "")).strip()
        if not desc:
            errores.append("Falta la descripción.")
        if desc.lower() in vistos:
            errores.append("Descripción repetida en tu tabla.")
        vistos.add(desc.lower())
        clave, sugerida = d.get("clave", "").strip(), False
        if clave and claves.descripcion(clave) is None:
            errores.append(f"La clave {clave} no existe en el catálogo del SAT.")
        if not clave and desc:
            top = claves.sugerir(desc, limit=1)
            if top:
                clave, sugerida = top[0]["clave"], True
                avisos.append(f"Clave sugerida: {clave} · {top[0]['descripcion']}. Confírmala.")
            else:
                errores.append("No traes clave y no pude sugerir una. Búscala en Claves SAT.")
        if clave.startswith("51"):
            avisos.append("Familia de medicamentos y productos farmacéuticos: confirma que sea lo que vendes.")
        unidad = d.get("unidad", "").strip().upper() or ("E48" if clave[:2].isdigit() and int(clave[:2]) >= 70 else "H87")
        if claves.descripcion(unidad, "unidad") is None:
            errores.append(f"La unidad {unidad} no existe.")
        precio = Decimal(0)
        if d.get("precio"):
            try:
                precio = Decimal(re.sub(r"[\s$,]", "", d["precio"]))
                if precio < 0:
                    raise InvalidOperation
            except InvalidOperation:
                errores.append(f"El precio «{d['precio']}» no es un número.")
        imp = impuestos_de_texto(d.get("impuesto", ""), emisor.region_fronteriza)
        if imp is None:
            errores.append(f"No entiendo el impuesto «{d['impuesto']}» (usa 16, 8, 0, exento, honorarios, resico o ninguno).")
        estado = "error" if errores else ("actualiza" if desc.lower() in existentes else "nuevo")
        out.append({"n": n, "estado": estado, "descripcion": desc, "clave": clave, "clave_sugerida": sugerida,
                    "unidad": unidad, "precio": str(precio), "sku": d.get("sku", ""),
                    "impuestos": imp[0] if imp else [], "objeto_imp": imp[1] if imp else "02",
                    "errores": errores, "avisos": avisos})
    cuenta = {k: sum(1 for f in out if f["estado"] == k) for k in ("nuevo", "actualiza", "error")}
    cuenta["sugeridas"] = sum(1 for f in out if f["clave_sugerida"] and f["estado"] != "error")
    return {"filas": out, "resumen": cuenta, "error": None}


def confirmar(db: Session, emisor: Emisor, filas: list[list[str]], aceptar_sugeridas: bool) -> dict:
    prev = previsualizar(db, emisor, filas)
    if prev["error"]:
        raise ValueError(prev["error"])
    existentes = {x.descripcion.strip().lower(): x for x in db.query(Producto).filter_by(emisor_id=emisor.id)}
    nuevos = actualizados = omitidos = 0
    for f in prev["filas"]:
        if f["estado"] == "error" or (f["clave_sugerida"] and not aceptar_sugeridas):
            omitidos += 1
            continue
        datos = dict(descripcion=f["descripcion"], clave_prod_serv=f["clave"], clave_unidad=f["unidad"],
                     precio=Decimal(f["precio"]), no_identificacion=f["sku"] or None, impuestos=f["impuestos"],
                     objeto_imp=f["objeto_imp"])
        ex = existentes.get(f["descripcion"].lower())
        if ex:
            for k, v in datos.items():
                setattr(ex, k, v)
            actualizados += 1
        else:
            db.add(Producto(emisor_id=emisor.id, **datos))
            nuevos += 1
    db.commit()
    return {"nuevos": nuevos, "actualizados": actualizados, "omitidos": omitidos}
