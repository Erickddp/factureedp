"""Facturas recurrentes: una plantilla con día del mes. El programador las revisa solo.

- auto_timbrar=True: se timbra sola ese día (el programador revisa cada 10 minutos mientras Timbra está abierto; en el
  servidor web, siempre). Si falla, se apaga el automático y queda en "Por timbrar" (nunca reintenta en bucle contra el PAC).
  Si va atrasada más de MAX_ATRASO_AUTO días, no se timbra sola: espera a que la revises.
- auto_timbrar=False: aparece en el dashboard como "Por timbrar hoy" y se timbra con un clic.
En las descripciones puedes usar {mes}, {MES}, {año}, {mes_anterior}: "Honorarios contables {mes} {año}".
"""
import calendar
import threading
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


# Una automática sólo se timbra sola si va al día. Si Timbra estuvo cerrado y ya pasó este margen, espera tu visto bueno
# (así no salen de golpe varias facturas viejas sin que nadie las vea).
MAX_ATRASO_AUTO = 5  # días
_candado = threading.Lock()  # programador y clic manual nunca timbran la misma recurrente a la vez


class YaTimbrada(Exception):
    pass


def ejecutar(db: Session, p: Plantilla, hoy: datetime | None = None, solo_si_vence: bool = False):
    """Timbra una recurrente. La plantilla avanza en la MISMA transacción que la factura: no hay duplicados.

    El periodo es el PROGRAMADO (`p.proxima`), no el día en que corre: la iguala de septiembre que se timbra el 3 de
    octubre dice «septiembre» y la siguiente queda para octubre (antes se saltaba un mes y cambiaba el texto).
    """
    from . import facturacion

    hoy = hoy or ahora_mx()
    with _candado:
        db.refresh(p)  # por si la otra vía (programador o clic) la acaba de timbrar
        if solo_si_vence and (p.proxima is None or p.proxima > hoy or not p.auto_timbrar):
            raise YaTimbrada(p.nombre)
        periodo = p.proxima or hoy
        data = payload(p, periodo)
        p.proxima = siguiente(p.dia, periodo)
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
        log.info("Recurrente «%s» timbrada: %s%s (periodo %s)", p.nombre, f.serie, f.folio, periodo.strftime("%m/%Y"))
        return f


def correr_automaticas(db: Session, hoy: datetime | None = None) -> int:
    """Lo llama el programador cada 10 minutos. Devuelve cuántas timbró."""
    hoy = hoy or ahora_mx()
    n = 0
    for p in pendientes(db, hoy=hoy):
        if not p.auto_timbrar:
            continue
        atraso = (hoy.date() - p.proxima.date()).days
        if atraso > MAX_ATRASO_AUTO:
            aviso = f"Atrasada {atraso} días"
            if not (p.ultimo_error or "").startswith("Atrasada"):
                p.ultimo_error = (f"{aviso}: Timbra no estuvo abierto el día que tocaba. No se timbró sola para que la revises; "
                                  f"tímbrala a mano y el automático sigue el mes que viene.")
                db.commit()
                log.warning("Recurrente «%s» atrasada %s días: espera revisión", p.nombre, atraso)
            continue
        try:
            ejecutar(db, p, hoy, solo_si_vence=True)
            n += 1
        except YaTimbrada:
            pass
        except Exception:
            pass
    return n
