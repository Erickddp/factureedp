"""Portal de autofactura: el cliente captura folio + total del ticket y sus datos fiscales, y se lleva su CFDI.

Público (sin login). Protecciones: ticket de un solo uso, total exacto, sólo tickets del mes en curso
(después entran a la factura global), límite de intentos por IP y descarga con firma HMAC.
Ojo: en la instalación local sólo lo ve tu red; para publicarlo usa un túnel (Cloudflare Tunnel) o el servidor.
"""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..logs import log
from ..models import Emisor, Factura, Ticket
from ..schemas import AutofacturaIn, FacturaIn, TicketIn
from ..security import current_user
from ..services import facturacion as svc
from ..services import pdf as pdf_svc
from ..services.cfdi import ahora_mx

publico = APIRouter(prefix="/portal", tags=["portal"])
router = APIRouter(prefix="/tickets", tags=["portal"], dependencies=[Depends(current_user)])

_intentos: dict[str, deque] = defaultdict(deque)
MAX_INTENTOS, VENTANA = 10, 600


def _limitar(ip: str):
    q, ahora = _intentos[ip], time.time()
    while q and ahora - q[0] > VENTANA:
        q.popleft()
    if len(q) >= MAX_INTENTOS:
        raise HTTPException(429, "Demasiados intentos. Espera unos minutos.")
    q.append(ahora)


def _firma(uuid: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), uuid.encode(), hashlib.sha256).hexdigest()[:32]


def _emisor(db: Session, clave: str) -> Emisor:
    e = db.query(Emisor).filter_by(portal_clave=clave, portal_activo=True).first()
    if not e:
        raise HTTPException(404, "Portal no disponible.")
    return e


def _conceptos(e: Emisor, t: Ticket) -> list[dict]:
    if t.conceptos:
        return t.conceptos
    cfg = e.portal_config or {}
    tasa = Decimal(str(cfg.get("tasa", "0.08" if e.region_fronteriza else "0.16")))
    base = (t.total / (1 + tasa)).quantize(Decimal("0.000001"))
    return [{"clave_prod_serv": cfg.get("clave_prod_serv", "01010101"), "clave_unidad": cfg.get("clave_unidad", "ACT"),
             "descripcion": cfg.get("descripcion", f"Venta ticket {t.folio}"), "cantidad": "1",
             "valor_unitario": str(base), "objeto_imp": "02",
             "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": str(tasa)}]}]


@publico.get("/{clave}")
def info(clave: str, db: Session = Depends(get_db)):
    e = _emisor(db, clave)
    return {"nombre": e.nombre, "rfc": e.rfc, "logo_b64": e.logo_b64, "color": e.color}


@publico.post("/{clave}/facturar")
def autofacturar(clave: str, data: AutofacturaIn, request: Request, db: Session = Depends(get_db)):
    _limitar(request.client.host if request.client else "?")
    e = _emisor(db, clave)
    t = db.query(Ticket).filter_by(emisor_id=e.id, folio=data.folio).with_for_update().first()
    if not t or abs(Decimal(t.total) - data.total) > Decimal("0.009"):
        raise HTTPException(404, "No encontramos un ticket con ese folio y total. Revisa tu ticket.")
    if t.factura_id:
        raise HTTPException(409, "Ese ticket ya se facturó. Si no recibiste tu factura, contacta al negocio.")
    hoy = ahora_mx()
    if (t.fecha.year, t.fecha.month) != (hoy.year, hoy.month):
        raise HTTPException(422, "Sólo se facturan tickets del mes en curso. Los anteriores ya entraron a la "
                                 "factura global; contacta al negocio.")
    if data.rfc in ("XAXX010101000", "XEXX010101000"):
        raise HTTPException(422, "Para público en general no necesitas factura.")
    payload = FacturaIn(
        emisor_id=e.id, tipo="I", metodo_pago="PUE", forma_pago=t.forma_pago, conceptos=_conceptos(e, t),
        receptor={"rfc": data.rfc, "nombre": data.nombre, "regimen_fiscal": data.regimen_fiscal,
                  "codigo_postal": data.codigo_postal, "uso_cfdi": data.uso_cfdi, "guardar": True},
    )
    try:
        f = svc.emitir(db, payload)
    except Exception as ex:
        db.rollback()
        log.warning("Autofactura rechazada (ticket %s): %s", t.folio, ex)
        raise HTTPException(422, str(ex).replace("No timbré, corrige esto: ", "Revisa tus datos: "))
    t = db.get(Ticket, t.id)
    t.factura_id = f.id
    if data.email and f.cliente and data.email not in (f.cliente.emails or []):
        f.cliente.emails = [*(f.cliente.emails or []), data.email]
    db.commit()
    if data.email:
        try:
            svc.enviar(f, [data.email])
        except Exception as ex:
            log.warning("Autofactura timbrada, correo falló: %s", ex)
    return {"uuid": f.uuid, "folio": f"{f.serie or ''}{f.folio}", "total": str(f.total), "firma": _firma(f.uuid)}


@publico.get("/{clave}/descarga/{uuid}")
def descarga(clave: str, uuid: str, firma: str, formato: str = "pdf", db: Session = Depends(get_db)):
    e = _emisor(db, clave)
    if not hmac.compare_digest(firma, _firma(uuid.upper())):
        raise HTTPException(403, "Liga inválida.")
    f = db.query(Factura).filter_by(uuid=uuid.upper(), emisor_id=e.id).first()
    if not f:
        raise HTTPException(404, "No existe.")
    if formato == "xml":
        return Response(f.xml, media_type="application/xml",
                        headers={"Content-Disposition": f'attachment; filename="{f.uuid}.xml"'})
    try:
        return Response(pdf_svc.pdf(f.xml, e), media_type="application/pdf")
    except RuntimeError:
        return Response(pdf_svc.html(f.xml, imprimir=True, emisor=e), media_type="text/html")


# ---------- Administración (con login) ----------
class PortalCfg(BaseModel):
    activo: bool
    config: dict = {}


@router.put("/portal/{emisor_id}")
def configurar(emisor_id: int, data: PortalCfg, db: Session = Depends(get_db)):
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe")
    e.portal_activo = data.activo
    e.portal_config = data.config
    if not e.portal_clave:
        e.portal_clave = secrets.token_urlsafe(9)
    db.commit()
    return {"activo": e.portal_activo, "clave": e.portal_clave, "config": e.portal_config}


@router.get("")
def listar(emisor_id: int, pendientes: bool = False, db: Session = Depends(get_db)):
    q = db.query(Ticket).filter(Ticket.emisor_id == emisor_id)
    if pendientes:
        q = q.filter(Ticket.factura_id.is_(None))
    return [{"id": t.id, "folio": t.folio, "fecha": t.fecha, "total": t.total, "forma_pago": t.forma_pago,
             "factura_id": t.factura_id} for t in q.order_by(Ticket.fecha.desc()).limit(500)]


@router.post("")
def crear(tickets: list[TicketIn], db: Session = Depends(get_db)):
    """Uno o muchos (pegados de Excel). Los folios repetidos se ignoran."""
    nuevos, vistos = 0, set()
    for t in tickets:
        llave = (t.emisor_id, t.folio.strip().upper())
        if llave in vistos or db.query(Ticket).filter_by(emisor_id=t.emisor_id, folio=llave[1]).first():
            continue
        vistos.add(llave)
        db.add(Ticket(emisor_id=t.emisor_id, folio=t.folio.strip().upper(), fecha=t.fecha, total=t.total,
                      forma_pago=t.forma_pago, conceptos=[c.model_dump(mode="json") for c in t.conceptos]))
        nuevos += 1
    db.commit()
    return {"nuevos": nuevos, "repetidos": len(tickets) - nuevos}


@router.delete("/{tid}")
def borrar(tid: int, db: Session = Depends(get_db)):
    t = db.get(Ticket, tid)
    if t and t.factura_id:
        raise HTTPException(409, "Ya se facturó; no se borra.")
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}
