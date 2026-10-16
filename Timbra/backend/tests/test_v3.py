"""Errores comunes con autocorrección, idempotencia, a cuenta de terceros, pedimentos y configuración de Facturar."""
import os
import uuid as uuidlib

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402
from satcfdi.cfdi import CFDI  # noqa: E402

from app.main import app  # noqa: E402
from app.services import errores_pac, pac as pac_svc  # noqa: E402
from test_v2 import IVA16, _cliente, _preparar  # noqa: E402


def _cuerpo(e, cli, **concepto):
    return {"emisor_id": e["id"], "cliente_id": cli["id"], "metodo_pago": "PUE", "forma_pago": "03",
            "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "Servicio",
                           "valor_unitario": "500", "impuestos": [IVA16], **concepto}]}


def test_diagnostico_de_errores_comunes():
    casos = {
        "Error 702: No se encontró el RFC del emisor": "rfc_pac",
        "ReadTimeout: HTTPSConnectionPool timed out": "red",
        "307 Comprobante timbrado previamente": "previo",
        "CFDI40101 - La fecha de emisión está fuera de rango": "fecha",
        "CFDI40145 El campo Nombre del receptor no coincide": "nombre_receptor",
        "CFDI40157 RegimenFiscalReceptor": "regimen_receptor",
        "No cuenta con timbres disponibles": "saldo",
        "718 - Timbres agotados, por favor contacte a su proveedor": "saldo",
        "CFDI40998 - El código postal no corresponde a Franja Fronteriza": "frontera",
    }
    for texto, clave in casos.items():
        d = errores_pac.diagnosticar(texto)
        assert d and d.clave == clave, (texto, d)
    assert errores_pac.diagnosticar("algo rarísimo") is None
    assert any(x["automatico"] for x in errores_pac.catalogo())


class _Falla(pac_svc.DemoPac):
    """PAC demo que falla N veces con un texto dado antes de timbrar."""

    def __init__(self, texto, veces=1):
        self.texto, self.veces, self.llamadas = texto, veces, 0

    def stamp(self, cfdi, accept=None):
        self.llamadas += 1
        if self.llamadas <= self.veces:
            raise ConnectionError(self.texto)
        return super().stamp(cfdi)


def _con_pac(falso):
    orig = pac_svc.get_pac
    pac_svc.get_pac = lambda p: falso
    pac_svc.ESPERA = (0, 0)
    return orig


def test_reintento_de_red_y_recuperacion_sin_duplicar():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        falso = _Falla("Read timed out", veces=1)
        orig = _con_pac(falso)
        try:
            r = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli))
            assert r.status_code == 200, r.text
            assert falso.llamadas == 2  # un reintento con el mismo XML

            class Previo(pac_svc.DemoPac):
                llamadas = 0

                def stamp(self, cfdi, accept=None):
                    raise RuntimeError("307 - Comprobante timbrado previamente")

                def stamped(self, cfdi, accept=None):
                    Previo.llamadas += 1
                    return pac_svc.DemoPac().stamp(cfdi)

            pac_svc.get_pac = lambda p: Previo()
            r = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli))
            assert r.status_code == 200 and Previo.llamadas == 1, r.text

            pac_svc.get_pac = lambda p: _Falla("Error 702: No se encontró el RFC del emisor", veces=9)
            r = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli))
            assert r.status_code == 422 and "Qué hacer" in r.text and "Clientes" in r.text
        finally:
            pac_svc.get_pac = orig


def test_fecha_rechazada_se_rearma_sola():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        falso = _Falla("CFDI40101 La fecha de emisión está fuera de rango", veces=1)
        orig = _con_pac(falso)
        try:
            r = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli))
            assert r.status_code == 200, r.text
            assert falso.llamadas == 2
        finally:
            pac_svc.get_pac = orig


def test_idempotencia_no_timbra_dos_veces():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        llave = {**h, "Idempotency-Key": str(uuidlib.uuid4())}
        a = c.post("/api/facturas", headers=llave, json=_cuerpo(e, cli)).json()
        b = c.post("/api/facturas", headers=llave, json=_cuerpo(e, cli)).json()
        assert a["id"] == b["id"] and a["uuid"] == b["uuid"]


def test_a_cuenta_de_terceros_y_pedimento():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        assert c.post("/api/terceros", headers=h, json={"emisor_id": e["id"], "rfc": "EKU9003173C9", "nombre": "X",
                                                         "regimen_fiscal": "601", "codigo_postal": "42501"}).status_code == 422
        t = c.post("/api/terceros", headers=h, json={
            "emisor_id": e["id"], "rfc": "XOJI740919U48", "nombre": "INGRID XODAR JIMENEZ", "regimen_fiscal": "612",
            "codigo_postal": "88965", "alias": "Dueña del local"})
        assert t.status_code in (200, 409), t.text
        ter = {"rfc": "XOJI740919U48", "nombre": "INGRID XODAR JIMENEZ", "regimen_fiscal": "612", "codigo_postal": "88965"}
        r = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli, a_cuenta_terceros=ter, cuenta_predial="ABC123,XYZ9",
                                                              informacion_aduanera=["23-16-3456-1234567"]))
        assert r.status_code == 200, r.text
        crudo = c.get(f"/api/facturas/{r.json()['id']}/xml", headers=h).content
        con = CFDI.from_string(crudo)["Conceptos"][0]
        assert con["ACuentaTerceros"]["RfcACuentaTerceros"] == "XOJI740919U48"
        assert b'NumeroPedimento="23  16  3456  1234567"' in crudo
        assert b'Numero="ABC123"' in crudo and b'Numero="XYZ9"' in crudo
        malo = {**ter, "rfc": e["rfc"]}
        r = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli, a_cuenta_terceros=malo))
        assert r.status_code == 422 and "mismo emisor" in r.text


def test_config_facturar_y_repetir_ultima():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cfg = c.get(f"/api/emisores/{e['id']}/config-facturar", headers=h).json()
        assert cfg["nivel"] in ("simple", "estandar", "completo") and "visibles" in cfg
        cfg = c.put(f"/api/emisores/{e['id']}/config-facturar", headers=h, json={
            "nivel": "simple", "campos": {"terceros": True}, "basura": 1,
            "perfiles": [{"id": "h", "nombre": "Honorarios PF a PM", "metodo": "PPD", "impuesto": "IVA 16%"}, {"nombre": ""}]}).json()
        assert cfg["visibles"]["clave_sat"] is False and cfg["visibles"]["terceros"] is True
        assert len(cfg["perfiles"]) == 1 and "basura" not in cfg
        cli = _cliente(c, h, e)
        c.post("/api/facturas", headers=h, json=_cuerpo(e, cli, descripcion="Iguala mensual"))
        u = c.get(f"/api/facturas/ultima?cliente_id={cli['id']}", headers=h).json()
        assert u["payload"]["conceptos"][0]["descripcion"] == "Iguala mensual"


def test_disco_o_base_fallan_despues_de_timbrar():
    from sqlalchemy.orm import Session

    from app.services import facturacion, respaldo

    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        # 1) El respaldo en disco falla: la factura igual queda guardada
        orig_g = respaldo.guardar
        respaldo.guardar = lambda *a, **k: (_ for _ in ()).throw(OSError("disco lleno"))
        try:
            r = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli))
            assert r.status_code == 200 and r.json()["uuid"], r.text
        finally:
            respaldo.guardar = orig_g
        # 2) La base falla en el commit tras timbrar: se recupera sola del respaldo y no repite folio
        #    (el 1er commit es el que aparta el folio ANTES de llamar al PAC; el 2º, el de guardar lo timbrado)
        orig_c, estado = Session.commit, {"n": 0}

        def commit_que_falla(self):
            estado["n"] += 1
            if estado["n"] == 2:
                raise RuntimeError("database is locked")
            return orig_c(self)
        Session.commit = commit_que_falla
        try:
            r = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli))
        finally:
            Session.commit = orig_c
        assert r.status_code == 200, r.text
        rec = r.json()
        assert "Recuperada" in (rec["error"] or "")
        sig = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli)).json()
        assert sig["serie"] == rec["serie"] and int(sig["folio"]) == int(rec["folio"]) + 1
        # 3) El PAC rechaza: el folio ya se había confirmado antes de llamarlo, y se regresa (no queda hueco)
        from app.services import pac as pac_svc
        orig_t = facturacion.pac_svc.timbrar
        facturacion.pac_svc.timbrar = lambda *a, **k: (_ for _ in ()).throw(pac_svc.PacError("El PAC rechazó el CFDI: CFDI40999"))
        try:
            assert c.post("/api/facturas", headers=h, json=_cuerpo(e, cli)).status_code == 422
        finally:
            facturacion.pac_svc.timbrar = orig_t
        otra = c.post("/api/facturas", headers=h, json=_cuerpo(e, cli)).json()
        assert int(otra["folio"]) == int(sig["folio"]) + 1
