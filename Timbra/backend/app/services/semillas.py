"""Catálogo base de productos/servicios que se precarga a cada emisor nuevo.
Claves verificadas contra el catálogo c_ClaveProdServ que trae satcfdi."""
IVA16 = [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]
HON_PM = IVA16 + [
    {"tipo": "retencion", "impuesto": "001", "factor": "Tasa", "tasa": "0.100000"},
    {"tipo": "retencion", "impuesto": "002", "factor": "Tasa", "tasa": "0.106667"},
]
EXENTO = [{"tipo": "traslado", "impuesto": "002", "factor": "Exento", "tasa": None}]
ISR10 = {"tipo": "retencion", "impuesto": "001", "factor": "Tasa", "tasa": "0.100000"}

PRODUCTOS = [
    ("Servicios de contabilidad", "84111500", "E48", IVA16),
    ("Servicios de contabilidad mensual (iguala)", "84111500", "E48", IVA16),
    ("Declaraciones y cumplimiento fiscal", "84111800", "E48", IVA16),
    ("Auditoría", "84111600", "E48", IVA16),
    ("Consultoría fiscal", "80101500", "E48", IVA16),
    ("Honorarios profesionales (PF a PM)", "80101500", "E48", HON_PM),
    ("Asesoría y capacitación", "86101700", "E48", IVA16),
    ("Desarrollo de software", "81111500", "E48", IVA16),
    ("Soporte técnico / mantenimiento de sistemas", "81111800", "E48", IVA16),
    ("Servicios de diseño gráfico", "82141500", "E48", IVA16),
    ("Publicidad en internet / marketing digital", "82101603", "E48", IVA16),
    ("Arrendamiento de local comercial", "80131500", "E48", HON_PM),
    ("Consulta médica de especialidad (PF con título: exenta)", "85121600", "E48", EXENTO),
    ("Consulta médica general", "85121502", "E48", EXENTO),
    ("Honorarios médicos a persona moral (exento, ret. ISR 10%)", "85121600", "E48", EXENTO + [ISR10]),
    ("Servicios de laboratorio clínico", "85121800", "E48", EXENTO),
    ("Servicio de transporte de carga (flete)", "78101800", "E48", IVA16 + [
        {"tipo": "retencion", "impuesto": "002", "factor": "Tasa", "tasa": "0.040000"}]),
    ("Venta de mercancía (pieza)", "01010101", "H87", IVA16),
    ("Suplemento alimenticio (pieza)", "51191900", "H87", IVA16),
    ("Anticipo del bien o servicio (regla SAT: 84111506 + ACT)", "84111506", "ACT", IVA16),
    ("Comisiones", "80141628", "E48", IVA16),
]


RESICO = IVA16 + [{"tipo": "retencion", "impuesto": "001", "factor": "Tasa", "tasa": "0.012500"},
                  {"tipo": "retencion", "impuesto": "002", "factor": "Tasa", "tasa": "0.106667"}]
FLETE = IVA16 + [{"tipo": "retencion", "impuesto": "002", "factor": "Tasa", "tasa": "0.040000"}]

# Catálogos sugeridos por giro. (descripción, clave SAT, unidad, impuestos, etiqueta del impuesto)
# Todas las claves se verifican contra el catálogo vigente (tests/test_claves.py). Los precios van en 0: los pones tú.
PACKS = [
    {"id": "contabilidad", "nombre": "Contabilidad y despacho", "descripcion": "Iguala, declaraciones, auditoría, consultoría.",
     "productos": [
         ("Servicios contables (iguala mensual)", "84111500", "E48", IVA16, "IVA 16%"),
         ("Preparación y presentación de declaraciones", "84111800", "E48", IVA16, "IVA 16%"),
         ("Servicios de auditoría", "84111600", "E48", IVA16, "IVA 16%"),
         ("Consultoría de negocios y administración", "80101500", "E48", IVA16, "IVA 16%"),
         ("Honorarios profesionales a persona moral (PF: ret. ISR 10% e IVA)", "80101500", "E48", HON_PM, "IVA 16% + retenciones"),
         ("Capacitación", "86101700", "E48", IVA16, "IVA 16%"),
         ("Anticipo (clave del SAT para anticipos)", "84111506", "ACT", IVA16, "IVA 16%"),
     ]},
    {"id": "salud_sociedad", "nombre": "Salud · clínica o sociedad (IVA 16%)",
     "descripcion": "Consultas, control y seguimiento, laboratorio y suplementos facturados por una sociedad.",
     "nota": "Una sociedad (S.A., S.A.S., etc.) causa IVA 16% en servicios médicos. Confírmalo con tu contador.",
     "productos": [
         ("Servicios de control y seguimiento clínico", "85121503", "E48", IVA16, "IVA 16%"),
         ("Consulta médica de atención primaria", "85121502", "E48", IVA16, "IVA 16%"),
         ("Consulta médica de especialidad", "85121600", "E48", IVA16, "IVA 16%"),
         ("Servicios de laboratorio clínico", "85121800", "E48", IVA16, "IVA 16%"),
         ("Servicios de psicología", "85121608", "E48", IVA16, "IVA 16%"),
         ("Servicios de fisioterapia", "85122101", "E48", IVA16, "IVA 16%"),
         ("Servicios dentales", "85122000", "E48", IVA16, "IVA 16%"),
         ("Suplemento vitamínico (pieza)", "51191905", "H87", IVA16, "IVA 16%"),
         ("Suplemento dietético (pieza)", "51191900", "H87", IVA16, "IVA 16%"),
     ]},
    {"id": "salud_pf", "nombre": "Salud · persona física con título y cédula (exento)",
     "descripcion": "Servicios médicos personales exentos de IVA; los productos que vendes sí causan IVA.",
     "nota": "La exención aplica sólo a servicios prestados por persona física con título y cédula. Los suplementos son producto: IVA 16%.",
     "productos": [
         ("Consulta médica general (exenta)", "85121502", "E48", EXENTO, "Exento"),
         ("Consulta médica de especialidad (exenta)", "85121600", "E48", EXENTO, "Exento"),
         ("Honorarios médicos a persona moral (exento, ret. ISR 10%)", "85121600", "E48", EXENTO + [ISR10], "Exento + ret. ISR"),
         ("Servicios de psicología (exentos)", "85121608", "E48", EXENTO, "Exento"),
         ("Servicios de fisioterapia (exentos)", "85122101", "E48", EXENTO, "Exento"),
         ("Servicios dentales (exentos)", "85122000", "E48", EXENTO, "Exento"),
         ("Suplemento vitamínico (pieza)", "51191905", "H87", IVA16, "IVA 16%"),
     ]},
    {"id": "arrendamiento", "nombre": "Arrendamiento", "descripcion": "Renta de local, oficina o casa habitación.",
     "nota": "Captura la cuenta predial en el concepto al facturar. Casa habitación: exento de IVA.",
     "productos": [
         ("Renta de local comercial u oficina", "80131500", "E48", IVA16, "IVA 16%"),
         ("Renta a persona moral (PF: ret. ISR 10% e IVA)", "80131500", "E48", HON_PM, "IVA 16% + retenciones"),
         ("Renta de casa habitación (exento)", "80131500", "E48", EXENTO, "Exento"),
         ("Servicios de mantenimiento de edificios", "72101507", "E48", IVA16, "IVA 16%"),
     ]},
    {"id": "tecnologia", "nombre": "Tecnología y diseño", "descripcion": "Software, soporte, internet, diseño y publicidad.",
     "productos": [
         ("Desarrollo de software", "81111500", "E48", IVA16, "IVA 16%"),
         ("Servicios de sistemas y administración", "81111800", "E48", IVA16, "IVA 16%"),
         ("Mantenimiento y soporte de software", "81112200", "E48", IVA16, "IVA 16%"),
         ("Servicios de internet / hosting", "81112100", "E48", IVA16, "IVA 16%"),
         ("Diseño gráfico", "82141500", "E48", IVA16, "IVA 16%"),
         ("Publicidad en internet", "82101603", "E48", IVA16, "IVA 16%"),
     ]},
    {"id": "transporte", "nombre": "Transporte y mensajería", "descripcion": "Fletes y paquetería.",
     "nota": "Si trasladas mercancía por carretera revisa si corresponde el complemento Carta Porte.",
     "productos": [
         ("Servicio de transporte de carga (flete, ret. IVA 4%)", "78101800", "E48", FLETE, "IVA 16% + ret. IVA 4%"),
         ("Servicios de paquetería y mensajería", "78102200", "E48", IVA16, "IVA 16%"),
     ]},
    {"id": "servicios_generales", "nombre": "Servicios generales", "descripcion": "Limpieza, comida, capacitación, comisiones y más.",
     "productos": [
         ("Servicios de limpieza de edificios", "76111501", "E48", IVA16, "IVA 16%"),
         ("Servicios de comida para llevar y a domicilio", "90101800", "E48", IVA16, "IVA 16%"),
         ("Servicios de traducción", "82111804", "E48", IVA16, "IVA 16%"),
         ("Capacitación", "86101700", "E48", IVA16, "IVA 16%"),
         ("Comisiones (distribuidores por comisión)", "80141628", "E48", IVA16, "IVA 16%"),
         ("Gimnasio / centro de salud", "91101501", "E48", IVA16, "IVA 16%"),
     ]},
]


def a_frontera(imps: list[dict]) -> list[dict]:
    """IVA 16% → 8% y retención de IVA 2/3 (10.6667% → 5.3333%). Fletes (4%) no cambia."""
    out = []
    for i in imps:
        i = dict(i)
        if i["impuesto"] == "002" and i["tipo"] == "traslado" and str(i.get("tasa")) in ("0.16", "0.160000"):
            i["tasa"] = "0.08"
        elif i["impuesto"] == "002" and i["tipo"] == "retencion" and str(i.get("tasa")) in ("0.106667", "0.10666667"):
            i["tasa"] = "0.053333"
        out.append(i)
    return out


def productos_base(emisor_id: int, frontera: bool = False) -> list[dict]:
    from satcfdi.catalogs import select
    out = []
    for desc, clave, unidad, imps in PRODUCTOS:
        if select("C756_c_ClaveProdServ", clave) is None:  # por si el SAT la retira
            continue
        out.append(dict(emisor_id=emisor_id, descripcion=desc, clave_prod_serv=clave, clave_unidad=unidad,
                        precio=0, objeto_imp="02", impuestos=a_frontera(imps) if frontera else imps))
    return out
