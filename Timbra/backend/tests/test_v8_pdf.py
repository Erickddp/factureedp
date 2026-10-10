"""Representación impresa: requisitos de la regla 2.7.1.7 RMF / art. 29-A CFF, importe con letra y marca de modo demo."""
import os
import re

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import pdf  # noqa: E402
from test_lotes import rfc_de_prueba  # noqa: E402
from test_v2 import _preparar  # noqa: E402


def test_importe_con_letra():
    assert pdf.con_letra("4348.00") == "CUATRO MIL TRESCIENTOS CUARENTA Y OCHO PESOS 00/100 M.N."
    assert pdf.con_letra("9533.33") == "NUEVE MIL QUINIENTOS TREINTA Y TRES PESOS 33/100 M.N."
    assert pdf.con_letra("1") == "UN PESO 00/100 M.N."
    assert pdf.con_letra("100") == "CIEN PESOS 00/100 M.N."
    assert pdf.con_letra("101.5") == "CIENTO UN PESOS 50/100 M.N."
    assert pdf.con_letra("1000") == "MIL PESOS 00/100 M.N."
    assert pdf.con_letra("21021.99") == "VEINTIUN MIL VEINTIUN PESOS 99/100 M.N."
    assert pdf.con_letra("1000000") == "UN MILLON DE PESOS 00/100 M.N."
    assert pdf.con_letra("2500000.10") == "DOS MILLONES QUINIENTOS MIL PESOS 10/100 M.N."
    assert pdf.con_letra("0.75") == "CERO PESOS 75/100 M.N."
    assert pdf.con_letra("16", "USD") == "DIECISEIS DOLARES 00/100 USD"


def test_pdf_trae_todos_los_requisitos_fiscales():
    with TestClient(app) as c:
        h, e = _preparar(c)
        rfc = rfc_de_prueba(88)
        r = c.post("/api/clientes", headers=h, json={"emisor_id": e["id"], "rfc": rfc, "nombre": "CLIENTE DEL PDF",
                                                     "regimen_fiscal": "612", "codigo_postal": "42501", "uso_cfdi": "G03"})
        cli = r.json() if r.status_code == 200 else c.get(f"/api/clientes?emisor_id={e['id']}&q={rfc}", headers=h).json()[0]
        f = c.post("/api/facturas", headers=h, json={
            "emisor_id": e["id"], "cliente_id": cli["id"], "tipo": "I", "metodo_pago": "PUE", "forma_pago": "03", "moneda": "MXN",
            "enviar_email": False, "condiciones_pago": "Contado",
            "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "Servicio para el PDF", "cantidad": "2",
                           "valor_unitario": "2174", "objeto_imp": "02", "no_identificacion": "SKU-9",
                           "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"},
                                         {"tipo": "retencion", "impuesto": "001", "factor": "Tasa", "tasa": "0.10"}]}]}).json()
        html = c.get(f"/api/facturas/{f['id']}/html", headers=h).text
        xml = c.get(f"/api/facturas/{f['id']}/xml", headers=h).text
        attr = lambda nodo, a: re.search(rf"<[\w:]*{nodo}\b[^>]*?\b{a}=\"([^\"]*)\"", xml).group(1)  # noqa: E731

        debe = {
            "código QR": 'alt="Código QR de verificación del SAT"',
            "folio fiscal": f["uuid"],
            "certificado del emisor": attr("Comprobante", "NoCertificado"),
            "certificado del SAT": attr("TimbreFiscalDigital", "NoCertificadoSAT"),
            "RFC del PAC": attr("TimbreFiscalDigital", "RfcProvCertif"),
            "sello del emisor": attr("TimbreFiscalDigital", "SelloCFD")[:60],
            "sello del SAT": "Sello digital del SAT",
            "cadena original": f"||1.1|{f['uuid']}|",
            "leyenda": "Este documento es una representación impresa de un CFDI versión 4.0",
            "fecha de certificación": "Fecha y hora de certificación",
            "fecha de emisión": "Fecha y hora de emisión",
            "RFC emisor": e["rfc"], "nombre emisor": e["nombre"], "régimen emisor": "601 · General de Ley Personas Morales",
            "lugar de expedición": "CP 42501",
            "RFC receptor": rfc, "nombre receptor": "CLIENTE DEL PDF", "CP receptor": "Domicilio fiscal: CP 42501",
            "régimen receptor": "612 ·", "uso CFDI": "G03 · Gastos en general",
            "clave SAT": "84111506", "unidad": "E48", "descripción": "Servicio para el PDF", "no. identificación": "SKU-9",
            "valor unitario": "2,174.00", "importe": "4,348.00", "objeto de impuesto": "02 ·",
            "IVA por tasa": "IVA 16%", "retención": "Retención de ISR", "total": "$4,608.88",
            "total con letra": "CUATRO MIL SEISCIENTOS OCHO PESOS 88/100 M.N.",
            "forma de pago": "03 · Transferencia", "método de pago": "PUE ·", "moneda": "MXN · Peso Mexicano",
            "tipo de comprobante": "I · Ingreso", "exportación": "01 · No aplica", "condiciones": "Contado",
            "modo demo": "SIN VALIDEZ FISCAL",
        }
        faltan = [k for k, v in debe.items() if v not in html]
        assert not faltan, f"Al PDF le falta: {faltan}"
        # El QR apunta al verificador del SAT con UUID, RFC emisor/receptor, total y últimos 8 del sello
        from satcfdi.cfdi import CFDI
        url = CFDI.from_string(xml.encode()).verifica_url
        assert "verificacfdi.facturaelectronica.sat.gob.mx" in url and f["uuid"] in url and e["rfc"] in url and rfc in url
        assert attr("Comprobante", "Sello")[-8:] in url
