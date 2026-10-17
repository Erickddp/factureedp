"""Modo invitado: entrar a Timbra sin registrarse.

Un invitado es una cuenta REAL pero temporal, con el mismo aislamiento que cualquier otra (db.py): sólo ve lo suyo.
  · Dura 1 hora (fija, desde que entra). A esa hora el programador borra la cuenta, sus emisores, sus XML y todo lo que colgaba de ellos.
  · Puede recorrer la aplicación, bajar y leer XML del SAT con su e.firma (que nunca se guarda) y armar facturas hasta la vista previa.
  · NO puede timbrar, cancelar, subir CSD, mandar correos, tocar PACs ni nada que quede fuera de su hora: para eso crea su cuenta
    (auth.convertir: la MISMA cuenta pasa a ser normal y conserva lo que ya traía).
  · No trae timbres de regalo: esos llegan al confirmar el correo de una cuenta real.
"""
import re
import secrets
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import settings
from ..db import Base
from ..logs import log
from ..models import Emisor, Usuario
from ..security import hash_password

DURACION = timedelta(hours=1)
DOMINIO = "invitado.timbra"

# Lo que un invitado SÍ puede escribir (todo lo que sea GET se permite siempre, sobre lo suyo)
PERMITIDO = ("/api/xml", "/api/emisores", "/api/clientes", "/api/productos", "/api/constancia", "/api/deducibles",
             "/api/facturas/preview", "/api/lotes", "/api/auth/convertir", "/api/auth/invitado", "/api/debug/cliente", "/api/claves",
             "/api/catalogos")
# …y aun dentro de eso, lo que nunca: sellar, timbrar, mandar o salir de su hora
PROHIBIDO = re.compile(r"/(csd|ejecutar|carpeta|practica|enviar|cancelar|timbrar|migracion|drive|pacs|correo|usuarios|soporte|portal)(/|$)|/productos-a-frontera")

MENSAJE = "Crea tu cuenta para usar esto: como invitado puedes explorar y bajar tus XML, pero no timbrar ni guardar de forma permanente."


def es_invitado(u: Usuario) -> bool:
    return bool(u.invitado)


def vencido(u) -> bool:
    return bool(u.invitado and u.expira and u.expira < datetime.now())


def permite(metodo: str, ruta: str) -> bool:
    """¿Puede un invitado hacer esta petición? GET/HEAD/OPTIONS siempre; escribir, sólo lo permitido y nunca lo prohibido."""
    if metodo.upper() in ("GET", "HEAD", "OPTIONS"):
        return True
    return ruta.startswith(PERMITIDO) and not PROHIBIDO.search(ruta)


def crear(db: Session, ip: str) -> Usuario:
    ahora = datetime.now()
    azar = secrets.token_hex(6)
    u = Usuario(email=f"invitado-{azar}@{DOMINIO}", nombre="Invitado", password_hash=hash_password(secrets.token_urlsafe(24)),
                activo=True, admin=False, timbres=0, correo_verificado=False, invitado=True, expira=ahora + DURACION,
                terminos_aceptados=ahora, terminos_ip=ip)
    db.add(u)
    db.commit()
    log.info("Invitado %s (expira %s)", u.id, u.expira)
    return u


def borrar(db: Session, u: Usuario) -> None:
    """Quita al invitado y TODO lo suyo: emisores con lo que cuelga de ellos (XML, clientes, constancias…), carpetas en disco y la cuenta."""
    for e in db.query(Emisor).filter(Emisor.usuario_id == u.id).all():
        for tabla in reversed(Base.metadata.sorted_tables):
            if tabla.name != "emisores" and "emisor_id" in tabla.c:
                db.execute(delete(tabla).where(tabla.c.emisor_id == e.id))
        db.delete(e)
        for carpeta in ("xml", "csf", "xml_estado"):
            shutil.rmtree(Path(settings.data_dir) / carpeta / str(e.id), ignore_errors=True)
    for tabla in reversed(Base.metadata.sorted_tables):
        if tabla.name != "usuarios" and "usuario_id" in tabla.c:
            db.execute(delete(tabla).where(tabla.c.usuario_id == u.id))
    db.delete(u)
    db.commit()


def purgar(db: Session) -> int:
    """Programador: borra los invitados cuya hora ya pasó. Devuelve cuántos."""
    n = 0
    for u in db.query(Usuario).filter(Usuario.invitado.is_(True), Usuario.expira < datetime.now()).all():
        try:
            borrar(db, u)
            n += 1
        except Exception:
            db.rollback()
            log.exception("No se pudo borrar al invitado %s", u.id)
    if n:
        log.info("Invitados vencidos borrados: %s", n)
    return n
