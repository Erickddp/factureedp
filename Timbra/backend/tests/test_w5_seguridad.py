"""Seguridad para producción: sesiones, intentos de acceso, plantillas de addenda aisladas, XML ajeno, tamaño y caché."""
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import auth, sat  # noqa: E402
from app.services import addenda  # noqa: E402
from test_v2 import _preparar  # noqa: E402
from test_w1_cuentas import _entrar, _usuario  # noqa: E402


@pytest.fixture(autouse=True)
def _sin_bloqueos():
    auth._FALLOS.clear()
    yield
    auth._FALLOS.clear()


def test_cambiar_la_contrasena_cierra_las_demas_sesiones():
    with TestClient(app) as c:
        admin, _ = _preparar(c)
        _usuario(c, admin, "sesiones@prueba.mx", "sesiones")
        celular = _entrar(c, "sesiones", "claveLarga1")   # sesión abierta en otro equipo
        oficina = _entrar(c, "sesiones", "claveLarga1")
        assert c.get("/api/emisores", headers=celular).status_code == 200
        r = c.post("/api/auth/password", headers=oficina, json={"actual": "claveLarga1", "nueva": "otraClaveLarga2"})
        assert r.status_code == 200 and r.json()["token"]
        # la del otro equipo deja de valer; la que hizo el cambio sigue con su token nuevo
        assert c.get("/api/emisores", headers=celular).status_code == 401
        assert c.get("/api/emisores", headers=oficina).status_code == 401
        nuevo = {"Authorization": "Bearer " + r.json()["token"]}
        assert c.get("/api/emisores", headers=nuevo).status_code == 200
        assert c.post("/api/auth/login", json={"email": "sesiones", "password": "claveLarga1"}).status_code == 401
        # se deja como estaba para las demás pruebas
        assert c.post("/api/auth/password", headers=nuevo, json={"actual": "otraClaveLarga2", "nueva": "claveLarga1"}).status_code == 200
        # una cuenta desactivada pierde la sesión de inmediato
        yo = next(u for u in c.get("/api/auth/usuarios", headers=admin).json() if u["usuario"] == "sesiones")
        vivo = _entrar(c, "sesiones", "claveLarga1")
        assert c.put(f"/api/auth/usuarios/{yo['id']}/activo", headers=admin, json={"activo": False}).status_code == 200
        assert c.get("/api/emisores", headers=vivo).status_code == 401
        assert c.put(f"/api/auth/usuarios/{yo['id']}/activo", headers=admin, json={"activo": True}).status_code == 200


def test_intentos_de_acceso_se_frenan_por_equipo_y_por_cuenta():
    with TestClient(app) as c:
        admin, _ = _preparar(c)
        _usuario(c, admin, "frenos@prueba.mx", "frenos")
        for _ in range(6):
            assert c.post("/api/auth/login", json={"email": "frenos", "password": "mala"}).status_code == 401
        r = c.post("/api/auth/login", json={"email": "frenos", "password": "claveLarga1"})
        assert r.status_code == 429 and "Espera" in r.json()["detail"]   # ni con la buena, desde ESE equipo
        # desde otro equipo el dueño sí entra: un extraño no lo deja fuera
        otro = TestClient(app, client=("203.0.113.9", 5000))
        assert otro.post("/api/auth/login", json={"email": "frenos", "password": "claveLarga1"}).status_code == 200
        # un mismo equipo no puede ir probando cuenta por cuenta
        auth._FALLOS.clear()
        codigos = [c.post("/api/auth/login", json={"email": f"nadie{i}@x.mx", "password": "x"}).status_code for i in range(32)]
        assert codigos[:30] == [401] * 30 and codigos[30:] == [429, 429]
        assert c.post("/api/auth/login", json={"email": "frenos", "password": "claveLarga1"}).status_code == 429
        # ni se dice si la cuenta existe: mismo mensaje para cuenta inexistente y contraseña mala
        auth._FALLOS.clear()
        a = c.post("/api/auth/login", json={"email": "frenos", "password": "mala"}).json()["detail"]
        b = c.post("/api/auth/login", json={"email": "no-existe@x.mx", "password": "mala"}).json()["detail"]
        assert a == b


def test_una_plantilla_de_addenda_no_puede_tocar_el_servidor():
    # lo normal sigue funcionando
    el = addenda.render("<Oc><Num>{{ datos.oc }}</Num><T>{{ cfdi.Total }}</T></Oc>", {"oc": "A&B <1>"}, {"Total": "116.00"})
    assert el.find("Num").text == "A&B <1>" and el.find("T").text == "116.00"
    # los trucos para salir de la plantilla y ejecutar código o leer la configuración, no
    for mala in ("<x>{{ ''.__class__.__mro__[1].__subclasses__() }}</x>",
                 "<x>{{ datos.__class__.__init__.__globals__ }}</x>",
                 "<x>{{ cycler.__init__.__globals__.os.popen('whoami').read() }}</x>",
                 "<x>{{ lipsum.__globals__['os'].environ }}</x>"):
        with pytest.raises(addenda.AddendaError):
            addenda.render(mala, {}, {})
    # ni un XML con entidades hace que el servidor lea sus propios archivos
    secreto = os.path.abspath(os.path.join("_test_datos", "secreto.txt"))
    open(secreto, "w").write("LLAVE-QUE-NO-DEBE-SALIR")
    try:
        xxe = f'<!DOCTYPE a [<!ENTITY e SYSTEM "file:///{secreto.replace(os.sep, "/")}">]><a>&e;</a>'
        try:
            from lxml import etree
            salida = etree.tostring(addenda.render(xxe, {}, {})).decode()
        except addenda.AddendaError:
            salida = ""
        assert "LLAVE-QUE-NO-DEBE-SALIR" not in salida
    finally:
        os.remove(secreto)


def test_addendas_solo_las_administra_el_administrador():
    with TestClient(app) as c:
        admin, _ = _preparar(c)
        usuario = _usuario(c, admin, "addendas@prueba.mx", "addendasx")
        cuerpo = {"nombre": "Prueba de permisos", "descripcion": "x", "plantilla": "<A>{{ datos.oc }}</A>", "campos": []}
        assert c.get("/api/addendas", headers=usuario).status_code == 200            # usarlas, sí
        assert c.post("/api/addendas", headers=usuario, json=cuerpo).status_code == 403
        assert c.post("/api/addendas/probar", headers=usuario, json={"plantilla": "<A/>"}).status_code == 403
        assert c.post("/api/addendas/probar", headers=admin, json={"plantilla": "<A>{{ datos.oc }}</A>", "datos": {"oc": "7"}}).json()["xml"].strip() == "<A>7</A>"
        assert c.post("/api/addendas/probar", headers=admin, json={}).status_code == 422
        assert c.post("/api/addendas/probar", headers=admin, json={"plantilla": "<x>{{ ''.__class__.__mro__ }}</x>"}).status_code == 422


def test_xml_ajeno_con_entidades_se_rechaza_y_la_efirma_no_se_guarda_en_web(monkeypatch):
    with TestClient(app) as c:
        h, e = _preparar(c)
        malo = b'<?xml version="1.0"?><!DOCTYPE c [<!ENTITY x SYSTEM "file:///etc/passwd">]><c>&x;</c>'
        r = c.post(f"/api/sat/importar-xml/{e['id']}", headers=h, files=[("archivos", ("malo.xml", malo, "text/xml"))])
        assert r.status_code == 200 and r.json() == {"nuevos": 0, "errores": 1}
        monkeypatch.setattr(sat, "EN_WEB", True)
        r = c.post(f"/api/sat/fiel/{e['id']}", headers=h, data={"password": "x"},
                   files={"cer": ("a.cer", b"x"), "key": ("a.key", b"x")})
        assert r.status_code == 409 and "e.firma" in r.json()["detail"]


def test_tamano_maximo_cache_y_compresion():
    with TestClient(app) as c:
        h, e = _preparar(c)
        # un envío gigante se corta antes de leerlo
        r = c.post("/api/lotes", headers={**h, "Content-Length": str(60 * 1024 * 1024)}, content=b"x")
        assert r.status_code == 413
        # los datos nunca se guardan en caché; los archivos con huella en el nombre, para siempre
        r = c.get(f"/api/clientes?emisor_id={e['id']}", headers=h)
        assert r.headers["cache-control"] == "no-store"
        estaticos = os.path.join("static", "_next", "static", "chunks")
        if os.path.isdir(estaticos):
            js = next(f for f in sorted(os.listdir(estaticos)) if f.endswith(".js") and os.path.getsize(os.path.join(estaticos, f)) > 5000)
            r = c.get(f"/_next/static/chunks/{js}", headers={"Accept-Encoding": "gzip"})
            assert r.status_code == 200 and "immutable" in r.headers["cache-control"] and r.headers.get("content-encoding") == "gzip"
            r = c.get("/inicio/")
            assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
        # sin sesión no hay nada: ni datos ni respaldos ni registros
        for ruta in ("/api/emisores", f"/api/clientes?emisor_id={e['id']}", "/api/facturas?emisor_id=1", "/api/debug/respaldo",
                     "/api/debug/logs", "/api/auth/usuarios", "/api/lotes?emisor_id=1", "/api/pacs", "/api/correo"):
            assert c.get(ruta).status_code in (401, 403), ruta
        assert c.get("/api/emisores", headers={"Authorization": "Bearer no.es.un.token"}).status_code == 401
