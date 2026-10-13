"""Descarga masiva del SAT y conciliación para COI."""
import csv
import io
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import EN_WEB
from ..db import get_db
from ..models import CfdiSat, Emisor, Factura, SolicitudSat
from ..security import current_user
from ..services import descarga_sat as svc
from ..services.signer import CsdError

router = APIRouter(prefix="/sat", tags=["sat"], dependencies=[Depends(current_user)])


def _emisor(db, emisor_id) -> Emisor:
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe")
    return e


@router.post("/fiel/{emisor_id}")
async def subir_fiel(emisor_id: int, cer: UploadFile = File(...), key: UploadFile = File(...),
                     password: str = Form(...), db: Session = Depends(get_db)):
    e = _emisor(db, emisor_id)
    if EN_WEB:  # la e.firma equivale a tu firma autógrafa: no se guarda en un servidor compartido
        raise HTTPException(409, "En la versión web no se guarda la e.firma. La descarga del SAT se hace en la aplicación "
                                 "de XML (xml.erickddp.com) o con Timbra instalado en tu computadora.")
    try:
        svc.cargar_fiel(e, await cer.read(), await key.read(), password)
    except CsdError as ex:
        raise HTTPException(422, str(ex))
    db.commit()
    return {"ok": True, "vence": e.fiel_vence}


class SolicitudIn(BaseModel):
    emisor_id: int
    direccion: str = "recibido"  # recibido | emitido
    tipo: str = "CFDI"  # CFDI | Metadata
    desde: datetime
    hasta: datetime


@router.post("/solicitudes")
def solicitar(data: SolicitudIn, db: Session = Depends(get_db)):
    e = _emisor(db, data.emisor_id)
    try:
        s = svc.solicitar(db, e, data.direccion, data.desde, data.hasta, data.tipo)
    except CsdError as ex:
        raise HTTPException(422, str(ex))
    except Exception as ex:
        raise HTTPException(502, f"El SAT no respondió: {ex}")
    return _sol(s)


def _sol(s: SolicitudSat):
    return {"id": s.id, "id_solicitud": s.id_solicitud, "direccion": s.direccion, "tipo": s.tipo, "desde": s.desde,
            "hasta": s.hasta, "estado": s.estado, "mensaje": s.mensaje, "descargados": s.descargados,
            "creado": s.creado, "actualizado": s.actualizado}


@router.get("/solicitudes")
def solicitudes(emisor_id: int, db: Session = Depends(get_db)):
    return [_sol(s) for s in db.query(SolicitudSat).filter_by(emisor_id=emisor_id).order_by(SolicitudSat.id.desc()).limit(50)]


@router.post("/solicitudes/{sid}/verificar")
def verificar(sid: int, db: Session = Depends(get_db)):
    s = db.get(SolicitudSat, sid)
    if not s:
        raise HTTPException(404, "Solicitud no existe")
    try:
        return _sol(svc.verificar(db, s))
    except Exception as ex:
        raise HTTPException(502, f"El SAT no respondió: {ex}")


@router.post("/importar-xml/{emisor_id}")
async def importar_xml(emisor_id: int, archivos: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Por si ya tienes los XML (del portal del SAT o de un ZIP): súbelos y quedan igual que la descarga."""
    e = _emisor(db, emisor_id)
    n = err = 0
    for a in archivos:
        data = await a.read()
        blobs = []
        if a.filename and a.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                blobs = [z.read(x) for x in z.namelist() if x.lower().endswith(".xml")]
        else:
            blobs = [data]
        for b in blobs:
            if b"<!DOCTYPE" in b[:4096] or b"<!ENTITY" in b[:4096]:  # un CFDI nunca trae DTD ni entidades: es un XML armado para leer archivos
                err += 1
                continue
            try:
                n += svc.guardar_xml(db, e, b)
            except Exception:
                err += 1
    db.commit()
    return {"nuevos": n, "errores": err}


def _filtrar(db, emisor_id, direccion, desde, hasta):
    q = db.query(CfdiSat).filter(CfdiSat.emisor_id == emisor_id)
    if direccion:
        q = q.filter(CfdiSat.direccion == direccion)
    if desde:
        q = q.filter(CfdiSat.fecha >= desde)
    if hasta:
        q = q.filter(CfdiSat.fecha <= hasta)
    return q.order_by(CfdiSat.fecha)


@router.get("/cfdi")
def cfdi(emisor_id: int, direccion: str | None = None, desde: datetime | None = None, hasta: datetime | None = None,
         lista_69b: bool = False, db: Session = Depends(get_db)):
    """lista_69b=true cruza a quien te factura (recibidos) con la lista 69-B del SAT: necesita internet la primera vez."""
    filas = _filtrar(db, emisor_id, direccion, desde, hasta).all()
    listado: dict[str, str] = {}
    aviso_69b = None
    if lista_69b:
        from ..services import clientes_io
        try:
            listado = clientes_io.listado_69b()
        except clientes_io.ListaNoDisponible as e:
            aviso_69b = str(e)
    locales = {u for (u,) in db.query(Factura.uuid).filter(Factura.emisor_id == emisor_id, Factura.uuid.isnot(None))}
    return [{"id": c.id, "uuid": c.uuid, "direccion": c.direccion, "tipo": c.tipo, "fecha": c.fecha,
             "rfc": c.rfc_emisor if c.direccion == "recibido" else c.rfc_receptor,
             "nombre": c.nombre_emisor if c.direccion == "recibido" else c.nombre_receptor,
             "subtotal": c.subtotal, "iva": c.iva, "iva_retenido": c.iva_retenido, "isr_retenido": c.isr_retenido,
             "total": c.total, "estado": c.estado, "metodo_pago": c.metodo_pago, "uso_cfdi": c.uso_cfdi,
             "tiene_xml": c.xml is not None, "en_timbra": c.uuid in locales,
             "lista_69b": listado.get(c.rfc_emisor if c.direccion == "recibido" else c.rfc_receptor),
             "aviso_69b": aviso_69b} for c in filas]


@router.get("/conciliacion")
def conciliacion(emisor_id: int, desde: datetime, hasta: datetime, db: Session = Depends(get_db)):
    """Emitidos: lo que el SAT tiene contra lo que tiene Timbra (faltantes de cada lado y estatus distinto)."""
    sat = {c.uuid: c for c in _filtrar(db, emisor_id, "emitido", desde, hasta)}
    loc = {f.uuid: f for f in db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.uuid.isnot(None),
                                                       Factura.fecha >= desde, Factura.fecha <= hasta)}
    solo_sat = [{"uuid": u, "total": c.total, "fecha": c.fecha, "nombre": c.nombre_receptor} for u, c in sat.items()
                if u not in loc]
    solo_timbra = [{"uuid": u, "total": f.total, "fecha": f.fecha, "folio": f"{f.serie or ''}{f.folio or ''}"}
                   for u, f in loc.items() if u not in sat]
    estatus = [{"uuid": u, "sat": sat[u].estado, "timbra": loc[u].estado} for u in sat.keys() & loc.keys()
               if (sat[u].estado == "Cancelado") != (loc[u].estado == "cancelada")]
    return {"solo_sat": solo_sat, "solo_timbra": solo_timbra, "estatus_distinto": estatus,
            "coinciden": len(sat.keys() & loc.keys())}


@router.get("/exportar/csv")
def exportar_csv(emisor_id: int, direccion: str = "recibido", desde: datetime | None = None,
                 hasta: datetime | None = None, db: Session = Depends(get_db)):
    """Layout para capturar pólizas en COI (abre directo en Excel)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Fecha", "UUID", "Tipo", "RFC", "Nombre", "Subtotal", "Descuento", "IVA", "IVA retenido",
                "ISR retenido", "Total", "Moneda", "Metodo", "Forma", "Uso", "Estado"])
    for c in _filtrar(db, emisor_id, direccion, desde, hasta):
        rfc, nom = (c.rfc_emisor, c.nombre_emisor) if c.direccion == "recibido" else (c.rfc_receptor, c.nombre_receptor)
        w.writerow([f"{c.fecha:%d/%m/%Y}" if c.fecha else "", c.uuid, c.tipo, rfc, nom, c.subtotal, c.descuento, c.iva,
                    c.iva_retenido, c.isr_retenido, c.total, c.moneda, c.metodo_pago, c.forma_pago, c.uso_cfdi, c.estado])
    return Response(("﻿" + out.getvalue()).encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="sat_{direccion}s.csv"'})


@router.get("/exportar/zip")
def exportar_zip(emisor_id: int, direccion: str = "recibido", desde: datetime | None = None,
                 hasta: datetime | None = None, db: Session = Depends(get_db)):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for c in _filtrar(db, emisor_id, direccion, desde, hasta):
            if c.xml:
                z.writestr(f"{c.rfc_emisor}_{c.uuid}.xml", c.xml)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="sat_{direccion}s.zip"'})
