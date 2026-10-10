from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Producto, Serie
from ..services.semillas import a_frontera, productos_base
from ..schemas import EmisorIn, EmisorOut, SerieIn, SerieOut
from ..security import current_user
from ..services.signer import CsdError, cargar_csd

router = APIRouter(prefix="/emisores", tags=["emisores"], dependencies=[Depends(current_user)])


def _get(db, emisor_id) -> Emisor:
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe")
    return e


@router.get("", response_model=list[EmisorOut])
def listar(db: Session = Depends(get_db)):
    return db.query(Emisor).order_by(Emisor.nombre).all()


@router.get("/{emisor_id}", response_model=EmisorOut)
def ver(emisor_id: int, db: Session = Depends(get_db)):
    return _get(db, emisor_id)


@router.post("", response_model=EmisorOut)
def crear(data: EmisorIn, db: Session = Depends(get_db)):
    if db.query(Emisor).filter_by(rfc=data.rfc).first():
        raise HTTPException(409, f"{data.rfc} ya está dado de alta")
    e = Emisor(**data.model_dump())
    e.series = [Serie(serie="A", tipo="I", default=True), Serie(serie="NC", tipo="E", default=True),
                Serie(serie="P", tipo="P", default=True), Serie(serie="T", tipo="T", default=True),
                Serie(serie="N", tipo="N", default=True)]
    db.add(e)
    db.flush()
    db.add_all(Producto(**p) for p in productos_base(e.id, e.region_fronteriza))  # catálogo base listo para usar
    db.commit()
    return e


@router.put("/{emisor_id}", response_model=EmisorOut)
def editar(emisor_id: int, data: EmisorIn, db: Session = Depends(get_db)):
    e = _get(db, emisor_id)
    for k, v in data.model_dump(exclude_unset=True).items():  # sin logo en el payload = se conserva
        setattr(e, k, v)
    db.commit()
    return e


@router.post("/{emisor_id}/csd", response_model=EmisorOut)
async def subir_csd(emisor_id: int, cer: UploadFile = File(...), key: UploadFile = File(...),
                    password: str = Form(...), db: Session = Depends(get_db)):
    e = _get(db, emisor_id)
    try:
        cargar_csd(e, await cer.read(), await key.read(), password)
    except CsdError as ex:
        raise HTTPException(422, str(ex))
    db.commit()
    return e


@router.post("/{emisor_id}/series", response_model=SerieOut)
def crear_serie(emisor_id: int, data: SerieIn, db: Session = Depends(get_db)):
    e = _get(db, emisor_id)
    if any(s.serie == data.serie for s in e.series):
        raise HTTPException(409, f"La serie {data.serie} ya existe en {e.rfc}.")
    if data.default:
        for s in e.series:
            if s.tipo == data.tipo:
                s.default = False
    s = Serie(emisor_id=e.id, **data.model_dump())
    db.add(s)
    db.commit()
    return s


@router.post("/{emisor_id}/productos-a-frontera")
def productos_a_frontera(emisor_id: int, db: Session = Depends(get_db)):
    """Pasa el catálogo del emisor de IVA 16% a 8% (y retención 10.6667% → 5.3333%)."""
    e = _get(db, emisor_id)
    n = 0
    for p in db.query(Producto).filter(Producto.emisor_id == e.id):
        nuevos = a_frontera(p.impuestos or [])
        if nuevos != p.impuestos:
            p.impuestos = nuevos
            n += 1
    db.commit()
    return {"actualizados": n}


@router.get("/{emisor_id}/config-facturar")
def ver_config(emisor_id: int, db: Session = Depends(get_db)):
    from ..services.config_facturar import efectiva
    return efectiva(_get(db, emisor_id).config_facturar)


@router.put("/{emisor_id}/config-facturar")
def guardar_config(emisor_id: int, data: dict, db: Session = Depends(get_db)):
    """Nivel, campos visibles, valores por defecto y perfiles rápidos de la barra de Facturar."""
    from ..services.config_facturar import efectiva, limpiar
    e = _get(db, emisor_id)
    e.config_facturar = {**(e.config_facturar or {}), **limpiar(data)}
    db.commit()
    return efectiva(e.config_facturar)
