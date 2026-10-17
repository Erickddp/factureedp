"""Constancia de Situación Fiscal: leerla para el alta rápida del emisor, guardarla y comparar con lo que tiene el emisor."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor
from ..security import current_user
from ..services import constancia as svc
from ..services.validacion import quitar_acentos, nombre_sin_societario

router = APIRouter(prefix="/constancia", tags=["constancia"], dependencies=[Depends(current_user)])


async def _leer(archivo: UploadFile) -> tuple[bytes, dict]:
    datos = await archivo.read(svc.MAX_PDF + 1)
    try:
        return datos, svc.leer(datos)
    except svc.ConstanciaError as e:
        raise HTTPException(422, str(e))


def _emisor(db: Session, emisor_id: int) -> Emisor:
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe.")
    return e


@router.post("/leer")
async def leer(archivo: UploadFile = File(...)):
    """Alta rápida: lee el PDF y devuelve lo que se le puede sugerir al nuevo emisor. No guarda nada."""
    _, c = await _leer(archivo)
    return {"constancia": c, "emisor": svc.emisor_sugerido(c)}


@router.post("/{emisor_id}")
async def subir(emisor_id: int, archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    """Guarda la constancia de un emisor (el RFC debe coincidir) y dice en qué difiere de lo que el emisor tiene. No cambia el emisor."""
    e = _emisor(db, emisor_id)
    datos, c = await _leer(archivo)
    try:
        f = svc.guardar(db, e, datos, c, db.info.get("uid_real"))
    except svc.ConstanciaError as err:
        raise HTTPException(422, str(err))
    return {"constancia": svc.a_dict(f), "diferencias": svc.diferencias(c, e), "avisos": svc.avisos(c, e.regimen_fiscal)}


@router.get("/{emisor_id}")
def ver(emisor_id: int, db: Session = Depends(get_db)):
    e = _emisor(db, emisor_id)
    f = svc.vigente(db, e.id)
    if f is None:
        return {"constancia": None}
    c = svc.a_dict(f)
    return {"constancia": c, "diferencias": svc.diferencias(c, e), "avisos": svc.avisos(c, e.regimen_fiscal)}


class Aplicar(BaseModel):
    regimen_fiscal: str | None = None
    lugar_expedicion: str | None = None
    nombre: bool = False  # true = usar el nombre de la constancia (sin régimen societario ni acentos)


@router.post("/{emisor_id}/aplicar")
def aplicar(emisor_id: int, data: Aplicar, db: Session = Depends(get_db)):
    """Aplica al emisor SÓLO lo que la persona eligió de las diferencias."""
    e = _emisor(db, emisor_id)
    f = svc.vigente(db, e.id)
    if f is None:
        raise HTTPException(409, "Este emisor no tiene constancia guardada.")
    claves = {r.get("clave") for r in f.regimenes or [] if not r.get("hasta")}
    if data.regimen_fiscal:
        if data.regimen_fiscal not in claves:
            raise HTTPException(422, "Ese régimen no está vigente en la constancia.")
        e.regimen_fiscal = data.regimen_fiscal
    if data.lugar_expedicion:
        if data.lugar_expedicion != f.cp:
            raise HTTPException(422, "Ese código postal no es el de la constancia.")
        e.lugar_expedicion = data.lugar_expedicion
    if data.nombre:
        e.nombre = quitar_acentos(nombre_sin_societario(f.nombre)).upper()
    db.commit()
    return {"ok": True, "diferencias": svc.diferencias(svc.a_dict(f), e)}
