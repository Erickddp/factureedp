"""Compra de timbres en línea (Mercado Pago). La lógica vive en services/pagos.py."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..logs import log
from ..models import Pago, Usuario
from ..security import current_user
from ..services import pagos, timbres

router = APIRouter(prefix="/pagos", tags=["pagos"])


def _yo(db: Session, email: str) -> Usuario:
    u = db.query(Usuario).filter(Usuario.email == email).first()
    if not u:
        raise HTTPException(401, "Sesión no válida")
    return u


@router.get("/paquetes")
def paquetes(email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = _yo(db, email)
    return {"activo": pagos.activo(), "paquetes": pagos.paquetes(), "timbres": None if u.admin else u.timbres,
            "vence": None if u.admin else timbres.proximo_vencimiento(db, u.id), "vigencia_meses": timbres.VIGENCIA_MESES}


class CompraIn(BaseModel):
    paquete: str


@router.post("")
def comprar(data: CompraIn, request: Request, email: str = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return pagos.crear(db, _yo(db, email), data.paquete, str(request.base_url))
    except pagos.PagoError as e:
        raise HTTPException(422, str(e))


@router.get("")
def mis_pagos(email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = _yo(db, email)
    return [pagos.publico(p) for p in db.query(Pago).filter(Pago.usuario_id == u.id).order_by(Pago.id.desc()).limit(20)]


class RegresoIn(BaseModel):
    pago: int
    payment_id: str | None = None


@router.post("/regreso")
def regreso(data: RegresoIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    """La persona regresa de Mercado Pago (trae ?payment_id=): se consulta en ese momento por si el aviso aún no llega."""
    u = _yo(db, email)
    p = db.get(Pago, data.pago)
    if not p or p.usuario_id != u.id:
        raise HTTPException(404, "Pago no existe")
    if data.payment_id and p.estado != "aprobado":
        try:
            pagos.procesar(db, data.payment_id)
        except pagos.PagoError as e:
            log.warning("No se pudo confirmar el pago %s al regresar: %s", p.id, e)
        db.expire_all()
        p = db.get(Pago, data.pago)
    return {**pagos.publico(p), "timbres_cuenta": db.get(Usuario, u.id).timbres}


@router.post("/aviso")
async def aviso(request: Request):
    """Webhook de Mercado Pago. Sin sesión: la seguridad es que el pago se CONSULTA en la API de Mercado Pago."""
    q = request.query_params
    try:
        cuerpo = await request.json()
    except ValueError:
        cuerpo = {}
    tipo = q.get("type") or q.get("topic") or cuerpo.get("type") or cuerpo.get("topic")
    data_id = str(q.get("data.id") or q.get("id") or (cuerpo.get("data") or {}).get("id") or "")
    if tipo != "payment" or not data_id.isdigit():
        return {"ok": True}  # otros avisos (merchant_order, etc.) no se usan
    if not pagos.firma_valida(request.headers.get("x-signature"), request.headers.get("x-request-id"), data_id):
        log.warning("Aviso de Mercado Pago con firma inválida (pago %s)", data_id)
        raise HTTPException(401, "Firma inválida")
    from fastapi.concurrency import run_in_threadpool

    def correr():
        with SessionLocal() as db:
            pagos.procesar(db, data_id)
    try:
        await run_in_threadpool(correr)
    except pagos.PagoError as e:
        log.error("Aviso de Mercado Pago %s: %s", data_id, e)
        raise HTTPException(502, "No se pudo consultar el pago")  # Mercado Pago reintenta
    return {"ok": True}
