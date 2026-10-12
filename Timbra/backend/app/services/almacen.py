"""¿Lo que guardas sobrevive a un reinicio o a una actualización?

Timbra anota en su propia carpeta de datos cuándo se usó por primera vez y cuántas veces ha arrancado. Si esa carpeta
se borrara con cada actualización (un servidor sin disco permanente), la cuenta volvería a 1 y la fecha a hoy: así se
nota desde fuera, con /api/health, sin entrar a la cuenta de nadie."""
import json
import logging
import os
from datetime import datetime

from ..config import EN_WEB, settings

log = logging.getLogger("timbra.almacen")
_ESTADO: dict = {}


def _ruta() -> str:
    return os.path.join(settings.data_dir, "almacen.json")


def _bd() -> str | None:
    """Ruta del archivo SQLite (None si la base es otra cosa, p. ej. Postgres)."""
    if not settings.database_url.startswith("sqlite"):
        return None
    return os.path.abspath(settings.database_url.split("///", 1)[-1])


def permanente() -> bool | None:
    """En web: ¿la carpeta de datos es un disco montado (volumen) y la base vive dentro? En tu PC siempre lo es."""
    if not EN_WEB:
        return True
    datos = os.path.abspath(settings.data_dir)
    bd = _bd()
    dentro = bd is None or os.path.commonpath([datos, bd]) == datos
    return bool(os.path.ismount(datos) and dentro)


def registrar_arranque(version: str, primer_dato: datetime | None = None) -> dict:
    """Se llama una vez al arrancar. Nunca detiene el arranque. `primer_dato`: fecha del registro más viejo de la base,
    para que una instalación que ya tenía datos no parezca nueva la primera vez que se lleva esta cuenta."""
    global _ESTADO
    ahora = datetime.now().replace(microsecond=0).isoformat()
    d = {}
    try:
        with open(_ruta(), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        pass
    d = {"desde": d.get("desde") or (primer_dato.replace(microsecond=0).isoformat() if primer_dato else ahora), "arranques": int(d.get("arranques") or 0) + 1,
         "ultimo": ahora, "version": version}
    try:
        tmp = _ruta() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        os.replace(tmp, _ruta())
    except OSError as e:
        log.error("No se pudo escribir en la carpeta de datos (%s): %s", settings.data_dir, e)
        d["error"] = str(e)
    _ESTADO = d
    if permanente() is False:
        log.error("ESTE SERVIDOR NO TIENE DISCO PERMANENTE en %s: todo lo que se guarde (cuentas, clientes, facturas, CSD) "
                  "se pierde en la siguiente actualización. Monta un volumen en esa ruta.", os.path.abspath(settings.data_dir))
    return d


def estado() -> dict:
    """Lo que se puede decir en público: desde cuándo hay datos, cuántos arranques y si el disco es permanente."""
    return {"desde": _ESTADO.get("desde"), "arranques": _ESTADO.get("arranques"), "permanente": permanente()}
