from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor
from ..security import current_user
from ..services import pendientes as svc

router = APIRouter(prefix="/pendientes", tags=["pendientes"], dependencies=[Depends(current_user)])


@router.get("")
def pendientes(emisor_id: int, db: Session = Depends(get_db)):
    if not db.get(Emisor, emisor_id):
        raise HTTPException(404, "Emisor no existe")
    return svc.reunir(db, emisor_id)


@router.get("/resumen")
def resumen(emisor_id: int, db: Session = Depends(get_db)):
    """Sólo los números (para el globo del menú)."""
    if not db.get(Emisor, emisor_id):
        raise HTTPException(404, "Emisor no existe")
    r = svc.reunir(db, emisor_id)
    return {"total": r["total"], "errores": r["errores"]}
