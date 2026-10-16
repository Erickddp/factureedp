"""Compra de timbres con Mercado Pago (Checkout Pro).

1. La cuenta elige un paquete → se crea la «preferencia» en Mercado Pago y se manda a la persona a su página de pago.
2. Mercado Pago avisa al webhook (y la persona regresa a /timbres con el número de pago).
3. En los dos casos Timbra CONSULTA el pago en la API de Mercado Pago con su llave: nunca cree lo que diga el aviso.
   Si está aprobado, por el monto y la moneda del paquete, abona los timbres UNA sola vez (mp_pago es único).

Variables: MP_ACCESS_TOKEN (la de producción o la TEST- de pruebas), MP_WEBHOOK_SECRET (opcional: firma de los avisos)
y PAQUETES_TIMBRES (opcional: JSON para cambiar precios sin tocar código).
"""
import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal

import requests
from sqlalchemy.orm import Session

from ..config import settings
from ..logs import log
from ..models import Pago, Usuario
from . import timbres

API = "https://api.mercadopago.com"
# Precios con IVA incluido. Costo de Finkok: $150 + IVA al mes hasta 500 timbres, $0.30 + IVA cada uno después.
PAQUETES = [
    {"clave": "p30", "timbres": 30, "precio": 50},
    {"clave": "p100", "timbres": 100, "precio": 130},
    {"clave": "p300", "timbres": 300, "precio": 330},
    {"clave": "p1000", "timbres": 1000, "precio": 900},
]


class PagoError(Exception):
    pass


def activo() -> bool:
    return bool(settings.mp_access_token)


def paquetes() -> list[dict]:
    if settings.paquetes_timbres:
        try:
            lista = json.loads(settings.paquetes_timbres)
            return [{"clave": str(p["clave"]), "timbres": int(p["timbres"]), "precio": Decimal(str(p["precio"]))} for p in lista]
        except (ValueError, KeyError, TypeError):
            log.error("PAQUETES_TIMBRES no es un JSON válido: se usan los de siempre")
    return [{**p, "precio": Decimal(str(p["precio"]))} for p in PAQUETES]


def _paquete(clave: str) -> dict:
    p = next((p for p in paquetes() if p["clave"] == clave), None)
    if p is None:
        raise PagoError("Ese paquete no existe.")
    return p


def _mp(metodo: str, ruta: str, **kw) -> dict:
    try:
        r = requests.request(metodo, API + ruta, headers={"Authorization": f"Bearer {settings.mp_access_token}"}, timeout=25, **kw)
    except requests.RequestException as e:
        raise PagoError(f"No pude conectar con Mercado Pago: {e}") from e
    if r.status_code >= 300:
        try:
            msg = r.json().get("message") or r.text
        except ValueError:
            msg = r.text
        raise PagoError(f"Mercado Pago respondió {r.status_code}: {str(msg)[:200]}")
    return r.json()


def crear(db: Session, usuario: Usuario, clave: str, base_url: str) -> dict:
    """Crea el pago pendiente y la preferencia de Mercado Pago. Devuelve a dónde mandar a la persona."""
    if not activo():
        raise PagoError("El pago en línea todavía no está activado. Pide tu recarga al administrador.")
    if usuario.admin:
        raise PagoError("La cuenta de administrador no lleva saldo de timbres.")
    p = _paquete(clave)
    pago = Pago(usuario_id=usuario.id, paquete=p["clave"], timbres=p["timbres"], monto=p["precio"])
    db.add(pago)
    db.flush()
    base = base_url.rstrip("/")
    cuerpo = {
        "items": [{"id": p["clave"], "title": f"{p['timbres']} timbres de Timbra", "quantity": 1, "currency_id": "MXN",
                   "unit_price": float(p["precio"])}],
        "external_reference": str(pago.id),
        "payer": {"email": usuario.email},
        "back_urls": {k: f"{base}/timbres?pago={pago.id}" for k in ("success", "failure", "pending")},
        "auto_return": "approved",
        "statement_descriptor": "TIMBRA",
    }
    if base.startswith("https://"):  # Mercado Pago no acepta avisos a localhost; en tu PC se confirma al regresar
        cuerpo["notification_url"] = f"{base}/api/pagos/aviso"
    pref = _mp("post", "/checkout/preferences", json=cuerpo)
    pago.preferencia = str(pref.get("id") or "")[:80]
    db.commit()
    log.info("Pago %s: %s timbres por $%s para la cuenta %s", pago.id, p["timbres"], p["precio"], usuario.id)
    return {"pago_id": pago.id, "url": pref.get("init_point") or pref.get("sandbox_init_point")}


def firma_valida(cabecera: str | None, request_id: str | None, data_id: str) -> bool:
    """Firma de los avisos de Mercado Pago (x-signature: ts=…,v1=…). Sin secreto configurado no se exige: de todas formas
    el pago se consulta en la API antes de abonar nada."""
    if not settings.mp_webhook_secret:
        return True
    partes = dict(p.strip().split("=", 1) for p in (cabecera or "").split(",") if "=" in p)
    if not partes.get("ts") or not partes.get("v1"):
        return False
    manifiesto = f"id:{data_id.lower()};request-id:{request_id or ''};ts:{partes['ts']};"
    esperado = hmac.new(settings.mp_webhook_secret.encode(), manifiesto.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, partes["v1"])


def procesar(db: Session, mp_pago_id: str) -> Pago | None:
    """Consulta el pago en Mercado Pago y, si está aprobado, abona los timbres (una sola vez). Idempotente."""
    if not activo() or not str(mp_pago_id).isdigit():
        return None
    datos = _mp("get", f"/v1/payments/{mp_pago_id}")
    ref = str(datos.get("external_reference") or "")
    pago = db.get(Pago, int(ref)) if ref.isdigit() else None
    if pago is None:
        log.warning("Aviso de Mercado Pago %s sin pago de Timbra (referencia %r)", mp_pago_id, ref)
        return None
    if pago.estado == "aprobado":
        return pago  # ya se abonó
    estado = datos.get("status")
    monto_ok = Decimal(str(datos.get("transaction_amount") or 0)) >= Decimal(pago.monto) and datos.get("currency_id") == "MXN"
    if estado == "approved" and monto_ok:
        otro = db.query(Pago).filter(Pago.mp_pago == str(mp_pago_id), Pago.id != pago.id).first()
        if otro:
            log.error("El pago de Mercado Pago %s ya se usó en el pago %s", mp_pago_id, otro.id)
            return pago
        # El aviso y el regreso de la persona pueden llegar a la vez: sólo UNO logra pasar el pago a aprobado
        from sqlalchemy import update
        hecho = db.execute(update(Pago).where(Pago.id == pago.id, Pago.estado != "aprobado").values(
            estado="aprobado", mp_pago=str(mp_pago_id), acreditado=datetime.now(), detalle=None)).rowcount
        if hecho != 1:
            db.rollback()
            return db.get(Pago, pago.id)
        timbres.recargar(db, pago.usuario_id, pago.timbres, f"Compra en línea ${pago.monto:,.2f} (Mercado Pago {mp_pago_id})", None,
                         pago_id=pago.id)
        log.warning("PAGO APROBADO: pago %s, cuenta %s, %s timbres, $%s", pago.id, pago.usuario_id, pago.timbres, pago.monto)
        db.refresh(pago)
    elif estado == "approved":
        pago.detalle = f"Monto o moneda no coinciden ({datos.get('transaction_amount')} {datos.get('currency_id')})"
        log.error("Pago %s aprobado con monto distinto: %s", pago.id, pago.detalle)
        db.commit()
    elif estado in ("rejected", "cancelled", "refunded", "charged_back"):
        pago.estado = {"rejected": "rechazado"}.get(estado, "cancelado")
        pago.detalle = str(datos.get("status_detail") or "")[:200]
        db.commit()
    else:  # pending / in_process: se queda pendiente, llegará otro aviso
        pago.detalle = str(datos.get("status_detail") or estado or "")[:200]
        db.commit()
    return pago


def publico(p: Pago) -> dict:
    return {"id": p.id, "paquete": p.paquete, "timbres": p.timbres, "monto": p.monto, "estado": p.estado, "creado": p.creado,
            "acreditado": p.acreditado, "detalle": p.detalle}
