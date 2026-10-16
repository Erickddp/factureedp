"""Listos para producción: hora del CFDI según el CP de expedición y borrado de facturas de práctica (sólo demo)."""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Factura  # noqa: E402
from app.services import cfdi  # noqa: E402
from test_v2 import _preparar  # noqa: E402


def test_hora_del_cfdi_segun_cp_y_nunca_adelantada():
    assert str(cfdi.zona_de("42501")) == "America/Mexico_City"
    assert str(cfdi.zona_de("22000")) == "America/Tijuana"
    assert str(cfdi.zona_de("83000")) == "America/Mazatlan"
    assert str(cfdi.zona_de("77500")) == "America/Cancun"
    assert str(cfdi.zona_de("32330")) == "America/Matamoros"
    assert str(cfdi.zona_de("00000")) == "America/Mexico_City" and str(cfdi.zona_de(None)) == "America/Mexico_City"
    for cp in ("42501", "22000", "83000", "77500", "32330"):
        f = cfdi.ahora_mx(cp)
        oficial = datetime.now(cfdi.zona_de(cp)).replace(tzinfo=None)
        assert f <= oficial + timedelta(seconds=2), (cp, f, oficial)          # nunca en el futuro del huso del SAT
        assert oficial - f <= timedelta(hours=2, minutes=6), (cp, f, oficial)  # ni más de 2 h atrás
    # Tijuana va atrás de CDMX: con la hora de CDMX el PAC rechazaría por fecha futura
    assert cfdi.ahora_mx("22000") < datetime.now(ZoneInfo("America/Mexico_City")).replace(tzinfo=None) - timedelta(minutes=50)


def test_borrar_practica_solo_quita_demo_y_regresa_folios():
    with TestClient(app) as c:
        h, e = _preparar(c)
        n = c.get(f"/api/emisores/{e['id']}/practica", headers=h).json()["facturas"]
        assert n > 0
        # Una factura "real" (sin el sello DEMO) no debe tocarse
        with SessionLocal() as db:
            f = db.query(Factura).filter(Factura.emisor_id == e["id"], Factura.serie == "A", Factura.tipo == "I").order_by(Factura.id).first()
            real_id, real_folio = f.id, int(f.folio)
            f.xml = f.xml.replace(b'SelloSAT="DEMO"', b'SelloSAT="REALxx"')
            db.commit()
        r = c.post(f"/api/emisores/{e['id']}/practica/borrar", headers=h).json()
        assert r["borradas"] == n - 1, r
        assert r["folios"]["A"] == real_folio + 1, r
        with SessionLocal() as db:
            quedan = db.query(Factura).filter(Factura.emisor_id == e["id"]).all()
            assert [x.id for x in quedan] == [real_id]
        assert c.get(f"/api/emisores/{e['id']}/practica", headers=h).json()["facturas"] == 0
        assert not c.post("/api/facturas/recuperar", headers=h).json()["recuperadas"]  # los XML de práctica ya no están en el respaldo


def test_correo_de_envio_se_configura_desde_la_app(monkeypatch):
    from app.services import mailer
    enviados = []

    class Falso:
        def __init__(self, host, port, timeout=None): self.host = host
        def starttls(self): pass
        def login(self, u, p): self.cred = (u, p)
        def send_message(self, m, to_addrs=None): enviados.append((self.cred, m["From"], m["To"]))
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(mailer.smtplib, "SMTP", Falso)
    with TestClient(app) as c:
        h, _ = _preparar(c)
        c.delete("/api/correo", headers=h)
        assert c.put("/api/correo", headers=h, json={"host": "smtp.gmail.com", "user": "facturas@ejemplo.mx", "password": ""}).status_code == 422
        r = c.put("/api/correo", headers=h, json={"host": "smtp.gmail.com", "port": 587, "user": "facturas@ejemplo.mx",
                                                  "password": "abcd efgh ijkl mnop", "nombre": "Facturación de prueba"}).json()
        assert r["configurado"] and r["tiene_password"] and "password" not in r
        guardado = open(mailer._ruta(), encoding="utf-8").read()
        assert "abcd" not in guardado and "abcdefghijklmnop" not in guardado  # cifrada en disco
        assert c.post("/api/correo/probar", headers=h, json={"para": "destino@ejemplo.mx"}).status_code == 502   # dominio de relleno: no sale
        assert c.post("/api/correo/probar", headers=h, json={"para": "destino@despacho-prueba.mx"}).status_code == 200
        assert enviados[-1][0] == ("facturas@ejemplo.mx", "abcdefghijklmnop") and "Facturación de prueba" in enviados[-1][1]
        # cambiar el nombre sin volver a escribir la contraseña la conserva
        c.put("/api/correo", headers=h, json={"host": "smtp.gmail.com", "user": "facturas@ejemplo.mx", "nombre": "Otro"})
        assert mailer.config()["password"] == "abcdefghijklmnop"
        assert c.delete("/api/correo", headers=h).json()["configurado"] is False


def test_login_se_frena_tras_varios_fallos():
    from app.routers import auth
    with TestClient(app) as c:
        auth._FALLOS.clear()
        correo = "nadie@ejemplo.mx"
        for _ in range(auth._MAXIMO):
            assert c.post("/api/auth/login", json={"email": correo, "password": "x"}).status_code == 401
        assert c.post("/api/auth/login", json={"email": correo, "password": "x"}).status_code == 429
        h, _ = _preparar(c)  # otro correo no se ve afectado
        assert h["Authorization"]
        auth._FALLOS.clear()


def test_rfc_de_pruebas_del_sat_no_se_amarra_a_un_pac_de_produccion():
    """Reporte del tester: EKU9003173C9 con un Finkok de PRODUCCIÓN sólo daba «300 usuario o contraseña inválidos»."""
    from types import SimpleNamespace as NS
    from app.services import validacion
    fake = lambda pruebas: NS(rfc="EKU9003173C9", cer=b"x", csd_vence=None, regimen_fiscal="601", lugar_expedicion="01000",
                              pac=NS(proveedor="finkok", pruebas=pruebas, nombre="Finkok"))
    from app.schemas import FacturaIn
    data = FacturaIn.model_construct(tipo="I", publico_general=False, conceptos=[])
    for pruebas, esperado in ((False, True), (True, False)):
        r = validacion.validar(None, fake(pruebas), data, None)
        assert any(e["campo"] == "emisor.pac" and "PRUEBAS del SAT" in e["mensaje"] for e in r["errores"]) == esperado


def test_ambiente_del_emisor_llega_a_las_pantallas():
    """Propuesta del tester: el emisor de pruebas se marca y timbrar en producción pide confirmar. Las pantallas lo leen
    de EmisorOut.ambiente; si dijera «produccion» en pruebas, o al revés, la marca y la confirmación mentirían."""
    from app.models import Emisor, Pac
    e = Emisor(rfc="AAA010101AAA", nombre="X", regimen_fiscal="601", lugar_expedicion="42501")
    assert e.ambiente == "demo"
    for pac, esperado in ((Pac(nombre="Demo", proveedor="demo", pruebas=False), "demo"),
                          (Pac(nombre="Finkok", proveedor="finkok", pruebas=True), "pruebas"),
                          (Pac(nombre="Finkok", proveedor="finkok", pruebas=False), "produccion")):
        e.pac = pac
        assert e.ambiente == esperado, (pac.proveedor, pac.pruebas)
    with TestClient(app) as c:
        h, emisor = _preparar(c)  # EKU9003173C9 con PAC demo
        assert emisor["ambiente"] == "demo"
        assert {x["rfc"]: x["ambiente"] for x in c.get("/api/emisores", headers=h).json()}["EKU9003173C9"] == "demo"
