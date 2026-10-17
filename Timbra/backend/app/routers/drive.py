"""Google Drive de la cuenta: conectar, ver cómo va la copia de XML, copiar ahora y desconectar (services/drive.py)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import current_user
from ..services import drive

router = APIRouter(prefix="/drive", tags=["drive"], dependencies=[Depends(current_user)])


def _uid(db: Session) -> int:
    uid = db.info.get("uid")
    if uid is None:
        raise HTTPException(401, "Vuelve a entrar.")
    return uid


@router.get("")
def estado(db: Session = Depends(get_db)):
    return drive.estado(db, _uid(db))


@router.post("/conectar")
def conectar(db: Session = Depends(get_db)):
    if db.info.get("soporte"):
        raise HTTPException(403, "En modo soporte no se conecta un Drive: lo hace el dueño de la cuenta.")
    try:
        return {"url": drive.url_conectar(_uid(db))}
    except drive.DriveError as e:
        raise HTTPException(503, str(e))


@router.post("/sincronizar")
def sincronizar(db: Session = Depends(get_db)):
    uid = _uid(db)
    if not drive.estado(db, uid).get("conectado"):
        raise HTTPException(409, "Primero conecta tu Google Drive.")
    return {"iniciada": drive.lanzar(uid)}


@router.delete("")
def desconectar(db: Session = Depends(get_db)):
    drive.desconectar(db, _uid(db))
    return {"ok": True}
