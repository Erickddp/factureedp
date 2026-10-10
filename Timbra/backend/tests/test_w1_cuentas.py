"""Cuentas separadas: cada usuario ve y toca sólo sus emisores; entrada con usuario o correo; Google."""
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Usuario  # noqa: E402
from app.routers import auth  # noqa: E402
from test_lotes import rfc_de_prueba  # noqa: E402
from test_v2 import _preparar  # noqa: E402
from test_v5_clientes import rfc_moral  # noqa: E402


def _entrar(c, quien, pwd):
    r = c.post("/api/auth/login", json={"email": quien, "password": pwd})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _usuario(c, admin, correo, usuario):
    r = c.post("/api/auth/usuarios", headers=admin, json={"email": correo, "usuario": usuario, "nombre": usuario, "password": "claveLarga1"})
    assert r.status_code in (200, 409), r.text
    return _entrar(c, usuario, "claveLarga1")  # entra con el NOMBRE DE USUARIO, no con el correo


def _emisor(c, h, rfc, nombre):
    r = c.post("/api/emisores", headers=h, json={"rfc": rfc, "nombre": nombre, "regimen_fiscal": "601", "lugar_expedicion": "42501"})
    if r.status_code == 409:
        return next(e for e in c.get("/api/emisores", headers=h).json() if e["rfc"] == rfc)
    assert r.status_code == 200, r.text
    return r.json()


def _estado(url: str) -> str:
    return url.split("state=")[1].split("&")[0]


def test_cada_cuenta_ve_solo_lo_suyo():
    with TestClient(app) as c:
        admin, e_admin = _preparar(c)
        ha = _usuario(c, admin, "ana@cuentas.mx", "ana.cuentas")
        hb = _usuario(c, admin, "beto@cuentas.mx", "beto.cuentas")
        ea = _emisor(c, ha, rfc_moral(41), "EMPRESA DE ANA")
        eb = _emisor(c, hb, rfc_moral(42), "EMPRESA DE BETO")

        # Listas: cada quien lo suyo; el admin, todo
        assert {e["rfc"] for e in c.get("/api/emisores", headers=ha).json()} == {ea["rfc"]}
        assert {e["rfc"] for e in c.get("/api/emisores", headers=hb).json()} == {eb["rfc"]}
        assert {ea["rfc"], eb["rfc"], e_admin["rfc"]} <= {e["rfc"] for e in c.get("/api/emisores", headers=admin).json()}

        # Ana da de alta un cliente
        cli = c.post("/api/clientes", headers=ha, json={"emisor_id": ea["id"], "rfc": rfc_de_prueba(51), "nombre": "CLIENTE DE ANA",
                                                         "regimen_fiscal": "612", "codigo_postal": "42501", "uso_cfdi": "G03"})
        assert cli.status_code == 200, cli.text
        cli = cli.json()
        # y ve el catálogo base que se crea con su emisor
        assert len(c.get(f"/api/productos?emisor_id={ea['id']}", headers=ha).json()) > 0

        # Beto no puede leer, ni por lista ni adivinando el número
        assert c.get(f"/api/emisores/{ea['id']}", headers=hb).status_code == 404
        assert c.get(f"/api/clientes?emisor_id={ea['id']}", headers=hb).json() == []
        assert c.get(f"/api/productos?emisor_id={ea['id']}", headers=hb).json() == []
        assert c.get(f"/api/facturas?emisor_id={e_admin['id']}", headers=hb).json() == []
        assert c.get(f"/api/clientes/recientes?emisor_id={ea['id']}", headers=hb).json() == []
        # ni escribir en lo de Ana
        r = c.post("/api/clientes", headers=hb, json={"emisor_id": ea["id"], "rfc": rfc_de_prueba(52), "nombre": "INTRUSO",
                                                       "regimen_fiscal": "612", "codigo_postal": "42501", "uso_cfdi": "G03"})
        assert r.status_code == 403, r.text
        assert c.put(f"/api/clientes/{cli['id']}", headers=hb, json={**cli, "nombre": "CAMBIADO"}).status_code == 404
        assert c.put(f"/api/emisores/{ea['id']}", headers=hb, json={"rfc": ea["rfc"], "nombre": "ROBADO", "regimen_fiscal": "601",
                                                                     "lugar_expedicion": "42501"}).status_code == 404
        # El cliente de Ana sigue intacto
        assert c.get(f"/api/clientes?emisor_id={ea['id']}", headers=ha).json()[0]["nombre"] == "CLIENTE DE ANA"

        # PAC: cada quien el suyo; Beto no puede usar el de Ana
        pa = c.post("/api/pacs", headers=ha, json={"nombre": "Demo de Ana", "proveedor": "demo"}).json()
        assert c.get("/api/pacs", headers=hb).json() == []
        r = c.put(f"/api/emisores/{eb['id']}", headers=hb, json={"rfc": eb["rfc"], "nombre": eb["nombre"], "regimen_fiscal": "601",
                                                                  "lugar_expedicion": "42501", "pac_id": pa["id"]})
        assert r.status_code == 403, r.text

        # Mismo RFC en otra cuenta: mensaje claro, no un error del sistema
        r = c.post("/api/emisores", headers=hb, json={"rfc": ea["rfc"], "nombre": "X", "regimen_fiscal": "601", "lugar_expedicion": "42501"})
        assert r.status_code == 409 and "otra cuenta" in r.json()["detail"]

        # Rutas de administrador
        assert c.get("/api/auth/usuarios", headers=hb).status_code == 403
        assert c.get("/api/debug/logs", headers=hb).status_code == 403
        assert c.put("/api/correo", headers=hb, json={"host": "smtp.x.mx", "user": "a@x.mx", "password": "x"}).status_code == 403
        assert c.post("/api/facturas/recuperar", headers=hb).status_code == 403
        assert any(u["usuario"] == "ana.cuentas" and u["emisores"] == 1 for u in c.get("/api/auth/usuarios", headers=admin).json())

        # Cuenta desactivada: su token deja de servir
        uid = next(u["id"] for u in c.get("/api/auth/usuarios", headers=admin).json() if u["usuario"] == "beto.cuentas")
        c.put(f"/api/auth/usuarios/{uid}/activo", headers=admin, json={"activo": False})
        assert c.get("/api/emisores", headers=hb).status_code == 401
        c.put(f"/api/auth/usuarios/{uid}/activo", headers=admin, json={"activo": True})


def test_google_entra_vincula_y_no_abre_registro(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "cliente-de-prueba")
    monkeypatch.setattr(settings, "google_client_secret", "secreto-de-prueba")
    identidad = {"sub": "g-123", "email": "persona@gmail.com", "email_verified": True, "name": "Persona"}
    monkeypatch.setattr(auth, "_canjear", lambda code: dict(identidad))
    with TestClient(app, follow_redirects=False) as c:
        admin, _ = _preparar(c)
        assert c.get("/api/auth/config").json() == {"google": True}
        url = c.get("/api/auth/google/entrar").json()["url"]
        assert "accounts.google.com" in url and "client_id=cliente-de-prueba" in url and "scope=openid+email+profile" in url

        # Sin cuenta en Timbra y con registro cerrado: no entra
        r = c.get(f"/api/auth/google/callback?code=x&state={_estado(url)}")
        assert r.status_code == 302 and "#error=" in r.headers["location"] and "token=" not in r.headers["location"]
        # `state` inventado: se rechaza
        assert "#error=" in c.get("/api/auth/google/callback?code=x&state=falso").headers["location"]

        # Vincular desde una sesión ya abierta y luego entrar con Google
        ha = _usuario(c, admin, "gina@cuentas.mx", "gina.cuentas")
        r = c.get(f"/api/auth/google/callback?code=x&state={_estado(c.get('/api/auth/google/vincular', headers=ha).json()['url'])}")
        assert "#token=" in r.headers["location"]
        assert c.get("/api/auth/yo", headers=ha).json()["google_email"] == "persona@gmail.com"
        r = c.get(f"/api/auth/google/callback?code=x&state={_estado(c.get('/api/auth/google/entrar').json()['url'])}")
        token = r.headers["location"].split("#token=")[1].split("&")[0]
        assert c.get("/api/auth/yo", headers={"Authorization": f"Bearer {token}"}).json()["usuario"] == "gina.cuentas"
        assert c.delete("/api/auth/google", headers=ha).json()["google_email"] is None
        with SessionLocal() as db:
            assert db.query(Usuario).filter_by(email="persona@gmail.com").first() is None  # no se creó cuenta sola
