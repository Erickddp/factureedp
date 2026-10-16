"""Módulo de XML: la e.firma se pone cada vez y no se guarda; descarga con un SAT simulado (nunca se toca el SAT real),
cancelados, formato maestro de 65 columnas, Excel, PDF de una hoja, ZIP, estadísticas y cuentas separadas.
Los CFDI de estas pruebas los timbra el propio Timbra en modo demo: no hay datos de nadie."""
import base64
import io
import os
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Emisor, XmlTrabajo  # noqa: E402
from app.services import xml_firma, xml_indice, xml_tareas  # noqa: E402
from app.xmlsat import lector  # noqa: E402
from test_v2 import CSD, _cliente, _factura, _preparar  # noqa: E402
from test_w1_cuentas import _usuario  # noqa: E402

# El formato maestro, escrito a mano: si alguien mueve, quita o renombra una columna, esta prueba truena.
EDDP = ["Tipo", "Fecha", "Año", "Mes", "Día", "Hora", "Comprobante", "Efecto", "Versión", "Serie", "Folio", "RFC Emisor",
        "Nombre Emisor", "Régimen Emisor", "RFC Receptor", "Nombre Receptor", "Régimen Receptor", "Uso CFDI",
        "Domicilio Receptor", "SubTotal", "Descuento", "IVA Trasladado", "IEPS Trasladado", "IVA Retenido", "ISR Retenido",
        "Ret. Total", "Total", "Base IVA 16", "Base IVA 8", "Base IVA 0", "Base Exento", "Moneda", "Tipo Cambio", "Método Pago",
        "Forma Pago", "Condiciones Pago", "Exportación", "Es Pago", "Monto Total Pago", "Fecha Pago", "Forma Pago P",
        "Moneda Pago", "TC Pago", "Num Operación", "Doc Pagado UUID", "Doc Serie", "Doc Folio", "Parcialidad", "Saldo Anterior",
        "Imp Pagado", "Saldo Insoluto", "Base Doc", "IVA Doc", "Tasa Doc", "Objeto Imp Doc", "Relacionados", "Tipo Relación",
        "Conceptos", "Descripción", "Claves ProdServ", "No Identificación", "Complementos", "UUID", "Fecha Timbrado", "RFC PAC"]


def test_formato_maestro_no_cambia():
    assert xml_indice.FORMATO_EDDP == EDDP and len(EDDP) == 65
    assert len(lector.COLUMNAS) == 73
    assert [c for c in lector.COLUMNAS if c not in EDDP] == [
        "Clase", "Estatus Pago", "Pagado REP", "Num REP", "NC Aplicadas", "Saldo Pendiente", "Factura Encontrada", "Archivo"]


# ---------------------------------------------------------------- ayudas
def efirma_de_prueba(rfc="EKU9003173C9", clave="12345678a", csd=False, dias=365):
    """(.cer, .key) con la forma de una e.firma del SAT: certificado DER y llave PKCS#8 cifrada. Inventada al vuelo."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sujeto = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CONTRIBUYENTE DE PRUEBA"),
                        x509.NameAttribute(NameOID.X500_UNIQUE_IDENTIFIER, rfc)])
    hoy = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(sujeto).issuer_name(sujeto).public_key(llave.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(hoy - timedelta(days=400))
            .not_valid_after(hoy + timedelta(days=dias))
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                         data_encipherment=not csd, key_agreement=not csd, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(llave, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.DER),
            llave.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                serialization.BestAvailableEncryption(clave.encode())))


class SatSimulado:
    """Responde como la descarga masiva del SAT: acepta, termina y entrega un ZIP (de XML, o la lista de estatus)."""

    def __init__(self, xml_por_tipo, listas=None):
        self.xml_por_tipo = xml_por_tipo   # {"emitidos": [(nombre, bytes)], "recibidos": [...]}
        self.listas = listas or {}          # {"emitidos": "Uuid~RfcEmisor~…", …}
        self.solicitudes = []

    def token(self):
        return "token-simulado"

    def _alta(self, clase, tipo, desde, hasta, hay):
        self.solicitudes.append((clase, tipo, desde, hasta))
        if not hay:
            return {"cod_estatus": "5004", "mensaje": "No se encontró la información", "id_solicitud": None}
        return {"cod_estatus": "5000", "mensaje": "Solicitud Aceptada", "id_solicitud": f"sol-{clase}-{tipo}-{len(self.solicitudes)}"}

    def solicitar(self, rfc, tipo, desde, hasta):
        return self._alta("xml", tipo, desde, hasta, self.xml_por_tipo.get(tipo))

    def solicitar_metadata(self, rfc, tipo, desde, hasta):
        return self._alta("lista", tipo, desde, hasta, self.listas.get(tipo))

    def verificar(self, rfc, id_solicitud):
        _, clase, tipo, _n = id_solicitud.split("-")
        return {"estado_solicitud": "3", "cod_estatus": "5000", "numero_cfdis": "1", "mensaje": "ok", "paquetes": [f"paq-{clase}-{tipo}"]}

    def descargar_paquete(self, rfc, id_paquete):
        _, clase, tipo = id_paquete.split("-")
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as z:
            if clase == "lista":
                z.writestr("lista.txt", self.listas[tipo])
            else:
                for nombre, datos in self.xml_por_tipo[tipo]:
                    z.writestr(nombre, datos)
        return {"cod_estatus": "5000", "mensaje": "ok", "paquete_b64": base64.b64encode(mem.getvalue()).decode()}


def esperar(c, h, tid, segundos=120):
    fin = time.time() + segundos
    t = {}
    while time.time() < fin:
        t = c.get(f"/api/xml/trabajos/{tid}", headers=h).json()
        if t["estado"] != "curso":
            return t
        time.sleep(0.05)
    raise AssertionError(f"el trabajo {tid} no terminó: {t}")


def _vaciar(c, h, e):
    """Estas pruebas comparten el emisor de pruebas: se empieza sin XML y sin historial de solicitudes."""
    assert c.post("/api/xml/borrar", headers=h, json={"emisor_id": e["id"], "estatus": ""}).status_code == 200
    for f in xml_indice.carpeta_estado().glob(f"*_{e['id']}.json"):
        f.unlink()
    xml_firma.olvidar_todas()


def _recibido(rfc_emisor, nombre, total="100", receptor="EKU9003173C9", tasa=None):
    """Un CFDI que le facturan al emisor de pruebas (lo sella el CSD de pruebas y lo «timbra» el PAC demo)."""
    from satcfdi.create.cfd import cfdi40
    from satcfdi.models import Signer

    from app.services.pac import DemoPac
    Signer.load(certificate=open(CSD / "EKU9003173C9.cer", "rb").read(), key=open(CSD / "EKU9003173C9.key", "rb").read(), password="12345678a")
    imp = {} if tasa is None else {"impuestos": cfdi40.Impuestos(traslados=cfdi40.Traslado(impuesto="002", tipo_factor="Tasa", tasa_o_cuota=Decimal(tasa)))}
    comp = cfdi40.Comprobante(
        emisor=cfdi40.Emisor(rfc=rfc_emisor, nombre=nombre, regimen_fiscal="601"), lugar_expedicion="42501",
        receptor=cfdi40.Receptor(rfc=receptor, nombre="ESCUELA KEMPER URGATE", domicilio_fiscal_receptor="42501",
                                 regimen_fiscal_receptor="601", uso_cfdi="G03"),
        conceptos=[cfdi40.Concepto(clave_prod_serv="84111500", cantidad=1, clave_unidad="E48", descripcion="Renta de oficina",
                                   valor_unitario=Decimal(total), objeto_imp="01" if tasa is None else "02", **imp)],
        forma_pago="03", metodo_pago="PUE")
    return DemoPac().stamp(comp).xml


def _uuid(xml: bytes) -> str:
    import re
    return re.search(rb'UUID="([0-9A-Fa-f-]{36})"', xml).group(1).decode().upper()


def _juego(c, h, e):
    """Lo que un contribuyente tiene en un mes: factura PPD, otra PUE, nota de crédito, un pago que paga dos facturas
    y dos gastos. Devuelve los XML listos para el SAT simulado."""
    cli = _cliente(c, h, e)
    f1, _ = _factura(c, h, e, cli, total="1000", metodo="PPD", descripcion="Honorarios de octubre")
    f2, _ = _factura(c, h, e, cli, total="500", metodo="PPD", descripcion="Asesoría")
    f3, _ = _factura(c, h, e, cli, total="200", metodo="PUE", descripcion="Venta de mostrador")
    nc = c.post("/api/facturas", headers=h, json={
        "emisor_id": e["id"], "cliente_id": cli["id"], "tipo": "E", "metodo_pago": "PUE", "forma_pago": "03",
        "relacionados": [{"tipo_relacion": "01", "uuids": [f3["uuid"]]}],
        "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "ACT", "descripcion": "Descuento", "valor_unitario": "50",
                       "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]}]})
    assert nc.status_code == 200, nc.text
    pago = c.post("/api/facturas/pagos", headers=h, json={
        "emisor_id": e["id"], "cliente_id": cli["id"], "fecha_pago": f"{date.today():%Y-%m-%d}T10:00:00", "forma_pago": "03",
        "documentos": [{"factura_id": f1["id"], "imp_pagado": "1160"}, {"factura_id": f2["id"], "imp_pagado": "300"}]})
    assert pago.status_code == 200, pago.text
    x = {n: c.get(f"/api/facturas/{d['id']}/xml", headers=h).content
         for n, d in (("f1", f1), ("f2", f2), ("f3", f3), ("nc", nc.json()), ("pago", pago.json()))}
    x["g1"] = _recibido("KIJ0906199R1", "KERNEL INDUSTIA JUGUETERA", "300", tasa="0.16")
    x["g2"] = _recibido("CTE950627K46", "COMERCIALIZADORA TEXTIL ELEGANTE", "100")
    return x, {"f1": f1, "f2": f2, "f3": f3, "nc": nc.json(), "pago": pago.json()}


@pytest.fixture()
def sat():
    yield
    xml_tareas.fabrica_cliente = None
    xml_firma.olvidar_todas()


# ---------------------------------------------------------------- e.firma
def test_la_efirma_se_pone_cada_vez_y_nunca_se_guarda(sat, monkeypatch):
    with TestClient(app) as c:
        h, e = _preparar(c)
        _vaciar(c, h, e)
        url = f"/api/xml/efirma/{e['id']}"
        cer, key = efirma_de_prueba()

        def poner(cer_, key_, clave="12345678a"):
            return c.post(url, headers=h, data={"password": clave}, files={"cer": ("e.cer", cer_), "key": ("e.key", key_)})

        assert c.get(f"/api/xml/efirma?emisor_id={e['id']}", headers=h).json() == {"puesta": False}
        # sin e.firma no hay descarga, y el mensaje dice por qué
        hoy = date.today().isoformat()
        r = c.post("/api/xml/descargas", headers=h, json={"emisor_id": e["id"], "desde": hoy, "hasta": hoy})
        assert r.status_code == 422 and "no se guarda" in r.json()["detail"]
        # lo que no es una e.firma válida se explica
        assert "CSD" in poner(open(CSD / "EKU9003173C9.cer", "rb").read(), open(CSD / "EKU9003173C9.key", "rb").read()).json()["detail"]
        assert "contraseña" in poner(cer, key, "otra").json()["detail"]
        assert "pareja" in poner(cer, efirma_de_prueba()[1]).json()["detail"]
        assert "venció" in poner(*efirma_de_prueba(dias=-5)).json()["detail"]
        ajena = poner(*efirma_de_prueba(rfc="KIJ0906199R1"))
        assert ajena.status_code == 422 and "KIJ0906199R1" in ajena.json()["detail"] and e["rfc"] in ajena.json()["detail"]
        assert poner(b"basura", b"basura").status_code == 422
        assert c.get(f"/api/xml/efirma?emisor_id={e['id']}", headers=h).json() == {"puesta": False}

        r = poner(cer, key)
        assert r.status_code == 200, r.text
        est = r.json()
        assert est["puesta"] and est["rfc"] == e["rfc"] and est["minutos"] >= 119 and "fiel" not in est and "key" not in str(est).lower()
        # NO se guardó: ni en la base ni en ningún archivo de la carpeta de datos
        with SessionLocal() as db:
            em = db.get(Emisor, e["id"])
            assert em.fiel_cer is None and em.fiel_key_enc is None and em.fiel_password_enc is None and em.fiel_vence is None
        from app.config import settings
        firma = key[:64]
        for raiz, _dirs, archivos in os.walk(settings.data_dir):
            for a in archivos:
                with open(os.path.join(raiz, a), "rb") as fh:
                    assert firma not in fh.read(), f"la llave apareció en {a}"
        # otra cuenta no la ve ni la usa
        ajeno = _usuario(c, h, "xml-ajeno@prueba.mx", "xmlajeno")
        assert c.get(f"/api/xml/efirma?emisor_id={e['id']}", headers=ajeno).status_code == 404
        assert c.post(f"{url}/probar", headers=ajeno).status_code == 404
        assert c.delete(url, headers=ajeno).status_code == 404
        # se olvida sola con el tiempo…
        real = time.time
        monkeypatch.setattr(xml_firma.time, "time", lambda: real() + xml_firma.ESPERA + 5)
        assert c.get(f"/api/xml/efirma?emisor_id={e['id']}", headers=h).json() == {"puesta": False}
        monkeypatch.setattr(xml_firma.time, "time", real)
        # …o cuando lo pides
        assert poner(cer, key).status_code == 200
        assert c.delete(url, headers=h).json() == {"ok": True}
        assert c.get(f"/api/xml/efirma?emisor_id={e['id']}", headers=h).json() == {"puesta": False}
        # y al reiniciar el servidor no queda nada
        assert poner(cer, key).status_code == 200
        xml_firma.olvidar_todas()  # lo que pasa con la memoria al reiniciar
        assert xml_tareas.probar_efirma(e["id"])[0] is False


# ---------------------------------------------------------------- descarga completa
def test_descarga_del_sat_con_cancelados_tabla_y_exportaciones(sat):
    with TestClient(app) as c:
        h, e = _preparar(c)
        _vaciar(c, h, e)
        x, f = _juego(c, h, e)
        cancelado_sin_xml, vigente_sin_xml = "AAAAAAAA-1111-4222-8333-444444444444", "BBBBBBBB-1111-4222-8333-444444444444"
        cab = "Uuid~RfcEmisor~NombreEmisor~RfcReceptor~NombreReceptor~RfcPac~FechaEmision~FechaCertificacionSat~Monto~EfectoComprobante~Estatus~FechaCancelacion"
        hoy = date.today()
        lista_e = "\n".join([cab] + [
            f"{f[k]['uuid']}~{e['rfc']}~ESCUELA~CTE950627K46~CLIENTE~SPR190613I52~{hoy}T10:00:00~{hoy}T10:00:05~1160~I~1~" for k in ("f1", "f2", "pago")] + [
            f"{f['f3']['uuid']}~{e['rfc']}~ESCUELA~CTE950627K46~CLIENTE~SPR190613I52~{hoy}T10:00:00~{hoy}T10:00:05~232~I~0~{hoy}T18:30:00",
            f"{cancelado_sin_xml}~{e['rfc']}~ESCUELA~XAXX010101000~PUBLICO~SPR190613I52~{hoy}T09:00:00~{hoy}T09:00:05~999.50~I~0~{hoy}T09:30:00",
            f"{vigente_sin_xml}~{e['rfc']}~ESCUELA~XAXX010101000~PUBLICO~SPR190613I52~{hoy}T09:00:00~{hoy}T09:00:05~10~I~1~"])
        simulado = SatSimulado({"emitidos": [(f"{k}.xml", x[k]) for k in ("f1", "f2", "f3", "nc", "pago")] + [("leeme.txt", b"no soy xml")],
                                "recibidos": [("g1.xml", x["g1"]), ("g2.xml", x["g2"])]}, {"emitidos": lista_e})
        xml_tareas.fabrica_cliente = lambda emisor_id: simulado
        desde = hoy.replace(day=1).isoformat()
        r = c.post("/api/xml/descargas", headers=h, json={"emisor_id": e["id"], "desde": desde, "hasta": hoy.isoformat(), "tipo": "ambos"})
        assert r.status_code == 200, r.text
        t = esperar(c, h, r.json()["id"])
        assert t["estado"] == "listo", t
        assert t["resumen"]["nuevos"] == 7 and t["resumen"]["errores"] == [] and t["resumen"]["solicitudes"] == 4
        assert t["resumen"]["estatus"] == {"revisados": 6, "cancelados": 2, "nuevos_cancelados": 1, "sin_xml": 1}
        assert "XML nuevos" in t["registro"]

        base = f"/api/xml/cfdi?emisor_id={e['id']}"
        assert c.get(base, headers=h).json()["total"] == 8          # por omisión se ve todo, como en la tabla de siempre
        lista = c.get(base + "&estatus=Vigente", headers=h).json()
        assert lista["total"] == 6 and lista["cancelados"] == 2
        assert {k: v["n"] for k, v in lista["clases"].items()} == {"I": 2, "E": 1, "P": 1, "G": 2}
        assert c.get(base + "&estatus=Cancelado", headers=h).json()["total"] == 2
        todos = c.get(base + "&estatus=", headers=h).json()
        assert todos["total"] == 8
        por_uuid = {r_["uuid"]: r_ for r_ in todos["filas"]}
        assert por_uuid[f["f3"]["uuid"]]["estatus"] == "Cancelado" and por_uuid[f["f3"]["uuid"]]["cancelado_el"].startswith(str(hoy))
        aviso = por_uuid[cancelado_sin_xml]
        assert aviso["origen"] == "aviso" and aviso["estatus"] == "Cancelado" and aviso["total"] == 999.5 and aviso["clase"] == "I"
        assert vigente_sin_xml not in por_uuid                      # el SAT lo tiene y aquí falta: se cuenta, no se inventa
        assert c.get(base + "&tipo=Recibido", headers=h).json()["total"] == 2
        assert c.get(base + f"&q={f['f1']['uuid'][:8].lower()}", headers=h).json()["total"] == 1
        assert c.get(base + "&clase=G&q=kernel", headers=h).json()["total"] == 1
        assert c.get(base + "&mes=2019", headers=h).json()["total"] == 0

        # --- formato maestro: 65 columnas, un renglón por documento pagado
        completo = c.post("/api/xml/copiar", headers=h, json={"emisor_id": e["id"]}).text.split("\n")
        assert completo[0].split("\t") == EDDP and len(completo) == 1 + 9   # sin filtro: todo, cancelados incluidos
        tsv = c.post("/api/xml/copiar", headers=h, json={"emisor_id": e["id"], "estatus": "Vigente"}).text.split("\n")
        assert tsv[0].split("\t") == EDDP and all(len(l.split("\t")) == 65 for l in tsv)
        filas = [dict(zip(EDDP, l.split("\t"))) for l in tsv[1:]]
        assert len(filas) == 7                                       # 6 vigentes; el pago trae 2 documentos
        f1 = next(r_ for r_ in filas if r_["UUID"] == f["f1"]["uuid"])
        assert (f1["Tipo"], f1["Comprobante"], f1["Efecto"], f1["Método Pago"]) == ("Emitido", "Ingreso", "Ingreso (+)", "PPD")
        assert (f1["SubTotal"], f1["IVA Trasladado"], f1["Total"], f1["Base IVA 16"], f1["Tipo Cambio"]) == ("1000.0", "160.0", "1160.0", "1000.0", "1.0")
        assert f1["Fecha"][10] == " " and "T" in f1["Fecha Timbrado"] and f1["Descripción"] == "Honorarios de octubre"
        pagos = [r_ for r_ in filas if r_["UUID"] == f["pago"]["uuid"]]
        assert len(pagos) == 2 and {p["Doc Pagado UUID"] for p in pagos} == {f["f1"]["uuid"], f["f2"]["uuid"]}
        assert all(p["Es Pago"] == "Sí" and p["Monto Total Pago"] == "1460.0" and p["Efecto"] == "Pago cobrado" for p in pagos)
        assert sorted(p["Imp Pagado"] for p in pagos) == ["1160.0", "300.0"]
        nota = next(r_ for r_ in filas if r_["UUID"] == f["nc"]["uuid"])
        assert nota["Efecto"] == "Nota crédito emitida (-)" and nota["Relacionados"] == f["f3"]["uuid"] and nota["Total"] == "58.0"
        gasto = next(r_ for r_ in filas if r_["RFC Emisor"] == "KIJ0906199R1")
        assert (gasto["Tipo"], gasto["Efecto"], gasto["Total"]) == ("Recibido", "Gasto (-)", "348.0")
        assert not any(r_["UUID"] == f["f3"]["uuid"] for r_ in filas)  # con «sólo vigentes» la cancelada no viaja
        con_cancel = c.post("/api/xml/copiar", headers=h, json={"emisor_id": e["id"], "clase": "I"}).text.split("\n")
        assert len(con_cancel) == 1 + 4

        # --- Excel: las 73 de siempre + estatus al final, y el seguimiento de pago calculado
        from openpyxl import load_workbook
        r = c.post("/api/xml/excel", headers=h, json={"emisor_id": e["id"], "estatus": ""})
        assert r.status_code == 200 and e["rfc"] in r.headers["content-disposition"]
        wb = load_workbook(io.BytesIO(r.content))
        ws = wb["CFDI"]
        cab_x = [cel.value for cel in ws[1]]
        assert cab_x == EDDP and ws.max_column == 65          # la hoja principal es el formato maestro, ni una columna más
        assert wb.sheetnames == ["CFDI", "Seguimiento", "Resumen"]
        assert [cel.value for cel in wb["Seguimiento"][1]] == ["UUID", "Tipo", "Serie", "Folio", "Clase", "Estatus Pago", "Pagado REP", "Num REP",
                                                              "NC Aplicadas", "Saldo Pendiente", "Factura Encontrada", "Estatus SAT", "Cancelado el", "Archivo"]
        assert ws.max_row == wb["Seguimiento"].max_row       # mismo orden y mismos renglones en las dos hojas
        principal = [dict(zip(cab_x, [cel.value for cel in fila])) for fila in ws.iter_rows(min_row=2)]
        assert next(r_ for r_ in principal if r_["UUID"] == f["f1"]["uuid"])["Total"] == 1160
        ws = wb["Seguimiento"]
        cab_x = [cel.value for cel in ws[1]]
        hoja = [dict(zip(cab_x, [cel.value for cel in fila])) for fila in ws.iter_rows(min_row=2)]
        x1 = next(r_ for r_ in hoja if r_["UUID"] == f["f1"]["uuid"])
        x2 = next(r_ for r_ in hoja if r_["UUID"] == f["f2"]["uuid"])
        assert (x1["Clase"], x1["Estatus Pago"], x1["Pagado REP"], x1["Saldo Pendiente"], x1["Estatus SAT"]) == ("I", "Pagada", 1160, 0, "Vigente")
        assert (x2["Estatus Pago"], x2["Pagado REP"], x2["Saldo Pendiente"]) == ("Parcial", 300, 280)
        assert next(r_ for r_ in hoja if r_["UUID"] == f["f3"]["uuid"])["Estatus SAT"] == "Cancelado"

        # --- PDF propio: una sola hoja, y el XML tal cual
        from pypdf import PdfReader
        pid = por_uuid[f["f1"]["uuid"]]["id"]
        r = c.get(f"/api/xml/cfdi/{pid}/pdf", headers=h)
        assert r.status_code == 200 and r.content[:5] == b"%PDF-" and "_I_" in r.headers["content-disposition"]
        lector_pdf = PdfReader(io.BytesIO(r.content))
        assert len(lector_pdf.pages) == 1 and f["f1"]["uuid"] in lector_pdf.pages[0].extract_text()
        assert c.get(f"/api/xml/cfdi/{pid}/xml", headers=h).content == x["f1"]
        assert c.get(f"/api/xml/cfdi/{aviso['id']}/pdf", headers=h).status_code == 422   # del avisado no hay XML que pintar
        assert c.get(f"/api/xml/cfdi/{aviso['id']}/xml", headers=h).status_code == 404

        # --- ZIP con XML y PDF en las carpetas de siempre
        r = c.post("/api/xml/zip", headers=h, json={"filtros": {"emisor_id": e["id"], "estatus": "Vigente"}, "incluir": "ambos"})
        assert r.status_code == 200 and r.json()["total"] == 6
        tz = esperar(c, h, r.json()["id"])
        assert tz["estado"] == "listo" and tz["descargable"] and tz["resumen"]["comprobantes"] == 6 and not tz["resumen"]["avisos"], tz
        z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/xml/trabajos/{tz['id']}/archivo", headers=h).content))
        nombres = z.namelist()
        mes = f"{hoy:%Y%m} {e['rfc'][:4]}"
        assert len(nombres) == 12 and all(n.startswith(mes + "/emitidos/") or n.startswith(mes + "/recibidos/") for n in nombres)
        assert f"{mes}/emitidos/{f['f1']['uuid']}.xml" in nombres and sum(n.endswith(".pdf") for n in nombres) == 6

        # --- estadísticas reales, sin contar lo cancelado ni sumar los pagos como ingreso
        s = c.post("/api/xml/resumen", headers=h, json={"emisor_id": e["id"], "mes": f"{hoy:%Y-%m}"}).json()
        assert s["clases"]["I"] == {"n": 2, "subtotal": 1500.0, "iva": 240.0, "total": 1740.0}
        assert (s["ingresos"], s["gastos"], s["diferencia"]) == (1450.0, 400.0, 1050.0)   # 1,500 menos la nota de 50
        assert s["impuestos"]["iva_trasladado"] == 232.0 and s["impuestos"]["iva_acreditable"] == 48.0 and s["iva_a_cargo"] == 184.0
        assert s["cancelados"] == {"n": 2, "total": 1231.5}
        assert s["clientes"][0]["rfc"] == "CTE950627K46" and s["clientes"][0]["n"] == 2
        assert [p["rfc"] for p in s["proveedores"]] == ["KIJ0906199R1", "CTE950627K46"]
        assert s["por_mes"][0]["cobrado"] == 1460.0 and s["por_mes"][0]["ingresos"] == 1500.0 and s["por_mes"][0]["notas_emitidas"] == 50.0

        # --- pedir el mismo periodo otra vez no vuelve a molestar al SAT ni duplica nada
        antes = len(simulado.solicitudes)
        r = c.post("/api/xml/descargas", headers=h, json={"emisor_id": e["id"], "desde": desde, "hasta": hoy.isoformat(), "tipo": "ambos"})
        t2 = esperar(c, h, r.json()["id"])
        assert t2["estado"] == "listo" and t2["resumen"]["nuevos"] == 0 and len(simulado.solicitudes) == antes
        assert c.get(base + "&estatus=", headers=h).json()["total"] == 8
        # …pero la lista de cancelados sí se vuelve a pedir pasado un día (un CFDI se cancela después)
        estado = next(xml_indice.carpeta_estado().glob(f"estado_solicitudes_{e['id']}.json"))
        import json
        d = json.loads(estado.read_text(encoding="utf-8"))
        for k in d:
            d[k]["actualizado"] = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        estado.write_text(json.dumps(d), encoding="utf-8")
        simulado.listas["emitidos"] = lista_e.replace(f"{f['f2']['uuid']}~{e['rfc']}~ESCUELA~CTE950627K46~CLIENTE~SPR190613I52~{hoy}T10:00:00~{hoy}T10:00:05~1160~I~1~",
                                                      f"{f['f2']['uuid']}~{e['rfc']}~ESCUELA~CTE950627K46~CLIENTE~SPR190613I52~{hoy}T10:00:00~{hoy}T10:00:05~1160~I~0~{hoy}T20:00:00")
        r = c.post("/api/xml/descargas", headers=h, json={"emisor_id": e["id"], "desde": desde, "hasta": hoy.isoformat(), "tipo": "emitidos"})
        t3 = esperar(c, h, r.json()["id"])
        nuevas = simulado.solicitudes[antes:]
        assert t3["estado"] == "listo" and [n[0] for n in nuevas] == ["lista"], nuevas     # sólo la lista, ningún XML
        assert c.get(base + "&estatus=Cancelado", headers=h).json()["total"] == 3

        # --- otra cuenta no ve nada de esto
        ajeno = _usuario(c, h, "xml-ajeno2@prueba.mx", "xmlajeno2")
        assert c.get(base, headers=ajeno).status_code == 404
        for metodo, ruta, cuerpo in [("get", f"/api/xml/cfdi/{pid}/pdf", None), ("get", f"/api/xml/cfdi/{pid}/xml", None),
                                     ("post", "/api/xml/copiar", {"emisor_id": e["id"]}), ("post", "/api/xml/excel", {"emisor_id": e["id"]}),
                                     ("post", "/api/xml/resumen", {"emisor_id": e["id"]}), ("post", "/api/xml/borrar", {"emisor_id": e["id"]}),
                                     ("get", f"/api/xml/trabajos/{tz['id']}", None), ("get", f"/api/xml/trabajos/{tz['id']}/archivo", None),
                                     ("post", "/api/xml/zip", {"filtros": {"emisor_id": e["id"]}}),
                                     ("post", "/api/xml/descargas", {"emisor_id": e["id"], "desde": desde, "hasta": hoy.isoformat()})]:
            r = getattr(c, metodo)(ruta, headers=ajeno, **({"json": cuerpo} if cuerpo is not None else {}))
            assert r.status_code == 404, (ruta, r.status_code)
        assert c.get(base + "&estatus=", headers=h).json()["total"] == 8   # y sigue todo ahí para su dueño


def test_leer_xml_propios_una_carpeta_un_zip_y_lo_que_no_es(sat):
    with TestClient(app) as c:
        h, e = _preparar(c)
        _vaciar(c, h, e)
        x, f = _juego(c, h, e)
        de_otro = _recibido("KIJ0906199R1", "KERNEL INDUSTIA JUGUETERA", "10", receptor="CTE950627K46")   # no es de este RFC
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as z:
            z.writestr("carpeta/octubre/g1.xml", x["g1"])
            z.writestr("carpeta/notas.txt", b"hola")
        archivos = [("archivos", ("f1.xml", x["f1"], "text/xml")), ("archivos", ("pago.xml", x["pago"], "text/xml")),
                    ("archivos", ("todo.zip", mem.getvalue(), "application/zip")), ("archivos", ("ajeno.xml", de_otro, "text/xml")),
                    ("archivos", ("basura.xml", b"<html>no soy cfdi</html>", "text/xml")), ("archivos", ("foto.png", b"\x89PNG", "image/png"))]
        r = c.post(f"/api/xml/subir?emisor_id={e['id']}", headers=h, files=archivos)
        assert r.status_code == 200 and r.json() == {"nuevos": 3, "repetidos": 0, "ajenos": 1, "invalidos": 1}, r.text
        assert c.post(f"/api/xml/subir?emisor_id={e['id']}", headers=h, files=archivos).json()["repetidos"] == 3   # leerla dos veces no duplica
        lista = c.get(f"/api/xml/cfdi?emisor_id={e['id']}", headers=h).json()
        assert lista["total"] == 3 and {k: v["n"] for k, v in lista["clases"].items()} == {"I": 1, "P": 1, "G": 1}
        assert all(r_["origen"] == "subido" for r_ in lista["filas"])
        assert lista["meses"] == [{"mes": f"{date.today():%Y-%m}", "n": 3}]
        # el XML quedó en la carpeta de datos, con la estructura de siempre
        ruta = xml_indice.carpeta_xml(e["id"]) / f"{date.today():%Y%m} {e['rfc'][:4]}" / "emitidos" / f"{f['f1']['uuid']}.xml"
        assert ruta.read_bytes() == x["f1"]
        # borrar lo que estás viendo: desaparece del índice y del disco, y se puede volver a leer
        assert c.post("/api/xml/borrar", headers=h, json={"emisor_id": e["id"], "clase": "I"}).json() == {"borrados": 1}
        assert not ruta.exists() and c.get(f"/api/xml/cfdi?emisor_id={e['id']}", headers=h).json()["total"] == 2
        assert c.post(f"/api/xml/subir?emisor_id={e['id']}", headers=h, files=archivos[:1]).json()["nuevos"] == 1
        assert c.post("/api/xml/zip", headers=h, json={"filtros": {"emisor_id": e["id"], "mes": "2019"}}).status_code == 422
        # lo que Timbra mismo cancela ante el SAT se ve cancelado aquí sin esperar a la lista del SAT
        assert c.post(f"/api/facturas/{f['f1']['id']}/cancelar", headers=h, json={"motivo": "02"}).status_code in (200, 422)
        c.post(f"/api/facturas/{f['f3']['id']}/cancelar", headers=h, json={"motivo": "02"})
        c.post(f"/api/xml/subir?emisor_id={e['id']}", headers=h, files=[("archivos", ("f3.xml", x["f3"], "text/xml"))])
        todos = {r_["uuid"]: r_["estatus"] for r_ in c.get(f"/api/xml/cfdi?emisor_id={e['id']}&estatus=", headers=h).json()["filas"]}
        assert todos[f["f3"]["uuid"]] == "Cancelado"


def test_descarga_que_falla_o_se_interrumpe_no_pierde_nada(sat):
    with TestClient(app) as c:
        h, e = _preparar(c)
        _vaciar(c, h, e)
        x, _f = _juego(c, h, e)
        hoy = date.today()
        cuerpo = {"emisor_id": e["id"], "desde": hoy.replace(day=1).isoformat(), "hasta": hoy.isoformat(), "tipo": "emitidos", "cancelados": True}

        class Tropieza(SatSimulado):
            def solicitar_metadata(self, rfc, tipo, desde, hasta):
                raise RuntimeError("el SAT no contestó la lista")

        xml_tareas.fabrica_cliente = lambda emisor_id: Tropieza({"emitidos": [("f1.xml", x["f1"])]})
        import app.xmlsat.flujo as flujo
        t = esperar(c, h, c.post("/api/xml/descargas", headers=h, json=cuerpo).json()["id"], 90)
        # los XML sí quedaron; lo de los cancelados va como aviso, no como error de la descarga
        assert t["estado"] == "listo" and t["resumen"]["nuevos"] == 1 and t["resumen"]["errores"] == [] and t["resumen"]["avisos"], t
        assert flujo.COD_SIN_INFO == "5004"
        # fechas imposibles
        assert c.post("/api/xml/descargas", headers=h, json={**cuerpo, "hasta": (hoy + timedelta(days=3)).isoformat()}).status_code == 422
        assert c.post("/api/xml/descargas", headers=h, json={**cuerpo, "desde": hoy.isoformat(), "hasta": (hoy - timedelta(days=1)).isoformat()}).status_code == 422
        assert c.post("/api/xml/descargas", headers=h, json={**cuerpo, "tipo": "todo"}).status_code == 422
        # si el servidor se reinicia a media descarga, queda marcada y dice qué hacer
        with SessionLocal() as db:
            db.add(XmlTrabajo(emisor_id=e["id"], clase="sat", params={}, resumen={}, registro="", estado="curso"))
            db.commit()
    with TestClient(app) as c:  # arranque nuevo
        h, e = _preparar(c)
        ts = c.get(f"/api/xml/trabajos?emisor_id={e['id']}", headers=h).json()
        assert ts[0]["estado"] == "interrumpido" and "e.firma" in ts[0]["mensaje"]
        assert c.get(f"/api/xml/cfdi?emisor_id={e['id']}", headers=h).json()["total"] == 1   # lo bajado sigue ahí


def test_leer_una_carpeta_de_cualquier_contribuyente_lo_abre_solo(sat):
    """Uso real: el contador eligió la carpeta de un cliente estando en otro RFC y «no jaló nada». Ahora el dueño de la
    carpeta se saca de los XML, se da de alta si hace falta, y ahí quedan guardados."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        nuevo, proveedores = "HEGT761003VZ6", ["KIJ0906199R1", "CTE950627K46", "ABC970528UHA"]   # RFC inventado: no existe en la cuenta
        for x in c.get("/api/emisores", headers=h).json():
            if x["rfc"] == nuevo:
                assert c.delete(f"/api/emisores/{x['id']}?confirmar={nuevo}", headers=h).status_code == 200
        xmls = [_recibido(p, "PROVEEDOR DE PRUEBA", str(100 + i), receptor=nuevo, tasa="0.16") for i, p in enumerate(proveedores)]
        ajeno = _recibido("ICV060329BY0", "INMOBILIARIA", "5", receptor="GCA000415UX7")
        # si todos los XML son del mismo proveedor, no se puede saber de quién es la carpeta: se pregunta, no se adivina
        dos = [("archivos", ("a.xml", xmls[0], "text/xml"))]
        duda = c.post("/api/xml/leer", headers=h, files=dos).json()
        assert {x["rfc"] for x in duda["elegir"]} == {nuevo, "KIJ0906199R1"} and "emisor_id" not in duda
        assert not any(x["rfc"] in (nuevo, "KIJ0906199R1") for x in c.get("/api/emisores", headers=h).json())   # no se dio de alta nada
        archivos = [("archivos", (f"{i}.xml", x, "text/xml")) for i, x in enumerate(xmls)] + [("archivos", ("otro.xml", ajeno, "text/xml"))]
        r = c.post("/api/xml/leer", headers=h, files=archivos)
        assert r.status_code == 200, r.text
        j = r.json()
        # el contribuyente es el RFC que aparece en (casi) todos; el que no es suyo se cuenta aparte
        assert (j["rfc"], j["creado"], j["nuevos"], j["ajenos"]) == (nuevo, True, 3, 1), j
        em = next(x for x in c.get("/api/emisores", headers=h).json() if x["id"] == j["emisor_id"])
        assert em["rfc"] == nuevo and em["nombre"] == "ESCUELA KEMPER URGATE" and em["lugar_expedicion"] == "42501" and em["regimen_fiscal"] == "601"
        lista = c.get(f"/api/xml/cfdi?emisor_id={j['emisor_id']}", headers=h).json()
        assert lista["total"] == 3 and {k: v["n"] for k, v in lista["clases"].items()} == {"G": 3}
        tsv = c.post("/api/xml/copiar", headers=h, json={"emisor_id": j["emisor_id"]}).text.split("\n")
        assert tsv[0].split("\t") == EDDP and len(tsv) == 1 + 3 and all(len(x.split("\t")) == 65 for x in tsv)
        assert {x.split("\t")[0] for x in tsv[1:]} == {"Recibido"} and {x.split("\t")[7] for x in tsv[1:]} == {"Gasto (-)"}
        # leerla otra vez no duplica ni vuelve a dar de alta
        r2 = c.post("/api/xml/leer", headers=h, files=archivos).json()
        assert (r2["creado"], r2["emisor_id"], r2["nuevos"], r2["repetidos"]) == (False, j["emisor_id"], 0, 3)
        # una carpeta sin CFDI se dice claro
        r = c.post("/api/xml/leer", headers=h, files=[("archivos", ("a.xml", b"<html/>", "text/xml"))])
        assert r.status_code == 422 and "CFDI" in r.json()["detail"]
        # otra cuenta no puede quedarse con un RFC que ya es de alguien
        ajeno_h = _usuario(c, h, "xml-ajeno3@prueba.mx", "xmlajeno3")
        r = c.post("/api/xml/leer", headers=ajeno_h, files=archivos)
        assert r.status_code == 409 and "otra cuenta" in r.json()["detail"]
        eid = j["emisor_id"]
    with TestClient(app) as c:   # lo guardado es de la cuenta: sigue ahí tras reiniciar
        h, _e = _preparar(c)
        assert c.get(f"/api/xml/cfdi?emisor_id={eid}", headers=h).json()["total"] == 3
        assert c.delete(f"/api/emisores/{eid}?confirmar={nuevo}", headers=h).status_code == 200
        assert not xml_indice.carpeta_xml(eid).exists()


def test_una_carpeta_con_varios_contribuyentes_se_separa_sola(sat):
    """Una carpeta con XML de dos clientes del despacho: cada CFDI se va con su dueño, y uno entre los dos queda en ambos."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        a, b = "MAAF800101AB1", "SOLB810202CD2"   # RFC inventados
        for x in c.get("/api/emisores", headers=h).json():
            if x["rfc"] in (a, b):
                c.delete(f"/api/emisores/{x['id']}?confirmar={x['rfc']}", headers=h)
        de_a = [_recibido(a, "CLIENTE A", str(300 + i), receptor=p) for i, p in enumerate(["KIJ0906199R1", "CTE950627K46", "ABC970528UHA", "ICV060329BY0"])]
        para_b = [_recibido(p, "PROVEEDOR", str(400 + i), receptor=b) for i, p in enumerate(["GCA000415UX7", "HHN0507087N4", "AMO8905171T1"])]
        entre = _recibido(a, "CLIENTE A", "999", receptor=b)                     # A le factura a B
        archivos = [("archivos", (f"{i}.xml", x, "text/xml")) for i, x in enumerate(de_a + para_b + [entre])]
        j = c.post("/api/xml/leer", headers=h, files=archivos).json()
        por_rfc = {x["rfc"]: x for x in j["contribuyentes"]}
        assert set(por_rfc) == {a, b} and all(x["creado"] for x in por_rfc.values()), j
        assert por_rfc[a]["nuevos"] == 5 and por_rfc[b]["nuevos"] == 4 and j["nuevos"] == 9 and j["ajenos"] == 0
        assert j["rfc"] == a   # el principal (el que más trae) va arriba para abrirlo en pantalla
        lista_a = c.get(f"/api/xml/cfdi?emisor_id={por_rfc[a]['emisor_id']}", headers=h).json()
        lista_b = c.get(f"/api/xml/cfdi?emisor_id={por_rfc[b]['emisor_id']}", headers=h).json()
        assert lista_a["total"] == 5 and lista_b["total"] == 4
        # otra tanda de la misma carpeta: ya son tuyos, no se duplica nada
        j2 = c.post("/api/xml/leer", headers=h, files=archivos).json()
        assert j2["nuevos"] == 0 and j2["repetidos"] == 9
        for x in por_rfc.values():
            c.delete(f"/api/emisores/{x['emisor_id']}?confirmar={x['rfc']}", headers=h)


def test_la_efirma_de_cualquier_contribuyente_abre_su_rfc(sat):
    with TestClient(app) as c:
        h, e = _preparar(c)
        rfc = "LOVA850312JK4"
        for x in c.get("/api/emisores", headers=h).json():
            if x["rfc"] == rfc:
                c.delete(f"/api/emisores/{x['id']}?confirmar={rfc}", headers=h)
        cer, key = efirma_de_prueba(rfc=rfc)
        archivos = {"cer": ("e.cer", cer), "key": ("e.key", key)}
        r = c.post("/api/xml/efirma", headers=h, data={"password": "12345678a"}, files=archivos)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["creado"] is True and j["rfc"] == rfc and j["puesta"] and j["emisor_id"] != e["id"] and "fiel" not in j
        assert c.get(f"/api/xml/efirma?emisor_id={j['emisor_id']}", headers=h).json()["puesta"] is True
        assert c.get(f"/api/xml/efirma?emisor_id={e['id']}", headers=h).json() == {"puesta": False}   # la de uno no sirve para otro
        r = c.post("/api/xml/efirma", headers=h, data={"password": "12345678a"}, files=archivos).json()
        assert r["creado"] is False and r["emisor_id"] == j["emisor_id"]
        assert c.post("/api/xml/efirma", headers=h, data={"password": "mala"}, files=archivos).status_code == 422
        assert c.delete(f"/api/emisores/{j['emisor_id']}?confirmar={rfc}", headers=h).status_code == 200
        assert xml_firma.estado(j["emisor_id"]) == {"puesta": False}   # al eliminar el RFC, su e.firma en memoria se olvida


def test_si_el_sat_rechaza_el_certificado_se_dice_una_vez_y_no_se_insiste(sat):
    """Uso real: con la e.firma del RFC de pruebas el SAT contestó «305 Certificado Inválido» una vez por cada mes."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        _vaciar(c, h, e)

        class Rechaza(SatSimulado):
            def solicitar(self, rfc, tipo, desde, hasta):
                self.solicitudes.append(("xml", tipo, desde, hasta))
                return {"cod_estatus": "305", "mensaje": "Certificado Inválido", "id_solicitud": None}

        simulado = Rechaza({})
        xml_tareas.fabrica_cliente = lambda emisor_id: simulado
        cer, key = efirma_de_prueba()
        c.post(f"/api/xml/efirma/{e['id']}", headers=h, data={"password": "12345678a"}, files={"cer": ("e.cer", cer), "key": ("e.key", key)})
        hoy = date.today()
        r = c.post("/api/xml/descargas", headers=h, json={"emisor_id": e["id"], "desde": f"{hoy.year}-01-01", "hasta": hoy.isoformat(), "tipo": "ambos"})
        t = esperar(c, h, r.json()["id"])
        assert t["estado"] == "error" and len(t["resumen"]["errores"]) == 1, t
        assert "no acepta ese certificado" in t["resumen"]["errores"][0] and "305" in t["resumen"]["errores"][0]
        assert len(simulado.solicitudes) == 1                      # una sola pregunta al SAT, no una por mes
        assert xml_firma.estado(e["id"]) == {"puesta": False}      # la e.firma que no sirvió se olvida


def _recibo_nomina(uuid, fecha, sueldo, exento, isr, seg, otra, receptor="EKU9003173C9", patron="SEP210905778"):
    """Recibo de nómina inventado con la forma del complemento Nómina 1.2."""
    per, ded = sueldo + exento, isr + seg + otra
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:nomina12="http://www.sat.gob.mx/nomina12" Version="4.0" Serie="N" Folio="{uuid[:4]}"
  Fecha="{fecha}T09:00:00" SubTotal="{per:.2f}" Descuento="{ded:.2f}" Total="{per - ded:.2f}" Moneda="MXN" TipoDeComprobante="N" MetodoPago="PUE" Exportacion="01" LugarExpedicion="42501">
  <cfdi:Emisor Rfc="{patron}" Nombre="PATRON DE PRUEBA" RegimenFiscal="603"/>
  <cfdi:Receptor Rfc="{receptor}" Nombre="TRABAJADOR DE PRUEBA" DomicilioFiscalReceptor="42501" RegimenFiscalReceptor="605" UsoCFDI="CN01"/>
  <cfdi:Conceptos><cfdi:Concepto ClaveProdServ="84111505" Cantidad="1" ClaveUnidad="ACT" Descripcion="Pago de nómina" ValorUnitario="{per:.2f}" Importe="{per:.2f}" Descuento="{ded:.2f}" ObjetoImp="01"/></cfdi:Conceptos>
  <cfdi:Complemento>
    <nomina12:Nomina Version="1.2" TipoNomina="O" FechaPago="{fecha}" FechaInicialPago="{fecha[:8]}01" FechaFinalPago="{fecha}" NumDiasPagados="15" TotalPercepciones="{per:.2f}" TotalDeducciones="{ded:.2f}">
      <nomina12:Emisor RegistroPatronal="Y1234567101"/>
      <nomina12:Receptor Curp="XEXX010101HNEXXXA4" NumEmpleado="7" Puesto="DOCENTE" TipoRegimen="02" PeriodicidadPago="04" ClaveEntFed="HID" TipoContrato="01"/>
      <nomina12:Percepciones TotalSueldos="{per:.2f}" TotalGravado="{sueldo:.2f}" TotalExento="{exento:.2f}">
        <nomina12:Percepcion TipoPercepcion="001" Clave="P1" Concepto="SUELDO BASE" ImporteGravado="{sueldo:.2f}" ImporteExento="0.00"/>
        <nomina12:Percepcion TipoPercepcion="038" Clave="P2" Concepto="AYUDA DE DESPENSA" ImporteGravado="0.00" ImporteExento="{exento:.2f}"/>
      </nomina12:Percepciones>
      <nomina12:Deducciones TotalOtrasDeducciones="{seg + otra:.2f}" TotalImpuestosRetenidos="{isr:.2f}">
        <nomina12:Deduccion TipoDeduccion="002" Clave="D1" Concepto="ISR" Importe="{isr:.2f}"/>
        <nomina12:Deduccion TipoDeduccion="001" Clave="D2" Concepto="SEGURO DE SALUD" Importe="{seg:.2f}"/>
        <nomina12:Deduccion TipoDeduccion="019" Clave="D3" Concepto="CUOTAS SINDICALES" Importe="{otra:.2f}"/>
      </nomina12:Deducciones>
    </nomina12:Nomina>
    <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha}T09:00:05" RfcProvCertif="SPR190613I52" SelloCFD="x" NoCertificadoSAT="1" SelloSAT="y"/>
  </cfdi:Complemento>
</cfdi:Comprobante>""".encode()


def test_nomina_a_detalle_sin_tocar_el_formato_maestro(sat):
    """Uso real: un contribuyente asalariado traía casi pura nómina y los datos no decían nada de ella."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        _vaciar(c, h, e)
        recibos = [("A0000001-1111-4222-8333-444444444444", "2026-08-15", 10000, 500, 1500, 400, 100),
                   ("A0000002-1111-4222-8333-444444444444", "2026-08-31", 10000, 500, 1500, 400, 100),
                   ("A0000003-1111-4222-8333-444444444444", "2026-09-15", 12000, 0, 2000, 480, 0)]
        archivos = [("archivos", (f"{u}.xml", _recibo_nomina(u, *r_), "text/xml")) for u, *r_ in recibos]
        archivos.append(("archivos", ("otro_patron.xml", _recibo_nomina("A0000004-1111-4222-8333-444444444444", "2026-09-30", 3000, 0, 100, 50, 0, patron="KIJ0906199R1"), "text/xml")))
        assert c.post(f"/api/xml/subir?emisor_id={e['id']}", headers=h, files=archivos).json()["nuevos"] == 4
        s = c.post("/api/xml/resumen", headers=h, json={"emisor_id": e["id"]}).json()
        n = s["nomina"]["recibida"]
        assert s["nomina"]["pagada"]["recibos"] == 0 and n["recibos"] == 4
        assert (n["percepciones"], n["gravado"], n["exento"]) == (36000.0, 35000.0, 1000.0)
        assert (n["isr"], n["imss"], n["otras_deducciones"], n["deducciones"]) == (5100.0, 1330.0, 200.0, 6630.0)
        assert n["neto"] == 29370.0 == round(n["percepciones"] + n["otros_pagos"] - n["deducciones"], 2)
        assert [(m["mes"], m["recibos"], m["percepciones"], m["isr"], m["neto"]) for m in n["por_mes"]] == [
            ("2026-08", 2, 21000.0, 3000.0, 17000.0), ("2026-09", 2, 15000.0, 2100.0, 12370.0)]
        assert [(q["rfc"], q["recibos"], q["percepciones"]) for q in n["por_quien"]] == [("SEP210905778", 3, 33000.0), ("KIJ0906199R1", 1, 3000.0)]
        assert n["percepciones_det"][0] == {"concepto": "SUELDO BASE", "tipo": "Sueldos y salarios", "gravado": 35000.0, "exento": 0.0}
        assert {d["concepto"]: d["importe"] for d in n["deducciones_det"]} == {"ISR": 5100.0, "SEGURO DE SALUD": 1330.0, "CUOTAS SINDICALES": 200.0}
        assert s["ingresos"] == 0 and s["gastos"] == 0            # la nómina no se mezcla con ingresos ni gastos facturados
        # el formato maestro no cambió: 65 columnas, y el desglose no se cuela en lo copiado
        tsv = c.post("/api/xml/copiar", headers=h, json={"emisor_id": e["id"]}).text.split("\n")
        assert tsv[0].split("\t") == EDDP and all(len(x.split("\t")) == 65 for x in tsv) and "SUELDO BASE" not in "".join(tsv)
        assert tsv[1].split("\t")[6:8] == ["Nómina", "Nómina"]
        # el Excel trae una hoja «Nómina» con un renglón por recibo
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(c.post("/api/xml/excel", headers=h, json={"emisor_id": e["id"]}).content))
        assert wb.sheetnames == ["CFDI", "Seguimiento", "Resumen", "Nómina"] and [x.value for x in wb["CFDI"][1]] == EDDP
        hoja = [[x.value for x in fila] for fila in wb["Nómina"].iter_rows()]
        assert len(hoja) == 5 and hoja[0][10:20] == ["Percepciones", "Gravado", "Exento", "Otros pagos", "Subsidio", "Deducciones", "ISR retenido", "Seguridad social", "Otras deducciones", "Neto pagado"]
        assert hoja[1][1] == "2026-08-15" and hoja[1][10:13] == [10500, 10000, 500] and hoja[1][16] == 1500 and hoja[1][19] == 8500
        # lo que se bajó antes de existir el desglose se completa solo al arrancar
        with SessionLocal() as db:
            from app.models import XmlCfdi
            x = db.query(XmlCfdi).filter_by(emisor_id=e["id"], clase="N").first()
            x.filas = [{k: v for k, v in x.filas[0].items() if k != "_nomina"}]
            db.commit()
            assert xml_indice.completar_nomina(db) == 1 and xml_indice.completar_nomina(db) == 0
        assert c.post("/api/xml/resumen", headers=h, json={"emisor_id": e["id"]}).json()["nomina"]["recibida"]["isr"] == 5100.0
        _vaciar(c, h, e)


def test_un_contribuyente_que_solo_baja_xml_no_recibe_avisos_de_csd(sat):
    with TestClient(app) as c:
        h, _e = _preparar(c)
        rfc = "MOGA900101AB1"
        for x in c.get("/api/emisores", headers=h).json():
            if x["rfc"] == rfc:
                c.delete(f"/api/emisores/{x['id']}?confirmar={rfc}", headers=h)
        archivos = [("archivos", (f"{i}.xml", _recibo_nomina(f"B000001{i}-1111-4222-8333-444444444444", "2026-08-15", 1000, 0, 50, 10, 0, receptor=rfc, patron=p), "text/xml"))
                    for i, p in enumerate(("SEP210905778", "KIJ0906199R1"))]
        j = c.post("/api/xml/leer", headers=h, files=archivos).json()
        assert j["rfc"] == rfc and j["creado"]
        assert not any("CSD" in a["texto"] for a in c.get(f"/api/dashboard?emisor_id={j['emisor_id']}", headers=h).json()["alertas"])
        assert c.get(f"/api/pendientes/resumen?emisor_id={j['emisor_id']}", headers=h).json()["errores"] == 0
        c.delete(f"/api/emisores/{j['emisor_id']}?confirmar={rfc}", headers=h)


def test_un_periodo_sin_comprobantes_no_es_un_error(sat):
    """Uso real: una contribuyente asalariada no tiene emitidos; el SAT terminó esas solicitudes en estado 5 con 5004
    y la descarga salía «con error» aunque todo lo recibido se había bajado bien."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        _vaciar(c, h, e)
        g1 = _recibido("KIJ0906199R1", "KERNEL INDUSTIA JUGUETERA", "300", tasa="0.16")

        class SinEmitidos(SatSimulado):
            def solicitar(self, rfc, tipo, desde, hasta):
                if tipo == "emitidos":   # el SAT sí acepta la solicitud…
                    self.solicitudes.append(("xml", tipo, desde, hasta))
                    return {"cod_estatus": "5000", "mensaje": "Solicitud Aceptada", "id_solicitud": "sol-xml-vacio-1"}
                return super().solicitar(rfc, tipo, desde, hasta)

            def verificar(self, rfc, id_solicitud):
                if "vacio" in id_solicitud:  # …y luego la termina rechazada porque no hay nada
                    return {"estado_solicitud": "5", "cod_estatus": "5000", "codigo_estado_solicitud": "5004", "numero_cfdis": "0",
                            "mensaje": "Solicitud Aceptada", "paquetes": []}
                return super().verificar(rfc, id_solicitud)

        xml_tareas.fabrica_cliente = lambda emisor_id: SinEmitidos({"recibidos": [("g1.xml", g1)]})
        hoy = date.today()
        r = c.post("/api/xml/descargas", headers=h, json={"emisor_id": e["id"], "desde": hoy.replace(day=1).isoformat(), "hasta": hoy.isoformat(),
                                                         "tipo": "ambos", "cancelados": False})
        t = esperar(c, h, r.json()["id"])
        assert t["estado"] == "listo" and t["resumen"]["errores"] == [] and t["resumen"]["nuevos"] == 1, t
        _vaciar(c, h, e)
