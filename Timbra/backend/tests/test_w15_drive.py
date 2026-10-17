"""Copia de XML a Google Drive (services/drive.py). Google se simula: nunca se toca el Drive real.
Sólo XML, cada uno una vez, sólo los de la cuenta, nada de facturas de práctica, y el permiso retirado se nota."""
import os
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services import drive  # noqa: E402
from app.services.xml_indice import carpeta_xml  # noqa: E402
from test_v2 import _cliente, _factura, _preparar  # noqa: E402
from test_w1_cuentas import _emisor, _usuario  # noqa: E402

UUID_SAT = "11111111-2222-3333-4444-555555555555"


class R:
    def __init__(self, status, cuerpo=None, texto=""):
        self.status_code, self._c, self.text = status, cuerpo or {}, texto or str(cuerpo)

    def json(self):
        return self._c


class GoogleFalso:
    """Token, renovación, revocación y Drive (carpetas + subidas) en memoria."""

    def __init__(self):
        self.archivos: dict[str, tuple[str, str | None]] = {}  # id -> (nombre, padre)
        self.revocados, self.retirado = [], False

    def post(self, url, data=None, timeout=None, **_):
        if url == drive.TOKEN and data.get("grant_type") == "authorization_code":
            idt = jwt.encode({"email": "rick.drive@gmail.com"}, "x", algorithm="HS256")
            return R(200, {"access_token": "a1", "refresh_token": "r1", "id_token": idt, "scope": f"openid email {drive.ALCANCE}"})
        if url == drive.TOKEN:
            return R(400, texto='{"error": "invalid_grant"}') if self.retirado else R(200, {"access_token": "a2"})
        if url == drive.REVOCAR:
            self.revocados.append(data["token"])
            return R(200)
        raise AssertionError(url)

    def Client(self, **_):  # noqa: N802 - imita httpx.Client
        g = self

        class Cli:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, params=None, json=None, content=None, headers=None):
                nid = f"id{len(g.archivos) + 1}"
                if url == drive.ARCHIVOS:  # carpeta
                    g.archivos[nid] = (json["name"], (json.get("parents") or [None])[0])
                else:  # subida multipart: el nombre y el padre van en la parte JSON
                    import json as _j
                    meta = _j.loads(content.split(b"\r\n\r\n", 1)[1].split(b"\r\n", 1)[0])
                    assert b"<cfdi:Comprobante" in content
                    g.archivos[nid] = (meta["name"], meta["parents"][0])
                return R(200, {"id": nid})
        return Cli()

    def ruta(self, aid):
        nombre, padre = self.archivos[aid]
        return f"{self.ruta(padre)}/{nombre}" if padre else nombre

    def xml(self):
        return sorted(self.ruta(i) for i, (n, _) in self.archivos.items() if n.endswith(".xml"))


@pytest.fixture()
def google(monkeypatch):
    g = GoogleFalso()
    monkeypatch.setattr(settings, "google_client_id", "cliente-pruebas")
    monkeypatch.setattr(settings, "google_client_secret", "secreto-pruebas")
    monkeypatch.setattr(drive, "httpx", SimpleNamespace(post=g.post, Client=g.Client))
    monkeypatch.setattr(drive, "lanzar", lambda uid: drive.sincronizar(uid) is not None)  # sin hilos en la prueba
    return g


def test_drive_copia_solo_los_xml_de_la_cuenta_una_vez(google):
    with TestClient(app) as c:
        h, e = _preparar(c)
        # una factura timbrada con el PAC demo: es de práctica, NO va a Drive
        _factura(c, h, e, _cliente(c, h, e))
        # un XML bajado del SAT, en la carpeta de siempre
        d = carpeta_xml(e["id"]) / "202610 EKU9" / "recibidos"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{UUID_SAT}.xml").write_bytes(b'<?xml version="1.0"?><cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"/>')
        locales = sorted(p.relative_to(carpeta_xml(e["id"])) for p in carpeta_xml(e["id"]).rglob("*.xml"))

        assert c.get("/api/drive", headers=h).json()["conectado"] is False
        url = c.post("/api/drive/conectar", headers=h).json()["url"]
        q = parse_qs(urlparse(url).query)
        assert drive.ALCANCE in q["scope"][0] and q["access_type"] == ["offline"]
        assert "drive.readonly" not in url and "spreadsheets" not in url  # sólo el permiso no sensible

        r = c.get("/api/auth/google/callback", params={"code": "c0d", "state": q["state"][0]}, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].endswith("/sat/#drive=ok"), r.headers.get("location")
        # el state de Drive no abre sesión: no hay token en el regreso
        assert "token=" not in r.headers["location"]

        subidos = google.xml()
        assert f"Timbra/EKU9003173C9/202610/recibidos/{UUID_SAT}.xml" in subidos
        assert len(subidos) == len(locales)  # todos los del SAT y ninguno de práctica
        assert all(s.startswith("Timbra/EKU9003173C9/") for s in subidos)
        assert not any(s.endswith(".pdf") for s in subidos)
        est = c.get("/api/drive", headers=h).json()
        assert est["conectado"] and est["correo"] == "rick.drive@gmail.com" and est["subidos"] == len(locales) and est["faltan"] == 0

        # copiar otra vez no sube nada repetido
        assert c.post("/api/drive/sincronizar", headers=h).status_code == 200
        assert google.xml() == subidos

        # otra cuenta no ve el Drive de ésta ni le toca nada
        otra = _usuario(c, h, "drive.otra@ejemplo.com", "driveotra")
        _emisor(c, otra, "XIA190128J61", "XENON INDUSTRIAL ARTICLES")
        assert c.get("/api/drive", headers=otra).json()["conectado"] is False
        assert c.post("/api/drive/sincronizar", headers=otra).status_code == 409

        # si el dueño quita el permiso en Google, se marca para volver a conectar
        google.retirado = True
        (d / "99999999-2222-3333-4444-555555555555.xml").write_bytes(b'<cfdi:Comprobante xmlns:cfdi="x"/>')
        c.post("/api/drive/sincronizar", headers=h)
        est = c.get("/api/drive", headers=h).json()
        assert est["estado"] == "revocada" and "Vuelve a conectar" in est["error"] and est["faltan"] == 1

        # desconectar revoca el token y olvida; lo que ya está en Drive se queda
        assert c.delete("/api/drive", headers=h).status_code == 200
        assert google.revocados == ["r1"] and c.get("/api/drive", headers=h).json()["conectado"] is False
        (d / "99999999-2222-3333-4444-555555555555.xml").unlink()


def test_drive_cancelado_en_google_regresa_con_aviso(google):
    with TestClient(app) as c:
        h, _ = _preparar(c)
        q = parse_qs(urlparse(c.post("/api/drive/conectar", headers=h).json()["url"]).query)
        r = c.get("/api/auth/google/callback", params={"error": "access_denied", "state": q["state"][0]}, follow_redirects=False)
        assert r.status_code == 302 and "/sat/#drive_error=" in r.headers["location"]
