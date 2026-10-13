"""Tareas en segundo plano mientras Timbra está abierto (cada 10 minutos):
recurrentes automáticas, solicitudes de descarga SAT, recordatorios de cobranza (lunes) y respaldo diario."""
import asyncio
import os
import zipfile
from datetime import datetime
from pathlib import Path

from ..config import EN_WEB, settings
from ..db import SessionLocal
from ..logs import log

CADA = 600
_ultimo: dict[str, str] = {}


def respaldo_diario(destino: Path | None = None, conservar: int = 14) -> Path | None:
    """ZIP de datos (BD + XML) y .env. Sin .env no se descifran los CSD: van juntos."""
    hoy = datetime.now().strftime("%Y%m%d")
    datos = Path(settings.data_dir).resolve()
    # En web sólo el volumen de datos sobrevive a una actualización: los respaldos van DENTRO de él
    destino = destino or (datos / "Respaldos" if EN_WEB else datos.parent / "Respaldos")
    destino.mkdir(parents=True, exist_ok=True)
    zip_path = destino / f"timbra_{hoy}.zip"
    if zip_path.exists():
        return None
    armar_respaldo(zip_path)
    viejos = sorted(destino.glob("timbra_*.zip"))[:-(7 if EN_WEB else conservar)]
    for v in viejos:
        v.unlink(missing_ok=True)
    log.info("Respaldo diario: %s", zip_path)
    return zip_path


def armar_respaldo(zip_path: Path) -> Path:
    """Escribe en `zip_path` todo lo que hace falta para levantar Timbra en otra máquina: base, XML, correo y .env."""
    datos = Path(settings.data_dir).resolve()
    copia = _copia_bd()  # copia consistente aunque la app esté escribiendo (modo WAL)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(datos):
            dirs[:] = [d for d in dirs if d not in ("logs", "Respaldos", "tmp")]  # ni registros, ni temporales, ni respaldos dentro de respaldos
            for f in files:
                p = Path(root) / f
                if copia and p.name.startswith(copia[1].name):  # .db, -wal, -shm: va la copia
                    continue
                z.write(p, Path("datos") / p.relative_to(datos))
        if copia:
            z.write(copia[0], Path("datos") / copia[1].relative_to(datos))
            copia[0].unlink(missing_ok=True)
        env = Path(".env")
        if env.exists():
            z.write(env, ".env")
    return zip_path


def _copia_bd() -> tuple[Path, Path] | None:
    """(copia temporal, archivo original) usando la API de respaldo de SQLite."""
    import sqlite3
    import tempfile

    url = settings.database_url
    if not url.startswith("sqlite:///"):
        return None
    original = Path(url.removeprefix("sqlite:///")).resolve()
    if not original.exists():
        return None
    fd, nombre = tempfile.mkstemp(suffix=".db")
    os.close(fd)  # Windows: el archivo no se puede borrar si queda abierto
    src, dst = sqlite3.connect(original), sqlite3.connect(nombre)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return Path(nombre), original


def _una_vez_al_dia(nombre: str) -> bool:
    hoy = datetime.now().strftime("%Y-%m-%d")
    if _ultimo.get(nombre) == hoy:
        return False
    _ultimo[nombre] = hoy
    return True


def tick():
    from . import cobranza, recurrentes

    with SessionLocal() as db:
        for nombre, fn in (("recurrentes", recurrentes.correr_automaticas),):
            try:
                n = fn(db)
                if n:
                    log.info("Programador · %s: %s", nombre, n)
            except Exception:
                db.rollback()
                log.exception("Programador · %s falló", nombre)
        if _una_vez_al_dia("cobranza"):
            try:
                cobranza.recordatorios_automaticos(db)
            except Exception:
                db.rollback()
                log.exception("Programador · cobranza falló")
    if _una_vez_al_dia("respaldo"):
        try:
            respaldo_diario()
        except Exception:
            log.exception("Respaldo diario falló")


async def correr():
    await asyncio.sleep(45)  # deja arrancar la app primero
    while True:
        await asyncio.to_thread(tick)
        await asyncio.sleep(CADA)
