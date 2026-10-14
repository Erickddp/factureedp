"""Correo por la API de Resend (en el servidor: Railway Hobby bloquea SMTP). Nunca se toca Resend: se simula."""
import base64
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")  # nunca la carpeta de datos reales
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import mailer  # noqa: E402


class Resp:
    def __init__(self, status, cuerpo):
        self.status_code, self._cuerpo, self.text = status, cuerpo, str(cuerpo)

    def json(self):
        return self._cuerpo


def test_con_llave_sale_por_resend_con_el_nombre_del_emisor(monkeypatch):
    import requests
    enviados = []
    monkeypatch.setattr(settings, "resend_api_key", "re_prueba")
    monkeypatch.setattr(requests, "post", lambda url, json=None, headers=None, timeout=None: enviados.append((url, json, headers)) or Resp(200, {"id": "x"}))
    assert mailer.publica()["configurado"] is True and mailer.publica()["origen"] == "resend"
    mailer.enviar(["cliente@prueba.mx, "], "Factura A1 - EMPRESA", "Hola", [("a.xml", b"<x/>", "application/xml")],
                  nombre='EMPRESA "DE" PRUEBA', responder_a="dueno@empresa.mx")
    url, cuerpo, headers = enviados[0]
    assert url == "https://api.resend.com/emails" and headers["Authorization"] == "Bearer re_prueba"
    assert cuerpo["from"] == f"EMPRESA DE PRUEBA <{settings.correo_remitente}>"
    assert cuerpo["to"] == ["cliente@prueba.mx"] and cuerpo["reply_to"] == ["dueno@empresa.mx"]
    assert cuerpo["attachments"] == [{"filename": "a.xml", "content": base64.b64encode(b"<x/>").decode()}]

    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(403, {"message": "The erickddp.com domain is not verified"}))
    with pytest.raises(mailer.CorreoError, match="no está verificado"):
        mailer.enviar(["cliente@prueba.mx"], "x", "y", [])
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(401, {"message": "API key is invalid"}))
    with pytest.raises(mailer.CorreoError, match="RESEND_API_KEY"):
        mailer.enviar(["cliente@prueba.mx"], "x", "y", [])
    with pytest.raises(mailer.CorreoError, match="destino válido"):
        mailer.enviar(["sin-arroba"], "x", "y", [])


def test_respaldo_diario_sale_del_servidor_cifrado(monkeypatch, tmp_path):
    import io
    import os
    import zipfile

    import requests
    from fastapi.testclient import TestClient

    from app.main import app
    from app.security import decrypt
    from app.services import programador

    with TestClient(app):  # base creada y migrada
        pass
    enviados = []
    monkeypatch.setattr(requests, "post", lambda url, json=None, headers=None, timeout=None: enviados.append(json) or Resp(200, {"id": "x"}))
    monkeypatch.setattr(settings, "resend_api_key", "re_prueba")
    monkeypatch.setattr(settings, "respaldo_correo", None)
    zip_path = programador.armar_respaldo(tmp_path / "timbra_20261014.zip")
    assert programador.respaldo_fuera(zip_path) is None and not enviados         # sin RESPALDO_CORREO no sale nada
    monkeypatch.setattr(settings, "respaldo_correo", "yo@prueba.mx")
    assert programador.respaldo_fuera(zip_path) == "yo@prueba.mx"
    adj = enviados[-1]["attachments"][0]
    assert adj["filename"] == "timbra_20261014.timbra" and enviados[-1]["to"] == ["yo@prueba.mx"]
    crudo = base64.b64decode(adj["content"])
    assert not crudo.startswith(b"PK")                                            # va cifrado, no es un zip legible
    with zipfile.ZipFile(io.BytesIO(decrypt(crudo))) as z:
        assert "datos/timbra.db" in z.namelist()
    # demasiado grande: va sólo la base
    monkeypatch.setattr(programador, "MAX_CORREO", 1)
    programador.respaldo_fuera(zip_path)
    with zipfile.ZipFile(io.BytesIO(decrypt(base64.b64decode(enviados[-1]["attachments"][0]["content"])))) as z:
        assert [n for n in z.namelist() if n != ".env"] == ["datos/timbra.db"]
    assert "sólo la base" in enviados[-1]["text"]
    assert not any(p.name.endswith("_solo_base.zip") for p in tmp_path.iterdir()) and os.path.exists(zip_path)


def test_sin_llave_sigue_por_smtp(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", None)
    assert mailer.publica()["origen"] != "resend"
