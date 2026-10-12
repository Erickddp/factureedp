"""Facturar pegando la hoja, igual que la skill: uso del perfil, canceladas, carpeta de entrega, formatos de Excel,
cuentas ajenas y, sobre todo, que lo guardado siga ahí después de apagar y encender."""
import os
import xml.etree.ElementTree as ET
from decimal import Decimal

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import almacen  # noqa: E402
from app.services import lotes as svc  # noqa: E402
from app.services.validacion import digito_rfc_ok  # noqa: E402
from test_lotes import REGIMEN_605, _esperar, _nuevo_lote, _perfil, fila  # noqa: E402
from test_v2 import _preparar  # noqa: E402
from test_v5_clientes import rfc_moral  # noqa: E402
from test_w1_cuentas import _usuario  # noqa: E402

def rfc_de_prueba(n: int) -> str:
    """RFC de persona física inventado con dígito verificador válido, distinto a los de las otras pruebas."""
    base = f"SKIL90{n // 28 % 12 + 1:02d}{n % 28 + 1:02d}Q{n % 10}"
    for c in "0123456789A":
        if digito_rfc_ok(base + c):
            return base + c
    raise AssertionError


NS = {"c": "http://www.sat.gob.mx/cfd/4", "t": "http://www.sat.gob.mx/TimbreFiscalDigital"}
PF612 = "Personas Físicas con Actividades Empresariales y Profesionales"
PM601 = "General de Ley Personas Morales"


def _xml(c, h, factura_id):
    r = c.get(f"/api/facturas/{factura_id}/xml", headers=h)
    assert r.status_code == 200, r.text
    return ET.fromstring(r.content)


def _timbrar(c, h, lote):
    c.post(f"/api/lotes/{lote['id']}/ejecutar", headers=h, json={})
    return _esperar(c, h, lote["id"])


def _por_ref(d, ref):
    return next(f for f in d["filas"] if f["referencia"] == ref)


def test_el_uso_del_perfil_manda_sobre_el_que_tiene_guardado_el_cliente():
    """Bug real (Finkok pruebas, 11-oct-2026): al cliente ya guardado con G03 el lote le timbraba G03 aunque el perfil
    dijera D01. Y por lo mismo una persona moral con D01 pasaba sin que nadie lo notara."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        rfc = rfc_de_prueba(41)
        r = c.post("/api/clientes", headers=h, json={"emisor_id": e["id"], "rfc": rfc, "nombre": "PACIENTE CON OTRO USO",
                                                     "regimen_fiscal": "612", "codigo_postal": "42501", "uso_cfdi": "G03"})
        assert r.status_code == 200, r.text
        pid = _perfil(c, h, e, serie="K")
        moral = rfc_moral(41)
        lote = _nuevo_lote(c, h, e, pid, [
            fila("K-500", "PACIENTE CON OTRO USO", rfc, "42501", "05/10/2026", "750", "562.50", "TDC", PF612),
            fila("K-501", "CLINICA MORAL", moral, "42501", "05/10/2026", "900", "675", "TRANSF", PM601),
        ])
        f500, f501 = _por_ref(lote, "K-500"), _por_ref(lote, "K-501")
        assert f500["estado"] == "listo" and f500["resumen"]["uso"] == "D01" and f500["resumen"]["cliente"] == "existe"
        assert f501["estado"] == "error" and "D01" in f501["error"] and f501["folio"] == "501"  # apartada con su folio
        d = _timbrar(c, h, lote)
        x = _xml(c, h, _por_ref(d, "K-500")["factura_id"])
        assert x.find("c:Receptor", NS).get("UsoCFDI") == "D01"
        # el cliente conserva el uso que tenía guardado: el lote no se lo cambia
        cli = c.get(f"/api/clientes?emisor_id={e['id']}&q={rfc}", headers=h).json()[0]
        assert cli["uso_cfdi"] == "G03"
        # la moral se rescata diciendo el uso de ESA fila
        r = c.put(f"/api/lotes/{lote['id']}/filas/{f501['id']}", headers=h, json={"datos": {"uso": "G03"}})
        assert r.status_code == 200 and r.json()["estado"] == "listo" and r.json()["folio"] == "501", r.text
        d = _timbrar(c, h, lote)
        assert _xml(c, h, _por_ref(d, "K-501")["factura_id"]).find("c:Receptor", NS).get("UsoCFDI") == "G03"
        assert d["estado"] == "terminado" and d["cuentas"]["timbrada"] == 2


def test_uso_distinto_en_una_sola_factura_sin_tocar_al_cliente():
    with TestClient(app) as c:
        h, e = _preparar(c)
        rfc = rfc_de_prueba(42)
        cli = c.post("/api/clientes", headers=h, json={"emisor_id": e["id"], "rfc": rfc, "nombre": "CLIENTE DOS USOS",
                                                       "regimen_fiscal": "612", "codigo_postal": "42501", "uso_cfdi": "G03"}).json()
        cuerpo = {"emisor_id": e["id"], "cliente_id": cli["id"], "metodo_pago": "PUE", "forma_pago": "03",
                  "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "Servicio",
                                 "valor_unitario": "100", "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]}]}
        f = c.post("/api/facturas", headers=h, json=cuerpo)
        assert f.status_code == 200 and _xml(c, h, f.json()["id"]).find("c:Receptor", NS).get("UsoCFDI") == "G03"
        f = c.post("/api/facturas", headers=h, json={**cuerpo, "uso_cfdi": "G01"})
        assert f.status_code == 200, f.text
        assert _xml(c, h, f.json()["id"]).find("c:Receptor", NS).get("UsoCFDI") == "G01"
        # un uso que su régimen no permite se detiene ANTES de timbrar
        pv = c.post("/api/facturas/preview", headers=h, json={**cuerpo, "uso_cfdi": "CN01"}).json()
        assert any("uso" in v["campo"] for v in pv["errores"]), pv
        assert c.post("/api/facturas", headers=h, json={**cuerpo, "uso_cfdi": "CN01"}).status_code == 422
        assert c.get(f"/api/clientes?emisor_id={e['id']}&q={rfc}", headers=h).json()[0]["uso_cfdi"] == "G03"


def test_la_hoja_tal_como_sale_de_excel():
    """Montos con $ y comas, forma de pago en minúsculas, CP sin su cero, régimen escrito con palabras."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e, serie="K")
        casos = [("K-510", "$1,200.00", "900.00", "tdd", "28", "9000", "06/10/2026"),
                 ("K-511", "1,100", "825", "Transf", "03", "42501", "07/10/2026"),
                 ("K-512", " 750 ", "562.5", "EFECT", "01", "42501", "08/10/2026"),
                 ("K-513", "5400", "4,050.00", "efe", "01", "42501", "09/10/2026"),
                 ("K-514", "850", "637.50", "TDC", "04", "42501", "09/10/2026")]
        lote = _nuevo_lote(c, h, e, pid, [fila(ref, f"PACIENTE {ref}", rfc_de_prueba(50 + i), cp, fecha, monto, serv, forma)
                                           for i, (ref, monto, serv, forma, _, cp, fecha) in enumerate(casos)])
        assert all(f["estado"] == "listo" for f in lote["filas"]), [(f["referencia"], f["error"]) for f in lote["filas"]]
        d = _timbrar(c, h, lote)
        assert d["cuentas"]["timbrada"] == len(casos), [(f["referencia"], f["estado"], f["error"]) for f in d["filas"]]
        for ref, monto, _, _, forma_sat, cp, fecha in casos:
            x = _xml(c, h, _por_ref(d, ref)["factura_id"])
            cons = x.findall("c:Conceptos/c:Concepto", NS)
            assert Decimal(x.get("Total")) == Decimal(monto.strip().replace("$", "").replace(",", "")), ref
            assert x.get("FormaPago") == forma_sat and x.get("MetodoPago") == "PUE", ref
            assert f"{x.get('Serie')}-{x.get('Folio')}" == ref
            assert x.find("c:Receptor", NS).get("DomicilioFiscalReceptor") == cp.zfill(5)
            assert x.find("c:Receptor", NS).get("RegimenFiscalReceptor") == "605" and REGIMEN_605
            assert [k.get("ClaveProdServ") for k in cons] == ["85121503", "51191905"]
            assert cons[0].get("NoIdentificacion") == "CED PROF 13868869" and cons[1].get("ClaveUnidad") == "H87"
            assert all(f"CORRESPONDIENTE AL DÍA {fecha[:2]} DE OCTUBRE DE 2026." in k.get("Descripcion") for k in cons), ref
            assert x.find("c:Complemento/t:TimbreFiscalDigital", NS) is not None
            # la suma de lo que dice cada concepto (importe + su IVA) es el total: nada se pierde en el redondeo
            suma = sum(Decimal(k.get("Importe")) + Decimal(k.find("c:Impuestos/c:Traslados/c:Traslado", NS).get("Importe")) for k in cons)
            assert suma == Decimal(x.get("Total")), ref


def test_una_fila_timbrada_y_luego_cancelada_no_se_omite_en_silencio():
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e, serie="K")
        renglon = fila("K-520", "PACIENTE CANCELADO", rfc_de_prueba(60), "42501", "05/10/2026", "800", "600", "TDC")
        d = _timbrar(c, h, _nuevo_lote(c, h, e, pid, [renglon]))
        fid = d["filas"][0]["factura_id"]
        # mientras está vigente, volver a pegar la hoja no hace nada
        assert _nuevo_lote(c, h, e, pid, [renglon])["filas"][0]["estado"] == "omitida"
        assert c.post(f"/api/facturas/{fid}/cancelar", headers=h, json={"motivo": "02"}).json()["estado"] == "cancelada"
        # cancelada: ya no se da por hecha; avisa y pide folio nuevo (el anterior ya se usó)
        otro = _nuevo_lote(c, h, e, pid, [renglon])
        f = otro["filas"][0]
        assert f["estado"] == "error" and "cancelada" in f["error"], f
        assert any("ponle un folio nuevo" in a["texto"] for a in f["avisos"])
        r = c.put(f"/api/lotes/{otro['id']}/filas/{f['id']}", headers=h, json={"datos": {"folio": "K-521"}}).json()
        assert r["estado"] == "listo" and r["folio"] == "521"
        d = _timbrar(c, h, otro)
        nueva = d["filas"][0]
        assert nueva["estado"] == "timbrada" and nueva["folio_timbra"] == "K521" and nueva["factura_id"] != fid
        # con folio consecutivo la misma referencia cancelada se vuelve a emitir sola
        pid2 = _perfil(c, h, e, serie="KC", folio_modo="consecutivo")
        ren = fila("NOTA-9", "PACIENTE CANCELADO", rfc_de_prueba(60), "42501", "05/10/2026", "800", "600", "TDC")
        d = _timbrar(c, h, _nuevo_lote(c, h, e, pid2, [ren]))
        primera = d["filas"][0]["factura_id"]
        c.post(f"/api/facturas/{primera}/cancelar", headers=h, json={"motivo": "02"})
        de_nuevo = _nuevo_lote(c, h, e, pid2, [ren])
        assert de_nuevo["filas"][0]["estado"] == "listo" and any("se emite de nuevo" in a["texto"] for a in de_nuevo["filas"][0]["avisos"])
        d = _timbrar(c, h, de_nuevo)
        assert d["filas"][0]["estado"] == "timbrada" and d["filas"][0]["factura_id"] != primera
        assert _nuevo_lote(c, h, e, pid2, [ren])["filas"][0]["estado"] == "omitida"  # y ahora sí: ya está vigente


def test_carpeta_de_entrega_deja_pdf_y_xml_como_la_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(svc.pdf_svc, "pdf_varios", lambda pares: [b"%PDF-1.4 prueba" for _ in pares])
    with TestClient(app) as c:
        h, e = _preparar(c)
        plantilla = str(tmp_path / "01 FACTURAS" / "{MM} {Mes}" / "Clientes Emitidas")
        pid = _perfil(c, h, e, serie="K", carpeta=plantilla)
        lote = _nuevo_lote(c, h, e, pid, [
            fila("K-530", "PACIENTE CARPETA UNO", rfc_de_prueba(70), "42501", "05/10/2026", "750", "562.50", "TDC"),
            fila("K-531", "PACIENTE CARPETA DOS", rfc_de_prueba(71), "42501", "05/10/2026", "900", "675", "EFE"),
            fila("K-532", "PACIENTE CARPETA MAL", "ZZZ", "42501", "05/10/2026", "900", "675", "EFE"),
        ])
        d = _timbrar(c, h, lote)
        assert d["cuentas"]["timbrada"] == 2 and d["guardando"] is False
        ent = d["entrega"]
        assert ent["guardadas"] == 2 and ent["timbradas"] == 2 and len(ent["carpetas"]) == 1, ent
        carpeta = ent["carpetas"][0]
        from datetime import datetime
        hoy = datetime.now()
        assert carpeta.endswith(os.path.join(f"{hoy:%m} {svc.MESES[hoy.month - 1].capitalize()}", "Clientes Emitidas"))
        esperados = set()
        for f in d["filas"]:
            if f["uuid"]:
                esperados |= {f"{f['referencia']}_{f['uuid']}.xml", f"{f['referencia']}_{f['uuid']}.pdf"}
        assert set(os.listdir(carpeta)) == esperados  # sólo lo timbrado, sin archivos a medias
        uno = next(f for f in d["filas"] if f["referencia"] == "K-530")
        en_disco = open(os.path.join(carpeta, f"K-530_{uno['uuid']}.xml"), "rb").read()
        assert en_disco == c.get(f"/api/facturas/{uno['factura_id']}/xml", headers=h).content  # el mismo XML timbrado
        # volver a pedirlo no pisa ni duplica; si falta uno, lo repone
        r = c.post(f"/api/lotes/{lote['id']}/carpeta", headers=h).json()
        assert r["archivos_nuevos"] == 0 and r["errores"] == []
        os.remove(os.path.join(carpeta, f"K-530_{uno['uuid']}.pdf"))
        assert c.get(f"/api/lotes/{lote['id']}", headers=h).json()["entrega"]["guardadas"] == 1
        r = c.post(f"/api/lotes/{lote['id']}/carpeta", headers=h).json()
        assert r["archivos_nuevos"] == 1 and r["guardadas"] == 2
        # la fila rescatada después también llega a la carpeta
        mala = _por_ref(d, "K-532")
        c.put(f"/api/lotes/{lote['id']}/filas/{mala['id']}", headers=h, json={"datos": {"rfc": rfc_de_prueba(72)}})
        d = _timbrar(c, h, lote)
        assert d["entrega"]["guardadas"] == 3 and len(os.listdir(carpeta)) == 6

        # un lote hecho ANTES de ponerle carpeta al perfil la toma al pedirlo
        pid2 = _perfil(c, h, e, serie="K")
        l2 = _timbrar(c, h, _nuevo_lote(c, h, e, pid2, [fila("K-535", "PACIENTE SIN CARPETA", rfc_de_prueba(73), "42501", "05/10/2026", "800", "600")]))
        assert l2["entrega"] is None
        assert c.post(f"/api/lotes/{l2['id']}/carpeta", headers=h).status_code == 409
        cfg = c.get(f"/api/lotes/perfiles?emisor_id={e['id']}", headers=h).json()
        mio = next(p for p in cfg if p["id"] == pid2)
        otra = str(tmp_path / "otra {AAAA}")
        assert c.put(f"/api/lotes/perfiles/{pid2}", headers=h, json={"emisor_id": e["id"], "nombre": mio["nombre"],
                                                                     "config": {**mio["config"], "carpeta": otra}}).status_code == 200
        r = c.post(f"/api/lotes/{l2['id']}/carpeta", headers=h)
        assert r.status_code == 200 and r.json()["guardadas"] == 1 and len(os.listdir(tmp_path / f"otra {hoy:%Y}")) == 2

        # rutas relativas o con comodines inventados no se aceptan
        r = c.put(f"/api/lotes/perfiles/{pid2}", headers=h, json={"emisor_id": e["id"], "nombre": "x", "config": {**mio["config"], "carpeta": "facturas\\{dia}"}})
        assert r.status_code == 422 and "ruta completa" in r.text and "{dia}" in r.text

        # en la web no hay carpetas: ni se guarda el perfil ni se escribe en el servidor
        monkeypatch.setattr(svc, "EN_WEB", True)
        r = c.put(f"/api/lotes/perfiles/{pid2}", headers=h, json={"emisor_id": e["id"], "nombre": "x", "config": {**mio["config"], "carpeta": otra}})
        assert r.status_code == 422 and "instalado" in r.text
        assert c.post(f"/api/lotes/{lote['id']}/carpeta", headers=h).status_code == 409
        assert c.get(f"/api/lotes/{lote['id']}", headers=h).json()["entrega"] is None


def test_si_la_carpeta_no_se_puede_escribir_las_facturas_siguen_timbradas(tmp_path, monkeypatch):
    monkeypatch.setattr(svc.pdf_svc, "pdf_varios", lambda pares: [b"%PDF" for _ in pares])
    estorbo = tmp_path / "ocupado"
    estorbo.write_text("soy un archivo, no una carpeta")
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e, serie="K", carpeta=str(estorbo / "dentro"))
        d = _timbrar(c, h, _nuevo_lote(c, h, e, pid, [fila("K-540", "PACIENTE DISCO LLENO", rfc_de_prueba(80), "42501", "05/10/2026", "750", "562.50")]))
        assert d["cuentas"]["timbrada"] == 1 and d["estado"] == "terminado" and d["filas"][0]["uuid"]
        assert d["entrega"]["guardadas"] == 0
        r = c.post(f"/api/lotes/{d['id']}/carpeta", headers=h).json()
        assert r["errores"] and "K-540" in r["errores"][0]
        assert c.get(f"/api/lotes/{d['id']}/cfdi.zip", headers=h).status_code == 200  # el ZIP sigue disponible


def test_otra_cuenta_no_ve_ni_toca_mis_lotes():
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e, serie="K")
        lote = _nuevo_lote(c, h, e, pid, [fila("K-550", "PACIENTE PRIVADO", rfc_de_prueba(90), "42501", "05/10/2026", "750", "562.50")])
        fid = lote["filas"][0]["id"]
        ajeno = _usuario(c, h, "lotes-ajeno@prueba.mx", "lotesajeno")
        assert c.get(f"/api/lotes/perfiles?emisor_id={e['id']}", headers=ajeno).json() == []
        assert c.get(f"/api/lotes?emisor_id={e['id']}", headers=ajeno).json() == []
        for metodo, ruta, cuerpo in [("get", f"/api/lotes/{lote['id']}", None), ("post", f"/api/lotes/{lote['id']}/ejecutar", {}),
                                     ("put", f"/api/lotes/{lote['id']}/filas/{fid}", {"datos": {"monto": "1"}}),
                                     ("post", f"/api/lotes/{lote['id']}/filas/{fid}/omitir", None),
                                     ("get", f"/api/lotes/{lote['id']}/cfdi.zip", None), ("get", f"/api/lotes/{lote['id']}/registro.csv", None),
                                     ("post", f"/api/lotes/{lote['id']}/carpeta", None), ("delete", f"/api/lotes/{lote['id']}", None)]:
            r = getattr(c, metodo)(ruta, headers=ajeno, **({"json": cuerpo} if cuerpo is not None else {}))
            assert r.status_code in (403, 404), (metodo, ruta, r.status_code, r.text[:120])
        r = c.post("/api/lotes", headers=ajeno, data={"emisor_id": e["id"], "perfil_id": pid, "texto": "x\ty"})
        assert r.status_code in (403, 404)
        r = c.put(f"/api/lotes/perfiles/{pid}", headers=ajeno, json={"emisor_id": e["id"], "nombre": "robado", "config": svc.PERFIL_EJEMPLO})
        assert r.status_code in (403, 404)
        # y sigue intacto para su dueño
        d = c.get(f"/api/lotes/{lote['id']}", headers=h).json()
        assert d["filas"][0]["estado"] == "listo" and d["filas"][0]["resumen"]["monto"] == "750"


def _huella(c, h, e) -> dict:
    """Todo lo que una cuenta espera volver a encontrar."""
    facturas = c.get(f"/api/facturas?emisor_id={e['id']}&limit=1000", headers=h).json()
    lotes = c.get(f"/api/lotes?emisor_id={e['id']}&limit=200", headers=h).json()
    return {
        "yo": c.get("/api/auth/yo", headers=h).json(),
        "emisor": [(x["rfc"], x["nombre"], x["no_certificado"], [(s["serie"], s["siguiente_folio"]) for s in x["series"]])
                   for x in c.get("/api/emisores", headers=h).json()],
        "clientes": sorted((x["rfc"], x["nombre"], x["codigo_postal"], x["regimen_fiscal"], x["uso_cfdi"])
                           for x in c.get(f"/api/clientes?emisor_id={e['id']}&limit=1000", headers=h).json()),
        "facturas": sorted((f["id"], f["serie"], f["folio"], f["uuid"], f["estado"], str(f["total"])) for f in facturas),
        "xml": {f["id"]: c.get(f"/api/facturas/{f['id']}/xml", headers=h).content for f in facturas if f["uuid"]},
        "perfiles": c.get(f"/api/lotes/perfiles?emisor_id={e['id']}", headers=h).json(),
        "lotes": [(x["id"], x["nombre"], x["estado"], x["cuentas"]) for x in lotes],
        "filas": [[(f["referencia"], f["estado"], f["folio"], f["uuid"], f["datos"]) for f in c.get(f"/api/lotes/{x['id']}", headers=h).json()["filas"]]
                  for x in lotes[:5]],
    }


def test_todo_sigue_ahi_despues_de_apagar_y_encender():
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e, serie="K")
        d = _timbrar(c, h, _nuevo_lote(c, h, e, pid, [
            fila("K-560", "PACIENTE QUE SE QUEDA", rfc_de_prueba(95), "42501", "05/10/2026", "2000", "1500", "TDC", correo="queda@example.com"),
            fila("K-561", "PACIENTE PENDIENTE", "MAL", "42501", "05/10/2026", "900", "675", "EFE")]))
        assert d["cuentas"] == {"listo": 0, "error": 1, "timbrando": 0, "timbrada": 1, "omitida": 0}
        ajeno = _usuario(c, h, "persistente@prueba.mx", "persistente")
        antes = _huella(c, h, e)
        salud = c.get("/api/health").json()["almacen"]
        assert antes["xml"] and antes["perfiles"] and antes["lotes"] and salud["arranques"] >= 1 and salud["desde"]

    engine.dispose()  # se cierran todas las conexiones: lo que no esté en disco, se pierde aquí

    with TestClient(app) as c:  # arranca de nuevo: migraciones, admin, recuperación de lotes… nada debe tocar los datos
        h2 = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "rick@erickddp.com", "password": "cambiame"}).json()["token"]}
        despues = _huella(c, h2, e)
        assert despues == antes
        s2 = c.get("/api/health").json()["almacen"]
        assert s2["arranques"] == salud["arranques"] + 1 and s2["desde"] == salud["desde"] and s2["permanente"] is True
        # la otra cuenta también entra con su usuario y contraseña de siempre, y sigue sin ver lo mío
        r = c.post("/api/auth/login", json={"email": "persistente", "password": "claveLarga1"})
        assert r.status_code == 200 and c.get("/api/emisores", headers={"Authorization": "Bearer " + r.json()["token"]}).json() == []
        assert ajeno
        # la fila que quedó pendiente conserva su folio apartado: nadie más lo toma
        f = c.post("/api/facturas", headers=h2, json={
            "emisor_id": e["id"], "serie": "K", "metodo_pago": "PUE", "forma_pago": "03",
            "receptor": {"rfc": "KIJ0906199R1", "nombre": "KERNEL INDUSTIA JUGUETERA", "regimen_fiscal": "601",
                         "codigo_postal": "42501", "uso_cfdi": "G03", "guardar": False},
            "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "x", "valor_unitario": "10",
                           "objeto_imp": "01", "impuestos": []}]})
        assert f.status_code == 200 and int(f.json()["folio"]) >= 562, f.text


def test_salud_dice_si_el_disco_es_permanente(monkeypatch, tmp_path):
    with TestClient(app) as c:
        s = c.get("/api/health").json()
        assert s["ok"] and s["web"] is False and s["almacen"]["permanente"] is True
        # en web sin volumen montado: se avisa (lo guardado se perdería en la siguiente actualización)
        monkeypatch.setattr(almacen, "EN_WEB", True)
        assert c.get("/api/health").json()["almacen"]["permanente"] is False
        # con volumen montado y la base dentro: permanente
        monkeypatch.setattr(almacen.os.path, "ismount", lambda p: True)
        assert c.get("/api/health").json()["almacen"]["permanente"] is True
        # volumen montado pero la base en otra parte: NO es permanente
        monkeypatch.setattr(almacen.settings, "database_url", "sqlite:///" + str(tmp_path / "fuera.db"))
        assert c.get("/api/health").json()["almacen"]["permanente"] is False
        # una ruta de la API que no existe es un 404, no la pantalla de inicio
        r = c.get("/api/esto-no-existe")
        assert r.status_code == 404 and "json" in r.headers["content-type"]


def _emisor_nuevo(c, h, rfc, nombre):
    r = c.post("/api/emisores", headers=h, json={"rfc": rfc, "nombre": nombre, "regimen_fiscal": "601", "lugar_expedicion": "42501"})
    assert r.status_code == 200, r.text
    return r.json()


def test_las_advertencias_del_resumen_son_solo_del_emisor_que_estas_viendo():
    with TestClient(app) as c:
        h, e = _preparar(c)
        otro = _emisor_nuevo(c, h, rfc_moral(77), "OTRO SIN CSD NI PAC")
        textos = lambda eid: " | ".join(a["texto"] for a in c.get(f"/api/dashboard?emisor_id={eid}", headers=h).json()["alertas"])  # noqa: E731
        assert otro["rfc"] in textos(otro["id"])
        assert otro["rfc"] not in textos(e["id"])  # antes salía «X está en modo demo» aunque estuvieras en otro RFC
        assert c.delete(f"/api/emisores/{otro['id']}?confirmar={otro['rfc']}", headers=h).status_code == 200


def test_eliminar_un_emisor_de_prueba_se_lleva_lo_suyo_y_nada_mas():
    with TestClient(app) as c:
        h, e = _preparar(c)
        antes = len(c.get(f"/api/facturas?emisor_id={e['id']}&limit=1000", headers=h).json())
        x = _emisor_nuevo(c, h, rfc_moral(78), "EMISOR QUE SE VA")
        cli = c.post("/api/clientes", headers=h, json={"emisor_id": x["id"], "rfc": rfc_de_prueba(120), "nombre": "CLIENTE QUE SE VA",
                                                       "regimen_fiscal": "612", "codigo_postal": "42501", "uso_cfdi": "G03"})
        assert cli.status_code == 200
        pid = _perfil(c, h, x, serie="Z")
        lote = _nuevo_lote(c, h, x, pid, [fila("Z-1", "PACIENTE", rfc_de_prueba(121), "42501", "05/10/2026", "750", "562.50")])
        # sin escribir el RFC no se elimina
        assert c.delete(f"/api/emisores/{x['id']}", headers=h).status_code == 422
        assert c.delete(f"/api/emisores/{x['id']}?confirmar=OTRO", headers=h).status_code == 422
        # otra cuenta no puede
        ajeno = _usuario(c, h, "borrador-ajeno@prueba.mx", "borradorajeno")
        assert c.delete(f"/api/emisores/{x['id']}?confirmar={x['rfc']}", headers=ajeno).status_code in (403, 404)
        r = c.delete(f"/api/emisores/{x['id']}?confirmar={x['rfc'].lower()}", headers=h)
        assert r.status_code == 200 and r.json()["borrado"].get("clientes") == 1 and r.json()["borrado"].get("lote_filas") == 1, r.text
        assert x["rfc"] not in {y["rfc"] for y in c.get("/api/emisores", headers=h).json()}
        assert c.get(f"/api/lotes/{lote['id']}", headers=h).status_code == 404
        assert c.get(f"/api/clientes?emisor_id={x['id']}", headers=h).json() == []
        # lo de los demás emisores sigue igual, y el RFC se puede volver a dar de alta
        assert len(c.get(f"/api/facturas?emisor_id={e['id']}&limit=1000", headers=h).json()) == antes
        assert _emisor_nuevo(c, h, x["rfc"], "EMISOR QUE VUELVE")["id"]
        assert c.delete(f"/api/emisores/{c.get('/api/emisores', headers=h).json()[0]['id']}", headers=h).status_code == 422


def test_no_se_elimina_un_emisor_con_facturas_timbradas_en_produccion():
    from app.db import SessionLocal
    from app.models import Emisor, Factura, Pac
    with TestClient(app) as c:
        h, _ = _preparar(c)
        x = _emisor_nuevo(c, h, rfc_moral(79), "EMISOR CON FACTURAS REALES")
        with SessionLocal() as db:
            pac = Pac(nombre="Producción de prueba", proveedor="finkok", pruebas=False, usuario_id=db.get(Emisor, x["id"]).usuario_id)
            db.add(pac)
            db.flush()
            db.get(Emisor, x["id"]).pac_id = pac.id
            db.add(Factura(emisor_id=x["id"], tipo="I", estado="timbrada", serie="A", folio="1", uuid="11111111-2222-3333-4444-555555555555",
                           total=100, subtotal=100, xml=b'<?xml version="1.0"?><x SelloSAT="abc"/>', payload={}))
            db.commit()
        r = c.delete(f"/api/emisores/{x['id']}?confirmar={x['rfc']}", headers=h)
        assert r.status_code == 409 and "validez fiscal" in r.text
        assert x["rfc"] in {y["rfc"] for y in c.get("/api/emisores", headers=h).json()}


def test_cobro_repetido_se_avisa_aunque_el_monto_venga_escrito_distinto():
    """Uso real: la hoja traía «$750.00» en un renglón y «750» en otro. Es el mismo cobro."""
    with TestClient(app) as c:
        h, e = _preparar(c)
        pid = _perfil(c, h, e, serie="K")
        rfc = rfc_de_prueba(130)
        lote = _nuevo_lote(c, h, e, pid, [
            fila("K-570", "PACIENTE DOBLE", rfc, "42501", "05/10/2026", "$750.00", "562.50"),
            fila("K-571", "PACIENTE DOBLE", rfc, "42501", "5/10/2026", "750", "562.5"),
            fila("K-572", "PACIENTE DOBLE", rfc, "42501", "06/10/2026", "750", "562.5"),
        ])
        avisos = {f["referencia"]: " ".join(a["texto"] for a in f["avisos"]) for f in lote["filas"]}
        assert "cobro repetido" in avisos["K-571"] and "fila 1" in avisos["K-571"]
        assert "cobro repetido" not in avisos["K-570"] and "cobro repetido" not in avisos["K-572"]
        # al corregir otra fila el aviso sigue ahí (se recalcula contra las filas de arriba)
        f571 = _por_ref(lote, "K-571")
        r = c.put(f"/api/lotes/{lote['id']}/filas/{f571['id']}", headers=h, json={"datos": {"correo": "x@example.com", "uso": ""}}).json()
        assert r["estado"] == "listo" and any("cobro repetido" in a["texto"] for a in r["avisos"])
        for f in lote["filas"]:
            c.post(f"/api/lotes/{lote['id']}/filas/{f['id']}/omitir", headers=h)


def test_respaldo_completo_se_descarga_y_trae_base_y_xml():
    import io
    import sqlite3
    import zipfile
    with TestClient(app) as c:
        h, e = _preparar(c)
        r = c.get("/api/debug/respaldo", headers=h)
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nombres = z.namelist()
        assert "datos/timbra.db" in nombres and any(n.endswith(".xml") for n in nombres)
        assert not any("/logs/" in n or "Respaldos" in n for n in nombres)
        # la base del respaldo se abre y trae lo mismo que la viva
        tmp = os.path.join("_test_datos", "restaurada.db")
        open(tmp, "wb").write(z.read("datos/timbra.db"))
        con = sqlite3.connect(tmp)
        try:
            n_fact = con.execute("select count(*) from facturas where uuid is not null").fetchone()[0]
            assert con.execute("pragma integrity_check").fetchone()[0] == "ok"
        finally:
            con.close()
            os.remove(tmp)
        vivas = sum(len(c.get(f"/api/facturas?emisor_id={x['id']}&limit=5000", headers=h).json()) for x in c.get("/api/emisores", headers=h).json())
        assert n_fact >= vivas > 0
        # sólo el administrador
        ajeno = _usuario(c, h, "sin-respaldo@prueba.mx", "sinrespaldo")
        assert c.get("/api/debug/respaldo", headers=ajeno).status_code == 403
        assert c.get("/api/debug/respaldo").status_code == 401


def test_respaldo_diario_en_web_queda_dentro_del_volumen(monkeypatch, tmp_path):
    from pathlib import Path

    from app.config import settings
    from app.services import programador
    with TestClient(app):
        monkeypatch.setattr(programador, "EN_WEB", True)
        z = programador.respaldo_diario()
        try:
            datos = Path(settings.data_dir).resolve()
            assert z is not None and z.parent == datos / "Respaldos"
            assert programador.respaldo_diario() is None  # uno por día
            import zipfile
            assert not any("Respaldos" in n for n in zipfile.ZipFile(z).namelist())
        finally:
            if z:
                z.unlink(missing_ok=True)


def test_cancelacion_pendiente_no_se_da_por_rechazada_si_el_sat_aun_no_la_refleja(monkeypatch):
    """Uso real (Finkok pruebas): tras pedir la cancelación el SAT siguió diciendo «Vigente» sin estatus, y Timbra la
    regresaba a «timbrada» como si nunca se hubiera pedido."""
    from app.services import pac as pac_svc
    with TestClient(app) as c:
        h, e = _preparar(c)
        f = c.post("/api/facturas", headers=h, json={
            "emisor_id": e["id"], "metodo_pago": "PUE", "forma_pago": "03",
            "receptor": {"rfc": rfc_de_prueba(140), "nombre": "CLIENTE QUE DEBE ACEPTAR", "regimen_fiscal": "612",
                         "codigo_postal": "42501", "uso_cfdi": "G03", "guardar": False},
            "conceptos": [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "x", "valor_unitario": "5000",
                           "objeto_imp": "01", "impuestos": []}]}).json()
        respuesta = {"Estado": "Vigente", "EstatusCancelacion": None}
        monkeypatch.setattr(pac_svc, "estatus", lambda pac, xml: dict(respuesta))
        r = c.post(f"/api/facturas/{f['id']}/cancelar", headers=h, json={"motivo": "02"}).json()
        assert r["estado"] == "cancelacion_pendiente"
        c.get(f"/api/facturas/{f['id']}/estatus", headers=h)
        assert c.get(f"/api/facturas/{f['id']}", headers=h).json()["estado"] == "cancelacion_pendiente"  # sigue pedida
        respuesta["EstatusCancelacion"] = "En proceso"
        c.get(f"/api/facturas/{f['id']}/estatus", headers=h)
        assert c.get(f"/api/facturas/{f['id']}", headers=h).json()["estado"] == "cancelacion_pendiente"
        respuesta["EstatusCancelacion"] = "Solicitud rechazada"
        c.get(f"/api/facturas/{f['id']}/estatus", headers=h)
        assert c.get(f"/api/facturas/{f['id']}", headers=h).json()["estado"] == "timbrada"  # ahora sí: el SAT lo dijo
        # se vuelve a pedir y el SAT la cancela
        respuesta.update(Estado="Vigente", EstatusCancelacion=None)
        assert c.post(f"/api/facturas/{f['id']}/cancelar", headers=h, json={"motivo": "02"}).json()["estado"] == "cancelacion_pendiente"
        respuesta.update(Estado="Cancelado", EstatusCancelacion="Cancelado con aceptación")
        c.get(f"/api/facturas/{f['id']}/estatus", headers=h)
        assert c.get(f"/api/facturas/{f['id']}", headers=h).json()["estado"] == "cancelada"
