"""Compra de timbres con Mercado Pago (simulado: nunca se toca Mercado Pago) y vencimiento de recargas a 12 meses."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import MovimientoTimbres, Pago, Usuario  # noqa: E402
from app.services import timbres  # noqa: E402
from test_v2 import _preparar  # noqa: E402
from test_w1_cuentas import _usuario  # noqa: E402


class Resp:
    def __init__(self, status, cuerpo):
        self.status_code, self._c, self.text = status, cuerpo, str(cuerpo)

    def json(self):
        return self._c


class MercadoPagoSimulado:
    """Crea preferencias y contesta pagos con el estado/monto que la prueba le diga."""

    def __init__(self):
        self.pagos = {}       # mp_id -> dict
        self.preferencias = []

    def __call__(self, metodo, url, headers=None, timeout=None, json=None):
        assert headers["Authorization"] == "Bearer TEST-llave"
        if url.endswith("/checkout/preferences"):
            self.preferencias.append(json)
            return Resp(201, {"id": f"pref-{len(self.preferencias)}", "init_point": "https://www.mercadopago.com.mx/checkout/v1/redirect?pref=x"})
        mp_id = url.rsplit("/", 1)[1]
        return Resp(200, self.pagos[mp_id]) if mp_id in self.pagos else Resp(404, {"message": "not found"})


@pytest.fixture()
def mp(monkeypatch):
    import requests
    sim = MercadoPagoSimulado()
    monkeypatch.setattr(requests, "request", sim)
    monkeypatch.setattr(settings, "mp_access_token", "TEST-llave")
    monkeypatch.setattr(settings, "mp_webhook_secret", None)
    return sim


def _saldo(uid):
    with SessionLocal() as db:
        return db.get(Usuario, uid).timbres


def test_comprar_timbres_se_abona_una_sola_vez(mp):
    with TestClient(app) as c:
        admin, _e = _preparar(c)
        h = _usuario(c, admin, "compra@prueba.mx", "compra")
        yo = c.get("/api/auth/yo", headers=h).json()
        antes = yo["timbres"]
        info = c.get("/api/pagos/paquetes", headers=h).json()
        assert info["activo"] and [p["clave"] for p in info["paquetes"]] == ["p30", "p100", "p300", "p1000"]
        assert c.post("/api/pagos", headers=h, json={"paquete": "no-existe"}).status_code == 422
        assert c.post("/api/pagos", headers=admin, json={"paquete": "p30"}).status_code == 422   # el admin no compra

        r = c.post("/api/pagos", headers=h, json={"paquete": "p30"})
        assert r.status_code == 200 and r.json()["url"].startswith("https://www.mercadopago.com.mx/"), r.text
        pid = r.json()["pago_id"]
        pref = mp.preferencias[-1]
        assert pref["external_reference"] == str(pid) and pref["items"][0]["unit_price"] == 50 and pref["items"][0]["currency_id"] == "MXN"
        assert "notification_url" not in pref     # http (local): Mercado Pago no avisaría a localhost

        # aviso falso: el pago no existe en Mercado Pago → nada
        assert c.post("/api/pagos/aviso?type=payment&data.id=999", json={}).status_code == 502
        # pendiente → no abona
        mp.pagos["111"] = {"status": "in_process", "external_reference": str(pid), "transaction_amount": 50, "currency_id": "MXN"}
        c.post("/api/pagos/aviso", json={"type": "payment", "data": {"id": "111"}})
        assert _saldo(yo["id"]) == antes
        # monto menor → no abona
        mp.pagos["112"] = {"status": "approved", "external_reference": str(pid), "transaction_amount": 1, "currency_id": "MXN"}
        c.post("/api/pagos/aviso", json={"type": "payment", "data": {"id": "112"}})
        assert _saldo(yo["id"]) == antes
        # aprobado: abona 30, y repetir el aviso (o regresar de Mercado Pago) no vuelve a abonar
        mp.pagos["113"] = {"status": "approved", "external_reference": str(pid), "transaction_amount": 50, "currency_id": "MXN"}
        for _ in range(3):
            assert c.post("/api/pagos/aviso?type=payment&data.id=113", json={}).status_code == 200
        r = c.post("/api/pagos/regreso", headers=h, json={"pago": pid, "payment_id": "113"}).json()
        assert r["estado"] == "aprobado" and r["timbres_cuenta"] == antes + 30
        assert _saldo(yo["id"]) == antes + 30
        assert c.post("/api/pagos/regreso", headers=admin, json={"pago": pid}).status_code == 404   # pago ajeno
        mios = c.get("/api/pagos", headers=h).json()
        assert mios[0]["id"] == pid and mios[0]["estado"] == "aprobado"
        assert c.get("/api/pagos", headers=admin).json() == [] or all(p["id"] != pid for p in c.get("/api/pagos", headers=admin).json())
        mov = c.get("/api/auth/timbres", headers=h).json()["movimientos"][0]
        assert mov["cantidad"] == 30 and "Mercado Pago 113" in mov["motivo"] and mov["restantes"] == 30 and mov["vence"]


def test_aviso_con_firma(mp, monkeypatch):
    with TestClient(app) as c:
        monkeypatch.setattr(settings, "mp_webhook_secret", "secreto")
        assert c.post("/api/pagos/aviso?type=payment&data.id=5", json={}, headers={"x-signature": "ts=1,v1=malo", "x-request-id": "r"}).status_code == 401
        firma = hmac.new(b"secreto", b"id:5;request-id:r;ts:1;", hashlib.sha256).hexdigest()
        r = c.post("/api/pagos/aviso?type=payment&data.id=5", json={}, headers={"x-signature": f"ts=1,v1={firma}", "x-request-id": "r"})
        assert r.status_code == 502   # firma buena; el pago 5 no existe en el simulador


def test_las_recargas_vencen_a_los_12_meses():
    with TestClient(app) as c:
        admin, _e = _preparar(c)
        h = _usuario(c, admin, "vence@prueba.mx", "vence")
        uid = c.get("/api/auth/yo", headers=h).json()["id"]
        with SessionLocal() as db:
            u = db.get(Usuario, uid)
            u.timbres = 3            # los 3 de regalo no vencen
            db.query(MovimientoTimbres).filter_by(usuario_id=uid).delete()
            db.commit()
            timbres.recargar(db, uid, 10, "Lote viejo", None)
            timbres.recargar(db, uid, 5, "Lote nuevo", None)
            viejo = db.query(MovimientoTimbres).filter_by(usuario_id=uid, motivo="Lote viejo").one()
            assert viejo.vence > datetime.now() + timedelta(days=360) and viejo.restantes == 10
            # gasta 4: salen del lote que vence antes
            for _ in range(4):
                db.query(Usuario).filter_by(id=uid).update({"timbres": Usuario.timbres - 1})
                timbres._gastar_de_lotes(db, uid, 1)
            db.commit()
            db.refresh(viejo)
            assert viejo.restantes == 6 and _saldo(uid) == 14
            # pasa un año: vencen los 6 que quedaban del lote viejo, nada más
            viejo.vence = datetime.now() - timedelta(days=1)
            db.commit()
            assert timbres.vencer(db) == 6
            assert _saldo(uid) == 8 and timbres.vencer(db) == 0
            ultimo = db.query(MovimientoTimbres).filter_by(usuario_id=uid).order_by(MovimientoTimbres.id.desc()).first()
            assert ultimo.cantidad == -6 and ultimo.motivo.startswith("Vencieron")
            # una corrección negativa del admin sale de los lotes
            timbres.recargar(db, uid, -2, "Corrección", None)
            nuevo = db.query(MovimientoTimbres).filter_by(usuario_id=uid, motivo="Lote nuevo").one()
            assert nuevo.restantes == 3 and _saldo(uid) == 6
            assert timbres.proximo_vencimiento(db, uid)["timbres"] == 3
        with SessionLocal() as db:
            db.query(Pago).filter_by(usuario_id=uid).delete()
            db.commit()
