"""Claves SAT: búsqueda con sinónimos, avisos, bloqueo por emisor, catálogos sugeridos e importación de productos."""
import os
import shutil
import time

shutil.rmtree("./_test_datos", ignore_errors=True)  # corrida limpia al ejecutar este archivo solo

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import claves as svc  # noqa: E402
from app.services.semillas import PACKS  # noqa: E402
from test_v2 import IVA16, _cliente, _preparar  # noqa: E402


def _top(q, n=3, tipo="prod_serv"):
    return [r["clave"] for r in svc.buscar(q, tipo, n)]


def test_busqueda_con_sinonimos_y_sin_acentos():
    svc.buscar("x")  # calienta el índice (una sola vez)
    casos = {
        "consulta medica": "85121502", "consulta médica": "85121502", "vitaminas": "51191905", "renta local": "80131500",
        "contador": "84111500", "contabilidad": "84111500", "dentista": "85122000", "psicologo": "85121608",
        "fisioterapia": "85122101", "laptop": "43211503", "anticipo": "84111506", "celular": "43191501",
        "pagina web": "81112100", "penter": "51191903",
    }
    for q, clave in casos.items():
        assert clave in _top(q, 3), (q, _top(q, 5))
    assert _top("85121", 3)[0].startswith("85121")  # por clave
    assert svc.buscar("zzzzqx") == []
    # rápido: se escribe y se ve (tras el índice, cada búsqueda es de milisegundos)
    t0 = time.perf_counter()
    for q in ("consulta medica", "renta", "software", "limpieza", "flete"):
        svc.buscar(q)
    assert (time.perf_counter() - t0) / 5 < 0.15


def test_unidades():
    assert _top("e48", 1, "unidad") == ["E48"]
    assert _top("mes", 1, "unidad") == ["MON"]
    assert _top("pieza", 1, "unidad") == ["H87"]
    assert _top("hora", 1, "unidad") == ["HUR"]
    assert all(u["descripcion"] for u in svc.unidades_comunes())


def test_avisos_notas_y_detalle():
    d = svc.detalle("51191905")
    assert d["alertas"] and "medicamentos" in d["alertas"][0]["texto"]
    assert any("suplemento" in n["texto"].lower() for n in d["notas"])
    assert d["jerarquia"][0]["clave"] == "51191900" and any(h["clave"] == "51191903" for h in d["hermanas"])
    assert any("IVA 16%" in n["texto"] for n in svc.detalle("85121503")["notas"])
    assert svc.detalle("00000000") is None
    assert svc.buscar("pentermina", bloqueadas={"51191903"})[0]["bloqueada"] is True
    assert svc.buscar("renta local")[0]["tipo"] == "Servicio" and svc.buscar("vitaminas")[0]["tipo"] == "Producto"


def test_catalogos_sugeridos_usan_claves_reales():
    for p in PACKS:
        for desc, clave, unidad, imps, etiqueta in p["productos"]:
            assert svc.descripcion(clave), (p["id"], clave)
            assert svc.descripcion(unidad, "unidad"), (p["id"], unidad)
            assert desc and etiqueta


def test_api_claves_packs_bloqueo_e_importacion():
    with TestClient(app) as c:
        h, e = _preparar(c)
        # búsqueda y detalle por API (con y sin emisor)
        r = c.get("/api/claves/buscar?q=consulta medica", headers=h).json()
        assert r[0]["clave"] == "85121502"
        assert c.get("/api/claves/85121502", headers=h).status_code == 200
        assert c.get("/api/claves/99999999", headers=h).status_code == 404
        assert c.get("/api/claves/unidades", headers=h).json()[0]["clave"] == "E48"
        assert c.get("/api/catalogos/buscar/prod_serv?q=vitaminas").json()[0]["clave"] == "51191905"  # forma de siempre

        # catálogo sugerido: se agrega una vez y no duplica
        eid = e["id"]
        antes = len(c.get(f"/api/productos?emisor_id={eid}", headers=h).json())
        packs = c.get(f"/api/productos/packs?emisor_id={eid}", headers=h).json()
        assert {p["id"] for p in packs} >= {"contabilidad", "salud_sociedad", "arrendamiento"}
        r1 = c.post(f"/api/productos/packs/arrendamiento?emisor_id={eid}", headers=h).json()
        r2 = c.post(f"/api/productos/packs/arrendamiento?emisor_id={eid}", headers=h).json()
        assert r1["agregados"] + r1["ya_estaban"] == 4 and r2["agregados"] == 0 and r2["ya_estaban"] == 4
        assert len(c.get(f"/api/productos?emisor_id={eid}&limit=500", headers=h).json()) >= antes
        assert c.post("/api/productos/packs/no-existe?emisor_id=%d" % eid, headers=h).status_code == 404

        # importación: vista previa, clave sugerida que debe aceptarse, errores claros, y confirmación
        tabla = ("DESCRIPCION\tCLAVE\tUNIDAD\tPRECIO\tIMPUESTO\n"
                 "Consulta de nutrición IMPORTADA\t85151600\tE48\t$800.00\t16\n"
                 "Renta de bodega IMPORTADA\t\t\t5,000\texento\n"
                 "Cosa rara IMPORTADA\t12345678\tE48\t10\t16\n"
                 "Producto sin precio válido\t51191905\tH87\tabc\t16\n"
                 "Honorarios IMPORTADOS\t80101500\tE48\t1000\thonorarios\n")
        r = c.post("/api/productos/importar", headers=h, data={"emisor_id": eid, "texto": tabla}).json()
        est = {f["descripcion"]: f for f in r["filas"]}
        assert est["Consulta de nutrición IMPORTADA"]["estado"] == "nuevo"
        assert est["Renta de bodega IMPORTADA"]["clave_sugerida"] is True and est["Renta de bodega IMPORTADA"]["clave"] == "80131500"
        assert est["Cosa rara IMPORTADA"]["estado"] == "error" and "no existe" in est["Cosa rara IMPORTADA"]["errores"][0]
        assert est["Producto sin precio válido"]["estado"] == "error"
        assert len(est["Honorarios IMPORTADOS"]["impuestos"]) == 3  # IVA + ret. ISR + ret. IVA
        # sin aceptar las sugeridas, esa fila no entra
        r = c.post("/api/productos/importar", headers=h, data={"emisor_id": eid, "texto": tabla, "confirmar": "true"}).json()
        assert r["nuevos"] == 2 and r["omitidos"] == 3
        r = c.post("/api/productos/importar", headers=h, data={"emisor_id": eid, "texto": tabla, "confirmar": "true",
                                                              "aceptar_sugeridas": "true"}).json()
        assert r["nuevos"] == 1 and r["actualizados"] == 2  # la sugerida entra; las otras 2 ya existían y se actualizan
        assert c.post("/api/productos/importar", headers=h, data={"emisor_id": eid, "texto": "solo una linea"}).json()["error"]

        # más usadas: salen del catálogo del emisor
        fr = c.get(f"/api/claves/frecuentes?emisor_id={eid}", headers=h).json()
        assert fr and all("descripcion" in x and x["usos"] > 0 for x in fr)

        # clave bloqueada por emisor: cualquier factura con ella se rechaza ANTES de timbrar
        cfg = c.put(f"/api/emisores/{eid}/config-facturar", headers=h, json={"claves_bloqueadas": ["51191903", "xx", "123"]}).json()
        assert cfg["claves_bloqueadas"] == ["51191903"]  # sólo claves de 8 dígitos
        assert c.get("/api/claves/buscar?q=pentermina&emisor_id=%d" % eid, headers=h).json()[0]["bloqueada"] is True
        cli = _cliente(c, h, e)
        body = {"emisor_id": eid, "cliente_id": cli["id"], "metodo_pago": "PUE", "forma_pago": "03",
                "conceptos": [{"clave_prod_serv": "51191903", "clave_unidad": "H87", "descripcion": "x", "valor_unitario": "10",
                               "impuestos": [IVA16]}]}
        r = c.post("/api/facturas", headers=h, json=body)
        assert r.status_code == 422 and "bloqueada" in r.text
        # y una clave de la familia 51 que NO está bloqueada sólo avisa
        body["conceptos"][0]["clave_prod_serv"] = "51191905"
        pv = c.post("/api/facturas/preview", headers=h, json=body).json()
        assert not pv["errores"] and any("medicamentos" in a["mensaje"] for a in pv["avisos"])
        c.put(f"/api/emisores/{eid}/config-facturar", headers=h, json={"claves_bloqueadas": []})
