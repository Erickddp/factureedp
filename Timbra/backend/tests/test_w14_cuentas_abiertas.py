"""Cuentas que se crean solas (correo y contraseña, o Google), confirmar el correo, «olvidé mi contraseña» y que todo eso
quede en cuentas persistentes. El correo se captura: nunca sale uno de verdad."""
import os
import re

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import MovimientoTimbres, Usuario  # noqa: E402
from app.routers import auth  # noqa: E402
from app.services import mailer, timbres  # noqa: E402
from test_w1_cuentas import _entrar, _estado, _usuario  # noqa: E402
from test_v2 import _preparar  # noqa: E402


@pytest.fixture()
def correos(monkeypatch):
    """Registro abierto y el correo en una lista (para, asunto, cuerpo)."""
    enviados = []
    monkeypatch.setattr(mailer, "enviar", lambda para, asunto, cuerpo, adj, nombre=None, responder_a=None: enviados.append((para, asunto, cuerpo)))
    monkeypatch.setattr(settings, "registro_abierto", True)
    auth._GOLPES.clear()
    yield enviados
    auth._GOLPES.clear()


def _token_del_correo(correos, accion):
    return re.search(rf"#{accion}=([\w.-]+)", correos[-1][2]).group(1)


def _registro(c, correo="nueva@personas.mx", password="MiClaveLarga9", **extra):
    return c.post("/api/auth/registro", json={"email": correo, "password": password, "nombre": "Nueva Persona", "acepto": True, **extra})


def _timbres(correo):
    with SessionLocal() as db:
        return db.query(Usuario).filter_by(email=correo).one().timbres


def test_con_el_registro_cerrado_nadie_se_crea_solo(monkeypatch):
    monkeypatch.setattr(settings, "registro_abierto", False)
    with TestClient(app) as c:
        assert c.get("/api/auth/config").json()["registro"] is False
        assert _registro(c).status_code == 403


def test_registro_con_correo_confirmacion_y_timbres_de_regalo(correos):
    with TestClient(app) as c:
        assert c.get("/api/auth/config").json()["registro"] is True
        # lo que no se acepta, y por qué
        assert _registro(c, correo="no-es-correo").status_code == 422
        assert _registro(c, correo="alguien@ejemplo.mx").status_code == 422 and "ejemplo" in _registro(c, correo="alguien@ejemplo.mx").json()["detail"]
        assert _registro(c, password="corta").status_code == 422
        assert _registro(c, password="cambiame").status_code == 422
        assert _registro(c, password="nueva@personas.mx").status_code == 422
        r = _registro(c, acepto=False)
        assert r.status_code == 422 and "Términos" in r.json()["detail"]
        assert correos == []

        r = _registro(c)
        assert r.status_code == 200 and r.json()["correo_enviado"] is True, r.text
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        yo = c.get("/api/auth/yo", headers=h).json()
        assert yo["email"] == "nueva@personas.mx" and yo["correo_verificado"] is False and yo["timbres"] == 0 and yo["admin"] is False
        assert yo["terminos"]["aceptada"] == yo["terminos"]["vigente"] and not yo["terminos"]["pendiente"]   # aceptó al registrarse
        assert len(correos) == 1 and correos[0][0] == ["nueva@personas.mx"] and "Confirma" in correos[0][1] and "/login/#verificar=" in correos[0][2]
        assert _registro(c).status_code == 409                                     # el correo ya tiene cuenta
        assert _entrar(c, "nueva@personas.mx", "MiClaveLarga9")                     # y entra con correo y contraseña

        # sin confirmar el correo no se timbra con el PAC de la plataforma, y el mensaje dice qué hacer
        with SessionLocal() as db:
            u = db.query(Usuario).filter_by(email="nueva@personas.mx").one()
            original = timbres._cuenta_que_paga
            timbres._cuenta_que_paga = lambda db_, e_: u
            try:
                assert "Confirma tu correo" in timbres.sin_saldo(db, None)
            finally:
                timbres._cuenta_que_paga = original

        # un enlace inventado no sirve; el del correo sí, y los 3 timbres llegan UNA sola vez
        assert c.post("/api/auth/verificar", json={"token": "inventado"}).status_code == 400
        token = _token_del_correo(correos, "verificar")
        r = c.post("/api/auth/verificar", json={"token": token}).json()
        assert r["ok"] and not r["ya_estaba"] and r["timbres"] == 3
        assert c.post("/api/auth/verificar", json={"token": token}).json()["ya_estaba"] is True
        assert _timbres("nueva@personas.mx") == 3
        with SessionLocal() as db:
            assert db.query(MovimientoTimbres).filter_by(motivo="Cortesía de bienvenida").count() >= 1
            uid = db.query(Usuario).filter_by(email="nueva@personas.mx").one().id
            assert db.query(MovimientoTimbres).filter_by(usuario_id=uid, motivo="Cortesía de bienvenida").count() == 1
        yo = c.get("/api/auth/yo", headers=h).json()
        assert yo["correo_verificado"] is True and yo["timbres"] == 3
        assert c.post("/api/auth/reenviar-verificacion", headers=h).json()["ya_estaba"] is True


def test_reenviar_confirmacion_tiene_tope(correos):
    with TestClient(app) as c:
        h = {"Authorization": f"Bearer {_registro(c, correo='reenvia@personas.mx').json()['token']}"}
        estados = [c.post("/api/auth/reenviar-verificacion", headers=h).status_code for _ in range(4)]
        assert estados == [200, 200, 200, 429]
        assert len(correos) == 1 + 3


def test_el_registro_se_frena_por_equipo(correos):
    with TestClient(app) as c:
        estados = [_registro(c, correo=f"masivo{i}@personas.mx").status_code for i in range(7)]
        assert estados[:5] == [200] * 5 and estados[5:] == [429, 429]


def test_olvide_mi_contrasena_por_correo(correos):
    with TestClient(app) as c:
        admin, _e = _preparar(c)
        vieja = _usuario(c, admin, "olvida@personas.mx", "olvida.personas")
        # la respuesta es la misma exista o no la cuenta, y sólo se manda correo si existe
        assert c.post("/api/auth/olvide", json={"email": "nadie@personas.mx"}).json() == {"ok": True}
        assert correos == []
        assert c.post("/api/auth/olvide", json={"email": "olvida.personas"}).json() == {"ok": True}   # también con el usuario
        assert len(correos) == 1 and correos[0][0] == ["olvida@personas.mx"] and "/login/#restablecer=" in correos[0][2]
        token = _token_del_correo(correos, "restablecer")

        assert c.post("/api/auth/restablecer", json={"token": token, "nueva": "corta"}).status_code == 422
        assert c.post("/api/auth/restablecer", json={"token": "inventado", "nueva": "OtraClaveLarga7"}).status_code == 400
        r = c.post("/api/auth/restablecer", json={"token": token, "nueva": "OtraClaveLarga7"})
        assert r.status_code == 200, r.text
        nueva_sesion = {"Authorization": f"Bearer {r.json()['token']}"}
        assert c.get("/api/auth/yo", headers=nueva_sesion).status_code == 200
        assert c.get("/api/auth/yo", headers=vieja).status_code == 401            # la sesión de la contraseña anterior ya no vale
        assert c.post("/api/auth/login", json={"email": "olvida.personas", "password": "claveLarga1"}).status_code == 401
        assert _entrar(c, "olvida.personas", "OtraClaveLarga7")
        # el enlace sirve UNA vez
        assert c.post("/api/auth/restablecer", json={"token": token, "nueva": "TercerClaveLarga5"}).status_code == 400
        # y un enlace no es una sesión
        assert c.get("/api/auth/yo", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_olvide_se_frena_por_cuenta_y_por_equipo(correos):
    with TestClient(app) as c:
        admin, _e = _preparar(c)
        _usuario(c, admin, "frena@personas.mx", "frena.personas")
        for _ in range(5):
            assert c.post("/api/auth/olvide", json={"email": "frena@personas.mx"}).status_code == 200
        assert len(correos) == 3                                                  # a la cuenta sólo 3 correos por hora
        assert [c.post("/api/auth/olvide", json={"email": f"otro{i}@personas.mx"}).status_code for i in range(5)] == [200, 200, 200, 429, 429]


def test_google_crea_la_cuenta_persistente_y_luego_se_le_pone_contrasena(correos, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "cliente-de-prueba")
    monkeypatch.setattr(settings, "google_client_secret", "secreto-de-prueba")
    identidad = {"sub": "g-nueva-1", "email": "con.google@gmail.com", "email_verified": True, "name": "Con Google"}
    monkeypatch.setattr(auth, "_canjear", lambda code: dict(identidad))
    with TestClient(app, follow_redirects=False) as c:
        def entrar_con_google():
            r = c.get(f"/api/auth/google/callback?code=x&state={_estado(c.get('/api/auth/google/entrar').json()['url'])}")
            return r.headers["location"]
        destino = entrar_con_google()
        assert "#token=" in destino                                               # con el registro abierto, Google crea la cuenta
        token = destino.split("#token=")[1].split("&")[0]
        yo = c.get("/api/auth/yo", headers={"Authorization": f"Bearer {token}"}).json()
        assert yo["email"] == "con.google@gmail.com" and yo["correo_verificado"] is True and yo["timbres"] == 3
        # la segunda vez entra a LA MISMA cuenta (nada se duplica)
        entrar_con_google()
        with SessionLocal() as db:
            assert db.query(Usuario).filter_by(google_sub="g-nueva-1").count() == 1
        # sin contraseña: «Olvidé mi contraseña» le deja elegir una y entrar también sin Google
        c.post("/api/auth/olvide", json={"email": "con.google@gmail.com"})
        r = c.post("/api/auth/restablecer", json={"token": _token_del_correo(correos, "restablecer"), "nueva": "ClaveParaGoogle8"})
        assert r.status_code == 200
        assert _entrar(c, "con.google@gmail.com", "ClaveParaGoogle8")


def test_quien_se_registra_con_un_correo_ajeno_no_se_queda_con_la_cuenta_de_su_dueno(correos, monkeypatch):
    """Alguien crea «victima@gmail.com» con su contraseña antes de que la víctima se registre. Cuando la víctima entra con Google
    (que sí comprobó el correo), la contraseña del atacante se invalida y la cuenta es de la víctima."""
    monkeypatch.setattr(settings, "google_client_id", "cliente-de-prueba")
    monkeypatch.setattr(settings, "google_client_secret", "secreto-de-prueba")
    monkeypatch.setattr(auth, "_canjear", lambda code: {"sub": "g-victima", "email": "victima@gmail.com", "email_verified": True, "name": "Víctima"})
    with TestClient(app, follow_redirects=False) as c:
        atacante = _registro(c, correo="victima@gmail.com", password="ClaveDelAtacante1")
        assert atacante.status_code == 200
        sesion_atacante = {"Authorization": f"Bearer {atacante.json()['token']}"}
        r = c.get(f"/api/auth/google/callback?code=x&state={_estado(c.get('/api/auth/google/entrar').json()['url'])}")
        assert "#token=" in r.headers["location"]
        assert c.post("/api/auth/login", json={"email": "victima@gmail.com", "password": "ClaveDelAtacante1"}).status_code == 401
        assert c.get("/api/auth/yo", headers=sesion_atacante).status_code == 401  # y su sesión abierta tampoco vale
        assert _timbres("victima@gmail.com") == 3
