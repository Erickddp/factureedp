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
    # En web el respaldo vive en el MISMO disco: sin los XML bajados del SAT (se pueden volver a bajar) y sólo 3 días,
    # o los respaldos solos llenarían el volumen y el servidor dejaría de arrancar
    armar_respaldo(zip_path, sin_xml_sat=EN_WEB)
    viejos = sorted(destino.glob("timbra_*.zip"))[:-(3 if EN_WEB else conservar)]
    for v in viejos:
        v.unlink(missing_ok=True)
    log.info("Respaldo diario: %s", zip_path)
    return zip_path


MAX_CORREO = 25 * 1024 * 1024  # el servicio de correo acepta ~40 MB ya en base64


def respaldo_fuera(zip_path: Path) -> str | None:
    """Copia del respaldo FUERA del servidor: por correo a RESPALDO_CORREO, cifrada con la SECRET_KEY (sin esa llave el
    archivo no sirve de nada, aunque alguien lo vea). Si pesa demasiado, va sólo la base (las facturas timbradas viven
    también ahí). Se abre con `python restaurar_respaldo.py archivo.timbra`. Devuelve a quién se mandó, o None."""
    from . import mailer
    from ..security import encrypt

    para = (settings.respaldo_correo or "").strip()
    if not para or not mailer.por_api():
        return None
    origen, nota = zip_path, "completo (base y XML)"
    if zip_path.stat().st_size > MAX_CORREO:
        origen = zip_path.with_name(zip_path.stem + "_solo_base.zip")
        armar_respaldo(origen, solo_base=True)
        nota = "sólo la base de datos (el completo pesa demasiado para correo; está en el servidor)"
    try:
        cifrado = encrypt(origen.read_bytes())
    finally:
        if origen != zip_path:
            origen.unlink(missing_ok=True)
    nombre = zip_path.stem + ".timbra"
    mailer.enviar([para], f"Respaldo de Timbra {datetime.now():%d/%m/%Y}",
                  f"Respaldo diario de Timbra: {nota}.\n\nEstá cifrado con tu SECRET_KEY: guárdalo tal cual. Para abrirlo, en tu PC:\n"
                  f"  cd Timbra\\backend\n  .venv\\Scripts\\python restaurar_respaldo.py {nombre}\n\nLa guía completa está en DESPLEGAR.md → «Restaurar un respaldo».",
                  [(nombre, cifrado, "application/octet-stream")], nombre="Timbra")
    log.info("Respaldo enviado fuera del servidor a %s (%s, %s KB)", para, nota, len(cifrado) // 1024)
    return para


def armar_respaldo(zip_path: Path, solo_base: bool = False, sin_xml_sat: bool = False) -> Path:
    """Escribe en `zip_path` todo lo que hace falta para levantar Timbra en otra máquina: base, XML, correo y .env.
    sin_xml_sat: deja fuera los XML bajados del SAT (carpeta xml/; los timbrados por Timbra van en la base y respaldo_xml)."""
    datos = Path(settings.data_dir).resolve()
    copia = _copia_bd()  # copia consistente aunque la app esté escribiendo (modo WAL)
    fuera = {"logs", "Respaldos", "tmp", "eliminados"} | ({"xml"} if sin_xml_sat else set())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in ([] if solo_base else os.walk(datos)):
            if Path(root) == datos:  # ni registros, ni temporales, ni respaldos dentro de respaldos
                dirs[:] = [d for d in dirs if d not in fuera]
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
        if _una_vez_al_dia("vencer_timbres"):
            try:
                from . import timbres
                n = timbres.vencer(db)
                if n:
                    log.info("Programador · vencieron %s timbres (recargas de hace 12 meses)", n)
            except Exception:
                db.rollback()
                log.exception("Programador · vencer timbres falló")
        if _una_vez_al_dia("cobranza"):
            try:
                cobranza.recordatorios_automaticos(db)
            except Exception:
                db.rollback()
                log.exception("Programador · cobranza falló")
    if _una_vez_al_dia("respaldo"):
        try:
            hecho = respaldo_diario()
            if hecho:
                respaldo_fuera(hecho)
        except Exception:
            log.exception("Respaldo diario falló")


async def correr():
    await asyncio.sleep(45)  # deja arrancar la app primero
    while True:
        await asyncio.to_thread(tick)
        await asyncio.sleep(CADA)
