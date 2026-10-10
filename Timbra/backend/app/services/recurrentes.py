"""Facturas recurrentes: una plantilla con día del mes. El programador las revisa solo.

- auto_timbrar=True: se timbra sola ese día. Si falla, se apaga el automático y queda en "Por timbrar"
  (nunca reintenta en bucle contra el PAC).
- auto_timbrar=False: aparece en el dashboard como "Por timbrar hoy" y se timbra con un clic.
En las descripciones puedes usar {mes}, {MES}, {año}, {mes_anterior}: "Honorarios contables {mes} {año}".
"""
import calendar
from datetime import datetime

from sqlalchemy.orm import Session

from ..logs import log
from ..models import Plantilla
from ..schemas import FacturaIn
from .cfdi import ahora_mx

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def fecha_en_mes(anio: int, mes: int, dia: int) -> datetime:
    return datetime(anio, mes, min(max(dia, 1), calendar.monthrange(anio, mes)[1]))


def siguiente(dia: int, despues_de: datetime) -> datetime:
    """Próxima fecha con ese día del mes estrictamente después del periodo de `despues_de`."""
    anio, mes = (despues_de.year + 1, 1) if despues_de.month == 12 else (despues_de.year, despues_de.month + 1)
    return fecha_en_mes(anio, mes, dia)


def primera(dia: int, hoy: datetime) -> datetime:
    f = fecha_en_mes(hoy.year, hoy.month, dia)
    return f if f.date() >= hoy.date() else siguiente(dia, hoy)


def _texto(s: str, f: datetime) -> str:
    ant = MESES[(f.month - 2) % 12]
    return (s.replace("{mes}", MESES[f.month - 1]).replace("{MES}", MESES[f.month - 1].upper())
             .replace("{año}", str(f.year)).replace("{mes_anterior}", ant))


def payload(p: Plantilla, fecha: datetime) -> FacturaIn:
    data = dict(p.payload)
    data["emisor_id"] = p.emisor_id
    if p.cliente_id:
        data["cliente_id"] = p.cliente_id
    data["enviar_email"] = p.enviar_email
    data["conceptos"] = [{**c, "descripcion": _texto(c.get("descripcion", ""), fecha)} for c in data.get("conceptos", [])]
    data.pop("informacion_global", None)  # público en general: se recalcula con el mes actual
    return FacturaIn.model_validate(data)


def pendientes(db: Session, emisor_id: int | None = None, hoy: datetime | None = None) -> list[Plantilla]:
    hoy = hoy or ahora_mx()
    q = db.query(Plantilla).filter(Plantilla.recurrente.is_(True), Plantilla.proxima.isnot(None),
                                   Plantilla.proxima <= hoy)
    if emisor_id:
        q = q.filter(Plantilla.emisor_id == emisor_id)
    return q.order_by(Plantilla.proxima).all()


def ejecutar(db: Session, p: Plantilla, hoy: datetime | None = None):
    """Timbra una recurrente. La plantilla avanza en la MISMA transacción que la factura: no hay duplicados."""
    from . import facturacion

    hoy = hoy or ahora_mx()
    data = payload(p, hoy)
    p.proxima = siguiente(p.dia, hoy)
    p.ultimo_error = None
    p.usos += 1
    try:
        f = facturacion.emitir(db, data)  # su commit guarda también la plantilla avanzada
    except Exception as e:
        db.rollback()
        p = db.get(Plantilla, p.id)
        p.ultimo_error = str(e)
        if p.auto_timbrar:
            p.auto_timbrar = False
            p.ultimo_error += " (se apagó el timbrado automático; revísala y timbra a mano)"
        db.commit()
        log.warning("Recurrente «%s» no se timbró: %s", p.nombre, e)
        raise
    p.ultima_factura_id = f.id
    db.commit()
    log.info("Recurrente «%s» timbrada: %s%s", p.nombre, f.serie, f.folio)
    return f


def correr_automaticas(db: Session) -> int:
    n = 0
    for p in pendientes(db):
        if p.auto_timbrar:
            try:
                ejecutar(db, p)
                n += 1
            except Exception:
                pass
    return n
