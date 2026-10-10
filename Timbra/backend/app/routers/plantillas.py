"""Plantillas: facturas guardadas como formato (iguala mensual, renta, honorarios...)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Cliente, Factura, Plantilla
from ..security import current_user
from ..services import recurrentes
from ..services.cfdi import ahora_mx

router = APIRouter(prefix="/plantillas", tags=["plantillas"], dependencies=[Depends(current_user)])

QUITAR = ("fecha", "enviar_email", "serie")


class PlantillaIn(BaseModel):
    emisor_id: int
    cliente_id: int | None = None
    nombre: str
    payload: dict


class AjustesIn(BaseModel):
    nombre: str | None = None
    favorita: int | None = None
    recurrente: bool = False
    dia: int = 1
    auto_timbrar: bool = False
    enviar_email: bool = False


def _out(p: Plantilla, db: Session):
    c = db.get(Cliente, p.cliente_id) if p.cliente_id else None
    return {"id": p.id, "emisor_id": p.emisor_id, "cliente_id": p.cliente_id, "nombre": p.nombre,
            "payload": p.payload, "usos": p.usos, "cliente_nombre": c.nombre if c else None,
            "favorita": p.favorita, "recurrente": p.recurrente, "dia": p.dia, "proxima": p.proxima,
            "auto_timbrar": p.auto_timbrar, "enviar_email": p.enviar_email,
            "ultima_factura_id": p.ultima_factura_id, "ultimo_error": p.ultimo_error}


def _limpiar(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k not in QUITAR}


@router.get("")
def listar(emisor_id: int, cliente_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Plantilla).filter(Plantilla.emisor_id == emisor_id)
    if cliente_id:
        q = q.filter((Plantilla.cliente_id == cliente_id) | (Plantilla.cliente_id.is_(None)))
    return [_out(p, db) for p in q.order_by(Plantilla.usos.desc(), Plantilla.nombre)]


@router.post("")
def crear(data: PlantillaIn, db: Session = Depends(get_db)):
    p = Plantilla(emisor_id=data.emisor_id, cliente_id=data.cliente_id or data.payload.get("cliente_id"),
                  nombre=data.nombre.strip(), payload=_limpiar(data.payload))
    db.add(p)
    db.commit()
    return _out(p, db)


@router.post("/desde-factura/{factura_id}")
def desde_factura(factura_id: int, nombre: str, db: Session = Depends(get_db)):
    f = db.get(Factura, factura_id)
    if not f or f.tipo == "P":
        raise HTTPException(404, "Factura no existe o es un complemento de pago")
    p = Plantilla(emisor_id=f.emisor_id, cliente_id=f.cliente_id, nombre=nombre, payload=_limpiar(f.payload))
    db.add(p)
    db.commit()
    return _out(p, db)


@router.get("/recurrentes/pendientes")
def pendientes(emisor_id: int | None = None, db: Session = Depends(get_db)):
    """Las que tocan hoy (o se atrasaron): el dashboard las muestra como "Por timbrar"."""
    return [_out(p, db) for p in recurrentes.pendientes(db, emisor_id)]


@router.put("/{pid}")
def ajustar(pid: int, data: AjustesIn, db: Session = Depends(get_db)):
    p = db.get(Plantilla, pid)
    if not p:
        raise HTTPException(404, "Plantilla no existe")
    if data.favorita is not None and not 1 <= data.favorita <= 9:
        raise HTTPException(422, "La favorita va del 1 al 9 (Alt+Shift+número).")
    if data.favorita:
        for o in db.query(Plantilla).filter(Plantilla.emisor_id == p.emisor_id, Plantilla.favorita == data.favorita,
                                            Plantilla.id != p.id):
            o.favorita = None
    if data.recurrente and not 1 <= data.dia <= 31:
        raise HTTPException(422, "El día del mes va del 1 al 31 (si el mes es más corto, se usa el último día).")
    if data.recurrente and not (p.cliente_id or p.payload.get("cliente_id") or p.payload.get("publico_general")):
        raise HTTPException(422, "Una recurrente necesita cliente fijo (o público en general).")
    if data.nombre:
        p.nombre = data.nombre.strip()
    p.favorita = data.favorita
    cambio_dia = data.recurrente and (not p.recurrente or p.dia != data.dia or p.proxima is None)
    p.recurrente, p.dia, p.auto_timbrar, p.enviar_email = data.recurrente, data.dia, data.auto_timbrar, data.enviar_email
    if cambio_dia:
        p.proxima = recurrentes.primera(data.dia, ahora_mx())
    if not data.recurrente:
        p.proxima = None
    p.ultimo_error = None if data.recurrente else p.ultimo_error
    db.commit()
    return _out(p, db)


@router.post("/{pid}/timbrar")
def timbrar_ya(pid: int, db: Session = Depends(get_db)):
    """Timbra la recurrente ahora y la avanza al siguiente mes."""
    p = db.get(Plantilla, pid)
    if not p:
        raise HTTPException(404, "Plantilla no existe")
    try:
        f = recurrentes.ejecutar(db, p)
    except Exception as e:
        raise HTTPException(422, str(e))
    return {"factura_id": f.id, "uuid": f.uuid, "folio": f"{f.serie or ''}{f.folio}", "total": str(f.total),
            "proxima": db.get(Plantilla, pid).proxima}


@router.post("/{pid}/usar")
def usar(pid: int, db: Session = Depends(get_db)):
    p = db.get(Plantilla, pid)
    if not p:
        raise HTTPException(404, "Plantilla no existe")
    p.usos += 1
    db.commit()
    return p.payload


@router.delete("/{pid}")
def borrar(pid: int, db: Session = Depends(get_db)):
    p = db.get(Plantilla, pid)
    if p:
        db.delete(p)
        db.commit()
    return {"ok": True}
