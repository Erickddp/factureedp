"""Trabajos en segundo plano del módulo de XML (descarga del SAT, armar un ZIP): corren en un hilo y dejan su avance en
la tabla `xml_trabajos`, así la pantalla sólo pregunta cómo van y se puede cerrar el navegador sin perder nada."""
import logging
import threading
import time
from datetime import datetime
from typing import Callable

from ..db import SessionLocal
from ..models import XmlTrabajo
from . import xml_indice

log = logging.getLogger("timbra.xml")
_vivos: dict[int, "Trabajo"] = {}


class Trabajo:
    def __init__(self, tid: int):
        self.id = tid
        self.cancelar = threading.Event()

    def _editar(self, **campos) -> None:
        with SessionLocal() as db:
            t = db.get(XmlTrabajo, self.id)
            if t is not None:
                for k, v in campos.items():
                    setattr(t, k, v)
                db.commit()

    def anotar(self, texto: str) -> None:
        with SessionLocal() as db:
            t = db.get(XmlTrabajo, self.id)
            if t is not None:
                t.registro = ((t.registro or "") + f"{datetime.now():%H:%M:%S}  {texto}\n")[-60000:]
                db.commit()

    def avance(self, hecho: int, total: int, mensaje: str = "") -> None:
        self._editar(avance=hecho, total=total, mensaje=mensaje[:300])

    def bitacora(self) -> logging.Logger:
        """Un logger que escribe en el registro del trabajo (el flujo del SAT habla con un logger)."""
        t = self

        class _A(logging.Handler):
            def emit(self, record):
                try:
                    t.anotar(record.getMessage())
                except Exception:  # noqa: BLE001 — el registro nunca debe tumbar la descarga
                    pass

        lg = logging.getLogger(f"timbra.xml.trabajo.{self.id}")
        lg.setLevel(logging.INFO)
        lg.propagate = False
        lg.handlers = [_A()]
        return lg


def crear(db, usuario_id: int | None, emisor_id: int, clase: str, params: dict) -> int:
    t = XmlTrabajo(usuario_id=usuario_id, emisor_id=emisor_id, clase=clase, params=params, resumen={}, registro="")
    db.add(t)
    db.commit()
    return t.id


def lanzar(tid: int, fn: Callable[[Trabajo], dict], al_terminar: Callable[[], None] | None = None) -> None:
    """Corre fn(trabajo) en un hilo. fn regresa el resumen; si trae "errores" o truena, el trabajo queda en error."""
    t = Trabajo(tid)
    _vivos[tid] = t

    def correr():
        estado, resumen, archivo = "listo", {}, ""
        try:
            resumen = fn(t) or {}
            archivo = resumen.pop("archivo", "")
            if t.cancelar.is_set():
                estado = "cancelado"
            elif resumen.get("errores"):
                estado = "error"
        except Exception as e:  # noqa: BLE001
            log.exception("Trabajo de XML %s falló", tid)
            estado, resumen = "error", {"errores": [str(e)]}
        finally:
            _vivos.pop(tid, None)
            try:
                if al_terminar:
                    al_terminar()
            finally:
                t._editar(estado=estado, resumen=resumen, archivo=archivo, terminado=datetime.now())

    threading.Thread(target=correr, name=f"xml-trabajo-{tid}", daemon=True).start()


def cancelar(tid: int) -> bool:
    t = _vivos.get(tid)
    if t:
        t.cancelar.set()
    return bool(t)


def vivo(tid: int) -> bool:
    return tid in _vivos


def recuperar_interrumpidos() -> None:
    """Al arrancar: lo que estaba corriendo cuando se apagó el servidor queda marcado, y se limpia lo temporal viejo."""
    with SessionLocal() as db:
        for t in db.query(XmlTrabajo).filter(XmlTrabajo.estado == "curso"):
            t.estado, t.terminado = "interrumpido", datetime.now()
            t.mensaje = "El servidor se reinició. Pon tu e.firma y vuelve a descargar el mismo periodo: se retoma sin pedirle de nuevo al SAT."
        db.commit()
    limpiar_temporales(0)


def limpiar_temporales(horas: float = 24) -> None:
    limite = time.time() - horas * 3600
    for f in xml_indice.carpeta_tmp().glob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass


def publico(t: XmlTrabajo, con_registro: bool = False) -> dict:
    d = {"id": t.id, "emisor_id": t.emisor_id, "clase": t.clase, "estado": t.estado, "avance": t.avance, "total": t.total,
         "mensaje": t.mensaje, "creado": t.creado, "terminado": t.terminado, "params": t.params or {}, "resumen": t.resumen or {},
         "descargable": bool(t.archivo)}
    if con_registro:
        d["registro"] = t.registro or ""
    return d
