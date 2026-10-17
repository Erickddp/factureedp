"""Gastos deducibles: lista clasificada de los CFDI recibidos, decisiones de la persona y lo que Timbra ha aprendido."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, PrefDeduccion
from ..security import current_user
from ..services import deducibles as svc

router = APIRouter(prefix="/deducibles", tags=["deducibles"], dependencies=[Depends(current_user)])


def _emisor(db: Session, emisor_id: int) -> Emisor:
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe.")
    return e


@router.get("")
def lista(emisor_id: int, desde: str | None = None, hasta: str | None = None, grupo: str | None = None, q: str | None = None,
          limite: int = 200, desplazar: int = 0, db: Session = Depends(get_db)):
    if grupo and grupo not in svc.GRUPOS:
        raise HTTPException(422, "Grupo desconocido.")
    return svc.listar(db, _emisor(db, emisor_id), desde, hasta, grupo, q, min(max(limite, 1), 1000), max(desplazar, 0))


class Decision(BaseModel):
    emisor_id: int
    uuids: list[str] = Field(min_length=1, max_length=2000)
    decision: str
    porcentaje: float | None = Field(default=None, ge=0, le=100)
    nota: str | None = Field(default=None, max_length=300)
    aprender: bool = True


@router.post("/decidir")
def decidir(d: Decision, db: Session = Depends(get_db)):
    e = _emisor(db, d.emisor_id)
    try:
        n = svc.decidir(db, e, db.info.get("uid_real"), d.uuids, d.decision, d.porcentaje, d.nota, d.aprender)
    except ValueError as err:
        raise HTTPException(422, str(err))
    return {"decididos": n}


class Uuids(BaseModel):
    emisor_id: int
    uuids: list[str] = Field(min_length=1, max_length=2000)


@router.post("/deshacer")
def deshacer(d: Uuids, db: Session = Depends(get_db)):
    """Quita la decisión de la persona: vuelve a valer la sugerencia (y se corrige lo aprendido)."""
    return {"deshechos": svc.deshacer(db, _emisor(db, d.emisor_id), d.uuids)}


@router.get("/aprendido")
def aprendido(emisor_id: int, db: Session = Depends(get_db)):
    """Lo que Timbra ha aprendido de tus decisiones, para que se vea y se pueda olvidar."""
    _emisor(db, emisor_id)
    return svc.aprendido(db, emisor_id)


@router.delete("/aprendido/{pid}")
def olvidar(pid: int, db: Session = Depends(get_db)):
    p = db.get(PrefDeduccion, pid)
    if p is None:
        raise HTTPException(404, "No existe.")
    db.delete(p)
    db.commit()
    return {"ok": True}
