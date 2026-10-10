from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Factura
from ..security import current_user
from ..services import cobranza, recurrentes, timbres
from ..services.cfdi import ahora_mx

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(current_user)])


@router.get("")
def resumen(emisor_id: int | None = None, db: Session = Depends(get_db)):
    hoy = ahora_mx()
    ini_mes = datetime(hoy.year, hoy.month, 1)
    base = db.query(Factura).filter(Factura.estado == "timbrada")
    if emisor_id:
        base = base.filter(Factura.emisor_id == emisor_id)
    mes = base.filter(Factura.fecha >= ini_mes)
    facturado = mes.filter(Factura.tipo == "I").with_entities(func.coalesce(func.sum(Factura.total), 0)).scalar()
    notas = mes.filter(Factura.tipo == "E").with_entities(func.coalesce(func.sum(Factura.total), 0)).scalar()
    cobrado = mes.filter(Factura.tipo == "P").with_entities(func.coalesce(func.sum(Factura.total), 0)).scalar()
    por_cobrar = base.filter(Factura.saldo > 0).with_entities(func.coalesce(func.sum(Factura.saldo), 0)).scalar()
    num = mes.count()

    alertas = []
    for e in db.query(Emisor).filter(Emisor.activo.is_(True)).all():
        if not e.cer:
            alertas.append({"nivel": "error", "texto": f"{e.rfc} no tiene CSD cargado"})
        elif e.csd_vence and (e.csd_vence - hoy).days < 30:
            dias = (e.csd_vence - hoy).days
            alertas.append({"nivel": "error" if dias < 0 else "aviso",
                            "texto": f"CSD de {e.rfc} {'venció' if dias < 0 else f'vence en {dias} días'}"})
        if e.pac is None or e.pac.proveedor == "demo":
            alertas.append({"nivel": "aviso", "texto": f"{e.rfc} está en modo demo (no timbra ante el SAT)"})
    for t in timbres.resumen(db):
        if t["texto"]:
            alertas.append({"nivel": t["nivel"] if t["nivel"] != "ok" else "info", "texto": t["texto"]})
    for e in db.query(Emisor).filter(Emisor.activo.is_(True), Emisor.fiel_vence.isnot(None)).all():
        if (e.fiel_vence - hoy).days < 30:
            alertas.append({"nivel": "aviso", "texto": f"e.firma de {e.rfc} vence el {e.fiel_vence:%d/%m/%Y}"})
    pend = db.query(Factura).filter(Factura.estado == "cancelacion_pendiente").count()
    if pend:
        alertas.append({"nivel": "aviso", "texto": f"{pend} cancelaciones esperando respuesta del receptor"})

    por_timbrar = [{"id": p.id, "nombre": p.nombre, "proxima": p.proxima, "auto": p.auto_timbrar,
                    "error": p.ultimo_error} for p in recurrentes.pendientes(db, emisor_id)]
    vencido = Decimal(0)
    if emisor_id:
        vencido = sum((f["saldo"] for f in cobranza.pendientes(db, emisor_id) if f["dias_vencido"] > 0), Decimal(0))
    return {
        "por_timbrar": por_timbrar,
        "vencido": vencido,
        "timbres": timbres.resumen(db),
        "facturado_mes": Decimal(facturado) - Decimal(notas),
        "cobrado_mes": Decimal(cobrado),
        "por_cobrar": Decimal(por_cobrar),
        "comprobantes_mes": num,
        "alertas": alertas,
    }
