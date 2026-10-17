"""Gastos deducibles: reglas del motor, aprendizaje de las decisiones, respeto a lo que decide la persona y aislamiento por cuenta."""
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConstanciaFiscal, XmlCfdi  # noqa: E402
from app.services import deducibles  # noqa: E402
from test_v2 import _preparar  # noqa: E402
from test_w1_cuentas import _emisor, _usuario  # noqa: E402

YO = "EKU9003173C9"


def _recibido(emisor_id, uuid, proveedor="AAA010101AAA", clave="80101506", uso="G03", forma="03", total=1000.0, receptor=YO, **kw):
    fila = {"Uso CFDI": uso, "Forma Pago": forma, "Claves ProdServ": clave, "Descripción": kw.pop("descripcion", "Servicio"), "Total": total}
    base = dict(emisor_id=emisor_id, uuid=uuid, tipo="Recibido", fecha="2026-10-05 10:00:00", clase="G", comprobante="Ingreso",
                rfc_emisor=proveedor, nombre_emisor=f"PROVEEDOR {proveedor}", rfc_receptor=receptor, total=total, iva=round(total / 1.16 * .16, 2),
                metodo="PUE", estatus="Vigente", origen="sat", filas=[fila], busca=f"{proveedor} {uuid}")
    base.update(kw)
    with SessionLocal() as db:
        db.query(XmlCfdi).filter(XmlCfdi.emisor_id == emisor_id, XmlCfdi.uuid == uuid, XmlCfdi.tipo == "Recibido").delete()
        db.add(XmlCfdi(**base))
        db.commit()


def _lista(c, h, e, **params):
    r = c.get("/api/deducibles", headers=h, params={"emisor_id": e["id"], "desde": "2026-10-01", "hasta": "2026-10-31", **params})
    assert r.status_code == 200, r.text
    return r.json()


def _fila(cuerpo, uuid):
    return next(f for f in cuerpo["filas"] if f["uuid"] == uuid)


def u(n):
    return f"AAAAAAAA-0000-4000-8000-{n:012d}"


@pytest.fixture()
def sin_69b(monkeypatch):
    monkeypatch.setattr(deducibles, "lista_69b", lambda: {"EEE010101EEE": "Definitivo", "PPP010101PPP": "Presunto"})


def test_reglas_del_motor(sin_69b):
    with TestClient(app) as c:
        h, e = _preparar(c)
        i = e["id"]
        _recibido(i, u(1))                                                    # servicio profesional común
        _recibido(i, u(2), estatus="Cancelado")                               # cancelado
        _recibido(i, u(3), uso="S01")                                         # sin efectos fiscales
        _recibido(i, u(4), forma="01", total=3000.0)                          # efectivo > $2,000
        _recibido(i, u(5), forma="01", total=1500.0)                          # efectivo chico: sí
        _recibido(i, u(6), uso="D01")                                         # deducción personal
        _recibido(i, u(7), receptor="XAXX010101000")                          # a nombre de otro
        _recibido(i, u(8), clave="90101501", total=500.0)                     # restaurante
        _recibido(i, u(9), clave="51191905")                                  # medicamentos: puede ser personal
        _recibido(i, u(10), clase="N")                                        # nómina que recibí
        _recibido(i, u(11), clase="P")                                        # complemento de pago
        _recibido(i, u(12), forma="01", clave="15101505", total=300.0)        # gasolina en efectivo
        _recibido(i, u(13), proveedor="EEE010101EEE")                         # 69-B definitivo
        _recibido(i, u(14), proveedor="PPP010101PPP")                         # 69-B presunto
        _recibido(i, u(15), filas=[], origen="aviso")                         # sólo se sabe que existe
        _recibido(i, u(16), clave="25101503")                                 # automóvil: con tope
        r = _lista(c, h, e)
        s = {n: _fila(r, u(n))["sugerencia"] for n in range(1, 17)}
        assert s[1] == "deducible" and s[5] == "deducible"
        assert {s[n] for n in (2, 3, 4, 7, 10, 11, 12, 13)} == {"no_deducible"}
        assert s[6] == "personal" and s[9] == "revisar"
        assert s[8] == "deducible" and _fila(r, u(8))["porcentaje_sug"] == 8.5  # restaurante: sólo 8.5%
        assert s[14] == "revisar" and s[15] == "revisar" and s[16] == "revisar"
        # cada sugerencia explica por qué
        assert all(_fila(r, u(n))["motivos"] for n in (1, 2, 3, 4, 6, 8, 9, 12, 13))
        assert any(m["regla"] == "efectivo" for m in _fila(r, u(4))["motivos"])
        # totales por grupo y filtro por grupo
        assert r["totales"]["no_deducible"]["n"] >= 8 and r["totales"]["personal"]["n"] == 1
        sol = _lista(c, h, e, grupo="personal")
        assert [f["uuid"] for f in sol["filas"]] == [u(6)]


def test_la_persona_decide_y_el_sistema_aprende(sin_69b):
    with TestClient(app) as c:
        h, e = _preparar(c)
        i = e["id"]
        # medicamentos de una farmacia: al principio se pregunta (revisar)
        _recibido(i, u(21), proveedor="FAR010101FAR", clave="51191905")
        _recibido(i, u(22), proveedor="FAR010101FAR", clave="51191905")
        assert _fila(_lista(c, h, e), u(21))["sugerencia"] == "revisar"

        # la persona lo marca deducible: su decisión manda y se aprende al proveedor
        r = c.post("/api/deducibles/decidir", headers=h, json={"emisor_id": i, "uuids": [u(21)], "decision": "deducible", "nota": "botiquín de la oficina"})
        assert r.status_code == 200 and r.json()["decididos"] == 1
        f = _fila(_lista(c, h, e), u(21))
        assert f["decision"] == "deducible" and f["final"] == "deducible" and f["nota"] == "botiquín de la oficina"
        f2 = _fila(_lista(c, h, e), u(22))
        assert f2["sugerencia"] == "deducible" and any(m["regla"] == "aprendido_proveedor" for m in f2["motivos"]) and f2["decision"] is None

        # recalcular (volver a pedir la lista) jamás toca la decisión
        assert _fila(_lista(c, h, e), u(21))["decision"] == "deducible"

        # aprendizaje por tipo de producto: dos decisiones iguales en proveedores distintos enseñan la clave
        _recibido(i, u(23), proveedor="BBB010101BBB", clave="53101902")
        _recibido(i, u(24), proveedor="CCC010101CCC", clave="53101902")
        _recibido(i, u(25), proveedor="DDD010101DDD", clave="53101902")
        assert _fila(_lista(c, h, e), u(25))["sugerencia"] == "revisar"
        c.post("/api/deducibles/decidir", headers=h, json={"emisor_id": i, "uuids": [u(23), u(24)], "decision": "no_deducible"})
        f5 = _fila(_lista(c, h, e), u(25))
        assert f5["sugerencia"] == "no_deducible" and any(m["regla"] == "aprendido_clave" for m in f5["motivos"])

        # lo aprendido se ve y se puede olvidar
        ap = c.get("/api/deducibles/aprendido", headers=h, params={"emisor_id": i}).json()
        assert any(p["tipo"] == "rfc" and p["valor"] == "FAR010101FAR" and p["si"] == 1 for p in ap)
        pid = next(p["id"] for p in ap if p["tipo"] == "clave" and p["valor"] == "5310")
        assert c.delete(f"/api/deducibles/aprendido/{pid}", headers=h).status_code == 200
        assert _fila(_lista(c, h, e), u(25))["sugerencia"] == "revisar"

        # cambiar de opinión corrige lo aprendido (no cuenta doble)
        c.post("/api/deducibles/decidir", headers=h, json={"emisor_id": i, "uuids": [u(21)], "decision": "no_deducible"})
        ap = c.get("/api/deducibles/aprendido", headers=h, params={"emisor_id": i}).json()
        far = next(p for p in ap if p["valor"] == "FAR010101FAR")
        assert (far["si"], far["no"]) == (0, 1)
        # volver a la sugerencia quita la decisión y lo aprendido
        assert c.post("/api/deducibles/deshacer", headers=h, json={"emisor_id": i, "uuids": [u(21)]}).json()["deshechos"] == 1
        assert _fila(_lista(c, h, e), u(21))["decision"] is None
        assert not any(p["valor"] == "FAR010101FAR" for p in c.get("/api/deducibles/aprendido", headers=h, params={"emisor_id": i}).json())

        # sin «aprender» la decisión vale sólo para ese CFDI
        c.post("/api/deducibles/decidir", headers=h, json={"emisor_id": i, "uuids": [u(21)], "decision": "deducible", "aprender": False})
        assert _fila(_lista(c, h, e), u(22))["sugerencia"] == "revisar"

        # lo que no es un gasto recibido no se puede decidir
        assert c.post("/api/deducibles/decidir", headers=h, json={"emisor_id": i, "uuids": ["NOEXISTE"], "decision": "deducible"}).json()["decididos"] == 0
        assert c.post("/api/deducibles/decidir", headers=h, json={"emisor_id": i, "uuids": [u(21)], "decision": "tal vez"}).status_code == 422


def test_la_actividad_y_el_regimen_de_la_constancia(sin_69b):
    with TestClient(app) as c:
        h, e = _preparar(c)
        i = e["id"]
        # una compra de ropa es dudosa; si la actividad de la constancia es comercio de ropa, ya se relaciona
        _recibido(i, u(31), clave="53101902", descripcion="Camisas de algodón para vender")
        assert _fila(_lista(c, h, e), u(31))["sugerencia"] == "revisar"
        with SessionLocal() as db:
            db.add(ConstanciaFiscal(emisor_id=i, rfc=YO, nombre="X", cp="42501", regimenes=[{"clave": "601", "nombre": "General", "desde": "2019-01-01", "hasta": None}],
                                    actividades=[{"orden": 1, "nombre": "Comercio al por menor de camisas", "porcentaje": 100, "desde": "2019-01-01", "hasta": None}]))
            db.commit()
        f = _fila(_lista(c, h, e), u(31))
        assert f["sugerencia"] == "deducible" and any(m["regla"] == "actividad" for m in f["motivos"])
        assert _lista(c, h, e)["constancia"]["rfc"] == YO

        # un régimen sin actividad de la que se resten gastos (sólo sueldos): ningún gasto del negocio es deducible
        with SessionLocal() as db:
            db.query(ConstanciaFiscal).filter(ConstanciaFiscal.emisor_id == i).delete()
            db.add(ConstanciaFiscal(emisor_id=i, rfc=YO, nombre="X", cp="42501", regimenes=[{"clave": "605", "nombre": "Sueldos", "desde": "2018-01-01", "hasta": None}], actividades=[]))
            db.commit()
        r = _lista(c, h, e)
        assert _fila(r, u(1))["sugerencia"] == "no_deducible" and r["permitido"] is False
        assert _fila(r, u(1))["motivos"][0]["regla"] == "regimen"
        # …pero las deducciones personales siguen siendo personales
        _recibido(i, u(32), uso="D02")
        assert _fila(_lista(c, h, e), u(32))["sugerencia"] == "personal"

        # RESICO persona física: el gasto sirve para acreditar IVA, no para restar ISR
        with SessionLocal() as db:
            db.query(ConstanciaFiscal).filter(ConstanciaFiscal.emisor_id == i).delete()
            db.commit()
        e2 = None
        otra = _usuario(c, h, "resico.x2@ejemplo.com", "resicox2")
        e2 = _emisor(c, otra, "XIAJ800101ABC", "JUAN XENON AGUILAR")
        c.put(f"/api/emisores/{e2['id']}", headers=otra, json={"rfc": "XIAJ800101ABC", "nombre": "JUAN XENON AGUILAR", "regimen_fiscal": "626", "lugar_expedicion": "42501"})
        _recibido(e2["id"], u(41), receptor="XIAJ800101ABC")
        r2 = c.get("/api/deducibles", headers=otra, params={"emisor_id": e2["id"], "desde": "2026-10-01", "hasta": "2026-10-31"}).json()
        f41 = _fila(r2, u(41))
        assert r2["solo_iva"] is True and f41["sugerencia"] == "deducible" and f41["efecto"] == "solo_iva"
        assert any(m["regla"] == "resico" for m in f41["motivos"])

        # aislamiento: la otra cuenta no ve los gastos de ésta, ni puede decidir sobre ellos
        assert u(1) not in {f["uuid"] for f in r2["filas"]}
        assert c.get("/api/deducibles", headers=otra, params={"emisor_id": i}).status_code == 404
        assert c.post("/api/deducibles/decidir", headers=otra, json={"emisor_id": i, "uuids": [u(1)], "decision": "deducible"}).status_code == 404
