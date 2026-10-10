"""A cuenta de terceros: catálogo por emisor para llenarlo en un clic en cada concepto."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Tercero
from ..schemas import TerceroIn, TerceroOut
from ..security import current_user
from ..services import validacion

router = APIRouter(prefix="/terceros", tags=["terceros"], dependencies=[Depends(current_user)])


def _validar(db: Session, data: TerceroIn):
    e = db.get(Emisor, data.emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe")
    errores = []
    if not validacion.rfc_valido(data.rfc) or data.rfc in validacion.GENERICOS:
        errores.append("RFC inválido (no se permiten genéricos).")
    elif data.rfc == e.rfc:
        errores.append("El tercero no puede ser el mismo emisor.")
    elif data.regimen_fiscal not in (validacion.REG_MORAL if validacion.tipo_persona(data.rfc) == "moral"
                                     else validacion.REG_FISICA):
        errores.append(f"El régimen {data.regimen_fiscal} no aplica a persona {validacion.tipo_persona(data.rfc)}.")
    if validacion.select("C756_c_CodigoPostal", data.codigo_postal) is None:
        errores.append(f"El CP {data.codigo_postal} no existe.")
    if errores:
        raise HTTPException(422, " · ".join(errores))
    data.nombre = validacion.nombre_sin_societario(data.nombre)


@router.get("", response_model=list[TerceroOut])
def listar(emisor_id: int, db: Session = Depends(get_db)):
    return db.query(Tercero).filter_by(emisor_id=emisor_id).order_by(Tercero.usos.desc(), Tercero.nombre).all()


@router.post("", response_model=TerceroOut)
def crear(data: TerceroIn, db: Session = Depends(get_db)):
    _validar(db, data)
    if db.query(Tercero).filter_by(emisor_id=data.emisor_id, rfc=data.rfc).first():
        raise HTTPException(409, f"{data.rfc} ya está en tus terceros.")
    t = Tercero(**data.model_dump())
    db.add(t)
    db.commit()
    return t


@router.put("/{tid}", response_model=TerceroOut)
def editar(tid: int, data: TerceroIn, db: Session = Depends(get_db)):
    t = db.get(Tercero, tid)
    if not t:
        raise HTTPException(404, "Tercero no existe")
    _validar(db, data)
    for k, v in data.model_dump().items():
        setattr(t, k, v)
    db.commit()
    return t


@router.post("/{tid}/usado")
def usado(tid: int, db: Session = Depends(get_db)):
    t = db.get(Tercero, tid)
    if t:
        t.usos += 1
        db.commit()
    return {"ok": True}


@router.delete("/{tid}")
def borrar(tid: int, db: Session = Depends(get_db)):
    t = db.get(Tercero, tid)
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}
