import csv
import io
import threading
import time
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Cliente, Factura
from ..schemas import CancelarIn, EnviarIn, FacturaIn, FacturaOut, PagoIn, TotalesOut
from ..security import current_user
from ..services import facturacion as svc
from ..services import pdf as pdf_svc
from ..services.addenda import AddendaError
from ..services.cfdi import CfdiError
from ..services.pac import PacError
from ..services.signer import CsdError

router = APIRouter(prefix="/facturas", tags=["facturas"], dependencies=[Depends(current_user)])

ERRORES = (svc.FacturacionError, CfdiError, CsdError, PacError, AddendaError)


def _out(f: Factura) -> FacturaOut:
    o = FacturaOut.model_validate(f)
    o.demo = pdf_svc.es_demo(f.xml)
    if f.cliente:
        o.receptor_nombre, o.receptor_rfc = f.cliente.nombre, f.cliente.rfc
    elif f.payload.get("publico_general"):
        o.receptor_nombre, o.receptor_rfc = "PUBLICO EN GENERAL", "XAXX010101000"
    return o


def _get(db, fid) -> Factura:
    f = db.get(Factura, fid)
    if not f:
        raise HTTPException(404, "Factura no existe")
    return f


@router.get("", response_model=list[FacturaOut])
def listar(emisor_id: int | None = None, estado: str | None = None, tipo: str | None = None,
           cliente_id: int | None = None, q: str | None = None, pendientes: bool = False,
           desde: datetime | None = None, hasta: datetime | None = None,
           limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    qs = db.query(Factura).outerjoin(Cliente)
    if emisor_id:
        qs = qs.filter(Factura.emisor_id == emisor_id)
    if estado:
        qs = qs.filter(Factura.estado == estado)
    if tipo:
        qs = qs.filter(Factura.tipo == tipo)
    if cliente_id:
        qs = qs.filter(Factura.cliente_id == cliente_id)
    if pendientes:
        qs = qs.filter(Factura.saldo > 0, Factura.estado == "timbrada")
    if desde:
        qs = qs.filter(Factura.fecha >= desde)
    if hasta:
        qs = qs.filter(Factura.fecha <= hasta)
    if q:
        like = f"%{q.upper()}%"
        qs = qs.filter((Cliente.nombre.like(like)) | (Cliente.rfc.like(like)) | (Factura.uuid.like(like))
                       | (func.coalesce(Factura.serie, "") + func.coalesce(Factura.folio, "")).like(like))
    return [_out(f) for f in qs.order_by(Factura.id.desc()).offset(offset).limit(limit).all()]


@router.post("/preview")
def preview(data: FacturaIn, db: Session = Depends(get_db)):
    """Totales en vivo sin timbrar (para el ticket del front)."""
    try:
        return svc.previsualizar(db, data)
    except ERRORES as e:
        raise HTTPException(422, str(e))


# Idempotencia: el navegador manda la misma llave si reintenta (doble clic, red que se cayó tras timbrar).
# Con la misma llave nunca se timbra dos veces: se regresa la factura ya hecha o se avisa que va en curso.
_IDEM: dict[str, tuple[float, int | None]] = {}
_IDEM_LOCK = threading.Lock()
_IDEM_TTL = 1800


def _idem_inicio(llave: str | None, db) -> Factura | None:
    if not llave:
        return None
    with _IDEM_LOCK:
        ahora = time.time()
        for k in [k for k, (t0, _) in _IDEM.items() if ahora - t0 > _IDEM_TTL]:
            _IDEM.pop(k, None)
        if llave in _IDEM:
            fid = _IDEM[llave][1]
            if fid is None:
                raise HTTPException(409, "Esta factura ya se está timbrando. Espera unos segundos.")
            if fid == -1:
                raise HTTPException(409, "Esta factura ya se timbró pero no se guardó. No la vuelvas a timbrar: "
                                         "usa Facturas → Recuperar desde respaldo.")
            return db.get(Factura, fid)
        _IDEM[llave] = (ahora, None)
    return None


def _idem_fin(llave: str | None, fid: int | None):
    if not llave:
        return
    with _IDEM_LOCK:
        if fid is None:
            _IDEM.pop(llave, None)  # falló: se puede volver a intentar
        else:
            _IDEM[llave] = (time.time(), fid)


@router.post("", response_model=FacturaOut)
def emitir(data: FacturaIn, db: Session = Depends(get_db), llave: str | None = Header(None, alias="Idempotency-Key")):
    """Un solo golpe: arma, sella, timbra, addenda, guarda y (opcional) manda correo."""
    previa = _idem_inicio(llave, db)
    if previa:
        return _out(previa)
    try:
        f = svc.emitir(db, data)
    except svc.TimbradoSinGuardar as e:
        _idem_fin(llave, -1)  # bloquea el reintento: ya hay timbre
        raise HTTPException(500, str(e))
    except ERRORES as e:
        db.rollback()  # regresa el folio reservado
        _idem_fin(llave, None)
        raise HTTPException(422, str(e))
    except Exception:
        _idem_fin(llave, None)
        raise
    _idem_fin(llave, f.id)
    return _out(f)


@router.post("/pagos", response_model=FacturaOut)
def emitir_pago(data: PagoIn, db: Session = Depends(get_db), llave: str | None = Header(None, alias="Idempotency-Key")):
    previa = _idem_inicio(llave, db)
    if previa:
        return _out(previa)
    try:
        f = svc.emitir_pago(db, data)
    except svc.TimbradoSinGuardar as e:
        _idem_fin(llave, -1)
        raise HTTPException(500, str(e))
    except ERRORES as e:
        db.rollback()
        _idem_fin(llave, None)
        raise HTTPException(422, str(e))
    except Exception:
        _idem_fin(llave, None)
        raise
    _idem_fin(llave, f.id)
    return _out(f)


def _filtrados(db, emisor_id, desde, hasta, tipo, estado):
    qs = db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.xml.isnot(None))
    if desde:
        qs = qs.filter(Factura.fecha >= desde)
    if hasta:
        qs = qs.filter(Factura.fecha <= hasta)
    if tipo:
        qs = qs.filter(Factura.tipo == tipo)
    if estado:
        qs = qs.filter(Factura.estado == estado)
    return qs.order_by(Factura.fecha).all()


@router.get("/exportar/zip")
def exportar_zip(emisor_id: int, desde: datetime | None = None, hasta: datetime | None = None,
                 tipo: str | None = None, estado: str | None = None, db: Session = Depends(get_db)):
    """Todos los XML del periodo en un ZIP (para la contabilidad / COI)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in _filtrados(db, emisor_id, desde, hasta, tipo, estado):
            carpeta = "canceladas/" if f.estado == "cancelada" else ""
            z.writestr(f"{carpeta}{f.serie or ''}{f.folio or ''}_{f.uuid}.xml", f.xml)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="xml_timbra.zip"'})


@router.get("/exportar/csv")
def exportar_csv(emisor_id: int, desde: datetime | None = None, hasta: datetime | None = None,
                 tipo: str | None = None, estado: str | None = None, db: Session = Depends(get_db)):
    """Reporte que abre directo en Excel (UTF-8 con BOM)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["FECHA", "SERIE", "FOLIO", "UUID", "TIPO", "RFC RECEPTOR", "RECEPTOR", "METODO", "FORMA",
                "MONEDA", "SUBTOTAL", "DESCUENTO", "TOTAL", "SALDO", "ESTADO"])
    for f in _filtrados(db, emisor_id, desde, hasta, tipo, estado):
        o = _out(f)
        w.writerow([f.fecha.strftime("%d/%m/%Y") if f.fecha else "", f.serie, f.folio, f.uuid, f.tipo,
                    o.receptor_rfc, o.receptor_nombre, f.metodo_pago, f.forma_pago, f.moneda,
                    f"{f.subtotal:.2f}", f"{f.descuento or 0:.2f}", f"{f.total:.2f}", f"{f.saldo:.2f}", f.estado])
    return Response(("\ufeff" + out.getvalue()).encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="facturas.csv"'})


@router.post("/recuperar")
def recuperar(db: Session = Depends(get_db)):
    """Reimporta XML del respaldo en disco que no estén en la BD."""
    return {"recuperadas": svc.recuperar(db)}


@router.get("/ultima")
def ultima(cliente_id: int, db: Session = Depends(get_db)):
    """La última factura (ingreso o nota) de ese cliente, lista para repetir: el atajo más rápido del día a día."""
    f = (db.query(Factura).filter(Factura.cliente_id == cliente_id, Factura.tipo.in_(("I", "E")),
                                   Factura.estado.in_(("timbrada", "cancelada")))
         .order_by(Factura.id.desc()).first())
    if not f:
        return None
    return {"factura_id": f.id, "folio": f"{f.serie or ''}{f.folio or ''}", "fecha": f.fecha, "total": f.total,
            "payload": {k: v for k, v in f.payload.items() if k not in ("fecha", "serie")}}


@router.get("/{fid}", response_model=FacturaOut)
def ver(fid: int, db: Session = Depends(get_db)):
    return _out(_get(db, fid))


@router.get("/{fid}/payload")
def payload(fid: int, db: Session = Depends(get_db)):
    """Para clonar una factura: el front lo usa como plantilla."""
    return _get(db, fid).payload


@router.get("/{fid}/xml")
def xml(fid: int, db: Session = Depends(get_db)):
    f = _get(db, fid)
    return Response(f.xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{f.uuid}.xml"'})


@router.get("/{fid}/pdf")
def pdf(fid: int, db: Session = Depends(get_db)):
    f = _get(db, fid)
    try:
        data = pdf_svc.pdf(f.xml, f.emisor)
    except RuntimeError:
        # Sin weasyprint/GTK (típico en Windows): HTML que se imprime solo a PDF
        return Response(pdf_svc.html(f.xml, imprimir=True, emisor=f.emisor), media_type="text/html")
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{f.uuid}.pdf"'})


@router.get("/{fid}/html")
def html(fid: int, db: Session = Depends(get_db)):
    f = _get(db, fid)
    return Response(pdf_svc.html(f.xml, emisor=f.emisor), media_type="text/html")


@router.post("/{fid}/cancelar", response_model=FacturaOut)
def cancelar(fid: int, data: CancelarIn, db: Session = Depends(get_db)):
    try:
        return _out(svc.cancelar(db, _get(db, fid), data.motivo, data.uuid_sustitucion))
    except ERRORES as e:
        raise HTTPException(422, str(e))


@router.get("/{fid}/estatus")
def estatus(fid: int, db: Session = Depends(get_db)):
    """Estatus ante el SAT (vigente/cancelado/cancelable)."""
    f = _get(db, fid)
    try:
        return svc.actualizar_estatus(db, f)
    except Exception as e:
        raise HTTPException(502, f"No se pudo consultar: {e}")


@router.post("/{fid}/enviar")
def enviar(fid: int, data: EnviarIn, db: Session = Depends(get_db)):
    f = _get(db, fid)
    para = data.para or (f.cliente.emails if f.cliente else [])
    if not para:
        raise HTTPException(422, "¿A quién se lo mando? El cliente no tiene correos.")
    try:
        svc.enviar(f, para, data.mensaje)
    except Exception as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "para": para}
