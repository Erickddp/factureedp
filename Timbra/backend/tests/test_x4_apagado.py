"""Un despliegue no debe cortar una descarga del SAT: al apagar se espera a que termine (y /api/health dice si hay algo en curso)."""
import os
import time

os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.services import xml_trabajos  # noqa: E402


def test_el_apagado_espera_a_que_termine_la_descarga(monkeypatch):
    vivos = {"xml": 1, "lotes": 0}
    monkeypatch.setattr(main, "_trabajos_vivos", lambda: (vivos["xml"], vivos["lotes"]))
    monkeypatch.setattr(time, "sleep", lambda s: time.perf_counter())  # sin esperar de verdad entre vueltas
    llamadas = []
    original = main._trabajos_vivos

    def contar():
        llamadas.append(1)
        if len(llamadas) == 4:
            vivos["xml"] = 0  # la descarga termina justo en la cuarta revisión
        return original()
    monkeypatch.setattr(main, "_trabajos_vivos", contar)
    t0 = time.time()
    main._esperar_trabajos(60)
    assert len(llamadas) == 4 and time.time() - t0 < 5  # revisó hasta que terminó, y no esperó los 60 s


def test_el_apagado_no_espera_para_siempre(monkeypatch):
    monkeypatch.setattr(main, "_trabajos_vivos", lambda: (1, 0))
    reloj = iter(range(0, 1000, 10))
    monkeypatch.setattr(time, "time", lambda: next(reloj))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    main._esperar_trabajos(25)  # se acaba el tiempo con la descarga viva: sale (queda «interrumpido» al volver a arrancar)


def test_health_dice_si_hay_trabajos_en_curso():
    with TestClient(main.app) as c:
        assert c.get("/api/health").json()["descargas"] == 0
        xml_trabajos._vivos[999] = xml_trabajos.Trabajo(999)
        try:
            h = c.get("/api/health").json()
            assert h["descargas"] == 1 and h["lotes"] == 0
        finally:
            xml_trabajos._vivos.pop(999, None)
