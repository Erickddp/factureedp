"""Clientes en masa: confirmación de importaciones con conflictos, auditoría de los guardados, duplicados/fusión y lista 69-B.

Principio: los datos fiscales (nombre, CP, régimen) nunca se pisan en silencio. Si la hoja dice algo distinto a lo guardado,
la fila queda "en conflicto" y TÚ eliges: usar la hoja, conservar lo guardado u omitir.
"""
import re
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..logs import log
from ..models import Cliente, Factura, Plantilla
from . import importar
from .validacion import GENERICOS, Resultado, usos_permitidos, validar_receptor_datos

FISCALES = ("nombre", "regimen_fiscal", "codigo_postal", "uso_cfdi")
OTROS = ("direccion", "telefono", "metodo_pago", "forma_pago", "notas")


def _n(s) -> str:
    return importar._norm(s)


def actuales_por_rfc(db: Session, emisor_id: int) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for c in db.query(Cliente).filter(Cliente.emisor_id == emisor_id).order_by(Cliente.id):
        out.setdefault(c.rfc, []).append({"id": c.id, "nombre": c.nombre, "codigo_postal": c.codigo_postal,
                                          "regimen_fiscal": c.regimen_fiscal, "uso_cfdi": c.uso_cfdi,
                                          "emails": c.emails or [], "telefono": c.telefono, "direccion": c.direccion})
    return out


def nombres_por_rfc(actuales: dict[str, list[dict]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for rfc, regs in actuales.items():
        for r in regs:
            out.setdefault(_n(r["nombre"]), set()).add(rfc)
    return out


# ---------------------------------------------------------------- confirmar importación
def confirmar(db: Session, emisor_id: int, filas: list[dict], modo: str) -> dict:
    creados = actualizados = omitidos = sin_decidir = 0
    for d in filas:
        accion, res, rfc = d.get("_accion"), d.get("_resolucion"), d["rfc"]
        regs = db.query(Cliente).filter_by(emisor_id=emisor_id, rfc=rfc).order_by(Cliente.id).all()
        c = next((x for x in regs if _n(x.nombre) == _n(d["nombre"])), regs[0] if regs else None)
        campos = {k: d.get(k) for k in FISCALES + OTROS}
        if c is None:
            db.add(Cliente(emisor_id=emisor_id, rfc=rfc, emails=d.get("emails") or [], **campos))
            creados += 1
            continue
        if accion == "igual":
            omitidos += 1
            continue
        if accion == "conflicto":
            if res not in ("hoja", "base"):
                sin_decidir += 1  # no se decidió: nada se toca
                continue
            fiscales = res == "hoja"
        else:
            if modo == "omitir":
                omitidos += 1
                continue
            fiscales = True
        for k, v in campos.items():
            if v in (None, ""):
                continue
            if k in FISCALES and not fiscales:
                continue
            if k == "nombre" and any(o.id != c.id and _n(o.nombre) == _n(v) for o in regs):
                continue  # ya existe otro registro con ese nombre: no se choca la llave única
            setattr(c, k, v)
        if d.get("emails"):
            c.emails = sorted(set((c.emails or []) + d["emails"]))
        actualizados += 1
    db.commit()
    log.info("Importación confirmada: %s nuevos, %s actualizados, %s omitidos, %s sin decidir", creados, actualizados,
             omitidos, sin_decidir)
    return {"creados": creados, "actualizados": actualizados, "omitidos": omitidos, "sin_decidir": sin_decidir}


# ---------------------------------------------------------------- auditoría de clientes guardados
def _problemas(c: Cliente) -> list[dict]:
    r = Resultado()
    validar_receptor_datos(r, c.rfc, c.nombre, c.regimen_fiscal, c.codigo_postal, c.uso_cfdi)
    out = []
    for nivel, lista in (("error", r.errores), ("aviso", r.avisos)):
        for p in lista:
            campo = p["campo"].split(".")[-1]
            arreglo = None
            if campo == "uso_cfdi" and p.get("sugerencia"):
                arreglo = {"uso_cfdi": p["sugerencia"].split(",")[0].strip()}
            elif campo == "nombre" and p.get("sugerencia"):
                arreglo = {"nombre": p["sugerencia"]}
            elif campo == "codigo_postal" and re.fullmatch(r"\d{4}", c.codigo_postal or ""):
                arreglo = {"codigo_postal": c.codigo_postal.zfill(5)}
            out.append({"campo": campo, "nivel": nivel, "mensaje": p["mensaje"], "arreglo": arreglo})
    if c.rfc not in GENERICOS and not (c.emails or []):
        out.append({"campo": "emails", "nivel": "info", "mensaje": "Sin correo: no se le podrá mandar su factura.", "arreglo": None})
    if c.telefono and len(re.sub(r"\D", "", c.telefono)) < 10:
        out.append({"campo": "telefono", "nivel": "aviso", "mensaje": f"El teléfono «{c.telefono}» no tiene 10 dígitos.", "arreglo": None})
    return out


def auditar(db: Session, emisor_id: int, incluir_info: bool = False) -> list[dict]:
    """Por defecto sólo clientes con errores o avisos reales; con incluir_info también los que sólo carecen de correo."""
    res = []
    for c in db.query(Cliente).filter(Cliente.emisor_id == emisor_id).order_by(Cliente.nombre):
        p = _problemas(c)
        if p and (incluir_info or any(x["nivel"] != "info" for x in p)):
            res.append({"cliente_id": c.id, "nombre": c.nombre, "rfc": c.rfc, "problemas": p,
                        "gravedad": "error" if any(x["nivel"] == "error" for x in p) else
                        "aviso" if any(x["nivel"] == "aviso" for x in p) else "info"})
    res.sort(key=lambda x: ({"error": 0, "aviso": 1, "info": 2}[x["gravedad"]], x["nombre"]))
    return res


def aplicar_arreglos(db: Session, emisor_id: int, arreglos: list[dict]) -> dict:
    """arreglos = [{cliente_id, cambios:{campo:valor}}]. Sólo campos seguros; nunca choca la llave única."""
    permitidos = {"uso_cfdi", "nombre", "codigo_postal"}
    ok = saltados = 0
    for a in arreglos:
        c = db.get(Cliente, a.get("cliente_id"))
        if c is None or c.emisor_id != emisor_id:
            saltados += 1
            continue
        cambios = {k: v for k, v in (a.get("cambios") or {}).items() if k in permitidos}
        nuevo_nombre = cambios.get("nombre")
        if nuevo_nombre and db.query(Cliente).filter(Cliente.emisor_id == emisor_id, Cliente.rfc == c.rfc,
                                                     Cliente.nombre == nuevo_nombre, Cliente.id != c.id).first():
            saltados += 1  # quedaría duplicado: se resuelve fusionando
            continue
        for k, v in cambios.items():
            setattr(c, k, v)
        ok += 1
    db.commit()
    return {"arreglados": ok, "saltados": saltados}


# ---------------------------------------------------------------- duplicados y fusión
def _con_facturas(db: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    return dict(db.query(Factura.cliente_id, func.count(Factura.id)).filter(Factura.cliente_id.in_(ids))
                .group_by(Factura.cliente_id).all())


def duplicados(db: Session, emisor_id: int) -> list[dict]:
    clientes = db.query(Cliente).filter(Cliente.emisor_id == emisor_id).order_by(Cliente.id).all()
    nf = _con_facturas(db, [c.id for c in clientes])

    def ficha(c):
        return {"id": c.id, "nombre": c.nombre, "rfc": c.rfc, "codigo_postal": c.codigo_postal, "regimen_fiscal": c.regimen_fiscal,
                "emails": c.emails or [], "facturas": nf.get(c.id, 0)}

    grupos = []
    por_rfc: dict[str, list[Cliente]] = {}
    por_nombre: dict[str, list[Cliente]] = {}
    for c in clientes:
        por_rfc.setdefault(c.rfc, []).append(c)
        por_nombre.setdefault(_n(c.nombre), []).append(c)
    for rfc, lst in por_rfc.items():
        if len(lst) > 1 and rfc not in GENERICOS:
            grupos.append({"tipo": "mismo_rfc", "clave": rfc, "clientes": [ficha(c) for c in lst],
                           "sugerido": max(lst, key=lambda c: (nf.get(c.id, 0), -c.id)).id, "fusionable": True})
    for nombre, lst in por_nombre.items():
        if len({c.rfc for c in lst}) > 1:
            grupos.append({"tipo": "mismo_nombre", "clave": nombre, "clientes": [ficha(c) for c in lst],
                           "sugerido": None, "fusionable": False})
    return grupos


def fusionar(db: Session, emisor_id: int, conservar_id: int, fusionar_ids: list[int]) -> dict:
    """Pasa facturas y plantillas al cliente que se conserva, completa sus datos vacíos y borra los demás. Sólo mismo RFC."""
    keep = db.get(Cliente, conservar_id)
    if keep is None or keep.emisor_id != emisor_id:
        raise ValueError("El cliente a conservar no existe.")
    otros = [db.get(Cliente, i) for i in fusionar_ids if i != conservar_id]
    if not otros or any(o is None or o.emisor_id != emisor_id for o in otros):
        raise ValueError("Elige al menos otro cliente válido para fusionar.")
    if any(o.rfc != keep.rfc for o in otros):
        raise ValueError("Sólo se fusionan registros con el MISMO RFC. Si son personas distintas, edítalos por separado.")
    movidas = 0
    for o in otros:
        movidas += db.query(Factura).filter(Factura.cliente_id == o.id).update({Factura.cliente_id: keep.id})
        db.query(Plantilla).filter(Plantilla.cliente_id == o.id).update({Plantilla.cliente_id: keep.id})
        keep.emails = sorted(set((keep.emails or []) + (o.emails or [])))
        for k in ("telefono", "direccion", "metodo_pago", "forma_pago", "addenda_id", "residencia_fiscal", "num_reg_id_trib"):
            if not getattr(keep, k) and getattr(o, k):
                setattr(keep, k, getattr(o, k))
        if o.notas and (o.notas not in (keep.notas or "")):
            keep.notas = f"{keep.notas}\n{o.notas}".strip() if keep.notas else o.notas
        keep.dias_credito = keep.dias_credito or o.dias_credito
        db.delete(o)
    db.commit()
    return {"conservado": keep.id, "fusionados": len(otros), "facturas_movidas": movidas}


# ---------------------------------------------------------------- lista 69-B del SAT
RIESGO_69B = {"presunto": "alerta", "definitivo": "rojo"}


class ListaNoDisponible(Exception):
    pass


def listado_69b() -> dict[str, str]:
    """RFC → situación (Presunto, Desvirtuado, Definitivo, Sentencia favorable). Se baja del SAT y se guarda en disco."""
    try:
        from satcfdi.pacs import sat as satmod
        return satmod._get_listado_69b()
    except Exception as e:
        raise ListaNoDisponible(f"No pude consultar la lista 69-B del SAT: {e}") from e


def verificar_69b(db: Session, emisor_id: int, rfcs: list[str] | None = None) -> dict:
    lista = listado_69b()
    if rfcs is None:
        rfcs = sorted({c.rfc for c in db.query(Cliente.rfc).filter(Cliente.emisor_id == emisor_id)})
    hallados = []
    for rfc in rfcs:
        est = lista.get(rfc)
        if est:
            nivel = RIESGO_69B.get(str(est).strip().lower(), "info")
            for c in db.query(Cliente).filter(Cliente.emisor_id == emisor_id, Cliente.rfc == rfc):
                hallados.append({"cliente_id": c.id, "nombre": c.nombre, "rfc": rfc, "estatus": est, "nivel": nivel})
    return {"revisados": len(rfcs), "en_lista": hallados, "consultado": datetime.now()}
