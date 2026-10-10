"""Correo de envío: la cuenta desde la que salen las facturas, estados de cuenta y recordatorios."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..logs import log
from ..security import current_user
from ..services import mailer

router = APIRouter(prefix="/correo", tags=["correo"], dependencies=[Depends(current_user)])


class CorreoIn(BaseModel):
    host: str
    port: int = 587
    user: str
    password: str | None = None  # vacío = conservar la guardada
    remitente: str | None = None
    nombre: str | None = None


class PruebaIn(BaseModel):
    para: str


@router.get("")
def ver():
    return mailer.publica()


@router.put("")
def guardar(data: CorreoIn):
    if "@" not in data.user or not data.host.strip():
        raise HTTPException(422, "Escribe el correo completo y el servidor.")
    try:
        r = mailer.guardar(data.host, data.port, data.user, data.password, data.remitente, data.nombre)
    except mailer.CorreoError as e:
        raise HTTPException(422, str(e))
    log.info("Correo de envío configurado: %s vía %s:%s", data.user, data.host, data.port)
    return r


@router.delete("")
def quitar():
    return mailer.quitar()


@router.post("/probar")
def probar(data: PruebaIn):
    try:
        mailer.enviar([data.para], "Prueba de Timbra", "Si lees esto, el correo de envío de Timbra quedó bien configurado.", [])
    except mailer.CorreoError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "para": data.para}
