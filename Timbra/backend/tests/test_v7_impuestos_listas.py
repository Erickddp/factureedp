"""IEPS (tasa y cuota, IVA sobre valor + IEPS), retención de IVA 6%, listas de clientes/conceptos, addendas básicas y modo demo."""
import os
from decimal import Decimal

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402
from lxml import etree  # noqa: E402

from app.main import app  # noqa: E402
from test_lotes import rfc_de_prueba  # noqa: E402
from test_v2 import _preparar  # noqa: E402

NS = {"c": "http://www.sat.gob.mx/cfd/4"}
IVA16 = {"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}


def _body(e, cliente_id, concepto):
    return {"emisor_id": e["id"], "cliente_id": cliente_id, "tipo": "I", "metodo_pago": "PUE", "forma_pago": "03",
            "moneda": "MXN", "enviar_email": False, "conceptos": [concepto]}


def _traslados(xml: bytes):
    root = etree.fromstring(xml)
    return [(t.get("Impuesto"), t.get("TipoFactor"), Decimal(t.get("Base")), Decimal(t.get("Importe")))
            for t in root.findall(".//c:Concepto/c:Impuestos/c:Traslados/c:Traslado", NS)]


def test_ieps_listas_addendas_demo():
    with TestClient(app) as c:
        h, e = _preparar(c)
        assert e["modo_demo"] is True
        r = c.post("/api/clientes", headers=h, json={"emisor_id": e["id"], "rfc": rfc_de_prueba(77), "nombre": "CLIENTE DE IMPUESTOS",
                                                     "regimen_fiscal": "612", "codigo_postal": "42501", "uso_cfdi": "G03"})
        assert r.status_code == 200, r.text
        cli = r.json()

        # IEPS 8% + IVA 16%: el IVA se calcula sobre valor + IEPS
        con = {"clave_prod_serv": "50192100", "clave_unidad": "H87", "descripcion": "Botana de prueba IEPS", "cantidad": "10",
               "valor_unitario": "100", "objeto_imp": "02",
               "impuestos": [{"tipo": "traslado", "impuesto": "003", "factor": "Tasa", "tasa": "0.08"}, IVA16]}
        pv = c.post("/api/facturas/preview", headers=h, json=_body(e, cli["id"], con)).json()
        assert not pv["errores"], pv
        assert Decimal(str(pv["total"])) == Decimal("1252.80"), pv  # 1000 + 80 + 16% de 1080
        f = c.post("/api/facturas", headers=h, json=_body(e, cli["id"], con))
        assert f.status_code == 200, f.text
        assert f.json()["demo"] is True
        tr = {(i, fa): (b, imp) for i, fa, b, imp in _traslados(c.get(f"/api/facturas/{f.json()['id']}/xml", headers=h).content)}
        assert tr[("003", "Tasa")] == (Decimal("1000.00"), Decimal("80.00"))
        assert tr[("002", "Tasa")] == (Decimal("1080.00"), Decimal("172.80"))
        assert "SIN VALIDEZ FISCAL" in c.get(f"/api/facturas/{f.json()['id']}/html", headers=h).text

        # IEPS por cuota: base = cantidad
        con2 = {**con, "descripcion": "Bebida de prueba cuota", "cantidad": "24", "valor_unitario": "10",
                "impuestos": [{"tipo": "traslado", "impuesto": "003", "factor": "Cuota", "tasa": "1.5"}, IVA16]}
        pv = c.post("/api/facturas/preview", headers=h, json=_body(e, cli["id"], con2)).json()
        assert not pv["errores"], pv
        assert Decimal(str(pv["total"])) == Decimal("320.16"), pv  # 240 + 36 + 16% de 276

        # Cuota sólo en IEPS
        malo = {**con, "impuestos": [{**IVA16, "factor": "Cuota"}]}
        assert any("cuota" in x["mensaje"] for x in c.post("/api/facturas/preview", headers=h, json=_body(e, cli["id"], malo)).json()["errores"])

        # Retención de IVA 6% (servicios especializados) y completa: válidas, sin error
        for tasa in ("0.06", "0.16"):
            con3 = {**con, "clave_prod_serv": "80111600", "clave_unidad": "E48", "descripcion": "Servicio especializado",
                    "impuestos": [IVA16, {"tipo": "retencion", "impuesto": "002", "factor": "Tasa", "tasa": tasa}]}
            pv = c.post("/api/facturas/preview", headers=h, json=_body(e, cli["id"], con3)).json()
            assert not pv["errores"], pv

        # Listas para los botones Clientes y Conceptos
        rec = c.get(f"/api/clientes/recientes?emisor_id={e['id']}", headers=h).json()
        assert rec[0]["id"] == cli["id"] and rec[0]["facturas"] >= 1 and rec[0]["ultima"]
        sug = c.get(f"/api/productos/sugerencias?emisor_id={e['id']}", headers=h).json()
        assert any(x["descripcion"] == "Botana de prueba IEPS" for x in sug["facturados"])
        sug = c.get(f"/api/productos/sugerencias?emisor_id={e['id']}&q=consulta medica", headers=h).json()
        assert sug["sat"] and all(len(x["clave"]) == 8 for x in sug["sat"])

        nombres = {a["nombre"] for a in c.get("/api/addendas", headers=h).json()}
        assert {"Contrato / arrendamiento (informativa)", "Referencia de pago (informativa)", "Servicios médicos (informativa)"} <= nombres

        yo = c.put("/api/auth/yo", headers=h, json={"nombre": "Prueba Perfil"}).json()
        assert yo["nombre"] == "Prueba Perfil" and yo["email"]


def test_mensaje_contrasena_en_espanol():
    from app.services.signer import motivo
    assert "contraseña" in motivo(Exception("Incorrect password, could not decrypt key"), "e.firma")
    assert "Incorrect" not in motivo(Exception("Incorrect password, could not decrypt key"), "CSD")
