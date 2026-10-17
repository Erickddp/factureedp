"""Mis datos: lo que guarda Timbra de la cuenta, casilla de novedades y cerrar la cuenta uno mismo."""
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Usuario  # noqa: E402
from test_v2 import _preparar  # noqa: E402
from test_w1_cuentas import _usuario  # noqa: E402


def test_mis_datos_novedades_y_cierre_de_cuenta():
    with SessionLocal() as db:  # la base de pruebas se reutiliza: la cuenta que este test cierra se reabre para la siguiente corrida
        for u in db.query(Usuario).filter(Usuario.email.in_(["datos-ana@personas.mx", "datos-beto@personas.mx"])):
            u.activo, u.cierre_solicitado = True, None
        db.commit()
    with TestClient(app) as c:
        admin, _e = _preparar(c)
        ana = _usuario(c, admin, "datos-ana@personas.mx", "datos.ana")
        beto = _usuario(c, admin, "datos-beto@personas.mx", "datos.beto")
        c.post("/api/emisores", headers=ana, json={"rfc": "XAXX010101000", "nombre": "DE ANA", "regimen_fiscal": "601", "lugar_expedicion": "42501"})

        r0 = c.get("/api/mis-datos", headers=ana); assert r0.status_code == 200, r0.text
        d = r0.json()
        assert d["cuenta"]["email"] == "datos-ana@personas.mx" and d["guardado"]["emisores"] == 1 and d["novedades"] is False
        assert c.get("/api/mis-datos", headers=beto).json()["guardado"]["emisores"] == 0     # cada cuenta cuenta lo suyo
        assert d["aceptacion"]["vigente"]

        assert c.put("/api/mis-datos/novedades", headers=ana, json={"acepta": True}).json()["novedades"] is True
        assert c.get("/api/mis-datos", headers=ana).json()["novedades"] is True
        assert c.put("/api/mis-datos/novedades", headers=ana, json={"acepta": False}).json()["novedades"] is False

        # cerrar: pide escribir el correo; el administrador no se cierra por aquí
        assert c.post("/api/mis-datos/cerrar", headers=ana, json={"confirmar": "otro@x.mx"}).status_code == 422
        assert c.post("/api/mis-datos/cerrar", headers=admin, json={"confirmar": "admin"}).status_code in (403, 422)
        assert c.post("/api/mis-datos/cerrar", headers=ana, json={"confirmar": " DATOS-ANA@personas.mx "}).json() == {"ok": True}
        assert c.get("/api/mis-datos", headers=ana).status_code == 401                        # ya no entra
        assert c.post("/api/auth/login", json={"email": "datos.ana", "password": "claveLarga1"}).status_code in (401, 403)
        with SessionLocal() as db:
            u = db.query(Usuario).filter_by(email="datos-ana@personas.mx").one()
            assert u.activo is False and u.cierre_solicitado is not None
        assert c.get("/api/mis-datos", headers=beto).status_code == 200                       # la otra cuenta sigue igual
