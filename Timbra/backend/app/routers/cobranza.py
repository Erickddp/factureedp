from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Cliente, Emisor
from ..security import current_user
from ..services import cobranza as svc

router = APIRouter(prefix="/cobranza", tags=["cobranza"], dependencies=[Depends(current_user)])


@router.get("")
def antiguedad(emisor_id: int, db: Session = Depends(get_db)):
    return svc.antiguedad(db, emisor_id)


@router.get("/facturas")
def facturas(emisor_id: int, cliente_id: int | None = None, db: Session = Depends(get_db)):
    return svc.pendientes(db, emisor_id, cliente_id)


def _cliente(db, cid) -> Cliente:
    c = db.get(Cliente, cid)
    if not c:
        raise HTTPException(404, "Cliente no existe")
    return c


@router.get("/estado-cuenta/{cliente_id}")
def estado_cuenta(cliente_id: int, db: Session = Depends(get_db)):
    return svc.estado_cuenta(db, _cliente(db, cliente_id))


@router.get("/estado-cuenta/{cliente_id}/html")
def estado_cuenta_html(cliente_id: int, db: Session = Depends(get_db)):
    c = _cliente(db, cliente_id)
    h = svc.html_estado(db.get(Emisor, c.emisor_id), svc.estado_cuenta(db, c))
    return Response(h.replace("</html>", "<script>setTimeout(()=>print(),300)</script></html>"), media_type="text/html")


class RecordarIn(BaseModel):
    cliente_ids: list[int]
    mensaje: str | None = None


@router.post("/recordar")
def recordar(data: RecordarIn, db: Session = Depends(get_db)):
    out = []
    for cid in data.cliente_ids:
        c = _cliente(db, cid)
        try:
            out.append(svc.recordar(db, db.get(Emisor, c.emisor_id), c, data.mensaje))
        except Exception as e:
            out.append({"cliente_id": cid, "ok": False, "error": str(e)})
    return out
