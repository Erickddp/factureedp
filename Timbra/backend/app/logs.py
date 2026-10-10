"""Registro de todo lo que pasa: memoria (para la consola en vivo) + archivo rotativo.

Uso en servicios:
    from ..logs import log, paso
    log.info("Timbrando %s", folio, extra={"datos": {...}})
    with paso("Timbrar con Finkok", pac="finkok"):
        ...   # registra inicio, duración y error con traza completa
"""
import contextvars
import itertools
import logging
import logging.handlers
import os
import threading
import time
import traceback
from collections import deque
from contextlib import contextmanager

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
log = logging.getLogger("timbra")


class _ReqFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "req"):
            record.req = request_id.get()
        return True


class Buffer(logging.Handler):
    """Últimos N eventos en memoria, consultables por id incremental."""

    def __init__(self, n: int = 3000):
        super().__init__()
        self.buf: deque = deque(maxlen=n)
        self.seq = itertools.count(1)
        self._mu = threading.Lock()

    def emit(self, r: logging.LogRecord):
        try:
            item = {
                "id": next(self.seq),
                "ts": r.created,
                "nivel": r.levelname,
                "origen": r.name,
                "mensaje": r.getMessage(),
                "req": getattr(r, "req", "-"),
                "datos": getattr(r, "datos", None),
                "traza": "".join(traceback.format_exception(*r.exc_info)) if r.exc_info else None,
            }
            with self._mu:
                self.buf.append(item)
        except Exception:  # el log nunca debe tumbar la app
            pass

    def consultar(self, despues: int = 0, nivel: str | None = None, q: str | None = None,
                  req: str | None = None, limite: int = 500) -> list[dict]:
        niveles = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        minimo = niveles.get((nivel or "DEBUG").upper(), 10)
        q = (q or "").lower()
        with self._mu:
            items = [i for i in self.buf if i["id"] > despues]
        out = []
        for i in items:
            if niveles.get(i["nivel"], 20) < minimo:
                continue
            if req and i["req"] != req:
                continue
            if q and q not in (i["mensaje"] + " " + (i["origen"] or "") + " " + (i["traza"] or "")).lower():
                continue
            out.append(i)
        return out[-limite:]

    def ultimo_id(self) -> int:
        with self._mu:
            return self.buf[-1]["id"] if self.buf else 0


BUFFER = Buffer()
ARCHIVO: str | None = None


def configurar(data_dir: str, debug: bool = True):
    global ARCHIVO
    root = logging.getLogger()
    if getattr(root, "_timbra", False):  # idempotente (recargas / pruebas)
        return
    root._timbra = True
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(req)s] %(name)s: %(message)s")
    filtro = _ReqFilter()

    os.makedirs(os.path.join(data_dir, "logs"), exist_ok=True)
    ARCHIVO = os.path.join(data_dir, "logs", "timbra.log")
    fh = logging.handlers.RotatingFileHandler(ARCHIVO, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(filtro)
    fh.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.addFilter(filtro)
    ch.setLevel(logging.INFO)

    BUFFER.addFilter(filtro)
    BUFFER.setLevel(logging.DEBUG if debug else logging.INFO)

    for h in (fh, ch, BUFFER):
        root.addHandler(h)

    # Ruido de librerías: sólo avisos y errores
    for ruidoso in ("uvicorn.access", "httpx", "httpcore", "zeep", "urllib3", "sqlalchemy", "multipart",
                    "alembic.runtime.migration", "fontTools", "weasyprint", "asyncio"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


@contextmanager
def paso(nombre: str, **datos):
    """Registra inicio, fin con duración y error con traza de un paso del proceso."""
    t0 = time.perf_counter()
    log.debug("→ %s", nombre, extra={"datos": datos or None})
    try:
        yield
    except Exception as e:
        ms = round((time.perf_counter() - t0) * 1000)
        log.error("✗ %s falló en %s ms: %s: %s", nombre, ms, type(e).__name__, e,
                  exc_info=True, extra={"datos": datos or None})
        raise
    ms = round((time.perf_counter() - t0) * 1000)
    log.info("✓ %s (%s ms)", nombre, ms, extra={"datos": datos or None})
