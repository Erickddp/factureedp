"""Cobranza: facturas PPD con saldo, vencimiento por días de crédito del cliente, estado de cuenta y recordatorios."""
import html as _html
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..logs import log, paso
from ..models import Cliente, Emisor, Factura
from . import mailer
from . import pdf as pdf_svc
from .cfdi import ahora_mx

RANGOS = [("corriente", None, 0), ("1-30", 1, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("+90", 91, None)]


def _rango(dias: int) -> str:
    for nombre, a, b in RANGOS:
        if (a is None or dias >= a) and (b is None or dias <= b):
            return nombre
    return "+90"


def pendientes(db: Session, emisor_id: int, cliente_id: int | None = None, hoy: datetime | None = None) -> list[dict]:
    hoy = hoy or ahora_mx()
    q = (db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.tipo == "I", Factura.estado == "timbrada",
                                  Factura.saldo > 0))
    if cliente_id:
        q = q.filter(Factura.cliente_id == cliente_id)
    out = []
    for f in q.order_by(Factura.fecha):
        cred = f.cliente.dias_credito if f.cliente else 0
        vence = (f.fecha or f.creado) + timedelta(days=cred or 0)
        dias = (hoy.date() - vence.date()).days
        out.append({"factura_id": f.id, "folio": f"{f.serie or ''}{f.folio or ''}", "uuid": f.uuid,
                    "cliente_id": f.cliente_id, "cliente": f.cliente.nombre if f.cliente else "—",
                    "rfc": f.cliente.rfc if f.cliente else "", "fecha": f.fecha, "vence": vence,
                    "dias_vencido": max(dias, 0), "rango": _rango(dias), "total": f.total, "saldo": f.saldo,
                    "moneda": f.moneda})
    return out


def antiguedad(db: Session, emisor_id: int) -> dict:
    filas = pendientes(db, emisor_id)
    clientes: dict[int | None, dict] = {}
    totales = {r[0]: Decimal(0) for r in RANGOS}
    for f in filas:
        c = clientes.setdefault(f["cliente_id"], {"cliente_id": f["cliente_id"], "cliente": f["cliente"], "rfc": f["rfc"],
                                                  "saldo": Decimal(0), "vencido": Decimal(0), "facturas": 0,
                                                  "max_dias": 0, **{r[0]: Decimal(0) for r in RANGOS}})
        c[f["rango"]] += f["saldo"]
        c["saldo"] += f["saldo"]
        c["facturas"] += 1
        c["max_dias"] = max(c["max_dias"], f["dias_vencido"])
        if f["rango"] != "corriente":
            c["vencido"] += f["saldo"]
        totales[f["rango"]] += f["saldo"]
    for cid, c in clientes.items():
        cli = db.get(Cliente, cid) if cid else None
        c["emails"] = cli.emails if cli else []
        c["ultimo_recordatorio"] = cli.ultimo_recordatorio if cli else None
    lista = sorted(clientes.values(), key=lambda c: (-c["vencido"], -c["saldo"]))
    return {"clientes": lista, "totales": totales, "total": sum(totales.values(), Decimal(0))}


def estado_cuenta(db: Session, cliente: Cliente, desde: datetime | None = None) -> dict:
    """Movimientos del cliente: facturas (cargo), notas de crédito y pagos (abono)."""
    q = db.query(Factura).filter(Factura.cliente_id == cliente.id, Factura.estado == "timbrada",
                                 Factura.tipo.in_(("I", "E", "P")))
    if desde:
        q = q.filter(Factura.fecha >= desde)
    movs, saldo = [], Decimal(0)
    for f in q.order_by(Factura.fecha, Factura.id):
        cargo = f.total if f.tipo == "I" and f.metodo_pago == "PPD" else Decimal(0)
        abono = f.total if f.tipo == "P" else Decimal(0)
        if f.tipo == "E":
            abono = f.total
        if not cargo and not abono:
            continue  # PUE: se cobró al facturar
        saldo += cargo - abono
        movs.append({"fecha": f.fecha, "folio": f"{f.serie or ''}{f.folio or ''}", "tipo": f.tipo, "uuid": f.uuid,
                     "cargo": cargo, "abono": abono, "saldo": saldo})
    return {"cliente": {"id": cliente.id, "nombre": cliente.nombre, "rfc": cliente.rfc,
                        "dias_credito": cliente.dias_credito},
            "movimientos": movs, "saldo": sum((p["saldo"] for p in pendientes(db, cliente.emisor_id, cliente.id)),
                                              Decimal(0)),
            "pendientes": pendientes(db, cliente.emisor_id, cliente.id)}


def _m(x) -> str:
    return f"${Decimal(x):,.2f}"


def html_estado(emisor: Emisor, ec: dict) -> str:
    color = emisor.color or "#111111"
    filas = "".join(
        f"<tr><td>{p['folio']}</td><td>{p['fecha']:%d/%m/%Y}</td><td>{p['vence']:%d/%m/%Y}</td>"
        f"<td class=r>{p['dias_vencido'] or ''}</td><td class=r>{_m(p['total'])}</td><td class=r><b>{_m(p['saldo'])}</b></td></tr>"
        for p in ec["pendientes"])
    c = ec["cliente"]
    return f"""<!doctype html><html lang="es-MX"><meta charset="utf-8"><title>Estado de cuenta {_html.escape(c['nombre'])}</title>
<style>body{{font:14px/1.5 -apple-system,Segoe UI,Arial,sans-serif;color:#111;max-width:760px;margin:32px auto;padding:0 16px}}
h1{{font-size:20px;margin:0}}.l{{border-bottom:3px solid {color};padding-bottom:12px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:6px 8px;border-bottom:1px solid #e5e5e5;text-align:left}}
th{{font-size:12px;color:#555;text-transform:uppercase;letter-spacing:.04em}}.r{{text-align:right}}
.t{{font-size:18px;text-align:right;margin-top:12px}}</style>
<div class="l"><h1>{_html.escape(emisor.nombre)}</h1><small>RFC {emisor.rfc}</small></div>
<p>Estado de cuenta de <b>{_html.escape(c['nombre'])}</b> ({c['rfc']}) al {ahora_mx():%d/%m/%Y}.</p>
<table><tr><th>Folio</th><th>Fecha</th><th>Vence</th><th class=r>Días vencido</th><th class=r>Total</th><th class=r>Saldo</th></tr>
{filas or '<tr><td colspan=6>Sin saldos pendientes. ¡Gracias!</td></tr>'}</table>
<p class="t">Saldo pendiente: <b>{_m(ec['saldo'])}</b></p></html>"""


def recordar(db: Session, emisor: Emisor, cliente: Cliente, mensaje: str | None = None) -> dict:
    ec = estado_cuenta(db, cliente)
    if not ec["pendientes"]:
        return {"cliente_id": cliente.id, "ok": False, "error": "No tiene saldo pendiente."}
    if not cliente.emails:
        return {"cliente_id": cliente.id, "ok": False, "error": "El cliente no tiene correo."}
    vencidas = [p for p in ec["pendientes"] if p["dias_vencido"] > 0]
    lineas = "\n".join(f"  • {p['folio']}  {_m(p['saldo'])}  (vence {p['vence']:%d/%m/%Y})" for p in ec["pendientes"])
    cuerpo = mensaje or (
        f"Hola,\n\nTe compartimos tu estado de cuenta con {emisor.nombre}. "
        f"{'Tienes ' + str(len(vencidas)) + ' factura(s) vencida(s). ' if vencidas else ''}"
        f"Saldo pendiente: {_m(ec['saldo'])}\n\n{lineas}\n\nSi ya pagaste, ignora este mensaje y mándanos tu "
        f"comprobante para emitir el complemento de pago.\n\nSaludos,\n{emisor.nombre}")
    h = html_estado(emisor, ec)
    try:  # PDF, que lo abre cualquiera en el celular; si no hay cómo generarlo, el HTML de siempre
        adj = [(f"estado_cuenta_{cliente.rfc}.pdf", pdf_svc.html_a_pdf(h), "application/pdf")]
    except RuntimeError:
        adj = [(f"estado_cuenta_{cliente.rfc}.html", h.encode(), "text/html")]
    for p in ec["pendientes"]:
        f = db.get(Factura, p["factura_id"])
        adj.append((f"{p['folio']}_{f.uuid}.xml", f.xml, "application/xml"))
    with paso(f"Recordatorio de cobranza a {cliente.nombre}", saldo=str(ec["saldo"])):
        mailer.enviar(mailer.destinatarios(emisor, cliente.emails), f"Estado de cuenta · {emisor.nombre}", cuerpo, adj,
                      nombre=emisor.nombre, responder_a=emisor.email)
    cliente.ultimo_recordatorio = datetime.now()
    db.commit()
    return {"cliente_id": cliente.id, "ok": True, "saldo": str(ec["saldo"])}


def recordatorios_automaticos(db: Session) -> int:
    """Lunes: un recordatorio por cliente con facturas vencidas (máximo uno por semana)."""
    hoy = ahora_mx()
    if hoy.weekday() != 0:
        return 0
    n = 0
    for e in db.query(Emisor).filter(Emisor.cobranza_auto.is_(True)):
        for c in antiguedad(db, e.id)["clientes"]:
            cli = db.get(Cliente, c["cliente_id"]) if c["cliente_id"] else None
            if not cli or c["vencido"] <= 0 or not cli.emails:
                continue
            if cli.ultimo_recordatorio and (datetime.now() - cli.ultimo_recordatorio).days < 6:
                continue
            try:
                if recordar(db, e, cli)["ok"]:
                    n += 1
            except Exception as ex:
                log.warning("Recordatorio a %s falló: %s", cli.nombre, ex)
    return n
