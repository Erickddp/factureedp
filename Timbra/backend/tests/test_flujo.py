"""Flujo completo con PAC demo y CSD de pruebas del SAT (EKU9003173C9 / 12345678a)."""
import os
from pathlib import Path

import shutil

shutil.rmtree("./_test_datos", ignore_errors=True)
os.environ["DATA_DIR"] = "./_test_datos"
os.environ["DATABASE_URL"] = "sqlite:///./_test_datos/timbra.db"
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402
from satcfdi.cfdi import CFDI  # noqa: E402

from app.main import app  # noqa: E402

CSD = Path(__file__).parent / "csd"


def test_todo():
    with TestClient(app) as c:
        tok = c.post("/api/auth/login", json={"email": "rick@erickddp.com", "password": "cambiame"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}

        pac = c.post("/api/pacs", headers=h, json={"nombre": "Demo", "proveedor": "demo"}).json()
        e = c.post("/api/emisores", headers=h, json={
            "rfc": "EKU9003173C9", "nombre": "ESCUELA KEMPER URGATE", "regimen_fiscal": "601",
            "lugar_expedicion": "42501", "pac_id": pac["id"]}).json()
        r = c.post(f"/api/emisores/{e['id']}/csd", headers=h,
                   files={"cer": open(CSD / "EKU9003173C9.cer", "rb"), "key": open(CSD / "EKU9003173C9.key", "rb")},
                   data={"password": "12345678a"})
        assert r.status_code == 200, r.text
        assert r.json()["no_certificado"]

        cli = c.post("/api/clientes", headers=h, json={
            "emisor_id": e["id"], "rfc": "URE180429TM6", "nombre": "UNIVERSIDAD ROBOTICA ESPAÑOLA",
            "regimen_fiscal": "601", "codigo_postal": "86991", "uso_cfdi": "G03",
            "emails": ["cxp@ure.mx"], "addenda_id": 1,
            "addenda_defaults": {"num_proveedor": "PROV-778"}}).json()

        concepto = {"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "Servicios contables",
                    "cantidad": 1, "valor_unitario": "10000",
                    "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"},
                                  {"tipo": "retencion", "impuesto": "001", "factor": "Tasa", "tasa": "0.10"},
                                  {"tipo": "retencion", "impuesto": "002", "factor": "Tasa", "tasa": "0.106667"}]}
        body = {"emisor_id": e["id"], "cliente_id": cli["id"], "metodo_pago": "PPD", "conceptos": [concepto],
                "addenda": {"addenda_id": 1, "datos": {"orden_compra": "OC-4521"}}}

        pv = c.post("/api/facturas/preview", headers=h, json=body).json()
        assert float(pv["total"]) == 9533.33, pv

        f = c.post("/api/facturas", headers=h, json=body)
        assert f.status_code == 200, f.text
        f = f.json()
        assert f["estado"] == "timbrada" and f["uuid"] and f["serie"] == "A" and f["folio"] == "1"
        assert float(f["saldo"]) == 9533.33

        xml = c.get(f"/api/facturas/{f['id']}/xml", headers=h).content
        assert b"OC-4521" in xml and b"PROV-778" in xml and b"TimbreFiscalDigital" in xml
        cf = CFDI.from_string(xml)
        assert cf["FormaPago"] == "99"

        # REP en dos parcialidades
        p1 = c.post("/api/facturas/pagos", headers=h, json={
            "emisor_id": e["id"], "cliente_id": cli["id"], "fecha_pago": "2026-09-10T12:00:00",
            "forma_pago": "03", "documentos": [{"factura_id": f["id"], "imp_pagado": "5000"}]})
        assert p1.status_code == 200, p1.text
        assert c.get(f"/api/facturas/{f['id']}", headers=h).json()["saldo"] is not None
        assert float(c.get(f"/api/facturas/{f['id']}", headers=h).json()["saldo"]) == 4533.33
        demasiado = c.post("/api/facturas/pagos", headers=h, json={
            "emisor_id": e["id"], "cliente_id": cli["id"], "fecha_pago": "2026-09-11T12:00:00",
            "documentos": [{"factura_id": f["id"], "imp_pagado": "99999"}]})
        assert demasiado.status_code == 422

        # Público en general / global + ISH local
        g = c.post("/api/facturas", headers=h, json={
            "emisor_id": e["id"], "publico_general": True, "metodo_pago": "PUE", "forma_pago": "01",
            "conceptos": [{**concepto, "clave_prod_serv": "01010101", "clave_unidad": "ACT", "descripcion": "Venta",
                           "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]}],
            "impuestos_locales": [{"tipo": "traslado", "nombre": "ISH", "tasa": "3", "importe": "300"}]})
        assert g.status_code == 200, g.text
        gx = CFDI.from_string(c.get(f"/api/facturas/{g.json()['id']}/xml", headers=h).content)
        assert gx["InformacionGlobal"]["Meses"] and gx["Total"] == gx["SubTotal"] + 1600 + 300

        # Nota de crédito relacionada
        nc = c.post("/api/facturas", headers=h, json={
            "emisor_id": e["id"], "cliente_id": cli["id"], "tipo": "E", "metodo_pago": "PUE", "forma_pago": "03",
            "relacionados": [{"tipo_relacion": "01", "uuids": [f["uuid"]]}],
            "conceptos": [{**concepto, "clave_prod_serv": "84111506", "clave_unidad": "ACT",
                           "descripcion": "Descuento", "valor_unitario": "500"}]})
        assert nc.status_code == 200, nc.text
        assert nc.json()["serie"] == "NC"

        # Motivo 01: el UUID sustituto debe tener formato de UUID (antes aceptaba «123-no-es-uuid»)
        for malo in ("123-no-es-uuid", g.json()["uuid"]):  # formato inválido y ella misma
            r = c.post(f"/api/facturas/{g.json()['id']}/cancelar", headers=h, json={"motivo": "01", "uuid_sustitucion": malo})
            assert r.status_code == 422, (malo, r.text)

        # Cancelar la global
        cn = c.post(f"/api/facturas/{g.json()['id']}/cancelar", headers=h, json={"motivo": "02"})
        assert cn.json()["estado"] == "cancelada"
        # No se cancela con REP vivos
        assert c.post(f"/api/facturas/{f['id']}/cancelar", headers=h, json={"motivo": "02"}).status_code == 422
        # Cancelar el REP devuelve el saldo y la parcialidad; la factura vuelve a poder cancelarse (reporte del tester: A37)
        assert c.post(f"/api/facturas/{p1.json()['id']}/cancelar", headers=h, json={"motivo": "02"}).json()["estado"] == "cancelada"
        fx = c.get(f"/api/facturas/{f['id']}", headers=h).json()
        assert float(fx["saldo"]) == 9533.33 and fx["parcialidades"] == 0
        # Se vuelve a registrar el pago para que el resto del flujo siga igual
        assert c.post("/api/facturas/pagos", headers=h, json={
            "emisor_id": e["id"], "cliente_id": cli["id"], "fecha_pago": "2026-09-10T12:00:00",
            "forma_pago": "03", "documentos": [{"factura_id": f["id"], "imp_pagado": "5000"}]}).status_code == 200
        assert float(c.get(f"/api/facturas/{f['id']}", headers=h).json()["saldo"]) == 4533.33

        # Plantillas
        pl = c.post("/api/plantillas", headers=h, json={"emisor_id": e["id"], "nombre": "Iguala mensual", "payload": body}).json()
        assert pl["cliente_id"] == cli["id"]
        assert c.post(f"/api/plantillas/desde-factura/{f['id']}?nombre=Copia", headers=h).status_code == 200
        lista = c.get(f"/api/plantillas?emisor_id={e['id']}&cliente_id={cli['id']}", headers=h).json()
        assert len(lista) == 2
        usada = c.post(f"/api/plantillas/{pl['id']}/usar", headers=h).json()
        assert usada["conceptos"][0]["descripcion"] == "Servicios contables"
        f2 = c.post("/api/facturas", headers=h, json={**usada, "emisor_id": e["id"]})
        assert f2.status_code == 200, f2.text

        # Catálogo base precargado
        prods = c.get(f"/api/productos?emisor_id={e['id']}", headers=h).json()
        assert len(prods) >= 15

        # Exportaciones
        z = c.get(f"/api/facturas/exportar/zip?emisor_id={e['id']}", headers=h)
        assert z.status_code == 200 and z.content[:2] == b"PK"
        cs = c.get(f"/api/facturas/exportar/csv?emisor_id={e['id']}", headers=h)
        assert "UNIVERSIDAD ROBOTICA" in cs.content.decode("utf-8-sig")

        # PDF o HTML imprimible
        pdf = c.get(f"/api/facturas/{f['id']}/pdf", headers=h)
        assert pdf.status_code == 200 and pdf.headers["content-type"].split(";")[0] in ("application/pdf", "text/html")

        # Respaldo en disco + recuperación si la BD pierde el registro
        assert list(Path("_test_datos/respaldo_xml/EKU9003173C9").rglob("*.xml"))
        from app.db import SessionLocal
        from app.models import Factura
        with SessionLocal() as db:
            db.query(Factura).filter_by(id=f2.json()["id"]).delete()
            db.commit()
        rec = c.post("/api/facturas/recuperar", headers=h).json()
        assert f2.json()["uuid"] in rec["recuperadas"]

        # Usuarios
        assert c.post("/api/auth/usuarios", headers=h, json={"email": "aux@x.mx", "password": "12345678"}).status_code == 200
        assert c.post("/api/auth/login", json={"email": "aux@x.mx", "password": "12345678"}).status_code == 200
        assert c.post("/api/auth/login", json={"email": "aux@x.mx", "password": "mal"}).status_code == 401

        # Validaciones SAT: uso incompatible con régimen, CP inexistente, PUE con 99
        malo = {**body, "cliente_id": None, "metodo_pago": "PUE", "forma_pago": "99",
                "receptor": {"rfc": "PEGA900115AB0", "nombre": "ANA PEREZ GARCIA DE PRUEBA", "regimen_fiscal": "605",
                             "codigo_postal": "00100", "uso_cfdi": "G03", "guardar": False}, "addenda": None}
        pv = c.post("/api/facturas/preview", headers=h, json=malo).json()
        textos = " ".join(e["mensaje"] for e in pv["errores"])
        assert "G03" in textos and "00100" in textos and "PUE" in textos, textos
        r = c.post("/api/facturas", headers=h, json=malo)
        assert r.status_code == 422 and "No timbré" in r.json()["detail"] and r.json()["request_id"]
        sin_receptor = c.post("/api/facturas/preview", headers=h, json={**body, "cliente_id": None}).json()
        assert float(sin_receptor["total"]) > 0 and any("receptor" in e["campo"] for e in sin_receptor["errores"])

        # Importación de clientes (formato de Rick, pegado desde Excel)
        pegado = ("NOMBRE\tRFC\tCP\tDIRECCION\tREGIMEN_FISCAL\tCORREO_O_CONTACTO\n"
                  "ANA PEREZ GARCIA DE PRUEBA\tPEGA900115AB0\t63190\tCALLE UNO 100 A, COLONIA EJEMPLO, TEPIC, NAYARIT\t"
                  "Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios\tana.prueba@ejemplo.mx\n"
                  "BERTA LOPEZ MARTINEZ DE PRUEBA\tLOMB920320CDA\t31220\tCALLE DOS 200, COLONIA EJEMPLO, CHIHUAHUA\t"
                  "Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios\tberta.prueba@ejemplo.mx | 6140000000\n"
                  "MAL\tXXX\t1\t\tcosa rara\t\n")
        pv = c.post("/api/clientes/importar/previsualizar", headers=h,
                    data={"emisor_id": str(e["id"]), "uso_default": "D01", "texto": pegado}).json()
        assert pv["resumen"]["nuevo"] == 2 and pv["resumen"]["error"] == 1, pv["resumen"]
        lilia = pv["filas"][1]["datos"]
        assert lilia["regimen_fiscal"] == "605" and lilia["uso_cfdi"] == "D01"
        assert lilia["emails"] == ["berta.prueba@ejemplo.mx"] and lilia["telefono"] == "6140000000"
        ok = [f["datos"] for f in pv["filas"] if f["accion"] != "error"]
        res = c.post("/api/clientes/importar/confirmar", headers=h, json={"emisor_id": e["id"], "filas": ok}).json()
        assert res["creados"] == 2
        assert c.get("/api/clientes/importar/plantilla", headers=h).content[:2] == b"PK"

        # Consola de depuración: registro y servicios
        lg = c.get("/api/debug/logs", headers=h).json()
        assert any("Timbre recibido" in i["mensaje"] for i in lg["items"])
        assert any(i["nivel"] == "WARNING" and "No timbré" in i["mensaje"] for i in lg["items"])
        sv = c.get("/api/debug/servicios", headers=h).json()
        assert any(x["nombre"] == "Base de datos" and x["estado"] == "ok" for x in sv)
        assert c.post("/api/debug/cliente", headers=h, json={"mensaje": "prueba navegador"}).status_code == 200

        d = c.get("/api/dashboard", headers=h).json()
        assert d["comprobantes_mes"] >= 1
        assert len(c.get("/api/catalogos/buscar/prod_serv?q=servicios contables").json()) > 0
        assert c.get("/api/facturas?q=URE", headers=h).json()


def _login(c):
    tok = c.post("/api/auth/login", json={"email": "rick@erickddp.com", "password": "cambiame"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_importar_clientes_y_reglas():
    with TestClient(app) as c:
        h = _login(c)
        e = c.get("/api/emisores", headers=h).json()[0]
        # Exactamente como Rick lo pegó desde Excel (tabuladores), con una fila mala y un CP sin cero
        texto = (
            "NOMBRE\tRFC\tCP\tDIRECCION\tREGIMEN_FISCAL\tCORREO_O_CONTACTO\n"
            "ANA PEREZ GARCIA DE PRUEBA\tPEGA900115AB0\t63190\tCALLE UNO 100 A, COLONIA EJEMPLO, TEPIC, NAYARIT\t"
            "Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios\tana.prueba@ejemplo.mx\n"
            "BERTA LOPEZ MARTINEZ DE PRUEBA\tLOMB920320CDA\t31220\tCALLE DOS 200, COLONIA EJEMPLO, CHIHUAHUA\t"
            "Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios\tberta.prueba@ejemplo.mx | 6140000000\n"
            "EMPRESA PATITO SA DE CV\tEPA0101019A1\t6600\t\t601\tcompras@patito.mx\n"
            "SIN REGIMEN\tXYZ\t123\t\tinventado\t\n"
        )
        r = c.post("/api/clientes/importar/previsualizar", headers=h,
                   data={"emisor_id": e["id"], "uso_default": "auto", "texto": texto})
        assert r.status_code == 200, r.text
        v = r.json()
        filas = {f["datos"]["rfc"]: f for f in v["filas"]}
        m = filas["PEGA900115AB0"]["datos"]
        assert m["regimen_fiscal"] == "605" and m["uso_cfdi"] == "S01"  # 605 no admite G03
        assert m["direccion"].startswith("CALLE UNO 100")
        lilia = filas["LOMB920320CDA"]["datos"]
        assert lilia["emails"] == ["berta.prueba@ejemplo.mx"] and lilia["telefono"] == "6140000000"
        patito = filas["EPA0101019A1"]["datos"]
        assert patito["codigo_postal"] == "06600" and "SA DE CV" not in patito["nombre"]
        assert filas["XYZ"]["accion"] == "error"

        # Pacientes de consultorio: D01 por defecto
        r2 = c.post("/api/clientes/importar/previsualizar", headers=h,
                    data={"emisor_id": e["id"], "uso_default": "D01", "texto": texto}).json()
        assert {f["datos"]["rfc"]: f for f in r2["filas"]}["PEGA900115AB0"]["datos"]["uso_cfdi"] == "D01"

        # Las filas idénticas a lo guardado salen "igual" (nada que cambiar); aquí se mandan igual para probar el modo clásico
        validas = [f["datos"] for f in v["filas"] if f["accion"] in ("nuevo", "actualizar", "igual")]
        ok = c.post("/api/clientes/importar/confirmar", headers=h,
                    json={"emisor_id": e["id"], "filas": validas, "modo": "actualizar"}).json()
        assert ok["creados"] + ok["actualizados"] >= 3, (ok, v["resumen"])
        maria = c.get(f"/api/clientes?emisor_id={e['id']}&q=PEGA900115AB0", headers=h).json()[0]
        assert maria["telefono"] is None and maria["emails"] == ["ana.prueba@ejemplo.mx"]

        # Formato Excel descargable
        fx = c.get("/api/clientes/importar/plantilla", headers=h)
        assert fx.status_code == 200 and fx.content[:2] == b"PK"

        # Reglas SAT antes de timbrar: G03 con régimen 605 debe bloquearse sin gastar timbre
        malo = c.post("/api/facturas", headers=h, json={
            "emisor_id": e["id"], "receptor": {"rfc": "PEGA900115AB0", "nombre": "ANA PEREZ GARCIA DE PRUEBA",
                                               "regimen_fiscal": "605", "codigo_postal": "63190", "uso_cfdi": "G03",
                                               "guardar": False},
            "metodo_pago": "PUE", "forma_pago": "03",
            "conceptos": [{"clave_prod_serv": "85121600", "clave_unidad": "E48", "descripcion": "Consulta",
                           "valor_unitario": "800", "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Exento", "tasa": None}]}]})
        assert malo.status_code == 422 and "605" in malo.text and malo.headers.get("x-request-id")
        pue99 = c.post("/api/facturas", headers=h, json={
            "emisor_id": e["id"], "cliente_id": maria["id"], "metodo_pago": "PUE", "forma_pago": "99",
            "conceptos": [{"clave_prod_serv": "85121600", "clave_unidad": "E48", "descripcion": "Consulta", "valor_unitario": "800"}]})
        assert pue99.status_code == 422
        # La vista previa trae las validaciones para mostrarlas en pantalla
        pv = c.post("/api/facturas/preview", headers=h, json={
            "emisor_id": e["id"], "cliente_id": maria["id"], "metodo_pago": "PUE", "forma_pago": "99",
            "conceptos": [{"clave_prod_serv": "85121600", "clave_unidad": "E48", "descripcion": "Consulta", "valor_unitario": "800"}]}).json()
        assert any("99" in str(x) for x in (pv.get("validacion") or pv.get("errores") or pv.values()))

        # Consola: el error quedó registrado con su folio
        rid = malo.headers["x-request-id"]
        lg = c.get(f"/api/debug/logs?req={rid}", headers=h).json()
        assert lg["items"], "el rechazo debe verse en la consola"
        assert c.post("/api/debug/cliente", headers=h, json={"nivel": "error", "mensaje": "prueba navegador"}).status_code == 200
        todo = c.get("/api/debug/logs?q=prueba navegador", headers=h).json()["items"]
        assert todo, "los errores del navegador también deben verse"
        sv = c.get("/api/debug/servicios", headers=h)
        assert sv.status_code == 200 and any("CSD" in s["nombre"] for s in sv.json())
        # Datos mal formados → mensaje legible
        mal = c.post("/api/facturas", headers=h, json={"emisor_id": e["id"], "conceptos": [{"descripcion": "x"}]})
        assert mal.status_code == 422 and "conceptos" in mal.json()["detail"]


def test_frontera_iva_8_honorarios_y_suplemento():
    with TestClient(app) as c:
        h = _login(c)
        e = c.get("/api/emisores", headers=h).json()[0]
        cli = c.post("/api/clientes", headers=h, json={
            "emisor_id": e["id"], "rfc": "KIJ0906199R1", "nombre": "KERNEL INDUSTIA JUGUETERA",
            "regimen_fiscal": "601", "codigo_postal": "42501", "uso_cfdi": "G03"}).json()
        IVA8 = {"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.08"}
        ISR10 = {"tipo": "retencion", "impuesto": "001", "factor": "Tasa", "tasa": "0.100000"}
        RET8 = {"tipo": "retencion", "impuesto": "002", "factor": "Tasa", "tasa": "0.053333"}
        body = {"emisor_id": e["id"], "cliente_id": cli["id"], "metodo_pago": "PUE", "forma_pago": "03",
                "conceptos": [
                    {"clave_prod_serv": "80101500", "clave_unidad": "E48", "descripcion": "Honorarios", "valor_unitario": "10000",
                     "impuestos": [IVA8, ISR10, RET8]},
                    {"clave_prod_serv": "51191900", "clave_unidad": "H87", "descripcion": "Suplemento", "valor_unitario": "500",
                     "impuestos": [IVA8]},
                ]}
        # Sin marcar frontera: se deja timbrar pero avisa
        pv = c.post("/api/facturas/preview", headers=h, json=body).json()
        assert float(pv["total"]) == 9806.67, pv
        assert "fronteriza" in str(pv)
        # Marcar el emisor como región fronteriza y convertir su catálogo
        ed = {k: e[k] for k in ("rfc", "nombre", "regimen_fiscal", "lugar_expedicion", "email", "color", "pac_id")}
        assert c.put(f"/api/emisores/{e['id']}", headers=h, json={**ed, "region_fronteriza": True}).json()["region_fronteriza"]
        assert c.post(f"/api/emisores/{e['id']}/productos-a-frontera", headers=h).json()["actualizados"] > 0
        prods = c.get(f"/api/productos?emisor_id={e['id']}", headers=h).json()
        assert not any(i.get("tasa") in ("0.16", "0.106667") for p in prods for i in p["impuestos"])
        f = c.post("/api/facturas", headers=h, json=body)
        assert f.status_code == 200, f.text
        x = c.get(f"/api/facturas/{f.json()['id']}/xml", headers=h).text
        import re as _re
        tasas = set(_re.findall(r'TasaOCuota="([0-9.]+)"', x))
        assert {"0.080000", "0.053333"} <= tasas, tasas
        # Error clásico: IVA 8% con retención de 10.6667%
        malo = {**body, "conceptos": [{**body["conceptos"][0], "impuestos": [IVA8, ISR10, {**RET8, "tasa": "0.106667"}]}]}
        r = c.post("/api/facturas", headers=h, json=malo)
        assert r.status_code == 422 and "5.3333" in r.text
        # Exento con retención de IVA: no hay IVA que retener
        ex = {**body, "conceptos": [{**body["conceptos"][0], "impuestos": [
            {"tipo": "traslado", "impuesto": "002", "factor": "Exento", "tasa": None}, ISR10, RET8]}]}
        assert c.post("/api/facturas", headers=h, json=ex).status_code == 422
        # Honorarios médicos exentos con ISR 10%: válido
        ok = {**body, "conceptos": [{**body["conceptos"][0], "clave_prod_serv": "85121600", "impuestos": [
            {"tipo": "traslado", "impuesto": "002", "factor": "Exento", "tasa": None}, ISR10]}]}
        assert c.post("/api/facturas", headers=h, json=ok).status_code == 200
        # IVA 0%
        cero = {**body, "conceptos": [{**body["conceptos"][1], "impuestos": [{**IVA8, "tasa": "0"}]}]}
        assert c.post("/api/facturas", headers=h, json=cero).status_code == 200
        # Prueba de PAC (demo)
        pac = c.get("/api/pacs", headers=h).json()[0]
        pr = c.post(f"/api/pacs/{pac['id']}/probar?emisor_id={e['id']}", headers=h)
        assert pr.status_code == 200 and pr.json()["uuid"], pr.text
        # Ciclo completo de certificación en sandbox: timbrar → cancelar → estatus
        pr = c.post(f"/api/pacs/{pac['id']}/probar?emisor_id={e['id']}&ciclo=true", headers=h).json()
        assert pr["ok"] and pr["cancelacion"]["codigo"] == "201", pr
        assert pr["estatus"]["Estado"] == "Cancelado", pr


def test_cancelacion_codigos_sat():
    from app.services import pac as pac_svc

    assert pac_svc._codigo("201") == "201" and pac_svc._codigo({"estatusUUID": "202"}) == "202"
    assert pac_svc.cancelacion_aceptada("201") and pac_svc.cancelacion_aceptada("202")
    assert not pac_svc.cancelacion_aceptada("205") and not pac_svc.cancelacion_aceptada(None)
    # 201 no es "cancelada": el estado lo decide la consulta al SAT
    assert pac_svc.estado_sat({"Estado": "Cancelado", "EstatusCancelacion": "Cancelado sin aceptación"}) == "cancelada"
    assert pac_svc.estado_sat({"Estado": "Vigente", "EstatusCancelacion": "En proceso"}) == "cancelacion_pendiente"
    assert pac_svc.estado_sat({"Estado": "Vigente", "EstatusCancelacion": "Solicitud rechazada"}) == "timbrada"
    assert pac_svc.estado_sat({"error": "timeout"}) == "?"

    class Pac205(pac_svc.DemoPac):
        def cancel(self, cfdi, reason, substitution_id=None, signer=None):
            return pac_svc.CancelationAcknowledgment(code="205", acuse=None)

    xml = pac_svc.DemoPac().stamp(_cfdi_minimo()).xml
    orig = pac_svc.get_pac
    pac_svc.get_pac = lambda p: Pac205()
    try:
        try:
            pac_svc.cancelar(None, xml, "02", None, None)
            raise AssertionError("debió rechazar el 205")
        except pac_svc.PacError as err:
            assert "205" in str(err)
    finally:
        pac_svc.get_pac = orig


def _cfdi_minimo():
    from decimal import Decimal

    from satcfdi.create.cfd import cfdi40
    from satcfdi.models import Signer

    s = Signer.load(certificate=open(CSD / "EKU9003173C9.cer", "rb").read(),
                    key=open(CSD / "EKU9003173C9.key", "rb").read(), password="12345678a")
    comp = cfdi40.Comprobante(
        emisor=cfdi40.Emisor(rfc="EKU9003173C9", nombre="ESCUELA KEMPER URGATE", regimen_fiscal="601"),
        lugar_expedicion="42501",
        receptor=cfdi40.Receptor(rfc="XAXX010101000", nombre="PUBLICO EN GENERAL", domicilio_fiscal_receptor="42501",
                                 regimen_fiscal_receptor="616", uso_cfdi="S01"),
        conceptos=[cfdi40.Concepto(clave_prod_serv="01010101", cantidad=1, clave_unidad="ACT", descripcion="Venta",
                                   valor_unitario=Decimal("1.00"), objeto_imp="01")],
        forma_pago="01", metodo_pago="PUE")
    comp.sign(s)
    return comp
