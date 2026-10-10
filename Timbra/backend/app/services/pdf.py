"""Representación impresa. satcfdi trae la plantilla (QR, cadena original, sellos, nómina, pagos);
aquí se le pone la marca del emisor: logo, color y encabezado limpio.
PDF requiere weasyprint + GTK. En Windows sin GTK se entrega HTML listo para imprimir (Ctrl+P → PDF)."""
import html as _html
import re

from satcfdi.cfdi import CFDI

_IMPRIMIR = "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),300))</script>"
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
TIPOS = {"I": "Factura", "E": "Nota de crédito", "P": "Complemento de pago", "T": "Traslado", "N": "Recibo de nómina"}


def _v(x):
    return getattr(x, "code", getattr(x, "value", x))


def _marca(cfdi, emisor) -> tuple[str, str]:
    """(css, encabezado) con el color y logo del emisor. Sin emisor o sin marca: tinta neutra."""
    color = emisor.color if emisor is not None and emisor.color and _COLOR.match(emisor.color) else "#111111"
    css = f"""
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #111; }}
    h3, h4 {{ background-color: {color} !important; letter-spacing: 2px; border-radius: 2px; }}
    h5 {{ background-color: {color}cc !important; }} h6 {{ background-color: {color}99 !important; }}
    table th {{ background-color: {color}14 !important; }}
    .marca {{ display: flex; align-items: center; gap: 16px; padding: 4px 0 12px; margin-bottom: 10px;
              border-bottom: 3px solid {color}; }}
    .marca img {{ max-height: 64px; max-width: 180px; object-fit: contain; }}
    .marca .quien {{ flex: 1; }} .marca .quien b {{ font-size: 13pt; display: block; }}
    .marca .doc {{ text-align: right; }} .marca .doc b {{ font-size: 13pt; color: {color}; display: block; }}
    .marca small {{ color: #555; font-size: 7.5pt; }}
    """
    e = cfdi["Emisor"]
    tipo = TIPOS.get(_v(cfdi.get("TipoDeComprobante")), "CFDI")
    if cfdi.get("Complemento", {}).get("Nomina"):
        tipo = TIPOS["N"]
    folio = f"{cfdi.get('Serie') or ''}{cfdi.get('Folio') or ''}"
    uuid = (cfdi.get("Complemento", {}).get("TimbreFiscalDigital") or {}).get("UUID", "")
    logo = ""
    if emisor is not None and emisor.logo_b64:
        src = emisor.logo_b64 if emisor.logo_b64.startswith("data:") else f"data:image/png;base64,{emisor.logo_b64}"
        logo = f'<img src="{_html.escape(src, quote=True)}" alt="logo">'
    enc = (f'<div class="marca">{logo}<div class="quien"><b>{_html.escape(e["Nombre"])}</b>'
           f'<small>RFC {_html.escape(e["Rfc"])} · Régimen {_html.escape(str(_v(e["RegimenFiscal"])))} · '
           f'CP {_html.escape(cfdi["LugarExpedicion"])}</small></div>'
           f'<div class="doc"><b>{tipo} {_html.escape(folio)}</b><small>{_html.escape(str(uuid))}</small></div></div>')
    return css, enc


_DEMO_CSS = """
    .demo { background: #b42318; color: #fff; text-align: center; font-weight: bold; letter-spacing: 1px;
            padding: 6px 8px; margin-bottom: 8px; font-size: 9pt; }
"""
_DEMO = '<div class="demo">MODO DEMO · SIN VALIDEZ FISCAL · No está timbrado ante el SAT</div>'


def es_demo(xml) -> bool:
    """El PAC demo firma el timbre con SelloSAT="DEMO"."""
    if not xml:
        return False
    return (b'SelloSAT="DEMO"' if isinstance(xml, bytes) else 'SelloSAT="DEMO"') in xml


def html(xml: bytes, imprimir: bool = False, emisor=None) -> str:
    from satcfdi import render
    cfdi = CFDI.from_string(xml)
    h = render.html_str(cfdi)
    css, enc = _marca(cfdi, emisor)
    if es_demo(xml):
        css, enc = css + _DEMO_CSS, _DEMO + enc
    h = h.replace("</style>", css + "</style>", 1)
    h = re.sub(r"(<body[^>]*>)", r"\1" + enc.replace("\\", "\\\\"), h, count=1)
    return h.replace("</body>", _IMPRIMIR + "</body>") if imprimir else h


def pdf(xml: bytes, emisor=None) -> bytes:
    try:
        import weasyprint
        from satcfdi.render import PDF_CSS
        return weasyprint.HTML(string=html(xml, emisor=emisor)).write_pdf(stylesheets=[PDF_CSS])
    except Exception as e:
        raise RuntimeError(f"PDF no disponible en esta máquina: {e}") from e
