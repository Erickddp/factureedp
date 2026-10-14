"""Timbrado para terceros: un solo PAC (el de la plataforma) para todas las cuentas, alta automática del RFC en Finkok
y saldo de timbres por cuenta (3 de regalo, recargas del administrador). Nunca se toca a Finkok: se simula."""
import os
from datetime import datetime

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Emisor, Pac, Usuario  # noqa: E402
from app.services import pac as pac_svc  # noqa: E402
from test_lotes import _esperar, _nuevo_lote, _perfil, fila  # noqa: E402
from test_v2 import _cliente, _preparar  # noqa: E402
from test_v5_clientes import rfc_moral  # noqa: E402
from test_w1_cuentas import _usuario  # noqa: E402
from test_w4_skill import rfc_de_prueba  # noqa: E402

CUERPO = {"metodo_pago": "PUE", "forma_pago": "03", "conceptos": [{
    "clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "Servicio", "valor_unitario": "100",
    "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]}]}


@pytest.fixture()
def plataforma(monkeypatch):
    """El administrador pone su Finkok de producción al servicio de todas las cuentas (el timbrado en sí se simula)."""
    monkeypatch.setattr(pac_svc, "get_pac", lambda pac: pac_svc.DemoPac())
    # el CSD de pruebas del repositorio venció en 2023: aquí se acepta para poder sellar (en producción real no se acepta)
    import app.services.facturacion as fac
    import app.services.signer as signer_mod
    monkeypatch.setattr(fac, "_modo_pruebas", lambda emisor: True)
    with TestClient(app) as c:
        admin, e = _preparar(c)
        r = c.post("/api/pacs", headers=admin, json={"nombre": "Finkok Timbra", "proveedor": "finkok", "usuario": "cuenta@timbra.mx",
                                                     "password": "Secreta#123", "pruebas": False, "plataforma": True})
        assert r.status_code == 200 and r.json()["plataforma"] is True and r.json()["propio"] is True, r.text
        with SessionLocal() as db:
            vence_real = db.query(Emisor).filter_by(rfc="EKU9003173C9").first().csd_vence
        yield c, admin, e, r.json()
        with SessionLocal() as db:  # se deja como estaba para las demás pruebas
            demo = db.query(Pac).filter_by(proveedor="demo").first()
            for em in db.query(Emisor).filter_by(pac_id=r.json()["id"]):
                em.pac_id = demo.id if em.rfc == "EKU9003173C9" else None
            eku = db.query(Emisor).filter_by(rfc="EKU9003173C9").first()
            eku.csd_vence = vence_real
            eku.usuario_id = db.query(Usuario).filter_by(email="rick@erickddp.com").first().id
            db.query(Pac).filter_by(id=r.json()["id"]).delete()
            db.commit()


def test_las_cuentas_timbran_con_el_pac_de_la_plataforma_y_se_les_descuenta(plataforma):
    c, admin, e, pac = plataforma
    cli = _cliente(c, admin, e)
    ana = _usuario(c, admin, "ana-terceros@prueba.mx", "anaterceros")
    yo = c.get("/api/auth/yo", headers=ana).json()
    c.post(f"/api/auth/usuarios/{yo['id']}/timbres", headers=admin, json={"cantidad": 3 - yo["timbres"], "motivo": "dejar en 3"}) if yo["timbres"] != 3 else None
    assert c.get("/api/auth/yo", headers=ana).json()["timbres"] == 3          # cada cuenta nueva trae 3 de regalo
    assert c.get("/api/auth/yo", headers=admin).json()["timbres"] is None     # el administrador no lleva saldo

    # Ana ve que tiene timbrado incluido, pero no las credenciales, y no puede tocar ese PAC
    suyos = c.get("/api/pacs", headers=ana).json()
    assert [(p["nombre"], p["usuario"], p["propio"], p["plataforma"]) for p in suyos] == [("Timbrado incluido en Timbra", None, False, True)]
    assert c.put(f"/api/pacs/{pac['id']}", headers=ana, json={"nombre": "mío", "proveedor": "demo"}).status_code == 404
    assert c.post(f"/api/pacs/{pac['id']}/probar?emisor_id={e['id']}", headers=ana).status_code == 404
    assert c.post(f"/api/pacs/{pac['id']}/alta?emisor_id={e['id']}", headers=ana).status_code == 404
    assert c.post("/api/pacs", headers=ana, json={"nombre": "x", "proveedor": "demo", "plataforma": True}).status_code == 403
    # un emisor nuevo de Ana ya nace con el PAC de la plataforma (no en modo demo)
    nuevo = c.post("/api/emisores", headers=ana, json={"rfc": rfc_moral(91), "nombre": "EMPRESA DE ANA TERCEROS", "regimen_fiscal": "601", "lugar_expedicion": "42501"}).json()
    assert nuevo["pac_id"] == pac["id"] and nuevo["modo_demo"] is False

    # Para timbrar hace falta CSD: el de pruebas es del RFC EKU, así que ese emisor se le pasa a Ana durante la prueba
    with SessionLocal() as db:
        em = db.get(Emisor, e["id"])
        em.usuario_id, em.pac_id = yo["id"], pac["id"]
        em.csd_vence = datetime(2099, 1, 1)   # para la revisión previa; el de verdad se restaura al terminar
        db.commit()
    cuerpo = {**CUERPO, "emisor_id": e["id"], "cliente_id": cli["id"]}
    for queda in (2, 1, 0):
        r = c.post("/api/facturas", headers=ana, json=cuerpo)
        assert r.status_code == 200, r.text
        assert c.get("/api/auth/yo", headers=ana).json()["timbres"] == queda
    r = c.post("/api/facturas", headers=ana, json=cuerpo)                      # la cuarta ya no
    assert r.status_code == 422 and "Se acabaron los timbres de tu cuenta" in r.json()["detail"]
    antes = len(c.get(f"/api/facturas?emisor_id={e['id']}&limit=1000", headers=ana).json())

    # sólo el administrador recarga, y queda anotado
    assert c.post(f"/api/auth/usuarios/{yo['id']}/timbres", headers=ana, json={"cantidad": 999}).status_code == 403
    assert c.post(f"/api/auth/usuarios/{yo['id']}/timbres", headers=admin, json={"cantidad": 0}).status_code == 422
    r = c.post(f"/api/auth/usuarios/{yo['id']}/timbres", headers=admin, json={"cantidad": 30, "motivo": "Recarga de $50"})
    assert r.json() == {"timbres": 30}
    mov = c.get("/api/auth/timbres", headers=ana).json()
    assert mov["timbres"] == 30 and mov["movimientos"][0]["cantidad"] == 30 and mov["movimientos"][0]["motivo"] == "Recarga de $50"
    assert any(u["usuario"] == "anaterceros" and u["timbres"] == 30 for u in c.get("/api/auth/usuarios", headers=admin).json())

    # ya puede: factura, nota de crédito, complemento de pago y lote; cada timbre descuenta uno
    f = c.post("/api/facturas", headers=ana, json={**cuerpo, "metodo_pago": "PPD", "forma_pago": "99"}).json()
    assert c.post("/api/facturas", headers=ana, json={**cuerpo, "tipo": "E", "relacionados": [{"tipo_relacion": "01", "uuids": [f["uuid"]]}]}).status_code == 200
    assert c.post("/api/facturas/pagos", headers=ana, json={"emisor_id": e["id"], "cliente_id": cli["id"], "fecha_pago": "2026-10-01T10:00:00",
                                                           "documentos": [{"factura_id": f["id"], "imp_pagado": "50"}]}).status_code == 200
    assert c.get("/api/auth/yo", headers=ana).json()["timbres"] == 27
    pid = _perfil(c, ana, e, serie="W")
    lote = _nuevo_lote(c, ana, e, pid, [fila("W-1", "PACIENTE TERCERO UNO", rfc_de_prueba(150), "42501", "05/10/2026", "750", "562.50"),
                                        fila("W-2", "PACIENTE TERCERO DOS", rfc_de_prueba(151), "42501", "05/10/2026", "900", "675")])
    c.post(f"/api/lotes/{lote['id']}/ejecutar", headers=ana, json={})
    assert _esperar(c, ana, lote["id"])["cuentas"]["timbrada"] == 2
    assert c.get("/api/auth/yo", headers=ana).json()["timbres"] == 25
    # cancelar no devuelve ni cobra timbres
    assert c.post(f"/api/facturas/{f['id']}/cancelar", headers=ana, json={"motivo": "02"}).status_code in (200, 422)
    assert c.get("/api/auth/yo", headers=ana).json()["timbres"] == 25
    assert len(c.get(f"/api/facturas?emisor_id={e['id']}&limit=1000", headers=ana).json()) == antes + 5

    # si el PAC rechaza, no se descuenta nada
    def truena(pac_, comp):
        raise pac_svc.PacError("El PAC rechazó el CFDI: CFDI40145")
    import app.services.facturacion as fac
    original = fac.pac_svc.timbrar
    fac.pac_svc.timbrar = truena
    try:
        assert c.post("/api/facturas", headers=ana, json=cuerpo).status_code == 422
    finally:
        fac.pac_svc.timbrar = original
    assert c.get("/api/auth/yo", headers=ana).json()["timbres"] == 25


def test_el_dia_del_cambio_a_produccion_nadie_se_queda_en_pruebas():
    """Del Finkok de pruebas al productivo: los emisores de los clientes se pasan solos; los del administrador no
    (pueden ser RFC de prueba), pero el resumen le avisa que siguen en pruebas."""
    with TestClient(app) as c:
        admin, e = _preparar(c)
        creados = []
        try:
            pruebas = c.post("/api/pacs", headers=admin, json={"nombre": "Finkok pruebas", "proveedor": "finkok", "usuario": "demo@timbra.mx",
                                                               "password": "Secreta#123", "pruebas": True, "plataforma": True}).json()
            creados.append(pruebas["id"])
            beto = _usuario(c, admin, "beto-cambio@prueba.mx", "betocambio")
            suyo = c.post("/api/emisores", headers=beto, json={"rfc": rfc_moral(92), "nombre": "EMPRESA DE BETO", "regimen_fiscal": "601",
                                                               "lugar_expedicion": "42501"}).json()
            assert suyo["pac_id"] == pruebas["id"]
            mio = c.post("/api/emisores", headers=admin, json={"rfc": rfc_moral(93), "nombre": "EMPRESA DE PRUEBA DEL ADMIN", "regimen_fiscal": "601",
                                                               "lugar_expedicion": "42501", "pac_id": pruebas["id"]}).json()

            prod = c.post("/api/pacs", headers=admin, json={"nombre": "Finkok producción", "proveedor": "finkok", "usuario": "real@timbra.mx",
                                                            "password": "Secreta#123", "pruebas": False, "plataforma": True}).json()
            creados.append(prod["id"])
            assert c.get(f"/api/emisores/{suyo['id']}", headers=beto).json()["pac_id"] == prod["id"]        # el cliente pasó solo
            assert c.get(f"/api/emisores/{suyo['id']}", headers=beto).json()["modo_demo"] is False
            assert c.get(f"/api/emisores/{mio['id']}", headers=admin).json()["pac_id"] == pruebas["id"]     # lo del admin, no
            alertas = c.get(f"/api/dashboard?emisor_id={mio['id']}", headers=admin).json()["alertas"]
            assert any("sigue timbrando en ambiente de pruebas" in a["texto"] and a["nivel"] == "error" for a in alertas)
            marcas = {p["id"]: p["plataforma"] for p in c.get("/api/pacs", headers=admin).json()}
            assert marcas[pruebas["id"]] is False and marcas[prod["id"]] is True                            # sólo uno a la vez

            # si el administrador lo retira, los emisores de los clientes no se quedan con un PAC que ya no ven
            c.put(f"/api/pacs/{prod['id']}", headers=admin, json={"nombre": "Finkok producción", "proveedor": "finkok", "usuario": "real@timbra.mx",
                                                                  "pruebas": False, "plataforma": False})
            assert c.get(f"/api/emisores/{suyo['id']}", headers=beto).json()["pac_id"] is None
            c.delete(f"/api/emisores/{mio['id']}?confirmar={mio['rfc']}", headers=admin)
        finally:
            with SessionLocal() as db:
                for em in db.query(Emisor).filter(Emisor.pac_id.in_(creados)):
                    em.pac_id = None
                db.query(Pac).filter(Pac.id.in_(creados)).delete()
                db.commit()


def test_el_rfc_se_da_de_alta_solo_en_finkok(monkeypatch):
    """Finkok responde 702 si el RFC emisor no está en la cuenta: Timbra lo registra y reintenta con el mismo XML."""
    enviados = []

    class Resp:
        status_code = 200
        text = ""

        def __init__(self, mensaje, ok):
            self.content = (f'<senv:Envelope xmlns:senv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="http://facturacion.finkok.com/registration" '
                            f'xmlns:s0="apps.services.soap.core.views"><senv:Body><tns:addResponse><tns:addResult><s0:message>{mensaje}</s0:message>'
                            f'<s0:success>{ok}</s0:success></tns:addResult></tns:addResponse></senv:Body></senv:Envelope>').encode()

    def post(url, data=None, headers=None, timeout=None):
        enviados.append((url, data.decode()))
        return Resp("Account Created successfully", "true")

    import requests
    monkeypatch.setattr(requests, "post", post)
    pac = Pac(nombre="Finkok", proveedor="finkok", usuario="cuenta@timbra.mx", password_enc=pac_svc.encrypt("Secreta#123") if hasattr(pac_svc, "encrypt") else None, pruebas=True)
    if pac.password_enc is None:
        from app.security import encrypt
        pac.password_enc = encrypt("Secreta#123")
    assert pac_svc.registrar_emisor(pac, "abc010101ab1") == "dado de alta ahora"
    url, cuerpo = enviados[0]
    assert url == "https://demo-facturacion.finkok.com/servicios/soap/registration"
    for trozo in ("<reg:reseller_username>cuenta@timbra.mx</reg:reseller_username>", "<reg:reseller_password>Secreta#123</reg:reseller_password>",
                  "<reg:taxpayer_id>ABC010101AB1</reg:taxpayer_id>", "<reg:type_user>O</reg:type_user>"):
        assert trozo in cuerpo
    pac.pruebas = False
    pac_svc.registrar_emisor(pac, "ABC010101AB1")
    assert enviados[1][0].startswith("https://facturacion.finkok.com/")
    # «ya existe» no es un error; un rechazo de verdad sí
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp("Account Already exists", "false"))
    assert pac_svc.registrar_emisor(pac, "ABC010101AB1") == "ya estaba dado de alta"
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp("Invalid credentials", "false"))
    with pytest.raises(pac_svc.PacError):
        pac_svc.registrar_emisor(pac, "ABC010101AB1")

    # Al timbrar: 702 → alta → reintento, una sola vez
    altas, intentos = [], []
    monkeypatch.setattr(pac_svc, "registrar_emisor", lambda p, rfc: altas.append(rfc) or "ok")
    demo = pac_svc.DemoPac()

    class Finkok702:
        def stamp(self, cfdi):
            intentos.append(1)
            if len(intentos) == 1:
                raise RuntimeError("702 - Sorry there was an error when validating the reseller and user")
            return demo.stamp(cfdi)

    monkeypatch.setattr(pac_svc, "get_pac", lambda p: Finkok702())
    with TestClient(app) as c:
        h, e = _preparar(c)
        from app.schemas import FacturaIn
        from app.services import cfdi as cfdi_svc
        from app.services.signer import signer_de
        with SessionLocal() as db:
            em = db.get(Emisor, e["id"])
            comp = cfdi_svc.construir(em, FacturaIn(emisor_id=em.id, publico_general=True, forma_pago="01", metodo_pago="PUE",
                                                    conceptos=CUERPO["conceptos"]), None, "A", "1")
            comp.sign(signer_de(em, permitir_vencido=True))
            uuid, xml = pac_svc.timbrar(pac, comp)
    assert altas == ["EKU9003173C9"] and len(intentos) == 2 and len(uuid) == 36
