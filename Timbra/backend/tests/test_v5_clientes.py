"""Fase 3: clientes masivos (conflictos, auditoría, duplicados/fusión, lista 69-B) y bandeja de pendientes."""
import os
import shutil

shutil.rmtree("./_test_datos", ignore_errors=True)
os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cliente, Factura, Plantilla  # noqa: E402
from app.services import clientes_io  # noqa: E402
from test_lotes import rfc_de_prueba  # noqa: E402
from test_v2 import _preparar  # noqa: E402

REG = "Sueldos y Salarios e Ingresos Asimilados a Salarios"


def rfc_moral(n: int) -> str:
    """RFC de persona moral inventado, con dígito verificador válido."""
    from app.services.validacion import digito_rfc_ok
    base = f"PRM9001{n % 28 + 1:02d}A{n % 9}"
    for c in "0123456789A":
        if digito_rfc_ok(base + c):
            return base + c
    raise AssertionError


def _imp(c, h, e, filas, resolver=None, modo="actualizar"):
    texto = "NOMBRE\tRFC\tCP\tREGIMEN_FISCAL\tCORREO_O_CONTACTO\n" + "\n".join("\t".join(f) for f in filas)
    v = c.post("/api/clientes/importar/previsualizar", headers=h_(h), data={"emisor_id": e["id"], "texto": texto}).json()
    return v


def h_(h):
    return h


def _confirmar(c, h, e, vista, decisiones=None, modo="actualizar"):
    decisiones = decisiones or {}
    filas = []
    for f in vista["filas"]:
        if f["accion"] in ("error", "duplicado"):
            continue
        filas.append({**f["datos"], "_accion": f["accion"], "_resolucion": decisiones.get(f["datos"]["rfc"])})
    return c.post("/api/clientes/importar/confirmar", headers=h, json={"emisor_id": e["id"], "filas": filas, "modo": modo}).json()


def test_importacion_con_conflictos_y_decision_por_fila():
    with TestClient(app) as c:
        h, e = _preparar(c)
        a, b, d = rfc_de_prueba(51), rfc_de_prueba(52), rfc_de_prueba(53)
        v = _imp(c, h, e, [("CLIENTE A", a, "42501", REG, "a@x.mx"), ("CLIENTE B", b, "42501", REG, ""), ("CLIENTE D", d, "42501", REG, "")])
        assert v["resumen"]["nuevo"] == 3
        assert _confirmar(c, h, e, v)["creados"] == 3

        # Mismos datos → "igual" (nada que hacer); CP distinto → conflicto; un correo nuevo → actualizar
        v = _imp(c, h, e, [("CLIENTE A", a, "42501", REG, "a@x.mx"), ("CLIENTE B", b, "42000", REG, ""),
                           ("CLIENTE D", d, "42501", REG, "d@x.mx"), ("OTRO NOMBRE", rfc_de_prueba(54), "42501", REG, "")])
        acc = {f["datos"]["rfc"]: f for f in v["filas"]}
        assert acc[a]["accion"] == "igual" and acc[d]["accion"] == "actualizar" and acc[b]["accion"] == "conflicto"
        dif = acc[b]["conflictos"][0]
        assert dif["campo"] == "codigo_postal" and dif["hoja"] == "42000" and dif["base"] == "42501"
        assert v["resumen"]["conflicto"] == 1 and v["resumen"]["igual"] == 1 and v["resumen"]["nuevo"] == 1

        # Sin decidir el conflicto, NO se toca el cliente
        r = _confirmar(c, h, e, v)
        assert r["sin_decidir"] == 1 and r["actualizados"] == 1 and r["creados"] == 1
        cb = c.get(f"/api/clientes?emisor_id={e['id']}&q={b}", headers=h).json()[0]
        assert cb["codigo_postal"] == "42501"
        # "base" conserva lo guardado; "hoja" aplica lo de la hoja
        assert _confirmar(c, h, e, v, {b: "base"})["actualizados"] >= 1
        assert c.get(f"/api/clientes?emisor_id={e['id']}&q={b}", headers=h).json()[0]["codigo_postal"] == "42501"
        v = _imp(c, h, e, [("CLIENTE B", b, "42000", REG, "")])
        _confirmar(c, h, e, v, {b: "hoja"})
        assert c.get(f"/api/clientes?emisor_id={e['id']}&q={b}", headers=h).json()[0]["codigo_postal"] == "42000"

        # El correo nuevo de D sí entró
        assert "d@x.mx" in c.get(f"/api/clientes?emisor_id={e['id']}&q={d}", headers=h).json()[0]["emails"]


def test_auditoria_arreglos_y_duplicados():
    with TestClient(app) as c:
        h, e = _preparar(c)
        base = {"emisor_id": e["id"], "regimen_fiscal": "601", "codigo_postal": "42501"}
        RFC_SUCIO = rfc_moral(5)
        # sociedad con nombre societario y uso D01 (no es de moral), + un cliente sano
        sucio = c.post("/api/clientes", headers=h, json={**base, "rfc": RFC_SUCIO, "nombre": "KERNEL INDUSTIA JUGUETERA SA DE CV",
                                                          "uso_cfdi": "D01"}).json()
        c.post("/api/clientes", headers=h, json={**base, "rfc": "URE180429TM6", "nombre": "UNIVERSIDAD ROBOTICA", "uso_cfdi": "G03",
                                                 "emails": ["a@b.mx"]})
        aud = c.get(f"/api/clientes/auditoria?emisor_id={e['id']}", headers=h).json()
        mio = [a for a in aud if a["cliente_id"] == sucio["id"]][0]
        campos = {p["campo"] for p in mio["problemas"]}
        assert {"nombre", "uso_cfdi"} <= campos and mio["gravedad"] == "error"
        arreglos = {p["campo"]: p["arreglo"] for p in mio["problemas"] if p["arreglo"]}
        assert arreglos["nombre"]["nombre"] == "KERNEL INDUSTIA JUGUETERA"
        r = c.post("/api/clientes/auditoria/arreglar", headers=h, json={
            "emisor_id": e["id"], "arreglos": [{"cliente_id": sucio["id"], "cambios": {**arreglos["nombre"], **arreglos["uso_cfdi"], "rfc": "HACK"}}]}).json()
        assert r["arreglados"] == 1
        nuevo = c.get(f"/api/clientes?emisor_id={e['id']}&q={RFC_SUCIO}", headers=h).json()[0]
        assert nuevo["nombre"] == "KERNEL INDUSTIA JUGUETERA" and nuevo["uso_cfdi"] != "D01" and nuevo["rfc"] == RFC_SUCIO

        # Duplicados: mismo RFC con dos nombres. Se fusionan y las facturas se mudan al que se conserva
        rfc = rfc_de_prueba(61)
        f1 = c.post("/api/clientes", headers=h, json={**base, "regimen_fiscal": "605", "rfc": rfc, "nombre": "JUAN PEREZ", "uso_cfdi": "S01"}).json()
        f2 = c.post("/api/clientes", headers=h, json={**base, "regimen_fiscal": "605", "rfc": rfc, "nombre": "JUAN PEREZ LOPEZ", "uso_cfdi": "S01",
                                                       "emails": ["j@x.mx"], "telefono": "6561112233"}).json()
        body = {"emisor_id": e["id"], "cliente_id": f2["id"], "metodo_pago": "PUE", "forma_pago": "03",
                "conceptos": [{"clave_prod_serv": "84111500", "clave_unidad": "E48", "descripcion": "x", "valor_unitario": "100",
                               "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]}]}
        r = c.post("/api/facturas", headers=h, json=body)
        assert r.status_code == 200, r.text
        grupos = c.get(f"/api/clientes/duplicados?emisor_id={e['id']}", headers=h).json()
        g = [x for x in grupos if x["clave"] == rfc][0]
        assert g["tipo"] == "mismo_rfc" and g["sugerido"] == f2["id"]  # el que tiene facturas
        # no se fusiona gente con distinto RFC
        assert c.post("/api/clientes/fusionar", headers=h, json={"emisor_id": e["id"], "conservar_id": f2["id"], "fusionar_ids": [sucio["id"]]}).status_code == 422
        r = c.post("/api/clientes/fusionar", headers=h, json={"emisor_id": e["id"], "conservar_id": f2["id"], "fusionar_ids": [f1["id"]]}).json()
        assert r["fusionados"] == 1
        with SessionLocal() as db:
            assert db.query(Cliente).filter_by(emisor_id=e["id"], rfc=rfc).count() == 1
            assert db.query(Factura).filter(Factura.cliente_id == f1["id"]).count() == 0
        # mismo nombre con otro RFC: sólo se avisa, no se fusiona
        c.post("/api/clientes", headers=h, json={**base, "rfc": rfc_de_prueba(62), "nombre": "MARIA GOMEZ", "uso_cfdi": "G03"})
        c.post("/api/clientes", headers=h, json={**base, "rfc": rfc_de_prueba(63), "nombre": "MARIA GOMEZ", "uso_cfdi": "G03"})
        g2 = [x for x in c.get(f"/api/clientes/duplicados?emisor_id={e['id']}", headers=h).json() if x["tipo"] == "mismo_nombre"]
        assert g2 and g2[0]["fusionable"] is False


def test_lista_69b_con_servicio_simulado():
    with TestClient(app) as c:
        h, e = _preparar(c)
        rfc = rfc_de_prueba(71)
        c.post("/api/clientes", headers=h, json={"emisor_id": e["id"], "rfc": rfc, "nombre": "PROVEEDOR DUDOSO", "regimen_fiscal": "601",
                                                 "codigo_postal": "42501", "uso_cfdi": "G03"})
        orig = clientes_io.listado_69b
        clientes_io.listado_69b = lambda: {rfc: "Definitivo", "XXX010101XX1": "Presunto"}
        try:
            r = c.post("/api/clientes/verificar-69b", headers=h, json={"emisor_id": e["id"]}).json()
            assert r["en_lista"][0]["rfc"] == rfc and r["en_lista"][0]["nivel"] == "rojo"
        finally:
            clientes_io.listado_69b = orig

        def sin_internet():
            raise clientes_io.ListaNoDisponible("sin internet")
        clientes_io.listado_69b = sin_internet
        try:
            r = c.post("/api/clientes/verificar-69b", headers=h, json={"emisor_id": e["id"]})
            assert r.status_code == 503 and "sin internet" in r.text
        finally:
            clientes_io.listado_69b = orig


def test_bandeja_de_pendientes():
    with TestClient(app) as c:
        h, e = _preparar(c)
        eid = e["id"]
        # un cliente con datos inválidos, una recurrente con error y una fila de lote por corregir
        c.post("/api/clientes", headers=h, json={"emisor_id": eid, "rfc": rfc_de_prueba(81), "nombre": "CLIENTE MALO", "regimen_fiscal": "601",
                                                 "codigo_postal": "42501", "uso_cfdi": "D01"})
        with SessionLocal() as db:
            db.add(Plantilla(emisor_id=eid, nombre="Iguala rota", recurrente=True, dia=1, ultimo_error="El cliente ya no existe",
                             payload={"publico_general": True, "conceptos": []}))
            db.commit()
        pid = c.post("/api/lotes/perfiles", headers=h, json={"emisor_id": eid, "nombre": "p", "config": __import__("copy").deepcopy(
            __import__("app.services.lotes", fromlist=["x"]).PERFIL_EJEMPLO)}).json()["id"]
        fila = "\t".join(["P-1", "PACIENTE", "ZZZ", "42501", "05/10/2026", "750", "562.50", "", "", "D01", "TDC", REG, "", "", ""])
        c.post("/api/lotes", headers=h, data={"emisor_id": eid, "perfil_id": pid, "texto": fila})

        p = c.get(f"/api/pendientes?emisor_id={eid}", headers=h).json()
        claves = {g["clave"] for g in p["grupos"]}
        assert {"lotes", "clientes", "recurrentes"} <= claves
        todos = [i for g in p["grupos"] for i in g["items"]]
        assert any("por corregir" in i["titulo"] and i["accion"]["ruta"].startswith("/lotes") for i in todos)
        assert any("falló" in i["titulo"] for i in todos)
        assert p["total"] >= 3 and p["errores"] >= 2
        assert c.get(f"/api/pendientes/resumen?emisor_id={eid}", headers=h).json()["total"] == p["total"]
        assert c.get("/api/pendientes?emisor_id=99999", headers=h).status_code == 404


def test_proveedores_recibidos_en_lista_69b():
    with TestClient(app) as c:
        h, e = _preparar(c)
        from app.services import descarga_sat
        from satcfdi.create.cfd import cfdi40
        from decimal import Decimal
        from test_v2 import CSD
        from satcfdi.models import Signer
        s = Signer.load(certificate=open(CSD / "EKU9003173C9.cer", "rb").read(), key=open(CSD / "EKU9003173C9.key", "rb").read(), password="12345678a")
        comp = cfdi40.Comprobante(
            emisor=cfdi40.Emisor(rfc="KIJ0906199R1", nombre="KERNEL INDUSTIA JUGUETERA", regimen_fiscal="601"), lugar_expedicion="42501",
            receptor=cfdi40.Receptor(rfc="EKU9003173C9", nombre="ESCUELA KEMPER URGATE", domicilio_fiscal_receptor="42501",
                                     regimen_fiscal_receptor="601", uso_cfdi="G03"),
            conceptos=[cfdi40.Concepto(clave_prod_serv="84111500", cantidad=1, clave_unidad="E48", descripcion="x", valor_unitario=Decimal("100"), objeto_imp="01")],
            forma_pago="03", metodo_pago="PUE")
        from app.services.pac import DemoPac
        xml = DemoPac().stamp(comp).xml  # CFDI "recibido": el emisor es otro
        with SessionLocal() as db:
            from app.models import Emisor
            descarga_sat.guardar_xml(db, db.get(Emisor, e["id"]), xml)
            db.commit()
        from app.services import clientes_io
        orig = clientes_io.listado_69b
        clientes_io.listado_69b = lambda: {"KIJ0906199R1": "Presunto"}
        try:
            filas = c.get(f"/api/sat/cfdi?emisor_id={e['id']}&direccion=recibido&lista_69b=true", headers=h).json()
            assert any(f["lista_69b"] == "Presunto" for f in filas)
            filas = c.get(f"/api/sat/cfdi?emisor_id={e['id']}&direccion=recibido", headers=h).json()
            assert all(f["lista_69b"] is None for f in filas)  # sin pedirlo no se consulta nada
        finally:
            clientes_io.listado_69b = orig


def test_auditoria_no_infla_con_clientes_solo_sin_correo():
    with TestClient(app) as c:
        h, e = _preparar(c)
        base = {"emisor_id": e["id"], "regimen_fiscal": "605", "codigo_postal": "42501", "uso_cfdi": "S01"}
        solo_info = c.post("/api/clientes", headers=h, json={**base, "rfc": rfc_de_prueba(91), "nombre": "SIN CORREO PERO SANO"}).json()
        ids = lambda info: {a["cliente_id"] for a in c.get(f"/api/clientes/auditoria?emisor_id={e['id']}&incluir_info={info}", headers=h).json()}
        assert solo_info["id"] not in ids("false") and solo_info["id"] in ids("true")
