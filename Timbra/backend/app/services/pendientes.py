"""Bandeja de pendientes: TODO lo que requiere una acción tuya, en un solo lugar y con el botón para resolverlo.

Cada elemento: {id, titulo, detalle, nivel (error|aviso|info), accion: {texto, ruta}}. Los grupos agrupan por tema.
`total` cuenta errores y avisos (lo "informativo" no suma al globo del menú).
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Emisor, Factura, Lote, LoteFila, Plantilla
from . import clientes_io, timbres
from .cfdi import ahora_mx


def _pl(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


def _item(id_, titulo, detalle, nivel, texto, ruta) -> dict:
    return {"id": id_, "titulo": titulo, "detalle": detalle, "nivel": nivel, "accion": {"texto": texto, "ruta": ruta}}


def reunir(db: Session, emisor_id: int) -> dict:
    e = db.get(Emisor, emisor_id)
    hoy = ahora_mx()
    grupos: list[dict] = []

    def grupo(clave, titulo, items):
        if items:
            grupos.append({"clave": clave, "titulo": titulo, "items": items})

    # --- facturación en lote: filas por corregir (agrupadas por lote)
    filas = (db.query(LoteFila).filter(LoteFila.emisor_id == emisor_id, LoteFila.estado == "error")
             .order_by(LoteFila.lote_id, LoteFila.n).all())
    por_lote: dict[int, list[LoteFila]] = {}
    for f in filas:
        por_lote.setdefault(f.lote_id, []).append(f)
    items = []
    for lid, fs in por_lote.items():
        lote = db.get(Lote, lid)
        rechazadas = sum(1 for f in fs if f.etapa == "timbrado")
        muestra = "; ".join(f"{f.referencia or '#' + str(f.n)}: {(f.error or '')[:70]}" for f in fs[:3])
        items.append(_item(f"lote-{lid}", f"{_pl(len(fs), 'factura por corregir', 'facturas por corregir')} · {lote.nombre}",
                           muestra + ("…" if len(fs) > 3 else "") + (f" ({rechazadas} rechazadas por el PAC/SAT)" if rechazadas else "")
                           + " · sus folios siguen apartados.", "error", "Abrir el lote", f"/lotes?lote={lid}"))
    grupo("lotes", "Facturas en lote", items)

    # --- clientes con datos que el SAT rechazaría
    aud = clientes_io.auditar(db, emisor_id)
    errores = [a for a in aud if a["gravedad"] == "error"]
    avisos = [a for a in aud if a["gravedad"] == "aviso"]
    items = []
    if errores:
        items.append(_item("clientes-error", f"{_pl(len(errores), 'cliente con datos inválidos', 'clientes con datos inválidos')}",
                           "Si les facturas hoy, el SAT o el PAC rechazaría el CFDI: " + ", ".join(a["nombre"] for a in errores[:3])
                           + ("…" if len(errores) > 3 else ""), "error", "Revisar clientes", "/clientes?revisar=1"))
    if avisos:
        items.append(_item("clientes-aviso", f"{_pl(len(avisos), 'cliente con avisos', 'clientes con avisos')}",
                           "Nombre con régimen societario, dígito verificador, teléfono…", "aviso", "Revisar clientes", "/clientes?revisar=1"))
    dups = [g for g in clientes_io.duplicados(db, emisor_id) if g["fusionable"]]
    if dups:
        items.append(_item("clientes-dup", f"{_pl(len(dups), 'cliente repetido', 'clientes repetidos')} (mismo RFC)",
                           "Fusionarlos evita facturas y cobranza partidas entre dos registros.", "aviso", "Ver duplicados",
                           "/clientes?revisar=duplicados"))
    grupo("clientes", "Clientes", items)

    # --- facturas emitidas con algo pendiente
    items = []
    for f in db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.estado == "cancelacion_pendiente"):
        items.append(_item(f"canc-{f.id}", f"Cancelación en espera · {f.serie or ''}{f.folio or ''}",
                           "El receptor debe aceptarla o rechazarla. Consulta el estatus.", "aviso", "Ver facturas", "/facturas"))
    con_error = db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.estado == "timbrada",
                                         Factura.error.isnot(None)).order_by(Factura.id.desc()).limit(20).all()
    for f in con_error:
        items.append(_item(f"fac-{f.id}", f"{f.serie or ''}{f.folio or ''} timbrada con un detalle",
                           (f.error or "")[:140], "aviso", "Ver facturas", "/facturas"))
    grupo("facturas", "Facturas emitidas", items)

    # --- recurrentes
    items = []
    for p in db.query(Plantilla).filter(Plantilla.emisor_id == emisor_id, Plantilla.recurrente.is_(True)):
        if p.ultimo_error:
            items.append(_item(f"rec-err-{p.id}", f"La recurrente «{p.nombre}» falló", p.ultimo_error[:140], "error",
                               "Abrir recurrentes", "/recurrentes"))
        elif p.proxima and p.proxima <= hoy:
            items.append(_item(f"rec-{p.id}", f"Toca timbrar «{p.nombre}»", f"Era para el {p.proxima:%d/%m/%Y}.", "aviso",
                               "Timbrar", "/recurrentes"))
    grupo("recurrentes", "Recurrentes", items)

    # --- cobranza vencida
    from . import cobranza
    venc = [x for x in cobranza.pendientes(db, emisor_id) if x["dias_vencido"] > 0]
    if venc:
        total = sum(x["saldo"] for x in venc)
        grupo("cobranza", "Cobranza", [_item("cobranza", f"{_pl(len(venc), 'factura vencida', 'facturas vencidas')} por ${total:,.2f}",
                                              "Manda un recordatorio con el estado de cuenta.", "aviso", "Ir a cobranza", "/cobranza")])

    # --- sistema: CSD, e.firma, timbres
    items = []
    from ..routers.dashboard import solo_xml
    if not e.cer and solo_xml(db, e.id):
        pass  # sólo se usa para XML del SAT: el CSD no le hace falta
    elif not e.cer:
        items.append(_item("csd-falta", f"{e.rfc} no tiene CSD", "Sin CSD no se puede sellar ni timbrar.", "error", "Subir CSD", "/emisores"))
    elif e.csd_vence and e.csd_vence < hoy.replace(tzinfo=None):
        items.append(_item("csd-vencido", f"El CSD de {e.rfc} venció el {e.csd_vence:%d/%m/%Y}", "Renuévalo en el SAT y súbelo.", "error",
                           "Subir CSD nuevo", "/emisores"))
    elif e.csd_vence and e.csd_vence < hoy.replace(tzinfo=None) + timedelta(days=30):
        items.append(_item("csd-vence", f"El CSD de {e.rfc} vence el {e.csd_vence:%d/%m/%Y}", "Tramita el nuevo con tiempo (tarda hasta 72 h).",
                           "aviso", "Ver emisor", "/emisores"))
    for t in timbres.resumen(db):
        if t["texto"] and t["nivel"] in ("aviso", "error"):
            items.append(_item(f"timbres-{t['pac_id']}", t["texto"], "Registra tu compra de timbres para que el aviso se actualice.",
                               t["nivel"], "Ver timbres", "/timbres"))
    grupo("sistema", "Sistema", items)

    n = sum(1 for g in grupos for i in g["items"] if i["nivel"] in ("error", "aviso"))
    errores_n = sum(1 for g in grupos for i in g["items"] if i["nivel"] == "error")
    return {"total": n, "errores": errores_n, "grupos": grupos, "generado": datetime.now()}
