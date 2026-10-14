"""Facturas en lote: fórmulas, centavo, folio de la hoja, pendientes que se rescatan, idempotencia y salidas."""
import copy
import io
import os
import shutil
import time
import zipfile
from decimal import Decimal

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Emisor, Factura  # noqa: E402
from app.services import lotes as svc  # noqa: E402
from app.services import pac as pac_svc  # noqa: E402
from app.services.validacion import digito_rfc_ok  # noqa: E402
from test_v2 import _preparar  # noqa: E402

REGIMEN_605 = "Sueldos y Salarios e Ingresos Asimilados a Salarios"
# Montos de la skill de Facturama: (MONTO, columna "IVA 0%" = servicio con IVA incluido)
GOLDEN = [("750", "562.50"), ("800", "600"), ("850", "637.50"), ("900", "675"), ("1100", "825"),
          ("1200", "900"), ("1400", "1050"), ("2000", "1500"), ("5400", "4050")]


def rfc_de_prueba(n: int) -> str:
    """RFC de persona física inventado pero con dígito verificador válido (no son datos de nadie)."""
    base = f"PRUB9001{n % 28 + 1:02d}A{n % 9}"[:12]
    base = f"PRUB9001{n % 28 + 1:02d}" + "A" + str(n % 9)
    for c in "0123456789A":
        if digito_rfc_ok(base + c):
            return base + c
    raise AssertionError


def fila(folio, nombre, rfc, cp, fecha, monto, servicio, forma="TDC", regimen=REGIMEN_605, correo=""):
    cols = [folio, nombre, rfc, cp, fecha, monto, servicio, "", "", "D01", forma, regimen, "texto viejo", "dir", correo]
    return "\t".join(cols)


def perfil_cfg(**cambios):
    cfg = copy.deepcopy(svc.PERFIL_EJEMPLO)
    cfg.update(cambios)
    return cfg


def _esperar(c, h, lid, hasta=30):
    for _ in range(hasta * 5):
        d = c.get(f"/api/lotes/{lid}", headers=h).json()
        if not d["ejecutando"]:
            return d
        time.sleep(0.2)
    raise AssertionError("el lote no terminó")


def _nuevo_lote(c, h, e, pid, filas, nombre="prueba"):
    r = c.post("/api/lotes", headers=h, data={"emisor_id": e["id"], "perfil_id": pid, "nombre": nombre,
                                              "texto": "\n".join(filas)})
    assert r.status_code == 200, r.text
    return r.json()


def _perfil(c, h, e, **cambios):
    r = c.post("/api/lotes/perfiles", headers=h, json={"emisor_id": e["id"], "nombre": f"p{time.time_ns()}",
                                                       "config": perfil_cfg(**cambios)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_formulas_seguras():
    v = {"monto": Decimal("900"), "servicio": Decimal("675")}
    assert svc.evaluar("(monto - servicio) / 1.16", v).quantize(Decimal("0.000001")) == Decimal("193.965517")
    for malo in ("__import__('os').system('x')", "monto ** 2", "open('a')", "monto.real", "[1]"):
        try:
            svc.evaluar(malo, v)
            raise AssertionError(malo)
        except svc.ErrorFila:
            pass
    try:
        svc.evaluar("monto / 0", v)
        raise AssertionError
    except svc.ErrorFila:
        pass
    try:
        svc.evaluar("costo * 2", v)
        raise AssertionError
    except svc.ErrorFila as e:
        assert "costo" in str(e)


def test_los_9_montos_cuadran_al_centavo():
    """Caso de oro: con 6 decimales 900 y 2000 salían un centavo fuera; el ajuste los cuadra y lo avisa."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        with SessionLocal() as db:
            emisor = db.get(Emisor, e["id"])
            cfg = perfil_cfg(folio_modo="consecutivo")
            ajustados = []
            for i, (monto, serv) in enumerate(GOLDEN):
                datos = {"folio": f"G-{i}", "nombre": f"PACIENTE PRUEBA {i}", "rfc": rfc_de_prueba(i), "cp": "42501",
                         "fecha": "05/09/2026", "monto": monto, "servicio": serv, "forma": "TDD",
                         "regimen": REGIMEN_605}
                r = svc.resolver(db, emisor, cfg, datos, None, {"n": i})
                assert r["estado"] == "listo", (monto, r["errores"])
                assert Decimal(r["resumen"]["total"]) == Decimal(monto), monto
                importes = [Decimal(x["importe"]) for x in r["resumen"]["conceptos"]]
                if "ajuste" in r["resumen"]:
                    ajustados.append(monto)
                    # el servicio no se aleja más de 1 centavo de lo que decía la hoja
                    assert abs(importes[0] - (Decimal(serv) / Decimal("1.16")).quantize(Decimal("0.01"))) <= Decimal("0.01")
                assert r["resumen"]["conceptos"][0]["descripcion"].startswith("SERVICIOS MÉDICOS")
            assert set(ajustados) == {"900", "2000"}

            # sin tolerancia no se timbra algo que no cuadre
            r = svc.resolver(db, emisor, perfil_cfg(folio_modo="consecutivo", ajuste_centavos=0),
                             {"folio": "G-x", "nombre": "PACIENTE PRUEBA", "rfc": rfc_de_prueba(1), "cp": "42501",
                              "fecha": "05/09/2026", "monto": "900", "servicio": "675", "forma": "TDD",
                              "regimen": REGIMEN_605}, None, {"n": 1})
            assert r["estado"] == "error" and "900.01" in r["error"]


def test_lote_con_folio_de_la_hoja_pendientes_y_rescate():
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e)
        # La serie C arranca en 30 (como pide la hoja)
        c.post(f"/api/emisores/{e['id']}/series", headers=h, json={"serie": "C", "tipo": "I", "siguiente_folio": 30})
        rfc_malo = "ZZZ"  # RFC inválido: esa fila quedará pendiente de corrección
        filas = [
            fila("C-30", "PACIENTE UNO", rfc_de_prueba(11), "42501", "05/10/2026", "750", "562.50", "TDC"),
            fila("C-31", "PACIENTE DOS", rfc_de_prueba(12), "42501", "06/10/2026", "900", "675", "TDD"),
            fila("C-32", "PACIENTE TRES", rfc_malo, "42501", "06/10/2026", "800", "600", "TRANSF"),
            fila("C-33", "PACIENTE CUATRO", rfc_de_prueba(14), "42501", "07/10/2026", "2000", "1500", "EFE"),
            fila("C-35", "PACIENTE CINCO", rfc_de_prueba(15), "42501", "08/10/2026", "5400", "4050", "TDC"),
            fila("C-34", "PACIENTE SEIS", rfc_de_prueba(16), "42501", "07/10/2026", "1100", "825", "TDC"),
        ]
        lote = _nuevo_lote(c, h, e, pid, filas)
        estados = {f["referencia"]: f["estado"] for f in lote["filas"]}
        assert estados["C-32"] == "error" and sum(1 for s in estados.values() if s == "listo") == 5
        f32 = [f for f in lote["filas"] if f["referencia"] == "C-32"][0]
        assert f32["folio"] == "32"  # el folio queda APARTADO aunque la fila tenga error
        f34 = [f for f in lote["filas"] if f["referencia"] == "C-34"][0]
        assert any("anterior" in a["texto"] for a in f34["avisos"])  # la fecha va hacia atrás: aviso
        assert [f for f in lote["filas"] if f["referencia"] == "C-33"][0]["resumen"].get("ajuste")  # 2000 → centavo

        # Una factura normal consecutiva NO puede tomar los folios apartados 30-35
        r = c.post("/api/facturas", headers=h, json={
            "emisor_id": e["id"], "serie": "C", "metodo_pago": "PUE", "forma_pago": "03",
            "receptor": {"rfc": "KIJ0906199R1", "nombre": "KERNEL INDUSTIA JUGUETERA", "regimen_fiscal": "601",
                         "codigo_postal": "42501", "uso_cfdi": "G03", "guardar": False},
            "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "x",
                           "valor_unitario": "10", "objeto_imp": "01", "impuestos": []}]})
        assert r.status_code == 200, r.text
        assert int(r.json()["folio"]) >= 36, r.json()["folio"]

        # Compuerta: sólo la primera, y se revisa
        assert c.post(f"/api/lotes/{lote['id']}/ejecutar", headers=h, json={"primeras": 1}).json()["iniciadas"] == 1
        d = _esperar(c, h, lote["id"])
        timbradas = [f for f in d["filas"] if f["estado"] == "timbrada"]
        assert len(timbradas) == 1 and timbradas[0]["referencia"] == "C-30" and timbradas[0]["folio_timbra"] == "C30"
        # el resto
        c.post(f"/api/lotes/{lote['id']}/ejecutar", headers=h, json={})
        d = _esperar(c, h, lote["id"])
        assert d["cuentas"]["timbrada"] == 5 and d["cuentas"]["error"] == 1
        assert sorted(f["folio_timbra"] for f in d["filas"] if f["estado"] == "timbrada") == \
            ["C30", "C31", "C33", "C34", "C35"]
        # el total timbrado es exactamente lo cobrado
        assert Decimal(d["total_timbrado"]) == Decimal("750") + 900 + 2000 + 5400 + 1100

        # Rescate: se corrige el RFC y sale con el MISMO folio
        fid = f32["id"]
        r = c.put(f"/api/lotes/{lote['id']}/filas/{fid}", headers=h, json={"datos": {"rfc": rfc_de_prueba(13)}})
        assert r.status_code == 200 and r.json()["estado"] == "listo" and r.json()["folio"] == "32"
        c.post(f"/api/lotes/{lote['id']}/ejecutar", headers=h, json={"ids": [fid]})
        d = _esperar(c, h, lote["id"])
        assert d["cuentas"]["timbrada"] == 6 and d["estado"] == "terminado"
        assert [f for f in d["filas"] if f["referencia"] == "C-32"][0]["folio_timbra"] == "C32"

        # Los clientes se dieron de alta solos, y los CFDI son válidos con la referencia guardada
        cli = c.get(f"/api/clientes?emisor_id={e['id']}&q={rfc_de_prueba(11)}", headers=h).json()
        assert cli and cli[0]["nombre"] == "PACIENTE UNO"
        lista = c.get(f"/api/facturas?emisor_id={e['id']}&limit=500", headers=h).json()
        assert "C-30" in {f["referencia"] for f in lista}  # la referencia (folio de la hoja) quedó en la factura

        # Volver a pegar la hoja completa NO duplica nada: todo sale "ya timbrada"
        antes = len(c.get(f"/api/facturas?emisor_id={e['id']}&limit=500", headers=h).json())
        otra = _nuevo_lote(c, h, e, pid, filas, "repetido")
        omitidas = [f for f in otra["filas"] if f["estado"] == "omitida"]
        assert len(omitidas) == 6
        assert c.post(f"/api/lotes/{otra['id']}/ejecutar", headers=h, json={}).json()["iniciadas"] == 0
        assert len(c.get(f"/api/facturas?emisor_id={e['id']}&limit=500", headers=h).json()) == antes

        # Salidas: registro y ZIP con PDF/HTML + XML nombrados {folio de la hoja}_{UUID}
        csv = c.get(f"/api/lotes/{lote['id']}/registro.csv", headers=h).content.decode("utf-8-sig")
        assert "C-32" in csv and "Timbrada" in csv
        uuid30 = timbradas[0]["uuid"]
        z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/lotes/{lote['id']}/cfdi.zip", headers=h).content))
        assert f"C-30_{uuid30}.xml" in z.namelist()


def test_error_del_pac_aparta_el_folio_y_se_rescata():
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e, serie="R")
        lote = _nuevo_lote(c, h, e, pid, [
            fila("R-70", "PACIENTE SIETE", rfc_de_prueba(21), "42501", "05/10/2026", "750", "562.50"),
            fila("R-71", "PACIENTE OCHO", rfc_de_prueba(22), "42501", "05/10/2026", "800", "600")])

        class Rechaza(pac_svc.DemoPac):
            def stamp(self, cfdi, accept=None):
                raise RuntimeError("CFDI40145 El campo Nombre del receptor no coincide")

        orig = pac_svc.get_pac
        pac_svc.get_pac = lambda p: Rechaza()
        try:
            c.post(f"/api/lotes/{lote['id']}/ejecutar", headers=h, json={})
            d = _esperar(c, h, lote["id"])
        finally:
            pac_svc.get_pac = orig
        assert d["cuentas"]["error"] == 2 and d["cuentas"]["timbrada"] == 0
        f70 = [f for f in d["filas"] if f["referencia"] == "R-70"][0]
        assert f70["etapa"] == "timbrado" and f70["resumen"]["diagnostico"] == "nombre_receptor"
        assert "Qué hacer" in f70["error"] and f70["folio"] == "70"  # el folio sigue apartado
        # no queda timbrada ninguna factura y no se gastó timbre
        with SessionLocal() as db:
            assert db.query(Factura).filter(Factura.referencia.in_(["R-70", "R-71"])).count() == 0
        # Corregida la causa, se reintenta (revalidar + ejecutar) con el mismo folio
        for f in d["filas"]:
            assert c.post(f"/api/lotes/{lote['id']}/filas/{f['id']}/revalidar", headers=h).json()["estado"] == "listo"
        c.post(f"/api/lotes/{lote['id']}/ejecutar", headers=h, json={})
        d = _esperar(c, h, lote["id"])
        assert d["cuentas"]["timbrada"] == 2
        assert sorted(f["folio_timbra"] for f in d["filas"]) == ["R70", "R71"]


def test_politicas_folio_ocupado_y_perfil_invalido():
    with TestClient(app) as c:
        h, e = _preparar(c)
        base = fila("S-5", "PACIENTE NUEVE", rfc_de_prueba(31), "42501", "05/10/2026", "750", "562.50")

        # Medicamento bloqueado: no se timbra
        cfg = perfil_cfg(serie="S")
        cfg["conceptos"][1]["clave_prod_serv"] = "51191903"
        pid = c.post("/api/lotes/perfiles", headers=h, json={"emisor_id": e["id"], "nombre": "med", "config": cfg}).json()["id"]
        d = _nuevo_lote(c, h, e, pid, [base])
        assert d["filas"][0]["estado"] == "error" and "⛔" in d["filas"][0]["error"]
        assert d["filas"][0]["resumen"]["bloqueo"] is True

        # IVA fuera de la política (exento) → error
        cfg = perfil_cfg(serie="S")
        cfg["conceptos"][0]["impuestos"] = [{"tipo": "traslado", "impuesto": "002", "factor": "Exento", "tasa": None}]
        pid = c.post("/api/lotes/perfiles", headers=h, json={"emisor_id": e["id"], "nombre": "ex", "config": cfg}).json()["id"]
        d = _nuevo_lote(c, h, e, pid, [base])
        assert d["filas"][0]["estado"] == "error" and "no está permitido" in d["filas"][0]["error"]

        # Folio ya usado por una factura emitida → error claro
        pid = _perfil(c, h, e, serie="S")
        d = _nuevo_lote(c, h, e, pid, [base])
        c.post(f"/api/lotes/{d['id']}/ejecutar", headers=h, json={})
        _esperar(c, h, d["id"])
        d2 = _nuevo_lote(c, h, e, pid, [fila("S-5", "OTRO PACIENTE", rfc_de_prueba(32), "42501", "05/10/2026", "800", "600")])
        assert d2["filas"][0]["estado"] == "error" and "ya lo tiene" in d2["filas"][0]["error"]
        # Folio repetido dentro de la misma tabla
        d3 = _nuevo_lote(c, h, e, pid, [
            fila("S-90", "A", rfc_de_prueba(33), "42501", "05/10/2026", "800", "600"),
            fila("S-90", "B", rfc_de_prueba(34), "42501", "05/10/2026", "800", "600")])
        assert d3["filas"][1]["estado"] == "error" and "repetido" in d3["filas"][1]["error"]

        # Perfil con fórmula peligrosa o columna inexistente se rechaza al guardar
        malo = perfil_cfg()
        malo["conceptos"][0]["valor"] = "__import__('os')"
        r = c.post("/api/lotes/perfiles", headers=h, json={"emisor_id": e["id"], "nombre": "x", "config": malo})
        assert r.status_code == 422
        malo = perfil_cfg()
        malo["conceptos"][0]["descripcion"] = "Hola {inexistente}"
        assert c.post("/api/lotes/perfiles", headers=h, json={"emisor_id": e["id"], "nombre": "x", "config": malo}).status_code == 422


def test_csv_con_encabezados_en_otro_orden_y_modo_consecutivo():
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e, folio_modo="consecutivo", serie="K")
        enc = "MONTO,NOMBRE,RFC,CP,FECHA DE PAGO,FORMA DE PAGO,IVA 0%,NO. FACTURA,REGIMEN FISCAL"
        linea = f'"1,200.00",PACIENTE DIEZ,{rfc_de_prueba(41)},42501,09/10/2026,TDC,900.00,K-1,{REGIMEN_605}'
        r = c.post("/api/lotes", headers=h, data={"emisor_id": e["id"], "perfil_id": pid},
                   files={"archivo": ("hoja.csv", (enc + "\n" + linea).encode("utf-8"), "text/csv")})
        assert r.status_code == 200, r.text
        f = r.json()["filas"][0]
        assert f["estado"] == "listo", f["errores"]
        assert f["resumen"]["total"].startswith("1200") and f["folio"] is None  # folio lo asigna Timbra
        c.post(f"/api/lotes/{r.json()['id']}/ejecutar", headers=h, json={})
        d = _esperar(c, h, r.json()["id"])
        assert d["filas"][0]["estado"] == "timbrada" and d["filas"][0]["referencia"] == "K-1"
