"""Correo por la API de Resend (en el servidor: Railway Hobby bloquea SMTP). Nunca se toca Resend: se simula."""
import base64

import pytest

from app.config import settings
from app.services import mailer


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


def test_sin_llave_sigue_por_smtp(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", None)
    assert mailer.publica()["origen"] != "resend"
