"""Complementos de pago (REP): se cancelan del más reciente al más antiguo y la parcialidad nunca se repite.
Reporte del tester (IVD, A13): cancelar P1 con P2 vivo dejaba el contador atrás y el REP nuevo salía con parcialidad 2 otra vez."""
import os
import re

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Factura  # noqa: E402
from test_v2 import _cliente, _factura, _preparar  # noqa: E402


def _pagar(c, h, e, cli, f, monto):
    r = c.post("/api/facturas/pagos", headers=h, json={
        "emisor_id": e["id"], "cliente_id": cli["id"], "fecha_pago": "2026-10-01T10:00:00", "forma_pago": "03",
        "documentos": [{"factura_id": f["id"], "imp_pagado": monto}]})
    assert r.status_code == 200, r.text
    return r.json()


def _parcialidad(c, h, rep):
    xml = c.get(f"/api/facturas/{rep['id']}/xml", headers=h).text
    return int(re.search(r'NumParcialidad="(\d+)"', xml).group(1))


def test_rep_se_cancela_en_orden_y_la_parcialidad_no_se_repite():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        f, _ = _factura(c, h, e, cli, total="3000", metodo="PPD")  # 3,480 con IVA
        p1 = _pagar(c, h, e, cli, f, "1000")
        p2 = _pagar(c, h, e, cli, f, "1000")
        assert (_parcialidad(c, h, p1), _parcialidad(c, h, p2)) == (1, 2)

        # Cancelar P1 con P2 vivo: se bloquea y dice cuál va primero
        r = c.post(f"/api/facturas/{p1['id']}/cancelar", headers=h, json={"motivo": "02"})
        assert r.status_code == 422 and "posteriores" in r.text and f"{p2['serie']}{p2['folio']}" in r.text, r.text
        assert float(c.get(f"/api/facturas/{f['id']}", headers=h).json()["saldo"]) == 1480

        # En orden sí: P2 y luego P1; el saldo regresa completo
        assert c.post(f"/api/facturas/{p2['id']}/cancelar", headers=h, json={"motivo": "02"}).json()["estado"] == "cancelada"
        assert c.post(f"/api/facturas/{p1['id']}/cancelar", headers=h, json={"motivo": "02"}).json()["estado"] == "cancelada"
        fx = c.get(f"/api/facturas/{f['id']}", headers=h).json()
        assert float(fx["saldo"]) == 3480 and fx["parcialidades"] == 0

        # Datos ya dañados (como A13): contador atrás con un REP vivo de parcialidad 2 → el nuevo sale con 3, no con 2
        p4 = _pagar(c, h, e, cli, f, "1000")
        p5 = _pagar(c, h, e, cli, f, "1000")
        with SessionLocal() as db:
            db.get(Factura, f["id"]).parcialidades = 1  # simula el contador viejo tras cancelar fuera de orden
            db.commit()
        p6 = _pagar(c, h, e, cli, f, "500")
        assert (_parcialidad(c, h, p4), _parcialidad(c, h, p5), _parcialidad(c, h, p6)) == (1, 2, 3)
