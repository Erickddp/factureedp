"""Representación impresa del CFDI.

Facturas, notas de crédito y traslados usan la plantilla propia de Timbra (limpia, con la marca del emisor) y traen TODO lo
que pide la regla 2.7.1.7 de la RMF y el art. 29-A del CFF (ver `REQUISITOS`). Nómina y complementos de pago usan la
plantilla de satcfdi (sabe pintar esos complementos) con la misma marca.

PDF: weasyprint si está (necesita GTK); si no, Edge o Chrome sin ventana (vienen en todo Windows 10/11); si tampoco,
se entrega el HTML listo para imprimir (Ctrl+P → Guardar como PDF).
"""
import base64
import hashlib
import html as _html
import io
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

from satcfdi.cfdi import CFDI

from ..logs import log

_IMPRIMIR = "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),300))</script>"
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
TIPOS = {"I": "Factura", "E": "Nota de crédito", "P": "Complemento de pago", "T": "Traslado", "N": "Recibo de nómina"}
LEYENDA = "Este documento es una representación impresa de un CFDI versión {v}"

# Lo que debe verse en la representación impresa (regla 2.7.1.7 RMF + art. 29-A CFF). tests/test_v8_pdf.py lo vigila.
REQUISITOS = [
    "código QR", "folio fiscal (UUID)", "número de serie del CSD del emisor", "número de serie del certificado del SAT",
    "fecha y hora de emisión", "fecha y hora de certificación", "sello digital del emisor", "sello digital del SAT",
    "cadena original del complemento de certificación", "leyenda de representación impresa", "RFC y nombre del emisor",
    "régimen fiscal del emisor", "lugar de expedición (CP)", "RFC, nombre, CP y régimen del receptor", "uso del CFDI",
    "clave de producto, cantidad, unidad y descripción", "valor unitario e importe", "impuestos por tasa", "total y total con letra",
    "forma y método de pago", "moneda", "tipo de comprobante", "exportación", "RFC del PAC",
]


def _v(x):
    return getattr(x, "code", getattr(x, "value", x))


def _e(x) -> str:
    return _html.escape("" if x is None else str(x))


def _cd(x) -> str:
    """Clave de catálogo con su descripción: «03 · Transferencia electrónica de fondos»."""
    if x is None:
        return ""
    d = getattr(x, "description", None)
    return f"{_e(_v(x))} · {_e(d)}" if d else _e(_v(x))


def _lista(x) -> list:
    if x is None:
        return []
    if isinstance(x, dict) and x and all(isinstance(v, dict) for v in x.values()) and not any(k in x for k in ("Impuesto", "Importe", "Numero", "NumeroPedimento")):
        return list(x.values())
    return list(x) if isinstance(x, (list, tuple)) else [x]


def _dinero(v) -> str:
    return f"{Decimal(str(v or 0)):,.2f}"


def _num(v, minimo=0) -> str:
    """Cantidades y precios: sin ceros de más, pero con al menos `minimo` decimales."""
    d = Decimal(str(v or 0)).normalize()
    dec = max(minimo, -d.as_tuple().exponent if d.as_tuple().exponent < 0 else 0)
    return f"{d:,.{dec}f}"


def _tasa(i: dict, k="TasaOCuota") -> str:
    factor = _v(i.get("TipoFactor"))
    if factor == "Exento":
        return "Exento"
    t = i.get(k)
    if t is None:
        return ""
    if factor == "Cuota":
        return f"cuota ${_num(t, 2)}"
    return f"{_num(Decimal(str(t)) * 100)}%"


# ---------------------------------------------------------------- importe con letra
_U = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE",
      "QUINCE", "DIECISEIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE", "VEINTIUN", "VEINTIDOS", "VEINTITRES",
      "VEINTICUATRO", "VEINTICINCO", "VEINTISEIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE"]
_D = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_C = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]
MONEDAS = {"MXN": ("PESOS", "M.N."), "USD": ("DOLARES", "USD"), "EUR": ("EUROS", "EUR")}


def _cientos(n: int) -> str:
    if n == 100:
        return "CIEN"
    c, r = divmod(n, 100)
    p = [_C[c]] if c else []
    if r < 30:
        p.append(_U[r])
    else:
        d, u = divmod(r, 10)
        p.append(_D[d] + (f" Y {_U[u]}" if u else ""))
    return " ".join(x for x in p if x)


def _entero(n: int) -> str:
    if n == 0:
        return "CERO"
    mm, r = divmod(n, 1_000_000)
    m, c = divmod(r, 1000)
    p = []
    if mm:
        p.append("UN MILLON" if mm == 1 else f"{_entero(mm)} MILLONES")
    if m:
        p.append("MIL" if m == 1 else f"{_cientos(m)} MIL")
    if c:
        p.append(_cientos(c))
    return " ".join(p)


def con_letra(total, moneda: str = "MXN") -> str:
    """4348.00 → «CUATRO MIL TRESCIENTOS CUARENTA Y OCHO PESOS 00/100 M.N.»"""
    t = Decimal(str(total or 0)).quantize(Decimal("0.01"))
    ent, cent = int(t), int((t - int(t)) * 100)
    nombre, sufijo = MONEDAS.get(moneda, (moneda, ""))
    letras = _entero(ent)
    if letras.endswith("MILLON") or letras.endswith("MILLONES"):
        letras += " DE"
    if ent == 1:
        nombre = {"PESOS": "PESO", "DOLARES": "DOLAR", "EUROS": "EURO"}.get(nombre, nombre)
    return f"{letras} {nombre} {cent:02d}/100 {sufijo}".strip()


# ---------------------------------------------------------------- piezas
_DEMO = '<div class="demo">MODO DEMO · SIN VALIDEZ FISCAL · No está timbrado ante el SAT</div>'


def es_demo(xml) -> bool:
    """El PAC demo firma el timbre con SelloSAT="DEMO"."""
    if not xml:
        return False
    return (b'SelloSAT="DEMO"' if isinstance(xml, bytes) else 'SelloSAT="DEMO"') in xml


def _color(emisor) -> str:
    return emisor.color if emisor is not None and emisor.color and _COLOR.match(emisor.color) else "#111111"


def _logo(emisor) -> str:
    if emisor is None or not emisor.logo_b64:
        return ""
    src = emisor.logo_b64 if emisor.logo_b64.startswith("data:") else f"data:image/png;base64,{emisor.logo_b64}"
    return f'<img class="logo" src="{_html.escape(src, quote=True)}" alt="logo">'


def _qr(url: str) -> str:
    import qrcode
    q = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=0)
    q.add_data(url)
    q.make(fit=True)
    b = io.BytesIO()
    q.make_image(fill_color="black", back_color="white").save(b, format="PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def _tipo(cfdi) -> str:
    if (cfdi.get("Complemento") or {}).get("Nomina"):
        return TIPOS["N"]
    return TIPOS.get(_v(cfdi.get("TipoDeComprobante")), "CFDI")


def _css(color: str) -> str:
    return f"""
  @page {{ size: Letter; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 8.5pt; line-height: 1.38; color: #111;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .hoja {{ width: 100%; border-collapse: collapse; }}
  .hoja > thead td, .hoja > tfoot td {{ height: 12mm; padding: 0; }}
  .hoja > tbody > tr > td {{ padding: 0 13mm; vertical-align: top; }}
  .demo {{ background: #b42318; color: #fff; text-align: center; font-weight: 700; letter-spacing: .08em; padding: 5px 8px;
           margin-bottom: 10px; font-size: 8pt; }}
  .cab {{ display: flex; align-items: center; gap: 14px; padding-bottom: 12px; border-bottom: 2px solid {color}; }}
  .logo {{ max-height: 58px; max-width: 170px; object-fit: contain; }}
  .cab .quien {{ flex: 1; min-width: 0; }}
  .cab .quien b {{ display: block; font-size: 13pt; letter-spacing: -.01em; line-height: 1.2; }}
  .cab .doc {{ text-align: right; }}
  .cab .doc .t {{ font-size: 8pt; text-transform: uppercase; letter-spacing: .14em; color: #666; }}
  .cab .doc b {{ display: block; font-size: 17pt; color: {color}; letter-spacing: -.02em; line-height: 1.15; }}
  .gris {{ color: #666; }} .mono {{ font-family: Consolas, 'Courier New', monospace; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .et {{ display: block; font-size: 6.5pt; text-transform: uppercase; letter-spacing: .12em; color: #777; margin-bottom: 1px; }}
  .partes {{ display: flex; gap: 22px; margin-top: 12px; }}
  .partes > div {{ flex: 1; min-width: 0; }}
  .partes b.n {{ display: block; font-size: 10pt; line-height: 1.25; }}
  .datos {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px 16px; margin-top: 12px; padding: 9px 0;
            border-top: 1px solid #ddd; border-bottom: 1px solid #ddd; }}
  .datos .ancho {{ grid-column: span 2; }}
  .nota {{ margin-top: 8px; padding: 6px 9px; background: #f4f4f2; border-radius: 3px; }}
  table.con {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
  table.con th {{ font-size: 6.5pt; text-transform: uppercase; letter-spacing: .12em; color: #777; font-weight: 600; text-align: left;
                  padding: 0 6px 5px; border-bottom: 1.5px solid #111; }}
  table.con th.num {{ text-align: right; }}
  table.con td {{ padding: 7px 6px; border-bottom: 1px solid #e4e4e4; vertical-align: top; }}
  table.con tr {{ break-inside: avoid; page-break-inside: avoid; }}
  table.con .sub {{ display: block; font-size: 7pt; color: #666; margin-top: 2px; }}
  table.con th:first-child, table.con td:first-child {{ padding-left: 0; }}
  table.con th:last-child, table.con td:last-child {{ padding-right: 0; }}
  .cierre {{ display: flex; gap: 22px; margin-top: 10px; break-inside: avoid; page-break-inside: avoid; }}
  .cierre .letra {{ flex: 1; min-width: 0; }}
  .cierre table {{ border-collapse: collapse; min-width: 235px; }}
  .cierre td {{ padding: 2.5px 0 2.5px 18px; }} .cierre td:first-child {{ padding-left: 0; color: #555; }}
  .cierre tr.total td {{ font-size: 12pt; font-weight: 700; color: #111; padding-top: 7px; border-top: 1.5px solid #111; }}
  .cierre tr.sep td {{ padding-top: 6px; }}
  .timbre {{ display: flex; gap: 14px; margin-top: 16px; padding-top: 11px; border-top: 2px solid {color};
             break-inside: avoid; page-break-inside: avoid; }}
  .timbre img {{ width: 31mm; height: 31mm; flex: none; image-rendering: pixelated; }}
  .timbre .t {{ flex: 1; min-width: 0; }}
  .timbre .fila {{ display: grid; grid-template-columns: 2.3fr 1.25fr .85fr 1.35fr; gap: 6px 12px; margin-bottom: 7px; }}
  .sello {{ font-family: Consolas, 'Courier New', monospace; font-size: 5.6pt; line-height: 1.3; color: #333; word-break: break-all;
            margin-bottom: 4px; }}
  .pie {{ margin-top: 10px; text-align: center; font-size: 7pt; color: #666; letter-spacing: .02em; }}
"""


def _campo(et: str, valor: str, clase: str = "") -> str:
    return f'<div class="{clase}"><span class="et">{et}</span>{valor or "—"}</div>' if valor else ""


def _concepto(c: dict) -> str:
    sub = []
    if c.get("NoIdentificacion"):
        sub.append(f"No. identificación: {_e(c['NoIdentificacion'])}")
    imp = c.get("Impuestos") or {}
    partes = []
    for t in _lista(imp.get("Traslados")):
        txt = f"{_e(getattr(t.get('Impuesto'), 'description', None) or _v(t.get('Impuesto')))} {_tasa(t)}"
        partes.append(txt + (f" ${_dinero(t.get('Importe'))}" if t.get("Importe") is not None else "") + f" (base ${_dinero(t.get('Base'))})")
    for t in _lista(imp.get("Retenciones")):
        partes.append(f"Ret. {_e(getattr(t.get('Impuesto'), 'description', None) or _v(t.get('Impuesto')))} {_tasa(t)} −${_dinero(t.get('Importe'))}")
    sub.append(" · ".join([f"Objeto de impuesto: {_cd(c.get('ObjetoImp'))}"] + partes))
    tercero = c.get("ACuentaTerceros")
    if tercero:
        sub.append(f"A cuenta de terceros: {_e(tercero.get('NombreACuentaTerceros'))} · RFC {_e(tercero.get('RfcACuentaTerceros'))} · "
                   f"Régimen {_e(_v(tercero.get('RegimenFiscalACuentaTerceros')))} · CP {_e(tercero.get('DomicilioFiscalACuentaTerceros'))}")
    predial = [_e(p.get("Numero") if isinstance(p, dict) else p) for p in _lista(c.get("CuentaPredial"))]
    if predial:
        sub.append("Cuenta predial: " + ", ".join(predial))
    aduana = [_e(p.get("NumeroPedimento") if isinstance(p, dict) else p) for p in _lista(c.get("InformacionAduanera"))]
    if aduana:
        sub.append("Pedimento: " + ", ".join(aduana))
    clave, unidad = c.get("ClaveProdServ"), c.get("ClaveUnidad")
    return (f'<tr><td class="num">{_num(c.get("Cantidad"))}</td>'
            f'<td>{_e(_v(unidad))}<span class="sub">{_e(c.get("Unidad") or getattr(unidad, "description", "") or "")}</span></td>'
            f'<td class="mono">{_e(_v(clave))}</td>'
            f'<td><b>{_e(c.get("Descripcion"))}</b><span class="sub">{_e(getattr(clave, "description", "") or "")}</span>'
            + "".join(f'<span class="sub">{s}</span>' for s in sub) + "</td>"
            f'<td class="num">{_num(c.get("ValorUnitario"), 2)}</td>'
            f'<td class="num">{_dinero(c["Descuento"]) if c.get("Descuento") else ""}</td>'
            f'<td class="num">{_dinero(c.get("Importe"))}</td></tr>')


def _propia(cfdi, emisor, demo: bool) -> str:
    e, r = cfdi["Emisor"], cfdi["Receptor"]
    tfd = (cfdi.get("Complemento") or {}).get("TimbreFiscalDigital") or {}
    moneda = _v(cfdi.get("Moneda")) or "MXN"
    folio = f"{cfdi.get('Serie') or ''}{cfdi.get('Folio') or ''}"
    tipo = _tipo(cfdi)
    es_traslado = _v(cfdi.get("TipoDeComprobante")) == "T"

    datos = "".join([
        _campo("Fecha y hora de emisión", _e(f"{cfdi['Fecha']:%d/%m/%Y %H:%M:%S}")),
        _campo("Lugar de expedición", f"CP {_e(cfdi.get('LugarExpedicion'))}"),
        _campo("Tipo de comprobante", _cd(cfdi.get("TipoDeComprobante"))),
        _campo("Moneda", _cd(cfdi.get("Moneda")) + (f" · TC {_num(cfdi['TipoCambio'], 2)}" if cfdi.get("TipoCambio") and moneda != "MXN" else "")),
        _campo("Forma de pago", _cd(cfdi.get("FormaPago"))),
        _campo("Método de pago", _cd(cfdi.get("MetodoPago"))),
        _campo("Exportación", _cd(cfdi.get("Exportacion"))),
        _campo("No. de certificado del emisor", f'<span class="mono">{_e(cfdi.get("NoCertificado"))}</span>'),
        _campo("Condiciones de pago", _e(cfdi.get("CondicionesDePago")), "ancho"),
    ])

    notas = ""
    for rel in _lista(cfdi.get("CfdiRelacionados")):
        uu = [u.get("UUID") if isinstance(u, dict) else u for u in _lista(rel.get("CfdiRelacionado"))]
        notas += (f'<div class="nota"><span class="et">CFDI relacionados · {_cd(rel.get("TipoRelacion"))}</span>'
                  f'<span class="mono">{"<br>".join(_e(u) for u in uu)}</span></div>')
    g = cfdi.get("InformacionGlobal")
    if g:
        notas += (f'<div class="nota"><span class="et">Factura global</span>Periodicidad: {_cd(g.get("Periodicidad"))} · '
                  f'Meses: {_cd(g.get("Meses"))} · Año: {_e(g.get("Año"))}</div>')

    filas = "".join(_concepto(c) for c in _lista(cfdi.get("Conceptos")))

    tot = [("Subtotal", _dinero(cfdi.get("SubTotal")))]
    if cfdi.get("Descuento"):
        tot.append(("Descuento", "−" + _dinero(cfdi["Descuento"])))
    imp = cfdi.get("Impuestos") or {}
    for t in _lista(imp.get("Traslados")):
        nombre = getattr(t.get("Impuesto"), "description", None) or _v(t.get("Impuesto"))
        tot.append((f"{_e(nombre)} {_tasa(t)}", _dinero(t.get("Importe")) if t.get("Importe") is not None else "0.00"))
    for t in _lista(imp.get("Retenciones")):
        nombre = getattr(t.get("Impuesto"), "description", None) or _v(t.get("Impuesto"))
        tot.append((f"Retención de {_e(nombre)}", "−" + _dinero(t.get("Importe"))))
    loc = (cfdi.get("Complemento") or {}).get("ImpuestosLocales") or {}
    for t in _lista(loc.get("TrasladosLocales")):
        tot.append((f"{_e(t.get('ImpLocTrasladado'))} {_num(t.get('TasadeTraslado'))}% (local)", _dinero(t.get("Importe"))))
    for t in _lista(loc.get("RetencionesLocales")):
        tot.append((f"Retención {_e(t.get('ImpLocRetenido'))} {_num(t.get('TasadeRetencion'))}% (local)", "−" + _dinero(t.get("Importe"))))
    totales = "".join(f'<tr><td>{a}</td><td class="num">{b}</td></tr>' for a, b in tot)
    totales += f'<tr class="total"><td>Total {_e(moneda)}</td><td class="num">${_dinero(cfdi.get("Total"))}</td></tr>'

    timbre = ""
    if tfd:
        timbre = f"""
  <div class="timbre">
    <img src="{_qr(cfdi.verifica_url)}" alt="Código QR de verificación del SAT">
    <div class="t">
      <div class="fila">
        <div><span class="et">Folio fiscal (UUID)</span><span class="mono" style="white-space:nowrap;font-size:7.6pt">{_e(tfd.get("UUID"))}</span></div>
        <div><span class="et">Fecha y hora de certificación</span>{_e(f"{tfd['FechaTimbrado']:%d/%m/%Y %H:%M:%S}")}</div>
        <div><span class="et">RFC del PAC</span>{_e(tfd.get("RfcProvCertif"))}</div>
        <div><span class="et">No. de certificado del SAT</span><span class="mono">{_e(tfd.get("NoCertificadoSAT"))}</span></div>
      </div>
      <span class="et">Sello digital del emisor (CFDI)</span><div class="sello">{_e(tfd.get("SelloCFD"))}</div>
      <span class="et">Sello digital del SAT</span><div class="sello">{_e(tfd.get("SelloSAT"))}</div>
      <span class="et">Cadena original del complemento de certificación digital del SAT</span><div class="sello">{_e(tfd.cadena_original())}</div>
    </div>
  </div>"""

    titulo = f"{tipo} {folio}".strip()
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{_e(titulo)} · {_e(tfd.get("UUID") or "")}</title>
<style>{_css(_color(emisor))}</style></head>
<body><table class="hoja"><thead><tr><td></td></tr></thead><tfoot><tr><td></td></tr></tfoot><tbody><tr><td>
  {_DEMO if demo else ""}
  <div class="cab">
    {_logo(emisor)}
    <div class="quien"><b>{_e(e["Nombre"])}</b></div>
    <div class="doc"><span class="t">{_e(tipo)}</span><b>{_e(folio) or "s/f"}</b></div>
  </div>
  <div class="partes">
    <div><span class="et">Emisor</span><b class="n">{_e(e["Nombre"])}</b>RFC {_e(e["Rfc"])}<br>
      Régimen fiscal: {_cd(e.get("RegimenFiscal"))}</div>
    <div><span class="et">Receptor</span><b class="n">{_e(r["Nombre"])}</b>RFC {_e(r["Rfc"])} · Domicilio fiscal: CP {_e(r.get("DomicilioFiscalReceptor"))}<br>
      Régimen fiscal: {_cd(r.get("RegimenFiscalReceptor"))}<br>Uso del CFDI: {_cd(r.get("UsoCFDI"))}</div>
  </div>
  <div class="datos">{datos}</div>
  {notas}
  <table class="con"><thead><tr><th class="num">Cant.</th><th>Unidad</th><th>Clave SAT</th><th>Descripción</th>
    <th class="num">Valor unitario</th><th class="num">Descuento</th><th class="num">Importe</th></tr></thead>
    <tbody>{filas}</tbody></table>
  <div class="cierre">
    <div class="letra">{"" if es_traslado else f'<span class="et">Importe con letra</span>{_e(con_letra(cfdi.get("Total"), moneda))}'}</div>
    <table>{totales}</table>
  </div>
  {timbre}
  <p class="pie">{_e(LEYENDA.format(v=cfdi.get("Version") or "4.0"))}</p>
</td></tr></tbody></table></body></html>"""


def _satcfdi(cfdi, emisor, demo: bool) -> str:
    """Nómina y pagos: plantilla de satcfdi con la marca del emisor y la leyenda."""
    from satcfdi import render
    color = _color(emisor)
    css = f"""
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #111; }}
    h3, h4 {{ background-color: {color} !important; letter-spacing: 2px; border-radius: 2px; }}
    h5 {{ background-color: {color}cc !important; }} h6 {{ background-color: {color}99 !important; }}
    table th {{ background-color: {color}14 !important; }}
    .marca {{ display: flex; align-items: center; gap: 16px; padding: 4px 0 12px; margin-bottom: 10px; border-bottom: 3px solid {color}; }}
    .marca img {{ max-height: 64px; max-width: 180px; object-fit: contain; }}
    .marca .quien {{ flex: 1; }} .marca .quien b {{ font-size: 13pt; display: block; }}
    .marca .doc {{ text-align: right; }} .marca .doc b {{ font-size: 13pt; color: {color}; display: block; }}
    .marca small {{ color: #555; font-size: 7.5pt; }}
    .demo {{ background: #b42318; color: #fff; text-align: center; font-weight: bold; letter-spacing: 1px; padding: 6px 8px; margin-bottom: 8px; font-size: 9pt; }}
    .pie {{ margin-top: 10px; text-align: center; font-size: 7pt; color: #666; }}
    """
    e = cfdi["Emisor"]
    folio = f"{cfdi.get('Serie') or ''}{cfdi.get('Folio') or ''}"
    uuid = ((cfdi.get("Complemento") or {}).get("TimbreFiscalDigital") or {}).get("UUID", "")
    enc = ((_DEMO if demo else "") + f'<div class="marca">{_logo(emisor)}<div class="quien"><b>{_e(e["Nombre"])}</b>'
           f'<small>RFC {_e(e["Rfc"])} · Régimen {_e(_v(e["RegimenFiscal"]))} · CP {_e(cfdi["LugarExpedicion"])}</small></div>'
           f'<div class="doc"><b>{_tipo(cfdi)} {_e(folio)}</b><small>{_e(uuid)}</small></div></div>')
    pie = f'<p class="pie">{_e(LEYENDA.format(v=cfdi.get("Version") or "4.0"))}</p>'
    h = render.html_str(cfdi)
    h = h.replace("</style>", css + "</style>", 1)
    h = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + enc, h, count=1)
    return h if "representación impresa" in h else h.replace("</body>", pie + "</body>", 1)  # satcfdi ya la trae al pie


def html(xml: bytes, imprimir: bool = False, emisor=None) -> str:
    cfdi = CFDI.from_string(xml)
    comp = cfdi.get("Complemento") or {}
    demo = es_demo(xml)
    if _v(cfdi.get("TipoDeComprobante")) in ("I", "E", "T") and not comp.get("Nomina") and not comp.get("Pagos"):
        h = _propia(cfdi, emisor, demo)
    else:
        h = _satcfdi(cfdi, emisor, demo)
    return h.replace("</body>", _IMPRIMIR + "</body>") if imprimir else h


# ---------------------------------------------------------------- PDF
def _navegador() -> str | None:
    """Edge (viene en todo Windows 10/11) o Chrome: imprimen el HTML a PDF sin abrir ventana."""
    rutas = []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            rutas += [Path(base) / "Microsoft/Edge/Application/msedge.exe", Path(base) / "Google/Chrome/Application/chrome.exe"]
    hallado = next((str(p) for p in rutas if p.exists()), None)
    if hallado:
        return hallado
    for nombre in ("chromium", "chromium-browser", "google-chrome", "microsoft-edge"):  # servidor Linux
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return None


# Cada PDF abre un navegador (cientos de MB). Sin tope, 30 PDF a la vez en el servidor lo dejan sin memoria y se cae
# todo Timbra; con tope, esperan su turno. Los ya hechos se guardan un rato en memoria (bajar dos veces es instantáneo).
_NAVEGADORES = threading.BoundedSemaphore(int(os.environ.get("PDF_SIMULTANEOS", "3")))
_HECHOS: "OrderedDict[str, bytes]" = OrderedDict()
_HECHOS_MAX = 64
_HECHOS_LOCK = threading.Lock()


def _pdf_navegador(h: str) -> bytes:
    clave = hashlib.sha256(h.encode("utf-8")).hexdigest()
    with _HECHOS_LOCK:
        if clave in _HECHOS:
            _HECHOS.move_to_end(clave)
            return _HECHOS[clave]
    with _NAVEGADORES:
        data = _pdf_navegador_sin_tope(h)
    with _HECHOS_LOCK:
        _HECHOS[clave] = data
        while len(_HECHOS) > _HECHOS_MAX:
            _HECHOS.popitem(last=False)
    return data


def _pdf_navegador_sin_tope(h: str) -> bytes:
    exe = _navegador()
    if not exe:
        raise RuntimeError("no hay Edge ni Chrome instalados")
    d = os.path.realpath(tempfile.mkdtemp(prefix="timbra_pdf_"))  # ruta larga: con la corta (ERICKD~1) no escribe el PDF
    try:
        src, out = Path(d) / "cfdi.html", Path(d) / "cfdi.pdf"
        src.write_text(h, encoding="utf-8")
        extra = [] if os.name == "nt" else ["--no-sandbox", "--disable-dev-shm-usage"]  # contenedor Linux
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-first-run", *extra, f"--user-data-dir={Path(d) / 'perfil'}",
                        "--no-pdf-header-footer", f"--print-to-pdf={out}", src.as_uri()],
                       capture_output=True, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # Edge regresa antes de terminar de escribir: se espera a que el archivo exista y deje de crecer
        previo, limite = -1, time.monotonic() + 25
        while time.monotonic() < limite:
            tam = out.stat().st_size if out.exists() else 0
            if tam > 1000 and tam == previo:
                try:
                    return out.read_bytes()
                except PermissionError:
                    pass
            previo = tam
            time.sleep(0.2)
        raise RuntimeError("el navegador no generó el PDF")
    finally:
        shutil.rmtree(d, ignore_errors=True)  # el perfil puede seguir abierto un instante: no es motivo para fallar


_weasy_ok: bool | None = None


def pdf(xml: bytes, emisor=None) -> bytes:
    global _weasy_ok
    h = html(xml, emisor=emisor)
    if _weasy_ok is not False:
        try:
            import weasyprint
            data = weasyprint.HTML(string=h).write_pdf()
            _weasy_ok = True
            return data
        except Exception as e:
            if _weasy_ok is None:
                log.info("weasyprint no disponible (%s): los PDF se generan con Edge/Chrome", str(e).splitlines()[0][:80] if str(e) else type(e).__name__)
            _weasy_ok = False
    try:
        return _pdf_navegador(h)
    except Exception as e:
        raise RuntimeError(f"PDF no disponible en esta máquina: {e}") from e


def pdf_varios(items: list[tuple[bytes, object]]) -> list[bytes | None]:
    """Varios PDF a la vez (ZIP de un lote). Cada elemento es (xml, emisor); None donde no se pudo generar."""
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    def uno(par):
        xml, em = par
        marca = None if em is None else SimpleNamespace(color=em.color, logo_b64=em.logo_b64)  # sin tocar la sesión de BD
        try:
            return pdf(xml, marca)
        except RuntimeError:
            return None

    listos = [(x, None if e is None else SimpleNamespace(color=e.color, logo_b64=e.logo_b64)) for x, e in items]
    with ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(uno, listos))
