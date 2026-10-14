from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Factura, Pac
from ..security import current_user
from ..services import cobranza, recurrentes, timbres
from ..services.cfdi import ahora_mx

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(current_user)])


def solo_xml(db: Session, emisor_id: int) -> bool:
    """Contribuyente que sólo se usa para bajar o leer XML (nunca ha facturado aquí): no hace falta pedirle CSD."""
    from ..models import XmlCfdi
    return (db.query(Factura.id).filter(Factura.emisor_id == emisor_id).first() is None
            and db.query(XmlCfdi.id).filter(XmlCfdi.emisor_id == emisor_id).first() is not None)


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

    # Las advertencias son del emisor que estás viendo: lo de otro RFC no tiene nada que hacer aquí
    alertas = []
    emisores = db.query(Emisor).filter(Emisor.activo.is_(True))
    if emisor_id:
        emisores = emisores.filter(Emisor.id == emisor_id)
    emisores = emisores.all()
    pacs_vistos = {e.pac_id for e in emisores}
    # ¿ya hay un PAC de producción a la mano? Entonces un emisor que sigue en el de pruebas es un descuido, no una decisión
    hay_productivo = db.query(Pac.id).filter(Pac.pruebas.is_(False), Pac.proveedor != "demo").first() is not None
    for e in emisores:
        if not e.cer:
            if solo_xml(db, e.id):
                continue  # contribuyente sólo para descargar XML: ni CSD ni PAC le hacen falta
            alertas.append({"nivel": "error", "texto": f"{e.rfc} no tiene CSD cargado"})
        elif e.csd_vence and (e.csd_vence - hoy).days < 30:
            dias = (e.csd_vence - hoy).days
            alertas.append({"nivel": "error" if dias < 0 else "aviso",
                            "texto": f"CSD de {e.rfc} {'venció' if dias < 0 else f'vence en {dias} días'}"})
        if e.pac is None or e.pac.proveedor == "demo":
            alertas.append({"nivel": "aviso", "texto": f"{e.rfc} está en modo demo (no timbra ante el SAT)"})
        elif e.pac.pruebas and hay_productivo:
            alertas.append({"nivel": "error", "texto": f"{e.rfc} sigue timbrando en ambiente de pruebas: sus facturas no valen ante el SAT. "
                                                       "Cámbiale el PAC en Emisores."})
    for t in timbres.resumen(db):
        if t["texto"] and (not emisor_id or t["pac_id"] in pacs_vistos):
            alertas.append({"nivel": t["nivel"] if t["nivel"] != "ok" else "info", "texto": t["texto"]})
    pend = db.query(Factura).filter(Factura.estado == "cancelacion_pendiente")
    if emisor_id:
        pend = pend.filter(Factura.emisor_id == emisor_id)
    pend = pend.count()
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
