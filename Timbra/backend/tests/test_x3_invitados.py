"""Modo invitado: entra sin registrarse, explora y baja XML, no timbra ni guarda; a la hora se borra; puede crear su cuenta conservando todo."""
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
from app.models import Emisor, Usuario, XmlCfdi  # noqa: E402
from app.routers import auth  # noqa: E402
from app.services import invitados  # noqa: E402
from test_v2 import _preparar  # noqa: E402


@pytest.fixture(autouse=True)
def registro_abierto(monkeypatch):
    monkeypatch.setattr(settings, "registro_abierto", True)
    auth._GOLPES.clear()


def _entrar(c):
    r = c.post("/api/auth/invitado", json={"acepto": True})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_invitado_explora_baja_xml_pero_no_timbra_ni_guarda():
    with TestClient(app) as c:
        assert c.post("/api/auth/invitado", json={"acepto": False}).status_code == 422  # sin aceptar no entra
        h = _entrar(c)
        yo = c.get("/api/auth/yo", headers=h).json()
        assert yo["invitado"] is True and yo["timbres"] == 0 and yo["expira"]
        assert c.get("/api/emisores", headers=h).json() == []                          # explora: ve lo suyo, que es nada

        # puede dar de alta un emisor (la e.firma/constancia lo necesitan) y tener sus gastos
        e = c.post("/api/emisores", headers=h, json={"rfc": "XIA190128J61", "nombre": "XENON INDUSTRIAL ARTICLES", "regimen_fiscal": "601", "lugar_expedicion": "42501"})
        assert e.status_code == 200, e.text
        assert c.get("/api/deducibles", headers=h, params={"emisor_id": e.json()["id"]}).status_code == 200
        assert c.post("/api/facturas/preview", headers=h, json={"emisor_id": e.json()["id"], "conceptos": []}).status_code in (200, 422)

        # lo que no puede: timbrar, subir CSD, PAC, correo, Drive, cancelar… con el mensaje que abre «Crea tu cuenta»
        for metodo, ruta in (("post", "/api/facturas"), ("post", "/api/facturas/pagos"), ("post", f"/api/emisores/{e.json()['id']}/csd"),
                             ("post", "/api/pacs"), ("post", "/api/drive/conectar"), ("post", "/api/facturas/1/cancelar"),
                             ("post", "/api/lotes/1/ejecutar"), ("post", "/api/nomina/timbrar"), ("post", "/api/auth/password")):
            r = getattr(c, metodo)(ruta, headers=h, json={})
            assert r.status_code == 403 and "Crea tu cuenta" in r.text, (ruta, r.status_code, r.text)


def test_invitado_aislado_y_sin_rastro_al_vencer():
    with TestClient(app) as c:
        admin, e0 = _preparar(c)
        h = _entrar(c)
        e = c.post("/api/emisores", headers=h, json={"rfc": "CACX7605101P8", "nombre": "CACTUS", "regimen_fiscal": "612", "lugar_expedicion": "42501"}).json()
        with SessionLocal() as db:
            db.add(XmlCfdi(emisor_id=e["id"], uuid="INV-0001", tipo="Recibido", fecha="2026-10-05 10:00:00", filas=[], busca=""))
            db.commit()
        # no ve lo del administrador ni éste lo suyo
        assert [x["rfc"] for x in c.get("/api/emisores", headers=h).json()] == ["CACX7605101P8"]
        assert c.get("/api/deducibles", headers=h, params={"emisor_id": e0["id"]}).status_code == 404

        # su hora pasa: la sesión ya no sirve y el programador lo borra con todo lo suyo
        with SessionLocal() as db:
            uid = db.query(Usuario).filter(Usuario.invitado.is_(True)).order_by(Usuario.id.desc()).first()
            uid.expira = datetime.now() - timedelta(minutes=1)
            db.commit()
        assert c.get("/api/auth/yo", headers=h).status_code == 401
        with SessionLocal() as db:
            assert invitados.purgar(db) >= 1
            assert db.query(Emisor).filter(Emisor.rfc == "CACX7605101P8").count() == 0
            assert db.query(XmlCfdi).filter(XmlCfdi.uuid == "INV-0001").count() == 0
        # el administrador y lo suyo siguen
        assert c.get("/api/emisores", headers=admin).status_code == 200


def test_invitado_crea_su_cuenta_y_conserva_lo_que_traia():
    with TestClient(app) as c:
        h = _entrar(c)
        e = c.post("/api/emisores", headers=h, json={"rfc": "FUNK671228PH6", "nombre": "KARLA FUENTE NOLASCO", "regimen_fiscal": "612", "lugar_expedicion": "42501"}).json()
        malo = {"email": "a@ejemplo.mx", "password": "claveLarga1", "acepto": True}
        assert c.post("/api/auth/convertir", headers=h, json=malo).status_code == 422             # correo de relleno
        assert c.post("/api/auth/convertir", headers=h, json={**malo, "email": "nuevo.x3@correo-real.mx", "acepto": False}).status_code == 422
        r = c.post("/api/auth/convertir", headers=h, json={**malo, "email": "nuevo.x3@correo-real.mx", "nombre": "Nueva Persona"})
        assert r.status_code == 200, r.text
        h2 = {"Authorization": f"Bearer {r.json()['token']}"}
        yo = c.get("/api/auth/yo", headers=h2).json()
        assert yo["invitado"] is False and yo["expira"] is None and yo["email"] == "nuevo.x3@correo-real.mx"
        assert [x["id"] for x in c.get("/api/emisores", headers=h2).json()] == [e["id"]]            # conservó su emisor
        assert c.post("/api/auth/convertir", headers=h2, json={**malo, "email": "otro.x3@correo-real.mx"}).status_code == 409  # ya es normal
        assert c.get("/api/auth/yo", headers=h).status_code == 401                                  # el token viejo ya no sirve
        # ya no la borra el programador
        with SessionLocal() as db:
            assert invitados.purgar(db) == 0
            assert db.query(Usuario).filter(Usuario.email == "nuevo.x3@correo-real.mx").count() == 1


def test_sin_registro_abierto_no_hay_invitados(monkeypatch):
    monkeypatch.setattr(settings, "registro_abierto", False)
    with TestClient(app) as c:
        assert c.post("/api/auth/invitado", json={"acepto": True}).status_code == 403
        assert c.get("/api/auth/config").json()["invitado"] is False


def test_limite_de_invitados_por_equipo():
    with TestClient(app) as c:
        codigos = [c.post("/api/auth/invitado", json={"acepto": True}).status_code for _ in range(8)]
        assert codigos[:6] == [200] * 6 and 429 in codigos[6:]
