"""El catálogo del SAT debe aguantar peticiones simultáneas (antes ≈16% de las consultas fallaban con «API misuse»)."""
from concurrent.futures import ThreadPoolExecutor

import app  # noqa: F401  (al importar app se asegura el catálogo para hilos)
from satcfdi.catalogs import catalog_code, select, select_all, trans


def _tarea(_):
    fallas = 0
    for k in range(250):
        try:
            assert select("C756_c_RegimenFiscal", "601")
            assert catalog_code("C756_c_FormaPago", "03")
            assert trans("Version")
            if k % 50 == 0:
                assert len(select_all("C756_c_FormaPago")) > 10
        except Exception:
            fallas += 1
    return fallas


def test_catalogo_sat_con_muchos_hilos():
    with ThreadPoolExecutor(12) as ex:
        assert sum(ex.map(_tarea, range(24))) == 0


def test_conexion_por_hilo_y_solo_lectura():
    import sqlite3

    import satcfdi.catalogs as cat
    cur = cat.conn.cursor()
    try:
        cur.execute("CREATE TABLE intruso (x)")
        raise AssertionError("el catálogo debe abrirse sólo para lectura")
    except sqlite3.OperationalError:
        pass
    finally:
        cur.close()
