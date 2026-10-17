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
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(403, {"message": "You can only send testing emails to your own email address "
                                                                              "(yo@prueba.mx). To send emails to other recipients, please verify a domain"}))
    with pytest.raises(mailer.CorreoError, match="sólo deja enviar a yo@prueba.mx"):
        mailer.enviar(["cliente@prueba.mx"], "x", "y", [])
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(401, {"message": "API key is invalid"}))
    with pytest.raises(mailer.CorreoError, match="RESEND_API_KEY"):
        mailer.enviar(["cliente@prueba.mx"], "x", "y", [])
    with pytest.raises(mailer.CorreoError, match="destino válido"):
        mailer.enviar(["sin-arroba"], "x", "y", [])
    with pytest.raises(mailer.CorreoError, match="no tiene la forma"):
        mailer.enviar(["cliente@gmail"], "x", "y", [])
    for falso in ("destino@ejemplo.mx", "a@example.com", "b@correo.ejemplo.com.mx", "c@algo.test", "d@midominio.com"):
        with pytest.raises(mailer.CorreoError, match="de ejemplo"):
            mailer.enviar([falso], "x", "y", [])
    for real in ("ana@gmail.com", "pagos@empresa.com.mx", "x@ejemplos-reales.mx"):
        assert mailer._validos([real]) == [real]
    # el punto que se cuela al final al copiar de un texto se quita solo
    monkeypatch.setattr(requests, "post", lambda url, json=None, headers=None, timeout=None: enviados.append((url, json, headers)) or Resp(200, {"id": "x"}))
    mailer.enviar(["cperickd@gmail.com."], "x", "y", [])
    assert enviados[-1][1]["to"] == ["cperickd@gmail.com"]


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


def test_tope_de_descargas_del_sat_a_la_vez(monkeypatch):
    from fastapi.testclient import TestClient

    from app.db import SessionLocal
    from app.main import app
    from app.models import Usuario, XmlTrabajo
    from app.routers import xml as xml_router
    from app.services import xml_tareas
    from test_v2 import _preparar

    monkeypatch.setattr(xml_tareas, "fabrica_cliente", object())  # sin e.firma real: no se llega a lanzar nada
    with TestClient(app) as c:
        h, e = _preparar(c)
        with SessionLocal() as db:
            uid = db.query(Usuario).filter_by(email="rick@erickddp.com").first().id
            falsos = [XmlTrabajo(usuario_id=uid, emisor_id=e["id"] + 1000 + i, clase="sat", estado="curso", params={}, resumen={}, registro="")
                      for i in range(xml_router.DESCARGAS_POR_CUENTA)]
            db.add_all(falsos)
            db.commit()
            ids = [f.id for f in falsos]
        try:
            r = c.post("/api/xml/descargas", headers=h, json={"emisor_id": e["id"], "desde": "2026-01-01", "hasta": "2026-01-31", "tipo": "emitidos"})
            assert r.status_code == 429 and "descargas del SAT en curso" in r.json()["detail"], r.text
        finally:
            with SessionLocal() as db:
                db.query(XmlTrabajo).filter(XmlTrabajo.id.in_(ids)).delete()
                db.commit()


def test_comprobantes_de_pruebas_nunca_van_al_cliente(monkeypatch):
    from types import SimpleNamespace as NS
    real = NS(pac=NS(proveedor="finkok", pruebas=False))
    assert mailer.destinatarios(real, ["cliente@empresa.mx"]) == ["cliente@empresa.mx"]
    for emisor in (NS(pac=None), NS(pac=NS(proveedor="demo", pruebas=True)), NS(pac=NS(proveedor="finkok", pruebas=True))):
        with pytest.raises(mailer.CorreoError, match="PRUEBAS"):
            mailer.destinatarios(emisor, ["cliente@empresa.mx"])
    monkeypatch.setattr(settings, "correo_pruebas", "yo@despacho.mx")
    assert mailer.destinatarios(NS(pac=None), ["cliente@empresa.mx"]) == ["yo@despacho.mx"]


def test_resumen_diario_de_errores_por_correo(monkeypatch, tmp_path):
    from datetime import datetime

    import requests

    from app import logs
    from app.services import programador
    log = tmp_path / "timbra.log"
    log.write_text("\n".join([
        "2026-10-15 08:00:00,000 ERROR   [aaaaaaaa] timbra: viejo, de hace dos días",
        "2026-10-16 09:00:00,000 INFO    [bbbbbbbb] timbra: GET /api/facturas → 200 (5 ms)",
        "2026-10-16 09:01:00,000 ERROR   [cccccccc] timbra: Respuesta del PAC: 718 - Timbres agotados",
        "2026-10-16 09:02:00,000 ERROR   [dddddddd] timbra: Respuesta del PAC: 718 - Timbres agotados",
        "2026-10-16 09:03:00,000 ERROR   [eeeeeeee] timbra: POST /api/facturas/12/enviar → 502 (30 ms)",
    ]), encoding="utf-8")
    monkeypatch.setattr(logs, "ARCHIVO", str(log))
    total, texto = programador.resumen_errores(ahora=datetime(2026, 10, 16, 20, 0))
    assert total == 3 and "2 ×" in texto and "viejo" not in texto and "INFO" not in texto
    enviados = []
    monkeypatch.setattr(requests, "post", lambda url, json=None, headers=None, timeout=None: enviados.append(json) or Resp(200, {"id": "x"}))
    monkeypatch.setattr(settings, "resend_api_key", "re_prueba")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(programador, "resumen_errores", lambda: (3, "texto"))
    assert programador.enviar_resumen_errores() is False                    # sin RESPALDO_CORREO no sale
    monkeypatch.setattr(settings, "respaldo_correo", "yo@despacho-prueba.mx")
    assert programador.enviar_resumen_errores() is True and enviados[-1]["to"] == ["yo@despacho-prueba.mx"]
    assert programador.enviar_resumen_errores() is False and len(enviados) == 1   # una vez al día, aunque reinicie


def test_sin_llave_sigue_por_smtp(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", None)
    assert mailer.publica()["origen"] != "resend"
