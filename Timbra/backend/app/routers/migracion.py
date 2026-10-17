"""Exportar mis emisores de una instalación de Timbra e importarlos en otra (ver services/migracion.py)."""
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..logs import log
from ..security import current_user
from ..services import migracion, timbres

router = APIRouter(prefix="/migracion", tags=["migracion"], dependencies=[Depends(current_user)])

MAX_ARCHIVO = 24 * 1024 * 1024  # el servidor no acepta cuerpos de más de 25 MB


def _propia(db: Session) -> None:
    """Llevar o traer llaves privadas es cosa de su dueño: ni en modo soporte."""
    if db.info.get("soporte"):
        raise HTTPException(403, "En modo soporte no se puede exportar ni importar: es una acción de la persona dueña de la cuenta.")


@router.get("/emisores")
def emisores(db: Session = Depends(get_db)):
    _propia(db)
    return migracion.lista_exportable(db)


class ExportarIn(BaseModel):
    emisor_ids: list[int]
    con_facturas: bool = True
    clave: str


@router.post("/exportar")
def exportar(data: ExportarIn, db: Session = Depends(get_db)):
    _propia(db)
    try:
        archivo, resumen = migracion.exportar(db, data.emisor_ids, data.con_facturas, data.clave)
    except migracion.MigracionError as e:
        raise HTTPException(422, str(e))
    if len(archivo) > MAX_ARCHIVO:
        raise HTTPException(422, f"El archivo pesa {len(archivo) // (1024 * 1024)} MB y el servidor sólo acepta {MAX_ARCHIVO // (1024 * 1024)} MB. "
                                 "Exporta menos emisores a la vez, o sin facturas.")
    nombre = f"cuenta_timbra_{datetime.now():%Y%m%d_%H%M}.timbracuenta"
    return Response(archivo, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}"})


def _importar(db: Session, contenido: bytes, clave: str, simular: bool) -> dict:
    paquete = migracion.abrir(contenido, clave)
    plataforma = timbres.pac_plataforma(db)
    informe = migracion.importar(db, paquete, plataforma.id if plataforma else None)
    if simular:
        db.rollback()
    else:
        db.commit()
    return {"simulacro": simular, "creado": paquete.get("creado"), "con_facturas": bool(paquete.get("con_facturas")), "emisores": informe}


@router.post("/importar")
async def importar(archivo: UploadFile = File(...), clave: str = Form(...), simular: bool = Form(True), db: Session = Depends(get_db)):
    """simular=true (lo que hace la pantalla primero): dice qué entraría, sin guardar nada. Después, simular=false."""
    _propia(db)
    contenido = await archivo.read(MAX_ARCHIVO + 1)
    if len(contenido) > MAX_ARCHIVO:
        raise HTTPException(422, "El archivo es demasiado grande.")
    try:
        r = await run_in_threadpool(_importar, db, contenido, clave, simular)
    except migracion.MigracionError as e:
        raise HTTPException(422, str(e))
    if not simular:
        log.warning("MIGRACIÓN: se importaron %s", [(x["rfc"], x["estado"]) for x in r["emisores"]])
    return r
