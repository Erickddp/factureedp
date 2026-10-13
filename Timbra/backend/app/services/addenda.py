"""Addendas: se inyectan DESPUÉS del timbrado, dentro de <cfdi:Addenda>.
La addenda no forma parte de la cadena original, así que no rompe el sello.

Cada cadena comercial (Walmart, Soriana, Liverpool, Chedraui, Amazon, Pemex, CFE...)
publica su propio XSD/manual. Aquí se guarda como plantilla Jinja2 editable,
con los campos que el usuario llena al facturar.
"""
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from lxml import etree

# Entorno aislado: una plantilla de addenda sólo acomoda datos, no puede alcanzar objetos de Python ni del servidor.
_env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=True)
# XML sin entidades externas ni red: un XML ajeno no puede hacer que el servidor lea sus propios archivos.
_SEGURO = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


class AddendaError(Exception):
    pass


def render(plantilla: str, datos: dict, cfdi: dict) -> etree._Element:
    try:
        txt = _env.from_string(plantilla).render(datos=datos, cfdi=cfdi)
    except Exception as e:
        raise AddendaError(f"Falta un dato de la addenda o la plantilla está mal: {e}") from e
    try:
        return etree.fromstring(txt.strip().encode(), _SEGURO)
    except etree.XMLSyntaxError as e:
        raise AddendaError(f"La addenda no es XML válido: {e}") from e


def inyectar(xml: bytes, plantilla: str, datos: dict, cfdi: dict) -> bytes:
    root = etree.fromstring(xml)
    ns = root.nsmap.get("cfdi", "http://www.sat.gob.mx/cfd/4")
    add = root.find(f"{{{ns}}}Addenda")
    if add is None:
        add = etree.SubElement(root, f"{{{ns}}}Addenda")
    add.append(render(plantilla, datos, cfdi))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


SEMILLAS = [
    {
        "nombre": "Genérica (orden de compra)",
        "descripcion": "La que más piden los corporativos: OC, número de proveedor y recepción.",
        "campos": [
            {"name": "orden_compra", "label": "Orden de compra", "required": True},
            {"name": "num_proveedor", "label": "Número de proveedor", "required": True},
            {"name": "recepcion", "label": "Folio de recepción / entrada", "required": False},
            {"name": "contacto", "label": "Contacto / comprador", "required": False},
        ],
        "plantilla": """<Generica xmlns="http://timbra.local/addenda/generica" version="1.0">
  <OrdenCompra>{{ datos.orden_compra }}</OrdenCompra>
  <NumeroProveedor>{{ datos.num_proveedor }}</NumeroProveedor>
  {% if datos.get('recepcion') %}<Recepcion>{{ datos.recepcion }}</Recepcion>{% endif %}
  {% if datos.get('contacto') %}<Contacto>{{ datos.contacto }}</Contacto>{% endif %}
  <Factura serie="{{ cfdi.get('Serie','') }}" folio="{{ cfdi.get('Folio','') }}" total="{{ cfdi.Total }}" moneda="{{ cfdi.Moneda }}"/>
</Generica>""",
    },
    {
        "nombre": "Contrato / arrendamiento (informativa)",
        "descripcion": "Datos del contrato y del periodo que se cobra. La cuenta predial NO va aquí: va en el concepto.",
        "campos": [
            {"name": "contrato", "label": "Número de contrato", "required": False},
            {"name": "inmueble", "label": "Inmueble o bien arrendado (dirección)", "required": True},
            {"name": "periodo", "label": "Periodo que se cobra (ej. octubre 2026)", "required": True},
            {"name": "vigencia", "label": "Vigencia del contrato", "required": False},
        ],
        "plantilla": """<Contrato xmlns="http://timbra.local/addenda/contrato" version="1.0">
  {% if datos.get('contrato') %}<Numero>{{ datos.contrato }}</Numero>{% endif %}
  <Inmueble>{{ datos.inmueble }}</Inmueble>
  <Periodo>{{ datos.periodo }}</Periodo>
  {% if datos.get('vigencia') %}<Vigencia>{{ datos.vigencia }}</Vigencia>{% endif %}
</Contrato>""",
    },
    {
        "nombre": "Referencia de pago (informativa)",
        "descripcion": "Referencia bancaria, pedido o proyecto para que tu cliente concilie el pago.",
        "campos": [
            {"name": "referencia", "label": "Referencia de pago", "required": True},
            {"name": "banco", "label": "Banco y cuenta o CLABE para el depósito", "required": False},
            {"name": "pedido", "label": "Pedido / proyecto", "required": False},
            {"name": "observaciones", "label": "Observaciones", "required": False},
        ],
        "plantilla": """<ReferenciaPago xmlns="http://timbra.local/addenda/referencia" version="1.0">
  <Referencia>{{ datos.referencia }}</Referencia>
  {% if datos.get('banco') %}<Banco>{{ datos.banco }}</Banco>{% endif %}
  {% if datos.get('pedido') %}<Pedido>{{ datos.pedido }}</Pedido>{% endif %}
  {% if datos.get('observaciones') %}<Observaciones>{{ datos.observaciones }}</Observaciones>{% endif %}
</ReferenciaPago>""",
    },
    {
        "nombre": "Servicios médicos (informativa)",
        "descripcion": "Paciente, expediente y médico tratante. Va fuera del sello: no cambia el CFDI.",
        "campos": [
            {"name": "paciente", "label": "Paciente", "required": True},
            {"name": "expediente", "label": "Expediente / folio interno", "required": False},
            {"name": "medico", "label": "Médico tratante", "required": False},
            {"name": "cedula", "label": "Cédula profesional", "required": False},
            {"name": "fecha_servicio", "label": "Fecha del servicio", "required": False},
        ],
        "plantilla": """<ServicioMedico xmlns="http://timbra.local/addenda/medico" version="1.0">
  <Paciente>{{ datos.paciente }}</Paciente>
  {% if datos.get('expediente') %}<Expediente>{{ datos.expediente }}</Expediente>{% endif %}
  {% if datos.get('medico') %}<Medico{% if datos.get('cedula') %} cedula="{{ datos.cedula }}"{% endif %}>{{ datos.medico }}</Medico>{% endif %}
  {% if datos.get('fecha_servicio') %}<FechaServicio>{{ datos.fecha_servicio }}</FechaServicio>{% endif %}
</ServicioMedico>""",
    },
    {
        "nombre": "Retail estilo AMECE/EDI (base, validar contra manual)",
        "descripcion": "Esqueleto tipo 'detallista' que usan varias cadenas. Ajusta nodos al manual vigente de tu cliente.",
        "campos": [
            {"name": "orden_compra", "label": "Orden de compra", "required": True},
            {"name": "fecha_oc", "label": "Fecha OC (AAAA-MM-DD)", "required": True},
            {"name": "gln_comprador", "label": "GLN comprador", "required": True},
            {"name": "gln_proveedor", "label": "GLN proveedor", "required": True},
            {"name": "num_proveedor", "label": "Número de proveedor", "required": True},
            {"name": "folio_recibo", "label": "Folio de recibo (contrarecibo)", "required": False},
        ],
        "plantilla": """<requestForPayment type="SimpleInvoiceType" contentVersion="1.3.1" documentStructureVersion="AMC7.1" documentStatus="ORIGINAL">
  <requestForPaymentIdentification>
    <entityType>INVOICE</entityType>
    <uniqueCreatorIdentification>{{ cfdi.get('Serie','') }}{{ cfdi.get('Folio','') }}</uniqueCreatorIdentification>
  </requestForPaymentIdentification>
  <orderIdentification>
    <referenceIdentification type="ON">{{ datos.orden_compra }}</referenceIdentification>
    <ReferenceDate>{{ datos.fecha_oc }}</ReferenceDate>
  </orderIdentification>
  {% if datos.get('folio_recibo') %}<DeliveryNote><referenceIdentification>{{ datos.folio_recibo }}</referenceIdentification></DeliveryNote>{% endif %}
  <buyer><gln>{{ datos.gln_comprador }}</gln></buyer>
  <seller><gln>{{ datos.gln_proveedor }}</gln><alternatePartyIdentification type="SELLER_ASSIGNED_IDENTIFIER_FOR_A_PARTY">{{ datos.num_proveedor }}</alternatePartyIdentification></seller>
  <currency currencyISOCode="{{ cfdi.Moneda }}"><currencyFunction>BILLING_CURRENCY</currencyFunction></currency>
  <baseAmount><Amount>{{ cfdi.SubTotal }}</Amount></baseAmount>
  <payableAmount><Amount>{{ cfdi.Total }}</Amount></payableAmount>
</requestForPayment>""",
    },
]
