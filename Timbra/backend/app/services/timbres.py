"""Control de timbres: cuántos llevas, cuántos te quedan y cuándo avisar.

Cada CFDI con UUID cuenta un timbre (también los cancelados: el PAC ya lo cobró).
- Prepago (SW, paquetes): contratados - usados desde `timbres_desde`. SW además se consulta en vivo por API.
- Pospago (Finkok OnDemand): no hay saldo; se muestra el consumo del mes contra el mínimo de 500.
"""
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..logs import log
from ..models import Emisor, Factura, Pac
from .cfdi import ahora_mx

MINIMO_FINKOK = 500


def _usados(db: Session, pac_id: int, desde: datetime | None) -> int:
    q = (db.query(func.count(Factura.id)).join(Emisor, Factura.emisor_id == Emisor.id)
         .filter(Emisor.pac_id == pac_id, Factura.uuid.isnot(None)))
    if desde:
        q = q.filter(Factura.fecha_timbrado >= desde)
    return q.scalar() or 0


def saldo_sw(pac: Pac) -> dict | None:
    """API Balance V2 de SW: GET /management/v2/api/users/balance."""
    from .pac import get_pac

    obj = get_pac(pac)
    r = obj._request("/management/v2/api/users/balance", method="get", service="api")
    d = (r or {}).get("data") or {}
    return {"saldo": d.get("stampsBalance"), "usados": d.get("stampsUsed"), "asignados": d.get("stampsAssigned"),
            "ilimitado": d.get("isUnlimited"), "vence": d.get("expirationDate")}


SIN_TIMBRES = "sin_timbres_desde"  # en Pac.extra: cuándo el PAC contestó que ya no hay timbres (Finkok 718)


def marcar_sin_timbres(pac_id: int | None, sin: bool) -> None:
    """El PAC dijo que no hay timbres (sin=True) o volvió a timbrar bien (sin=False). Se guarda en su propia sesión:
    quien llama puede deshacer su transacción (regresa el folio) y la marca no debe perderse."""
    if not pac_id:
        return
    from ..db import SessionLocal
    from .cfdi import ahora_mx
    with SessionLocal() as s:
        p = s.get(Pac, pac_id)
        if p is None or bool((p.extra or {}).get(SIN_TIMBRES)) == sin:
            return  # nada que cambiar: no se escribe en cada timbrado
        extra = {k: v for k, v in (p.extra or {}).items() if k != SIN_TIMBRES}
        if sin:
            extra[SIN_TIMBRES] = ahora_mx().replace(tzinfo=None).isoformat(timespec="minutes")
        p.extra = extra
        s.commit()


def resumen(db: Session, en_vivo: bool = False) -> list[dict]:
    hoy = ahora_mx()
    ini_mes = datetime(hoy.year, hoy.month, 1)
    out = []
    uid, admin = db.info.get("uid_real"), db.info.get("es_admin")
    for p in db.query(Pac).order_by(Pac.nombre):
        if p.proveedor == "demo":
            continue
        if uid is not None and not (p.usuario_id == uid or (p.usuario_id is None and admin)):
            continue  # el PAC de la plataforma no es de esta cuenta: ella ve su saldo de timbres, no el paquete del PAC
        r = {"pac_id": p.id, "nombre": p.nombre, "proveedor": p.proveedor, "pruebas": p.pruebas,
             "usados_mes": _usados(db, p.id, ini_mes), "contratados": p.timbres_contratados,
             "desde": p.timbres_desde, "alerta": p.timbres_alerta, "restantes": None, "nivel": "ok", "texto": None, "nota": None}
        agotado = (p.extra or {}).get(SIN_TIMBRES)
        if agotado:  # lo que dijo el PAC manda sobre cualquier conteo de Timbra, hasta que vuelva a timbrar bien
            r["nivel"], r["restantes"] = "error", 0
            r["texto"] = (f"{p.nombre}: el PAC respondió que ya no hay timbres disponibles ({agotado.replace('T', ' ')}). "
                          + ("En la cuenta gratuita de pruebas se renuevan el siguiente mes." if p.pruebas
                             else "Compra timbres en tu PAC; el aviso se quita solo con el siguiente timbrado."))
        if p.pruebas:
            # En pruebas no hay paquete que contar: la cuenta gratuita del PAC tiene su propio tope, que Timbra no ve.
            # Mostrar «restantes» de un paquete capturado a mano engañaba (decía 876 mientras Finkok contestaba 718).
            r["nota"] = ("Ambiente de pruebas: no se cobran ni tienen validez. La cuenta gratuita del PAC tiene su propio "
                         "tope; si contesta «718 timbres agotados», se acabaron las pruebas de este mes.")
            out.append(r)
            continue
        if p.timbres_contratados is not None:
            r["usados_paquete"] = _usados(db, p.id, p.timbres_desde)
            r["restantes"] = p.timbres_contratados - r["usados_paquete"]
        if en_vivo and p.proveedor == "swsapien" and not p.pruebas:
            try:
                r["pac"] = saldo_sw(p)
                if r["pac"] and r["pac"]["saldo"] is not None and not r["pac"]["ilimitado"]:
                    r["restantes"] = int(r["pac"]["saldo"])
            except Exception as e:  # el saldo en vivo es informativo: nunca tumba el dashboard
                log.warning("No se pudo consultar el saldo de SW: %s", e)
                r["pac_error"] = str(e)
        if r["restantes"] is not None:
            if r["restantes"] <= 0:
                r["nivel"], r["texto"] = "error", f"{p.nombre}: sin timbres. Compra un paquete antes de facturar."
            elif r["restantes"] <= p.timbres_alerta:
                r["nivel"], r["texto"] = "aviso", f"{p.nombre}: quedan {r['restantes']} timbres."
        elif p.proveedor == "finkok" and not p.pruebas and r["usados_mes"] < MINIMO_FINKOK:
            r["texto"] = (f"{p.nombre}: {r['usados_mes']} timbres este mes. Hasta {MINIMO_FINKOK} pagas la cuota "
                          f"mínima de Finkok.")
        out.append(r)
    return out


def _cuenta_que_paga(db: Session, emisor):
    """La cuenta a la que se le descuentan los timbres: la dueña del emisor, si timbra con el PAC de la plataforma en
    producción y no es administradora. None = no se descuenta (PAC propio, pruebas, demo o administrador)."""
    from ..models import Usuario
    pac = emisor.pac
    if pac is None or not pac.plataforma or pac.pruebas or pac.proveedor == "demo" or emisor.usuario_id is None:
        return None
    u = db.get(Usuario, emisor.usuario_id)
    return None if u is None or u.admin else u


def sin_saldo(db: Session, emisor) -> str | None:
    u = _cuenta_que_paga(db, emisor)
    if u is not None and not u.correo_verificado:
        return (f"Confirma tu correo ({u.email}) para empezar a timbrar: te mandamos un mensaje con un enlace. "
                "Al confirmarlo recibes tus timbres de regalo.")
    if u is not None and u.timbres <= 0:
        return "Se acabaron los timbres de tu cuenta. Recarga para seguir facturando (Timbres, en el menú)."
    return None


VIGENCIA_MESES = 12  # cada recarga vence a los 12 meses


def _gastar_de_lotes(db: Session, usuario_id: int, n: int) -> None:
    """Descuenta `n` de los lotes vigentes, primero el que vence antes. Lo que no alcance sale de los timbres sin
    vencimiento (los de regalo o de antes de que hubiera lotes)."""
    from sqlalchemy import select, update

    from ..models import MovimientoTimbres as M
    for _ in range(n):
        lote = db.execute(select(M.id).where(M.usuario_id == usuario_id, M.restantes > 0).order_by(M.vence, M.id).limit(1)).scalar()
        if lote is None:
            return
        db.execute(update(M).where(M.id == lote, M.restantes > 0).values(restantes=M.restantes - 1))


def consumir(db: Session, emisor) -> None:
    """Un timbre menos para la cuenta dueña del emisor. Se llama justo después de que el PAC timbró."""
    from sqlalchemy import update

    from ..models import Usuario
    u = _cuenta_que_paga(db, emisor)
    if u is not None:
        db.execute(update(Usuario).where(Usuario.id == u.id).values(timbres=Usuario.timbres - 1))
        _gastar_de_lotes(db, u.id, 1)


def recargar(db: Session, usuario_id: int, cantidad: int, motivo: str | None, admin_id: int | None,
             pago_id: int | None = None, vence: bool = True) -> int:
    """Abona (o corrige, si es negativo). Lo abonado es un lote que vence en VIGENCIA_MESES; una corrección negativa
    sale de los lotes como si fueran timbres usados."""
    from ..models import MovimientoTimbres, Usuario
    from .cfdi import ahora_mx
    u = db.get(Usuario, usuario_id)
    antes = u.timbres or 0
    u.timbres = max(0, antes + cantidad)
    mov = MovimientoTimbres(usuario_id=u.id, cantidad=cantidad, saldo=u.timbres, motivo=(motivo or "").strip()[:200] or None,
                            admin_id=admin_id, pago_id=pago_id)
    if cantidad > 0 and vence:
        hoy = ahora_mx().replace(tzinfo=None)
        mov.vence = _mas_meses(hoy, VIGENCIA_MESES)
        mov.restantes = cantidad
    elif cantidad < 0:
        _gastar_de_lotes(db, u.id, min(-cantidad, antes))
    db.add(mov)
    db.commit()
    return u.timbres


def _mas_meses(d: datetime, meses: int) -> datetime:
    import calendar
    m = d.month - 1 + meses
    a, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=a, month=m, day=min(d.day, calendar.monthrange(a, m)[1]))


def vencer(db: Session) -> int:
    """Descuenta lo que quedó en los lotes ya vencidos (corre una vez al día). Devuelve cuántos timbres vencieron."""
    from sqlalchemy import update

    from ..models import MovimientoTimbres as M, Usuario
    from .cfdi import ahora_mx
    hoy = ahora_mx().replace(tzinfo=None)
    total = 0
    for lote in db.query(M).filter(M.restantes > 0, M.vence <= hoy).order_by(M.id).all():
        quedan = lote.restantes
        lote.restantes = 0
        u = db.get(Usuario, lote.usuario_id)
        quita = min(quedan, u.timbres or 0)
        db.execute(update(Usuario).where(Usuario.id == u.id).values(timbres=Usuario.timbres - quita))
        db.flush()
        db.refresh(u)
        db.add(M(usuario_id=u.id, cantidad=-quita, saldo=u.timbres, motivo=f"Vencieron (recarga del {lote.creado:%d/%m/%Y})"))
        total += quita
    db.commit()
    return total


def proximo_vencimiento(db: Session, usuario_id: int) -> dict | None:
    from ..models import MovimientoTimbres as M
    lote = db.query(M).filter(M.usuario_id == usuario_id, M.restantes > 0).order_by(M.vence, M.id).first()
    return {"fecha": lote.vence, "timbres": lote.restantes} if lote else None


def pac_plataforma(db: Session) -> Pac | None:
    """El PAC con el que timbran todas las cuentas (se consulta sin el filtro de cuenta: es de todos)."""
    from sqlalchemy import select
    pid = db.connection().execute(select(Pac.__table__.c.id).where(Pac.__table__.c.plataforma.is_(True)).limit(1)).scalar()
    return db.get(Pac, pid) if pid else None


def bloqueo(pac: Pac | None, db: Session) -> str | None:
    """Si el paquete local llegó a cero, avisa antes de timbrar (el PAC rechazaría igual, pero así no hay sorpresa)."""
    if pac is None or pac.timbres_contratados is None or pac.pruebas:
        return None
    if pac.timbres_contratados - _usados(db, pac.id, pac.timbres_desde) <= 0:
        return (f"Se acabaron los timbres del paquete de {pac.nombre}. Registra la compra nueva en "
                "PAC, addendas y usuarios → Timbres.")
    return None
