"""Descarga del SAT: se piden todos los meses de una vez y se bajan conforme el SAT los tiene listos. El SAT se simula."""
import base64
import io
import logging
import zipfile
from datetime import datetime

from app.xmlsat.config import Opciones, Perfil
from app.xmlsat.flujo import Descargador


def _zip_vacio() -> str:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w"):
        pass
    return base64.b64encode(b.getvalue()).decode()


class SatLento:
    """Cada solicitud tarda `rondas[mes]` verificaciones en estar lista; None = nunca está lista."""

    def __init__(self, rondas):
        self.rondas = rondas
        self.vistas = {}
        self.pedidas = []

    def token(self):
        return "t"

    def solicitar(self, rfc, tipo, desde, hasta):
        self.pedidas.append((tipo, desde.month))
        return {"cod_estatus": "5000", "id_solicitud": f"{tipo}-{desde.month}", "mensaje": "ok"}

    def verificar(self, rfc, id_sol):
        self.vistas[id_sol] = self.vistas.get(id_sol, 0) + 1
        mes = int(id_sol.split("-")[1])
        falta = self.rondas.get(mes)
        if falta is not None and self.vistas[id_sol] >= falta:
            return {"estado_solicitud": "3", "cod_estatus": "5000", "numero_cfdis": 0, "paquetes": [f"P{id_sol}"]}
        return {"estado_solicitud": "2", "cod_estatus": "5000", "numero_cfdis": 0, "paquetes": []}

    def descargar_paquete(self, rfc, idp):
        return {"cod_estatus": "5000", "paquete_b64": _zip_vacio()}


def _descargador(tmp_path, sat, dormidas):
    perfil = Perfil(rfc="AAA010101AAA", nombre="PRUEBA", carpeta_estado=str(tmp_path), id="1")
    op = Opciones(carpeta_salida=str(tmp_path / "xml"), poll_intervalo_seg=30, poll_max_intentos=40)
    return Descargador(perfil, op, sat, logging.getLogger("prueba"), dormir=dormidas.append, clasificar=lambda r: None)


def test_pide_todo_primero_y_baja_conforme_estan_listos(tmp_path):
    sat = SatLento({1: 3, 2: 1, 3: 2})
    dormidas = []
    reloj = iter(range(0, 10_000, 10))
    r = _descargador(tmp_path, sat, dormidas).ejecutar_paralelo(datetime(2026, 1, 1), datetime(2026, 3, 31), ["emitidos"],
                                                                 limite_seg=9_999, reloj=lambda: next(reloj))
    assert [m for _t, m in sat.pedidas] == [1, 2, 3]            # los tres meses se pidieron antes de esperar a ninguno
    assert r.paquetes == 3 and not r.pendientes and not r.errores
    assert len(dormidas) == 2                                      # 3 rondas = 2 esperas (no 3 + 1 + 2 esperas por separado)
    # otra corrida: todo está completado, no se vuelve a pedir nada
    sat2 = SatLento({})
    r2 = _descargador(tmp_path, sat2, []).ejecutar_paralelo(datetime(2026, 1, 1), datetime(2026, 3, 31), ["emitidos"], limite_seg=60)
    assert sat2.pedidas == [] and r2.paquetes == 0


def test_si_el_sat_tarda_demasiado_quedan_pendientes_y_se_retoman(tmp_path):
    sat = SatLento({1: 1, 2: None})                                # febrero nunca está listo en esta corrida
    reloj = iter(range(0, 10_000, 1000))
    r = _descargador(tmp_path, sat, []).ejecutar_paralelo(datetime(2026, 1, 1), datetime(2026, 2, 28), ["emitidos"],
                                                          limite_seg=2_500, reloj=lambda: next(reloj))
    assert r.paquetes == 1 and r.pendientes == ["emitidos 2026-02"] and not r.errores
    # más tarde: febrero ya está listo y NO se vuelve a pedir (se retoma la misma solicitud)
    sat.rondas[2] = 1
    sat.vistas.clear()
    antes = len(sat.pedidas)
    r2 = _descargador(tmp_path, sat, []).ejecutar_paralelo(datetime(2026, 1, 1), datetime(2026, 2, 28), ["emitidos"], limite_seg=60)
    assert len(sat.pedidas) == antes and r2.paquetes == 1 and not r2.pendientes
