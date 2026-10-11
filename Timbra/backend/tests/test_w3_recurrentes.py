"""Timbrado automático de recurrentes: se timbra sola al día, no duplica, no salta meses y no suelta facturas viejas de golpe."""
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Factura, Plantilla  # noqa: E402
from app.services import recurrentes  # noqa: E402
from test_v2 import _cliente, _preparar  # noqa: E402

IVA16 = {"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}


def _plantilla(db, e, cli, nombre, dia, proxima, auto=True):
    p = Plantilla(emisor_id=e["id"], cliente_id=cli["id"], nombre=nombre, recurrente=True, dia=dia, auto_timbrar=auto, proxima=proxima,
                  payload={"metodo_pago": "PUE", "forma_pago": "03", "conceptos": [
                      {"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "Iguala {mes} {año}", "valor_unitario": "1000",
                       "impuestos": [IVA16]}]})
    db.add(p)
    db.commit()
    return p


def _descripcion(db, factura_id) -> str:
    return db.get(Factura, factura_id).payload["conceptos"][0]["descripcion"]


def test_automatica_al_dia_se_timbra_una_sola_vez():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        hoy = datetime.now().replace(microsecond=0)
        with SessionLocal() as db:
            p = _plantilla(db, e, cli, "Auto al día", hoy.day, hoy - timedelta(minutes=5))
            recurrentes.correr_automaticas(db)
            db.refresh(p)
            assert p.ultima_factura_id and p.ultimo_error is None and p.auto_timbrar is True
            assert p.proxima > hoy and (p.proxima.year, p.proxima.month) != (hoy.year, hoy.month)
            primera = p.ultima_factura_id
            # El programador vuelve a pasar (o alguien da clic a la vez): no hay segunda factura
            recurrentes.correr_automaticas(db)
            db.refresh(p)
            assert p.ultima_factura_id == primera
            assert f"{recurrentes.MESES[hoy.month - 1]} {hoy.year}" in _descripcion(db, primera)


def test_tarde_pero_dentro_del_margen_usa_el_periodo_programado_y_no_salta_mes():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        hoy = datetime(2026, 10, 3, 9, 0)  # tocaba el 30 de septiembre; Timbra se abre el 3 de octubre
        with SessionLocal() as db:
            p = _plantilla(db, e, cli, "Auto tarde", 30, datetime(2026, 9, 30))
            recurrentes.correr_automaticas(db, hoy)
            db.refresh(p)
            assert p.ultima_factura_id, p.ultimo_error
            assert "septiembre 2026" in _descripcion(db, p.ultima_factura_id)   # el periodo que tocaba, no "octubre"
            assert p.proxima == datetime(2026, 10, 30)                          # octubre NO se salta


def test_muy_atrasada_no_se_timbra_sola_y_se_recupera_mes_por_mes_a_mano():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        hoy = datetime(2026, 10, 3, 9, 0)
        with SessionLocal() as db:
            p = _plantilla(db, e, cli, "Auto atrasada", 15, datetime(2026, 8, 15))
            recurrentes.correr_automaticas(db, hoy)
            db.refresh(p)
            assert p.ultima_factura_id is None and p.auto_timbrar is True
            assert p.ultimo_error.startswith("Atrasada") and p.proxima == datetime(2026, 8, 15)
            # A mano: agosto, y sigue pendiente septiembre
            f = recurrentes.ejecutar(db, p, hoy)
            assert "agosto 2026" in _descripcion(db, f.id)
            db.refresh(p)
            assert p.proxima == datetime(2026, 9, 15) and p.ultimo_error is None
            assert any(x.id == p.id for x in recurrentes.pendientes(db, e["id"], hoy))
