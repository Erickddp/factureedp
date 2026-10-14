"""Términos de uso y aviso de privacidad: cada cuenta los acepta una vez por versión y queda constancia."""
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app import legal  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Usuario  # noqa: E402
from test_w1_cuentas import _entrar, _usuario  # noqa: E402


def test_cuenta_nueva_acepta_terminos_y_queda_constancia():
    with TestClient(app) as c:
        assert c.get("/api/auth/config").json()["terminos"] == legal.TERMINOS_VERSION
        admin = _entrar(c, "rick@erickddp.com", "cambiame")
        assert c.get("/api/auth/yo", headers=admin).json()["terminos"]["pendiente"] is False  # el proveedor no acepta sus propios términos

        h = _usuario(c, admin, "legal@ejemplo.mx", "cuentalegal")
        t = c.get("/api/auth/yo", headers=h).json()["terminos"]
        assert t["pendiente"] is True and t["aceptada"] is None

        # Una versión vieja (pantalla abierta desde antes del cambio) no cuenta
        assert c.post("/api/auth/terminos", headers=h, json={"version": "1999-01-01"}).status_code == 409
        r = c.post("/api/auth/terminos", headers=h, json={"version": legal.TERMINOS_VERSION})
        assert r.status_code == 200, r.text
        assert r.json()["terminos"]["pendiente"] is False
        with SessionLocal() as db:
            u = db.query(Usuario).filter_by(usuario="cuentalegal").one()
            assert u.terminos_version == legal.TERMINOS_VERSION and u.terminos_aceptados and u.terminos_ip

        # Si los términos cambian, se piden otra vez
        vieja = legal.TERMINOS_VERSION
        try:
            legal.TERMINOS_VERSION = "2099-01-01"
            assert legal.pendiente(u) is True
        finally:
            legal.TERMINOS_VERSION = vieja


def test_sin_sesion_no_se_aceptan():
    with TestClient(app) as c:
        assert c.post("/api/auth/terminos", json={"version": legal.TERMINOS_VERSION}).status_code == 401


def test_la_version_del_front_es_la_del_servidor():
    """Si sólo se sube una, la pantalla manda una versión que el servidor rechaza y nadie puede aceptar."""
    import re
    from pathlib import Path
    ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "legal.ts"
    if not ts.exists():  # instalador sin el código del front
        return
    assert re.search(r'VERSION = "([^"]+)"', ts.read_text(encoding="utf-8")).group(1) == legal.TERMINOS_VERSION
