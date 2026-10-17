"""Facturas en lote: perfiles de importación, revisión fila por fila, timbrado en segundo plano, pendientes y salidas."""
import copy
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Factura, Lote, LoteFila, PerfilLote
from ..security import current_user
from ..services import lotes as svc

router = APIRouter(prefix="/lotes", tags=["lotes"], dependencies=[Depends(current_user)])


class PerfilIn(BaseModel):
    emisor_id: int
    nombre: str
    config: dict


def _perfil(db: Session, pid: int) -> PerfilLote:
    p = db.get(PerfilLote, pid)
    if not p:
        raise HTTPException(404, "Perfil no existe")
    return p


def _lote(db: Session, lid: int) -> Lote:
    lote = db.get(Lote, lid)
    if not lote:
        raise HTTPException(404, "Lote no existe")
    return lote


def _out_perfil(p: PerfilLote) -> dict:
    return {"id": p.id, "emisor_id": p.emisor_id, "nombre": p.nombre, "config": p.config, "usos": p.usos}


# ---------------------------------------------------------------- perfiles
@router.get("/perfiles")
def perfiles(emisor_id: int, db: Session = Depends(get_db)):
    return [_out_perfil(p) for p in db.query(PerfilLote).filter_by(emisor_id=emisor_id).order_by(PerfilLote.nombre)]


@router.get("/perfiles/ejemplo")
def ejemplo():
    """Perfil de ejemplo (servicio + producto con IVA incluido) para editarlo a tu tabla."""
    return copy.deepcopy(svc.PERFIL_EJEMPLO)


@router.post("/perfiles")
def crear_perfil(data: PerfilIn, db: Session = Depends(get_db)):
    if not db.get(Emisor, data.emisor_id):
        raise HTTPException(404, "Emisor no existe")
    errores = svc.validar_perfil(data.config)
    if errores:
        raise HTTPException(422, "Perfil con detalles: " + " · ".join(errores))
    p = PerfilLote(emisor_id=data.emisor_id, nombre=data.nombre.strip(), config=data.config)
    db.add(p)
    db.commit()
    return _out_perfil(p)


@router.put("/perfiles/{pid}")
def editar_perfil(pid: int, data: PerfilIn, db: Session = Depends(get_db)):
    p = _perfil(db, pid)
    errores = svc.validar_perfil(data.config)
    if errores:
        raise HTTPException(422, "Perfil con detalles: " + " · ".join(errores))
    p.nombre, p.config = data.nombre.strip(), data.config
    db.commit()
    return _out_perfil(p)


@router.delete("/perfiles/{pid}")
def borrar_perfil(pid: int, db: Session = Depends(get_db)):
    p = db.get(PerfilLote, pid)
    if p:
        db.query(Lote).filter(Lote.perfil_id == pid).update({Lote.perfil_id: None})
        db.delete(p)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- lotes
def _fila(db: Session, f: LoteFila) -> dict:
    fac = db.get(Factura, f.factura_id) if f.factura_id else None
    return {"id": f.id, "n": f.n, "estado": f.estado, "etapa": f.etapa, "serie": f.serie, "folio": f.folio,
            "referencia": f.referencia, "datos": f.datos, "resumen": f.resumen, "errores": f.errores,
            "avisos": f.avisos, "error": f.error, "intentos": f.intentos, "factura_id": f.factura_id,
            "uuid": fac.uuid if fac else None, "folio_timbra": f"{fac.serie or ''}{fac.folio or ''}" if fac else None}


@router.get("")
def listar(emisor_id: int, limit: int = 30, db: Session = Depends(get_db)):
    q = db.query(Lote).filter_by(emisor_id=emisor_id).order_by(Lote.id.desc()).limit(limit)
    return [svc.resumen_lote(db, lote) for lote in q]


@router.post("")
async def crear(emisor_id: int = Form(...), perfil_id: int = Form(...), nombre: str | None = Form(None),
                texto: str | None = Form(None), archivo: UploadFile | None = File(None),
                db: Session = Depends(get_db)):
    emisor, perfil = db.get(Emisor, emisor_id), db.get(PerfilLote, perfil_id)
    if not emisor or not perfil or perfil.emisor_id != emisor.id:
        raise HTTPException(404, "Emisor o perfil no existe")
    contenido = await archivo.read() if archivo else None

    def armar():  # leer y validar hasta 1,000 filas es trabajo pesado: fuera del ciclo de eventos (no congela a los demás)
        try:
            filas = svc.leer_filas(perfil.config, texto, contenido, archivo.filename if archivo else None)
        except svc.ErrorFila as e:
            raise HTTPException(422, str(e))
        if not filas:
            raise HTTPException(422, "No encontré renglones. Pega las filas de tu tabla (con o sin encabezados).")
        if len(filas) > 1000:
            raise HTTPException(422, "Máximo 1,000 filas por lote. Divide la tabla.")
        perfil.usos += 1
        lote = svc.crear_lote(db, emisor, (nombre or "").strip() or f"{perfil.nombre} · {datetime.now():%d/%m/%Y %H:%M}",
                              copy.deepcopy(perfil.config), perfil.id, filas)
        return _detalle(lote.id, db)
    return await run_in_threadpool(armar)


def _detalle(lid: int, db: Session) -> dict:
    lote = _lote(db, lid)
    filas = db.query(LoteFila).filter_by(lote_id=lid).order_by(LoteFila.n).all()
    return {**svc.resumen_lote(db, lote), "filas": [_fila(db, f) for f in filas], "config": lote.config,
            "alertas": svc.alertas_lote(db, lote)}


@router.get("/{lid}")
def detalle(lid: int, db: Session = Depends(get_db)):
    return _detalle(lid, db)


class FilaIn(BaseModel):
    datos: dict


@router.put("/{lid}/filas/{fid}")
def corregir(lid: int, fid: int, data: FilaIn, db: Session = Depends(get_db)):
    lote, fila = _lote(db, lid), db.get(LoteFila, fid)
    if not fila or fila.lote_id != lid:
        raise HTTPException(404, "Fila no existe")
    try:
        fila = svc.actualizar_fila(db, lote, fila, data.datos)
    except svc.ErrorFila as e:
        raise HTTPException(409, str(e))
    return _fila(db, fila)


@router.post("/{lid}/filas/{fid}/omitir")
def omitir(lid: int, fid: int, db: Session = Depends(get_db)):
    fila = db.get(LoteFila, fid)
    if not fila or fila.lote_id != lid:
        raise HTTPException(404, "Fila no existe")
    try:
        svc.omitir_fila(db, fila)
    except svc.ErrorFila as e:
        raise HTTPException(409, str(e))
    return _fila(db, fila)


@router.post("/{lid}/descartar")
def descartar(lid: int, db: Session = Depends(get_db)):
    """Tira lo que no se ha timbrado y libera los folios que «Revisar filas» había apartado."""
    lote = _lote(db, lid)
    try:
        return {"liberadas": svc.descartar_lote(db, lote)}
    except svc.ErrorFila as e:
        raise HTTPException(409, str(e))


@router.post("/{lid}/filas/{fid}/revalidar")
def revalidar(lid: int, fid: int, db: Session = Depends(get_db)):
    """Vuelve a revisar una fila sin cambiarla (p. ej. después de corregir un cliente o cargar el CSD)."""
    lote, fila = _lote(db, lid), db.get(LoteFila, fid)
    if not fila or fila.lote_id != lid:
        raise HTTPException(404, "Fila no existe")
    try:
        fila = svc.actualizar_fila(db, lote, fila, {})
    except svc.ErrorFila as e:
        raise HTTPException(409, str(e))
    return _fila(db, fila)


class EjecutarIn(BaseModel):
    ids: list[int] | None = None
    primeras: int | None = None  # "timbrar la primera y revisar": primeras=1
    detener_en_error: bool = False


@router.post("/{lid}/ejecutar")
def ejecutar(lid: int, data: EjecutarIn, db: Session = Depends(get_db)):
    lote = _lote(db, lid)
    try:
        n = svc.iniciar(db, lote, data.ids, data.primeras, data.detener_en_error)
    except svc.ErrorFila as e:
        raise HTTPException(409, str(e))
    return {"iniciadas": n}


@router.post("/{lid}/detener")
def detener(lid: int, db: Session = Depends(get_db)):
    _lote(db, lid)
    svc.detener(lid)
    return {"ok": True}


@router.get("/{lid}/registro.csv")
def registro(lid: int, db: Session = Depends(get_db)):
    lote = _lote(db, lid)
    return Response(svc.registro_csv(db, lote), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="registro_lote_{lid}.csv"'})


@router.get("/{lid}/cfdi.zip")
def zip_(lid: int, db: Session = Depends(get_db)):
    lote = _lote(db, lid)
    return Response(svc.zip_cfdi(db, lote), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="cfdi_lote_{lid}.zip"'})


@router.post("/{lid}/carpeta")
def a_carpeta(lid: int, db: Session = Depends(get_db)):
    """Deja el PDF y el XML de lo timbrado en la carpeta de entrega del perfil (sólo Timbra instalado en tu PC)."""
    lote = _lote(db, lid)
    if svc.en_ejecucion(lid):
        raise HTTPException(409, "El lote se está timbrando; al terminar se guarda solo.")
    perfil = db.get(PerfilLote, lote.perfil_id) if lote.perfil_id else None
    actual = str((perfil.config if perfil else {}).get("carpeta") or "").strip()
    if actual and actual != lote.config.get("carpeta"):  # el lote se creó antes de ponerle (o cambiarle) la carpeta al perfil
        lote.config = {**lote.config, "carpeta": actual}
        db.commit()
    try:
        return svc.guardar_en_carpeta(db, lote)
    except svc.ErrorFila as e:
        raise HTTPException(409, str(e))


@router.delete("/{lid}")
def borrar(lid: int, db: Session = Depends(get_db)):
    lote = _lote(db, lid)
    if svc.en_ejecucion(lid):
        raise HTTPException(409, "El lote se está timbrando.")
    if db.query(LoteFila).filter(LoteFila.lote_id == lid, LoteFila.estado.in_(("timbrada", "timbrando"))).count():
        raise HTTPException(409, "Ya tiene facturas timbradas: no se borra (quedaría sin historial). Omite las filas pendientes.")
    db.query(LoteFila).filter_by(lote_id=lid).delete()
    db.delete(lote)
    db.commit()
    return {"ok": True}
