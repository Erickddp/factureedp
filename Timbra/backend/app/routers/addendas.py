from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db, solo_admin
from ..models import Addenda
from ..schemas import AddendaIn, AddendaOut
from ..security import current_user
from ..services.addenda import AddendaError, render

router = APIRouter(prefix="/addendas", tags=["addendas"], dependencies=[Depends(current_user)])


@router.get("", response_model=list[AddendaOut])
def listar(db: Session = Depends(get_db)):
    return db.query(Addenda).order_by(Addenda.nombre).all()


@router.post("", response_model=AddendaOut)
def crear(data: AddendaIn, db: Session = Depends(get_db)):
    a = Addenda(**data.model_dump())
    db.add(a)
    db.commit()
    return a


@router.put("/{addenda_id}", response_model=AddendaOut, dependencies=[Depends(solo_admin)])
def editar(addenda_id: int, data: AddendaIn, db: Session = Depends(get_db)):
    a = db.get(Addenda, addenda_id)
    if not a:
        raise HTTPException(404, "Addenda no existe")
    for k, v in data.model_dump().items():
        setattr(a, k, v)
    db.commit()
    return a


@router.post("/probar")
def probar(data: dict):
    """Renderiza una plantilla con datos de ejemplo para validar antes de guardar."""
    try:
        from lxml import etree
        el = render(data["plantilla"], data.get("datos", {}), data.get("cfdi", {"Total": "1160.00", "SubTotal": "1000.00", "Moneda": "MXN", "Serie": "A", "Folio": "1"}))
        return {"xml": etree.tostring(el, pretty_print=True).decode()}
    except AddendaError as e:
        raise HTTPException(422, str(e))
