"""Si el PAC contesta que ya no hay timbres (Finkok 718), la pantalla de Timbres lo dice en rojo hasta el siguiente
timbrado bueno, en lugar de un «restantes» calculado por Timbra que engaña."""
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Emisor, Pac  # noqa: E402
from app.services import pac as pac_svc  # noqa: E402
from app.services.errores_pac import Diagnostico  # noqa: E402
from test_v2 import _cliente, _preparar  # noqa: E402

CONCEPTO = [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "Servicio", "valor_unitario": "100",
             "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]}]
ORIGINAL = pac_svc.timbrar
DEMO = Pac(nombre="demo", proveedor="demo", pruebas=True)


def _timbres_de(c, h, pac_id):
    return next(x for x in c.get("/api/pacs/timbres", headers=h).json() if x["pac_id"] == pac_id)


def test_el_718_del_pac_se_ve_en_timbres_hasta_que_vuelve_a_timbrar(monkeypatch):
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        pac = c.post("/api/pacs", headers=h, json={"nombre": "Finkok pruebas 718", "proveedor": "finkok", "usuario": "demo@x.mx",
                                                   "password": "Secreta#123", "pruebas": True}).json()
        with SessionLocal() as db:
            antes = db.get(Emisor, e["id"]).pac_id
            db.get(Emisor, e["id"]).pac_id = pac["id"]
            db.commit()
        cuerpo = {"emisor_id": e["id"], "cliente_id": cli["id"], "metodo_pago": "PUE", "forma_pago": "03", "conceptos": CONCEPTO}
        try:
            def agotado(pac_, comp):
                raise pac_svc.PacError("718 - Timbres agotados", Diagnostico("saldo", "Tu cuenta del PAC no tiene timbres disponibles", "Compra timbres."))
            monkeypatch.setattr(pac_svc, "timbrar", agotado)
            assert c.post("/api/facturas", headers=h, json=cuerpo).status_code == 422
            t = _timbres_de(c, h, pac["id"])
            assert t["nivel"] == "error" and t["restantes"] == 0 and "ya no hay timbres" in t["texto"]
            assert any("ya no hay timbres" in a["texto"] for a in c.get(f"/api/dashboard?emisor_id={e['id']}", headers=h).json()["alertas"])
            # vuelve a timbrar bien: el aviso se quita solo
            monkeypatch.setattr(pac_svc, "timbrar", lambda pac_, comp: ORIGINAL(DEMO, comp))
            assert c.post("/api/facturas", headers=h, json=cuerpo).status_code == 200
            t = _timbres_de(c, h, pac["id"])
            assert t["nivel"] == "ok" and t["restantes"] is None and t["nota"]
        finally:
            with SessionLocal() as db:
                db.get(Emisor, e["id"]).pac_id = antes
                db.query(Pac).filter_by(id=pac["id"]).delete()
                db.commit()
