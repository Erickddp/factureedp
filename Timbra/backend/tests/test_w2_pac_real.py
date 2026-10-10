"""Fallas que sólo aparecieron al timbrar contra Finkok (ambiente de pruebas) el 10-oct-2026. El PAC demo no las detecta."""
import os
import re
from datetime import datetime

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import errores_pac  # noqa: E402
from test_lotes import rfc_de_prueba  # noqa: E402
from test_v2 import _preparar  # noqa: E402

IVA = {"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}


def _cliente(c, h, e, n, nombre):
    rfc = rfc_de_prueba(n)
    r = c.post("/api/clientes", headers=h, json={"emisor_id": e["id"], "rfc": rfc, "nombre": nombre, "regimen_fiscal": "612",
                                                 "codigo_postal": "42501", "uso_cfdi": "G03"})
    return r.json() if r.status_code == 200 else next(x for x in c.get(f"/api/clientes?emisor_id={e['id']}&q={rfc}", headers=h).json())


def test_dinero_siempre_con_dos_decimales_en_el_xml():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e, 61, "CLIENTE DECIMALES")
        base = {"emisor_id": e["id"], "cliente_id": cli["id"], "tipo": "I", "forma_pago": "03", "moneda": "MXN", "enviar_email": False}
        con = {"clave_prod_serv": "80101500", "clave_unidad": "E48", "descripcion": "Con descuento", "cantidad": "3", "valor_unitario": "800",
               "objeto_imp": "02", "impuestos": [IVA]}

        # CFDI40112: el descuento "200" (sin decimales) lo rechazó Finkok; debe salir 200.00
        f = c.post("/api/facturas", headers=h, json={**base, "metodo_pago": "PUE", "conceptos": [{**con, "descuento": "200"}]})
        assert f.status_code == 200, f.text
        xml = c.get(f"/api/facturas/{f.json()['id']}/xml", headers=h).text
        assert set(re.findall(r'Descuento="([^"]+)"', xml)) == {"200.00"}, re.findall(r'Descuento="([^"]+)"', xml)

        # CRP20240: el saldo se guarda con 6 decimales; en el complemento de pago van 2
        ppd = c.post("/api/facturas", headers=h, json={**base, "metodo_pago": "PPD", "forma_pago": "99",
                                                       "conceptos": [{**con, "descripcion": "A crédito", "cantidad": "2", "valor_unitario": "4250.50"}]}).json()
        p = c.post("/api/facturas/pagos", headers=h, json={"emisor_id": e["id"], "cliente_id": cli["id"], "forma_pago": "03",
                                                           "fecha_pago": datetime.now().replace(microsecond=0).isoformat(),
                                                           "documentos": [{"factura_id": ppd["id"], "imp_pagado": "4000"}]})
        assert p.status_code == 200, p.text
        xml = c.get(f"/api/facturas/{p.json()['id']}/xml", headers=h).text
        for campo in ("ImpSaldoAnt", "ImpPagado", "ImpSaldoInsoluto"):
            valores = re.findall(rf'{campo}="([^"]+)"', xml)
            assert valores and all(re.fullmatch(r"\d+\.\d{2}", v) for v in valores), (campo, valores)
        assert 'ImpSaldoAnt="9861.16"' in xml and 'ImpSaldoInsoluto="5861.16"' in xml


def test_error_de_saldo_del_documento_no_se_confunde_con_falta_de_timbres():
    d = errores_pac.diagnosticar("CRP20240 - El valor del campo ImpSaldoAnt debe tener hasta la cantidad de decimales que soporte la moneda")
    assert d is None or d.clave != "saldo"
    assert errores_pac.diagnosticar("El usuario no cuenta con timbres disponibles").clave in ("saldo", "credenciales")
    assert errores_pac.diagnosticar("Saldo insuficiente").clave == "saldo"
