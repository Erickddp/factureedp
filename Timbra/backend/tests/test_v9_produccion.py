"""Listos para producción: hora del CFDI según el CP de expedición y borrado de facturas de práctica (sólo demo)."""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Factura  # noqa: E402
from app.services import cfdi  # noqa: E402
from test_v2 import _preparar  # noqa: E402


def test_hora_del_cfdi_segun_cp_y_nunca_adelantada():
    assert str(cfdi.zona_de("42501")) == "America/Mexico_City"
    assert str(cfdi.zona_de("22000")) == "America/Tijuana"
    assert str(cfdi.zona_de("83000")) == "America/Mazatlan"
    assert str(cfdi.zona_de("77500")) == "America/Cancun"
    assert str(cfdi.zona_de("32330")) == "America/Matamoros"
    assert str(cfdi.zona_de("00000")) == "America/Mexico_City" and str(cfdi.zona_de(None)) == "America/Mexico_City"
    for cp in ("42501", "22000", "83000", "77500", "32330"):
        f = cfdi.ahora_mx(cp)
        oficial = datetime.now(cfdi.zona_de(cp)).replace(tzinfo=None)
        assert f <= oficial + timedelta(seconds=2), (cp, f, oficial)          # nunca en el futuro del huso del SAT
        assert oficial - f <= timedelta(hours=2, minutes=6), (cp, f, oficial)  # ni más de 2 h atrás
    # Tijuana va atrás de CDMX: con la hora de CDMX el PAC rechazaría por fecha futura
    assert cfdi.ahora_mx("22000") < datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None) - timedelta(minutes=50)


def test_borrar_practica_solo_quita_demo_y_regresa_folios():
    with TestClient(app) as c:
        h, e = _preparar(c)
        n = c.get(f"/api/emisores/{e['id']}/practica", headers=h).json()["facturas"]
        assert n > 0
        # Una factura "real" (sin el sello DEMO) no debe tocarse
        with SessionLocal() as db:
            f = db.query(Factura).filter(Factura.emisor_id == e["id"], Factura.serie == "A", Factura.tipo == "I").order_by(Factura.id).first()
            real_id, real_folio = f.id, int(f.folio)
            f.xml = f.xml.replace(b'SelloSAT="DEMO"', b'SelloSAT="REALxx"')
            db.commit()
        r = c.post(f"/api/emisores/{e['id']}/practica/borrar", headers=h).json()
        assert r["borradas"] == n - 1, r
        assert r["folios"]["A"] == real_folio + 1, r
        with SessionLocal() as db:
            quedan = db.query(Factura).filter(Factura.emisor_id == e["id"]).all()
            assert [x.id for x in quedan] == [real_id]
        assert c.get(f"/api/emisores/{e['id']}/practica", headers=h).json()["facturas"] == 0
        assert not c.post("/api/facturas/recuperar", headers=h).json()["recuperadas"]  # los XML de práctica ya no están en el respaldo


def test_correo_de_envio_se_configura_desde_la_app(monkeypatch):
    from app.services import mailer
    enviados = []

    class Falso:
        def __init__(self, host, port, timeout=None): self.host = host
        def starttls(self): pass
        def login(self, u, p): self.cred = (u, p)
        def send_message(self, m, to_addrs=None): enviados.append((self.cred, m["From"], m["To"]))
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(mailer.smtplib, "SMTP", Falso)
    with TestClient(app) as c:
        h, _ = _preparar(c)
        c.delete("/api/correo", headers=h)
        assert c.put("/api/correo", headers=h, json={"host": "smtp.gmail.com", "user": "facturas@ejemplo.mx", "password": ""}).status_code == 422
        r = c.put("/api/correo", headers=h, json={"host": "smtp.gmail.com", "port": 587, "user": "facturas@ejemplo.mx",
                                                  "password": "abcd efgh ijkl mnop", "nombre": "Facturación de prueba"}).json()
        assert r["configurado"] and r["tiene_password"] and "password" not in r
        guardado = open(mailer._ruta(), encoding="utf-8").read()
        assert "abcd" not in guardado and "abcdefghijklmnop" not in guardado  # cifrada en disco
        assert c.post("/api/correo/probar", headers=h, json={"para": "destino@ejemplo.mx"}).status_code == 200
        assert enviados[-1][0] == ("facturas@ejemplo.mx", "abcdefghijklmnop") and "Facturación de prueba" in enviados[-1][1]
        # cambiar el nombre sin volver a escribir la contraseña la conserva
        c.put("/api/correo", headers=h, json={"host": "smtp.gmail.com", "user": "facturas@ejemplo.mx", "nombre": "Otro"})
        assert mailer.config()["password"] == "abcdefghijklmnop"
        assert c.delete("/api/correo", headers=h).json()["configurado"] is False


def test_login_se_frena_tras_varios_fallos():
    from app.routers import auth
    with TestClient(app) as c:
        auth._FALLOS.clear()
        correo = "nadie@ejemplo.mx"
        for _ in range(auth._MAXIMO):
            assert c.post("/api/auth/login", json={"email": correo, "password": "x"}).status_code == 401
        assert c.post("/api/auth/login", json={"email": correo, "password": "x"}).status_code == 429
        h, _ = _preparar(c)  # otro correo no se ve afectado
        assert h["Authorization"]
        auth._FALLOS.clear()
