"""Pasar emisores de una cuenta/instalación a otra: archivo cifrado con contraseña, simulacro antes de importar, CSD re-cifrado,
ids remapeados (clientes, facturas, payloads), folios que continúan y nada se pisa."""
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Factura, Serie  # noqa: E402
from test_v2 import _cliente, _factura, _preparar  # noqa: E402
from test_w1_cuentas import _usuario  # noqa: E402

CLAVE = "contraseña-larga-123"


def _importar(c, h, contenido, clave=CLAVE, simular=True):
    return c.post("/api/migracion/importar", headers=h, files={"archivo": ("cuenta.timbracuenta", contenido)},
                  data={"clave": clave, "simular": "true" if simular else "false"})


def test_exportar_e_importar_en_otra_cuenta():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e, emails=["ventas@despacho-prueba.mx"])
        f1, _ = _factura(c, h, e, cli, total="1000")
        ppd, _ = _factura(c, h, e, cli, total="2000", metodo="PPD")
        c.post("/api/plantillas", headers=h, json={"emisor_id": e["id"], "cliente_id": cli["id"], "nombre": "Mensual",
                                                   "payload": {"emisor_id": e["id"], "cliente_id": cli["id"], "conceptos": []}})
        xml_original = c.get(f"/api/facturas/{f1['id']}/xml", headers=h).content
        with SessionLocal() as db:
            ultimo_folio = max(int(x.folio) for x in db.query(Factura).filter_by(emisor_id=e["id"], serie=ppd["serie"]) if x.folio and x.folio.isdigit())

        # lo que se puede exportar, con sus números; el RFC de pruebas del SAT no viene marcado de entrada
        fila = next(x for x in c.get("/api/migracion/emisores", headers=h).json() if x["id"] == e["id"])
        assert fila["tiene_csd"] and fila["clientes"] >= 1 and fila["facturas"] >= 2 and fila["sugerido"] is False

        # la contraseña es obligatoria y larga
        assert c.post("/api/migracion/exportar", headers=h, json={"emisor_ids": [e["id"]], "clave": "corta"}).status_code == 422
        assert c.post("/api/migracion/exportar", headers=h, json={"emisor_ids": [], "clave": CLAVE}).status_code == 422
        r = c.post("/api/migracion/exportar", headers=h, json={"emisor_ids": [e["id"]], "con_facturas": True, "clave": CLAVE})
        assert r.status_code == 200 and ".timbracuenta" in r.headers["content-disposition"]
        archivo = r.content
        # cifrado de verdad: ni el RFC, ni la contraseña del CSD, ni el XML se ven en el archivo
        assert b"EKU9003173C9" not in archivo and b"12345678a" not in archivo and b"TimbreFiscalDigital" not in archivo
        sin_facturas = c.post("/api/migracion/exportar", headers=h, json={"emisor_ids": [e["id"]], "con_facturas": False, "clave": CLAVE}).content

        # contraseña equivocada o archivo que no es de Timbra
        assert _importar(c, h, archivo, clave="otra-contraseña-larga").status_code == 422
        assert _importar(c, h, b"esto no es un archivo de timbra" * 5).status_code == 422
        # en la misma cuenta ya existe: se dice y no se toca
        r = _importar(c, h, archivo).json()
        assert r["simulacro"] and r["emisores"][0]["estado"] == "ya_existe"

        # otra cuenta sí puede traerse el mismo RFC aunque siga en la primera (cada cuenta lleva lo suyo)
        b = _usuario(c, h, "migra-b@prueba.mx", "migrab")
        r = _importar(c, b, archivo).json()
        assert r["emisores"][0]["estado"] == "nuevo"
        assert c.delete(f"/api/emisores/{e['id']}?confirmar=EKU9003173C9", headers=h).status_code == 200
        try:
            # simulacro: dice qué entraría y NO guarda nada
            r = _importar(c, b, archivo).json()
            x = r["emisores"][0]
            assert r["simulacro"] and x["estado"] == "nuevo" and x["csd"] == "ok" and x["facturas"] >= 2 and x["clientes"] >= 1 and x["plantillas"] >= 1
            assert c.get("/api/emisores", headers=b).json() == []
            x_plantillas = x["plantillas"]
            # de verdad
            r = _importar(c, b, archivo, simular=False).json()
            assert not r["simulacro"] and r["emisores"][0]["estado"] == "nuevo"
            mios = c.get("/api/emisores", headers=b).json()
            assert [m["rfc"] for m in mios] == ["EKU9003173C9"] and mios[0]["no_certificado"] and mios[0]["color"] == "#0a7c66"
            nuevo = mios[0]
            assert c.get("/api/emisores", headers=h).json() is not None and all(m["rfc"] != "EKU9003173C9" for m in c.get("/api/emisores", headers=h).json())

            # clientes, facturas con su XML, saldo de la PPD y payloads con los ids NUEVOS
            clientes = c.get(f"/api/clientes?emisor_id={nuevo['id']}&limit=1000", headers=b).json()
            assert any(k["rfc"] == cli["rfc"] and k["emails"] == cli["emails"] for k in clientes)   # el mismo cliente, con sus correos
            facturas = c.get(f"/api/facturas?emisor_id={nuevo['id']}&limit=100", headers=b).json()
            por_uuid = {x["uuid"]: x for x in facturas}
            assert f1["uuid"] in por_uuid and ppd["uuid"] in por_uuid
            assert float(por_uuid[ppd["uuid"]]["saldo"]) == 2320 and por_uuid[ppd["uuid"]]["receptor_rfc"] == cli["rfc"]
            assert c.get(f"/api/facturas/{por_uuid[f1['uuid']]['id']}/xml", headers=b).content == xml_original
            payload = c.get(f"/api/facturas/{por_uuid[f1['uuid']]['id']}/payload", headers=b).json()
            assert payload["emisor_id"] == nuevo["id"] and payload["cliente_id"] in {k["id"] for k in clientes}
            plantillas = c.get(f"/api/plantillas?emisor_id={nuevo['id']}", headers=b).json()
            assert "Mensual" in [p["nombre"] for p in plantillas] and len(plantillas) == x_plantillas

            # el folio continúa donde iba: la siguiente factura no repite ninguno
            with SessionLocal() as db:
                assert db.query(Serie).filter_by(emisor_id=nuevo["id"], serie=ppd["serie"]).one().siguiente_folio > ultimo_folio
            cli_b = next(k for k in clientes if k["rfc"] == cli["rfc"])
            r = c.post("/api/facturas", headers=b, json={"emisor_id": nuevo["id"], "cliente_id": cli_b["id"], "metodo_pago": "PUE", "forma_pago": "03",
                                                         "serie": ppd["serie"], "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "E48",
                                                         "descripcion": "Otra", "valor_unitario": "100",
                                                         "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]}]})
            assert r.status_code == 200, r.text   # el CSD importado sella
            assert int(r.json()["folio"]) > ultimo_folio

            # importar otra vez no duplica nada
            r = _importar(c, b, archivo, simular=False).json()
            assert r["emisores"][0]["estado"] == "ya_existe"
            assert len(c.get(f"/api/emisores", headers=b).json()) == 1

            # sin facturas: llega todo menos ellas (otro RFC no hay: se prueba con el simulacro tras borrar)
            assert c.delete(f"/api/emisores/{nuevo['id']}?confirmar=EKU9003173C9", headers=b).status_code == 200
            x = _importar(c, b, sin_facturas).json()["emisores"][0]
            assert x["estado"] == "nuevo" and x["facturas"] == 0 and x["clientes"] >= 1
        finally:
            for m in c.get("/api/emisores", headers=b).json():
                c.delete(f"/api/emisores/{m['id']}?confirmar={m['rfc']}", headers=b)


def test_en_modo_soporte_no_se_exporta_ni_se_importa():
    with TestClient(app) as c:
        h, _e = _preparar(c)
        b = _usuario(c, h, "migra-c@prueba.mx", "migrac")
        uid = c.get("/api/auth/yo", headers=b).json()["id"]
        assert c.post(f"/api/auth/soporte/{uid}", headers=h, json={"motivo": "prueba"}).status_code == 200
        try:
            soporte = {**h, "X-Soporte": str(uid)}
            assert c.get("/api/migracion/emisores", headers=soporte).status_code == 403
            assert c.post("/api/migracion/exportar", headers=soporte, json={"emisor_ids": [1], "clave": CLAVE}).status_code == 403
            assert _importar(c, soporte, b"x").status_code == 403
        finally:
            c.delete(f"/api/auth/soporte/{uid}", headers=h)
