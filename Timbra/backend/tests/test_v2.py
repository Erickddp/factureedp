"""Timbres, PDF con marca, recurrentes, nómina 1.2, portal de autofactura, cobranza, descarga SAT y respaldo."""
import os
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402
from satcfdi.cfdi import CFDI  # noqa: E402

from app.main import app  # noqa: E402

CSD = Path(__file__).parent / "csd"
IVA16 = {"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}


def _preparar(c):
    """Login + emisor EKU9003173C9 con CSD de pruebas y PAC demo (reusa el de otras pruebas si existe)."""
    tok = c.post("/api/auth/login", json={"email": "rick@erickddp.com", "password": "cambiame"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    es = [e for e in c.get("/api/emisores", headers=h).json() if e["rfc"] == "EKU9003173C9"]
    if es:
        e = es[0]
    else:
        pac = c.post("/api/pacs", headers=h, json={"nombre": "Demo", "proveedor": "demo"}).json()
        e = c.post("/api/emisores", headers=h, json={
            "rfc": "EKU9003173C9", "nombre": "ESCUELA KEMPER URGATE", "regimen_fiscal": "601",
            "lugar_expedicion": "42501", "pac_id": pac["id"]}).json()
    if not e.get("no_certificado"):
        c.post(f"/api/emisores/{e['id']}/csd", headers=h,
               files={"cer": open(CSD / "EKU9003173C9.cer", "rb"), "key": open(CSD / "EKU9003173C9.key", "rb")},
               data={"password": "12345678a"})
    e = c.put(f"/api/emisores/{e['id']}", headers=h, json={
        "rfc": e["rfc"], "nombre": e["nombre"], "regimen_fiscal": "601", "lugar_expedicion": "42501",
        "pac_id": e["pac_id"], "region_fronteriza": False, "registro_patronal": "Y5234567101",
        "color": "#0a7c66", "logo_b64": "data:image/png;base64,iVBORw0KGgo="}).json()
    return h, e


def _cliente(c, h, e, rfc="CTE950627K46", nombre="COMERCIALIZADORA TEXTIL ELEGANTE", cp="57740", dias=0, emails=()):
    r = c.post("/api/clientes", headers=h, json={
        "emisor_id": e["id"], "rfc": rfc, "nombre": nombre, "regimen_fiscal": "601", "codigo_postal": cp,
        "uso_cfdi": "G03", "dias_credito": dias, "emails": list(emails)})
    if r.status_code == 200:
        return r.json()
    assert r.status_code == 409, r.text
    return [x for x in c.get(f"/api/clientes?emisor_id={e['id']}", headers=h).json() if x["rfc"] == rfc][0]


def _factura(c, h, e, cli, total="1000", metodo="PUE", descripcion="Servicio"):
    body = {"emisor_id": e["id"], "cliente_id": cli["id"], "metodo_pago": metodo, "forma_pago": "03",
            "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": descripcion,
                           "valor_unitario": total, "impuestos": [IVA16]}]}
    r = c.post("/api/facturas", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json(), body


def test_timbres_y_pdf_con_marca():
    from app.db import SessionLocal
    from app.models import Factura, Pac
    from app.services import timbres

    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        f, _ = _factura(c, h, e, cli)
        html = c.get(f"/api/facturas/{f['id']}/html", headers=h).text
        assert 'class="logo"' in html and "#0a7c66" in html and "data:image/png;base64" in html
        assert "ESCUELA KEMPER URGATE" in html

        # Paquete de 2 timbres en un PAC de producción: con 2 UUID ya usados, bloquea antes de timbrar
        with SessionLocal() as db:
            p = Pac(nombre="SW paquete", proveedor="swsapien", pruebas=False, timbres_contratados=2,
                    timbres_desde=datetime.now() - timedelta(days=1), timbres_alerta=1, extra={})
            db.add(p)
            db.flush()
            from app.models import Emisor
            otro = Emisor(rfc="AAA010101AAA", nombre="PRUEBA TIMBRES", regimen_fiscal="601", lugar_expedicion="01000",
                          pac_id=p.id)
            db.add(otro)
            db.flush()
            r = timbres.resumen(db)
            fila = [x for x in r if x["pac_id"] == p.id][0]
            assert fila["restantes"] == 2 and fila["nivel"] == "ok"
            for i in range(2):
                db.add(Factura(emisor_id=otro.id, tipo="I", uuid=f"00000000-0000-0000-0000-00000000000{i}",
                               fecha_timbrado=datetime.now(), estado="timbrada", payload={}))
            db.flush()
            fila = [x for x in timbres.resumen(db) if x["pac_id"] == p.id][0]
            assert fila["restantes"] == 0 and fila["nivel"] == "error"
            assert "Se acabaron" in timbres.bloqueo(p, db)
            db.rollback()
        assert c.get("/api/pacs/timbres", headers=h).status_code == 200


def test_recurrente_iguala_mensual():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        f, _ = _factura(c, h, e, cli, descripcion="Honorarios contables {MES} {año}")
        p = c.post(f"/api/plantillas/desde-factura/{f['id']}?nombre=Iguala URE", headers=h).json()
        hoy = date.today()
        p = c.put(f"/api/plantillas/{p['id']}", headers=h,
                  json={"recurrente": True, "dia": hoy.day, "favorita": 1}).json()
        assert p["proxima"].startswith(hoy.isoformat()) and p["favorita"] == 1
        pend = c.get(f"/api/plantillas/recurrentes/pendientes?emisor_id={e['id']}", headers=h).json()
        assert any(x["id"] == p["id"] for x in pend)
        r = c.post(f"/api/plantillas/{p['id']}/timbrar", headers=h)
        assert r.status_code == 200, r.text
        xml = c.get(f"/api/facturas/{r.json()['factura_id']}/xml", headers=h).content
        from app.services.recurrentes import MESES
        assert f"Honorarios contables {MESES[hoy.month - 1].upper()} {hoy.year}".encode() in xml
        # Ya no está pendiente: avanzó al siguiente mes
        pend = c.get(f"/api/plantillas/recurrentes/pendientes?emisor_id={e['id']}", headers=h).json()
        assert not any(x["id"] == p["id"] for x in pend)
        assert c.get("/api/dashboard", headers=h, params={"emisor_id": e["id"]}).json()["por_timbrar"] is not None


def test_recurrente_automatica_se_apaga_si_falla():
    from app.db import SessionLocal
    from app.models import Plantilla
    from app.services import recurrentes

    with TestClient(app) as c:
        h, e = _preparar(c)
        with SessionLocal() as db:
            p = Plantilla(emisor_id=e["id"], nombre="Rota", recurrente=True, dia=1, auto_timbrar=True,
                          proxima=datetime.now() - timedelta(days=1),
                          payload={"publico_general": True, "conceptos": []})  # sin conceptos: falla antes del PAC
            db.add(p)
            db.commit()
            assert recurrentes.correr_automaticas(db) == 0
            db.refresh(p)
            assert p.auto_timbrar is False and "automático" in p.ultimo_error
            assert p.proxima < datetime.now()  # sigue pendiente para timbrarla a mano


def test_nomina_sueldos_y_asimilados():
    with TestClient(app) as c:
        h, e = _preparar(c)
        emp = c.post("/api/nomina/empleados", headers=h, json={
            "emisor_id": e["id"], "num_empleado": "7", "rfc": "XOJI740919U48", "curp": "XOJI740919HDFRNS07",
            "nombre": "INGRID XODAR JIMENEZ", "codigo_postal": "88965", "nss": "12345678901", "tipo_contrato": "01",
            "tipo_regimen": "02", "periodicidad_pago": "04", "clave_ent_fed": "CMX",
            "fecha_inicio": "2020-01-06T00:00:00", "riesgo_puesto": "1", "salario_diario": "500", "sdi": "530"})
        assert emp.status_code in (200, 409), emp.text
        borr = c.get(f"/api/nomina/borrador?emisor_id={e['id']}&desde=2026-10-01&hasta=2026-10-15", headers=h).json()
        rec = [r for r in borr if r["percepciones"]][0]
        assert rec["percepciones"][0]["gravado"] == "7500.00"  # 500 × 15 días
        rec["deducciones"][0]["importe"] = "650.00"  # ISR
        rec["deducciones"][1]["importe"] = "190.00"  # IMSS
        r = c.post("/api/nomina/timbrar", headers=h, json={"emisor_id": e["id"], "recibos": [rec]}).json()
        assert r[0]["ok"], r
        assert r[0]["neto"].startswith("6660")
        fac = c.get(f"/api/facturas/{r[0]['factura_id']}/xml", headers=h).content
        x = CFDI.from_string(fac)
        nom = x["Complemento"]["Nomina"]
        assert nom["Emisor"]["RegistroPatronal"] == "Y5234567101"
        assert nom["Receptor"]["Antigüedad"].startswith("P") and x["Receptor"]["UsoCFDI"] == "CN01"
        assert "TotalOtrasDeducciones" in nom["Deducciones"]
        # Errores por recibo: no truena el lote, regresa el motivo
        malo = {**rec, "deducciones": [{"tipo": "002", "clave": "002", "concepto": "ISR", "importe": "99999"}]}
        r = c.post("/api/nomina/timbrar", headers=h, json={"emisor_id": e["id"], "recibos": [malo]}).json()
        assert not r[0]["ok"] and "negativo" in r[0]["error"]
        assert c.get(f"/api/nomina/recibos?emisor_id={e['id']}", headers=h).json()[0]["tipo"] == "N"
        # Cancelar un recibo de nómina usa el mismo flujo (PAC demo)
        recibo = c.get(f"/api/nomina/recibos?emisor_id={e['id']}", headers=h).json()[0]
        cn = c.post(f"/api/facturas/{recibo['id']}/cancelar", headers=h, json={"motivo": "02"})
        assert cn.status_code == 200 and cn.json()["estado"] == "cancelada", cn.text


def test_portal_autofactura():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cfg = c.put(f"/api/tickets/portal/{e['id']}", headers=h, json={"activo": True, "config": {
            "clave_prod_serv": "90101501", "clave_unidad": "E48", "descripcion": "Consumo de alimentos"}}).json()
        clave = cfg["clave"]
        hoy = datetime.now().replace(microsecond=0).isoformat()
        assert c.post("/api/tickets", headers=h, json=[
            {"emisor_id": e["id"], "folio": "T-100", "fecha": hoy, "total": "580.00"},
            {"emisor_id": e["id"], "folio": "T-100", "fecha": hoy, "total": "580.00"}]).json()["nuevos"] in (0, 1)
        assert c.get(f"/api/portal/{clave}").json()["rfc"] == "EKU9003173C9"  # sin login
        datos = {"folio": "t-100", "total": "580", "rfc": "KIJ0906199R1", "nombre": "KERNEL INDUSTIA JUGUETERA",
                 "regimen_fiscal": "601", "codigo_postal": "42501", "uso_cfdi": "G03"}
        assert c.post(f"/api/portal/{clave}/facturar", json={**datos, "total": "581"}).status_code == 404
        r = c.post(f"/api/portal/{clave}/facturar", json=datos)
        if r.status_code == 409:  # la corrida anterior ya lo facturó
            return
        assert r.status_code == 200, r.text
        j = r.json()
        assert c.post(f"/api/portal/{clave}/facturar", json=datos).status_code == 409
        assert c.get(f"/api/portal/{clave}/descarga/{j['uuid']}?firma=mala").status_code == 403
        x = c.get(f"/api/portal/{clave}/descarga/{j['uuid']}?firma={j['firma']}&formato=xml")
        assert x.status_code == 200 and b"Consumo de alimentos" in x.content
        assert c.post("/api/portal/no-existe/facturar", json=datos).status_code == 404


def test_cobranza_y_estado_de_cuenta():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e, rfc="IIA040805DZ4", nombre="INDISTRIA ILUMINADORA DE ALMACENES", cp="62661",
                       emails=["pagos@iia.mx"])
        f, _ = _factura(c, h, e, cli, total="2000", metodo="PPD")
        ant = c.get(f"/api/cobranza?emisor_id={e['id']}", headers=h).json()
        fila = [x for x in ant["clientes"] if x["cliente_id"] == cli["id"]][0]
        assert float(fila["saldo"]) >= 2320 and fila["facturas"] >= 1
        ec = c.get(f"/api/cobranza/estado-cuenta/{cli['id']}", headers=h).json()
        assert ec["movimientos"] and float(ec["saldo"]) >= 2320
        assert "Estado de cuenta" in c.get(f"/api/cobranza/estado-cuenta/{cli['id']}/html", headers=h).text
        # Sin SMTP configurado: el recordatorio dice por qué no salió, no truena
        r = c.post("/api/cobranza/recordar", headers=h, json={"cliente_ids": [cli["id"]]}).json()
        assert r[0]["ok"] is False and "correo de envío" in r[0]["error"]


def test_sat_importar_conciliar_y_fiel():
    with TestClient(app) as c:
        h, e = _preparar(c)
        cli = _cliente(c, h, e)
        f, _ = _factura(c, h, e, cli, total="300")
        xml = c.get(f"/api/facturas/{f['id']}/xml", headers=h).content
        r = c.post(f"/api/sat/importar-xml/{e['id']}", headers=h, files=[("archivos", ("a.xml", xml, "application/xml"))])
        assert r.json()["nuevos"] == 1
        filas = c.get(f"/api/sat/cfdi?emisor_id={e['id']}&direccion=emitido", headers=h).json()
        mia = [x for x in filas if x["uuid"] == f["uuid"]][0]
        assert mia["en_timbra"] and float(mia["iva"]) == 48.0
        desde, hasta = (datetime.now() - timedelta(days=1)).isoformat(), (datetime.now() + timedelta(days=1)).isoformat()
        con = c.get(f"/api/sat/conciliacion?emisor_id={e['id']}&desde={desde}&hasta={hasta}", headers=h).json()
        assert con["coinciden"] >= 1 and f["uuid"] not in [x["uuid"] for x in con["solo_timbra"]]
        csv = c.get(f"/api/sat/exportar/csv?emisor_id={e['id']}&direccion=emitido", headers=h)
        assert f["uuid"].encode() in csv.content
        # La descarga masiva exige e.firma: un CSD se rechaza
        r = c.post(f"/api/sat/fiel/{e['id']}", headers=h,
                   files={"cer": open(CSD / "EKU9003173C9.cer", "rb"), "key": open(CSD / "EKU9003173C9.key", "rb")},
                   data={"password": "12345678a"})
        assert r.status_code == 422 and "CSD" in r.text
        assert c.post("/api/sat/solicitudes", headers=h, json={
            "emisor_id": e["id"], "desde": desde, "hasta": hasta}).status_code == 422


def test_respaldo_diario(tmp_path):
    from app.services import programador

    z = programador.respaldo_diario(tmp_path)
    assert z and z.exists()
    assert programador.respaldo_diario(tmp_path) is None  # uno por día
