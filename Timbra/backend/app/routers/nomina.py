from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Empleado, Factura
from ..schemas import EmpleadoIn, EmpleadoOut, FacturaOut, NominaIn
from ..security import current_user
from ..services import facturacion as svc
from ..services import nomina as nomina_svc

router = APIRouter(prefix="/nomina", tags=["nomina"], dependencies=[Depends(current_user)])


@router.get("/recetas")
def recetas():
    return nomina_svc.RECETAS


@router.get("/empleados", response_model=list[EmpleadoOut])
def empleados(emisor_id: int, todos: bool = False, db: Session = Depends(get_db)):
    q = db.query(Empleado).filter(Empleado.emisor_id == emisor_id)
    if not todos:
        q = q.filter(Empleado.activo.is_(True))
    return q.order_by(Empleado.num_empleado).all()


@router.post("/empleados", response_model=EmpleadoOut)
def crear(data: EmpleadoIn, db: Session = Depends(get_db)):
    if db.query(Empleado).filter_by(emisor_id=data.emisor_id, num_empleado=data.num_empleado).first():
        raise HTTPException(409, f"Ya existe el empleado número {data.num_empleado}")
    e = Empleado(**data.model_dump())
    db.add(e)
    db.commit()
    return e


@router.put("/empleados/{eid}", response_model=EmpleadoOut)
def editar(eid: int, data: EmpleadoIn, db: Session = Depends(get_db)):
    e = db.get(Empleado, eid)
    if not e:
        raise HTTPException(404, "Empleado no existe")
    for k, v in data.model_dump().items():
        setattr(e, k, v)
    db.commit()
    return e


@router.get("/borrador")
def borrador(emisor_id: int, desde: date, hasta: date, receta: str | None = None, db: Session = Depends(get_db)):
    """Recibos del periodo listos para revisar: uno por empleado activo, con su receta y sueldo calculado."""
    return [nomina_svc.payload_de_receta(e, receta, desde, hasta)
            for e in db.query(Empleado).filter_by(emisor_id=emisor_id, activo=True).order_by(Empleado.num_empleado)]


@router.post("/timbrar")
def timbrar(data: NominaIn, db: Session = Depends(get_db)):
    try:
        return svc.emitir_nomina(db, data)
    except svc.FacturacionError as e:
        raise HTTPException(422, str(e))


@router.get("/recibos", response_model=list[FacturaOut])
def recibos(emisor_id: int, limit: int = 200, db: Session = Depends(get_db)):
    out = []
    for f in (db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.tipo == "N")
              .order_by(Factura.id.desc()).limit(limit)):
        o = FacturaOut.model_validate(f)
        emp = db.get(Empleado, f.empleado_id) if f.empleado_id else None
        if emp:
            o.receptor_nombre, o.receptor_rfc = emp.nombre, emp.rfc
        out.append(o)
    return out
