"""Timbra. Al importar `app` se hace seguro para varios hilos el catálogo del SAT de satcfdi.

satcfdi abre UNA sola conexión SQLite (`satcfdi.catalogs.conn`, check_same_thread=False) y la comparte entre todos los hilos;
SQLite no lo soporta y, con peticiones simultáneas, falla con «bad parameter or other API misuse» (≈16% de las consultas
en una prueba de 12 hilos). Aquí se reemplaza por un objeto que entrega un cursor de una conexión PROPIA (sólo lectura)
por hilo. satcfdi busca `conn` en su módulo en cada llamada, así que el cambio cubre también a sus funciones internas.
"""
import sqlite3
import threading
from pathlib import Path


def _asegurar_catalogo_sat() -> None:
    import satcfdi.catalogs as cat

    class _ConexionPorHilo:
        def __init__(self, ruta: str):
            self._uri = Path(ruta).resolve().as_uri() + "?mode=ro"
            self._ruta = ruta
            self._local = threading.local()

        def cursor(self):
            con = getattr(self._local, "con", None)
            if con is None:
                try:
                    con = sqlite3.connect(self._uri, uri=True)
                except sqlite3.OperationalError:  # ubicación sin permiso de lectura por URI: conexión normal
                    con = sqlite3.connect(self._ruta)
                self._local.con = con
            return con.cursor()

    if not isinstance(cat.conn, _ConexionPorHilo):
        cat.conn = _ConexionPorHilo(cat.db_file)


_asegurar_catalogo_sat()
