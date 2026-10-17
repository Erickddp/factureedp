"""Constancia de Situación Fiscal: lector del PDF, alta rápida del emisor, comparación (nunca pisa en silencio) y candados."""
import os

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import constancia as csf  # noqa: E402
from _csf_texto import CSF_FISICA, CSF_MORAL  # noqa: E402
from test_v2 import _preparar  # noqa: E402

PDF = b"%PDF-1.4 falso"


@pytest.fixture()
def texto(monkeypatch):
    caja = {"t": CSF_FISICA}
    monkeypatch.setattr(csf, "texto_pdf", lambda datos: caja["t"])
    return caja


def test_lee_una_constancia_de_persona_fisica(texto):
    c = csf.leer(PDF)
    assert (c["rfc"], c["persona"], c["nombre"], c["cp"], c["id_cif"], c["emitida_el"]) == (
        "XIAJ800101ABC", "fisica", "JUAN XENON AGUILAR", "03100", "12345678901", "2026-03-16")
    assert c["curp"] == "XIAJ800101HDFXGN09" and c["estatus"] == "ACTIVO"
    assert [(r["clave"], r["desde"], r["hasta"]) for r in c["regimenes"]] == [("605", "2018-01-01", None), ("626", "2026-03-16", None)]
    assert [(a["orden"], a["porcentaje"]) for a in c["actividades"]] == [(1, 80), (2, 10), (3, 5), (4, 5)]
    assert c["actividades"][0]["nombre"] == "Asalariado" and "contabilidad" in c["actividades"][1]["nombre"]
    assert c["domicilio"]["colonia"] == "DEL VALLE" and c["domicilio"]["municipio"] == "BENITO JUAREZ"  # el renglón partido en dos se une
    assert "Pago definitivo mensual de IVA" in c["obligaciones"]


def test_sugiere_el_regimen_que_sirve_para_facturar(texto):
    s = csf.emisor_sugerido(csf.leer(PDF))
    assert s["regimen_fiscal"] == "626"  # 605 (sueldos) no factura
    assert [(r["clave"], r["emite"]) for r in s["regimenes"]] == [("605", False), ("626", True)]
    assert s["lugar_expedicion"] == "03100" and s["nombre"] == "JUAN XENON AGUILAR"
    assert any("más de un régimen" in a for a in s["avisos"])


def test_persona_moral_nombre_sin_regimen_de_capital(texto):
    texto["t"] = CSF_MORAL
    c = csf.leer(PDF)
    assert c["persona"] == "moral" and c["curp"] is None and c["regimenes"][0]["clave"] == "601"
    assert csf.emisor_sugerido(c)["nombre"] == "XENON INDUSTRIAL ARTICLES"  # sin «SA DE CV»


def test_rechaza_lo_que_no_es_una_constancia(monkeypatch):
    with pytest.raises(csf.ConstanciaError, match="no es un PDF"):
        csf.leer(b"no soy pdf")
    monkeypatch.setattr(csf, "texto_pdf", lambda d: "Esto es otro documento cualquiera " * 10)
    with pytest.raises(csf.ConstanciaError, match="no parece una Constancia"):
        csf.leer(PDF)
    # un PDF real sin texto (como una foto) se pide de nuevo; no se adivina
    from pypdf import PdfWriter
    import io as _io
    w, buf = PdfWriter(), _io.BytesIO()
    w.add_blank_page(200, 200)
    w.write(buf)
    monkeypatch.undo()
    with pytest.raises(csf.ConstanciaError, match="no trae texto"):
        csf.leer(buf.getvalue())


def test_api_alta_rapida_y_candados(texto):
    with TestClient(app) as c:
        h, e = _preparar(c)
        # alta rápida: lee y sugiere, sin guardar nada
        r = c.post("/api/constancia/leer", headers=h, files={"archivo": ("csf.pdf", PDF, "application/pdf")})
        assert r.status_code == 200, r.text
        assert r.json()["emisor"]["regimen_fiscal"] == "626" and r.json()["emisor"]["rfc"] == "XIAJ800101ABC"
        assert c.get("/api/constancia/%d" % e["id"], headers=h).json()["constancia"] is None

        # no es la constancia de este emisor (EKU9003173C9): se rechaza con el motivo
        r = c.post(f"/api/constancia/{e['id']}", headers=h, files={"archivo": ("csf.pdf", PDF, "application/pdf")})
        assert r.status_code == 422 and "XIAJ800101ABC" in r.text and "EKU9003173C9" in r.text

        # la constancia sí es de este emisor (moral): se guarda y se compara; el emisor NO cambia solo
        texto["t"] = CSF_MORAL.replace("XIA190128J61", "EKU9003173C9").replace("03100", "42501").replace(
            "XENON INDUSTRIAL ARTICLES SA DE CV", "ESCUELA KEMPER URGATE SA DE CV")
        r = c.post(f"/api/constancia/{e['id']}", headers=h, files={"archivo": ("csf.pdf", PDF, "application/pdf")})
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["constancia"]["rfc"] == "EKU9003173C9" and cuerpo["constancia"]["regimenes"][0]["clave"] == "601"
        assert c.get("/api/constancia/%d" % e["id"], headers=h).json()["constancia"]["id_cif"] == "12345678901"
        emisor = [x for x in c.get("/api/emisores", headers=h).json() if x["id"] == e["id"]][0]
        assert emisor["regimen_fiscal"] == e["regimen_fiscal"] and emisor["lugar_expedicion"] == e["lugar_expedicion"]

        # aplicar sólo lo que se elige, y sólo valores que la constancia respalda
        assert c.post(f"/api/constancia/{e['id']}/aplicar", headers=h, json={"regimen_fiscal": "612"}).status_code == 422
        assert c.post(f"/api/constancia/{e['id']}/aplicar", headers=h, json={"lugar_expedicion": "99999"}).status_code == 422
        assert c.post(f"/api/constancia/{e['id']}/aplicar", headers=h, json={"lugar_expedicion": "42501"}).status_code == 200
