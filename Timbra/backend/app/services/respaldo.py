"""Respaldo en disco de cada XML timbrado, ANTES de tocar la base de datos.
Si la BD truena después del timbrado, el UUID no se pierde: /facturas/recuperar lo reimporta."""
import os
from datetime import datetime

from ..config import settings


def ruta(rfc: str, uuid: str, fecha: datetime | None = None) -> str:
    f = fecha or datetime.now()
    d = os.path.join(settings.data_dir, "respaldo_xml", rfc.upper(), f"{f:%Y-%m}")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{uuid.upper()}.xml")


def guardar(rfc: str, uuid: str, xml: bytes) -> str:
    p = ruta(rfc, uuid)
    with open(p, "wb") as fh:
        fh.write(xml)
    return p


def todos():
    base = os.path.join(settings.data_dir, "respaldo_xml")
    for root, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith(".xml"):
                yield os.path.join(root, f)
