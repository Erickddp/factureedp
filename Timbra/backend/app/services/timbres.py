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


def resumen(db: Session, en_vivo: bool = False) -> list[dict]:
    hoy = ahora_mx()
    ini_mes = datetime(hoy.year, hoy.month, 1)
    out = []
    for p in db.query(Pac).order_by(Pac.nombre):
        if p.proveedor == "demo":
            continue
        r = {"pac_id": p.id, "nombre": p.nombre, "proveedor": p.proveedor, "pruebas": p.pruebas,
             "usados_mes": _usados(db, p.id, ini_mes), "contratados": p.timbres_contratados,
             "desde": p.timbres_desde, "alerta": p.timbres_alerta, "restantes": None, "nivel": "ok", "texto": None}
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
    if u is not None and u.timbres <= 0:
        return "Se acabaron los timbres de tu cuenta. Recarga para seguir facturando (Timbres, en el menú)."
    return None


def consumir(db: Session, emisor) -> None:
    """Un timbre menos para la cuenta dueña del emisor. Se llama justo después de que el PAC timbró."""
    from sqlalchemy import update

    from ..models import Usuario
    u = _cuenta_que_paga(db, emisor)
    if u is not None:
        db.execute(update(Usuario).where(Usuario.id == u.id).values(timbres=Usuario.timbres - 1))


def recargar(db: Session, usuario_id: int, cantidad: int, motivo: str | None, admin_id: int | None) -> int:
    from ..models import MovimientoTimbres, Usuario
    u = db.get(Usuario, usuario_id)
    u.timbres = max(0, (u.timbres or 0) + cantidad)
    db.add(MovimientoTimbres(usuario_id=u.id, cantidad=cantidad, saldo=u.timbres, motivo=(motivo or "").strip()[:200] or None, admin_id=admin_id))
    db.commit()
    return u.timbres


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
