"""Acceso: usuario o correo + contraseña, o cuenta de Google. Cada cuenta ve sólo sus emisores (ver app/db.py)."""
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import EN_WEB, settings
from ..db import get_db, solo_admin
from ..logs import log
from ..models import Usuario
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

USUARIO_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
# Contraseñas de práctica: sirven en tu PC, nunca en un servidor
DEBILES = {"admin", "cambiame", "password", "12345678", "123456"}


class LoginIn(BaseModel):
    email: str  # correo o nombre de usuario
    password: str


class UsuarioIn(BaseModel):
    email: str
    usuario: str | None = None
    nombre: str | None = None
    password: str
    admin: bool = False


class CambioIn(BaseModel):
    actual: str
    nueva: str


class PerfilIn(BaseModel):
    nombre: str


def _yo(u: Usuario) -> dict:
    return {"id": u.id, "email": u.email, "usuario": u.usuario, "nombre": u.nombre, "admin": u.admin, "creado": u.creado,
            "google_email": u.google_email}


def _actual(db: Session, email: str) -> Usuario:
    u = db.query(Usuario).filter_by(email=email, activo=True).first()
    if not u:
        raise HTTPException(401, "Tu sesión ya no es válida. Vuelve a entrar.")
    return u


def asegurar_admin(db: Session):
    """Primer arranque: crea el admin del .env si no hay usuarios."""
    if not db.query(Usuario).count():
        db.add(Usuario(email=settings.admin_email.lower(), nombre="Administrador",
                       password_hash=hash_password(settings.admin_password), admin=True))
        db.commit()


# Freno a quien prueba contraseñas: 6 intentos fallidos por cuenta en 10 minutos y se bloquea un rato.
_FALLOS: dict[str, list[float]] = {}
_VENTANA, _MAXIMO = 600, 6


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    quien = data.email.strip().lower()
    ahora = time.time()
    recientes = [t for t in _FALLOS.get(quien, []) if ahora - t < _VENTANA]
    if len(recientes) >= _MAXIMO:
        espera = int((_VENTANA - (ahora - recientes[0])) // 60) + 1
        raise HTTPException(429, f"Demasiados intentos fallidos. Espera {espera} min y vuelve a intentar.")
    u = db.query(Usuario).filter(or_(Usuario.email == quien, Usuario.usuario == quien), Usuario.activo.is_(True)).first()
    if not u or not verify_password(data.password, u.password_hash):
        _FALLOS[quien] = recientes + [ahora]
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    _FALLOS.pop(quien, None)
    if EN_WEB and data.password.lower() in DEBILES:
        raise HTTPException(403, "Esa contraseña de práctica no se permite en el servidor. Pide al administrador que la cambie.")
    return {"token": create_token(u.email), "nombre": u.nombre, "admin": u.admin}


@router.get("/config")
def config():
    """Lo que la pantalla de entrada necesita saber sin haber entrado."""
    return {"google": bool(settings.google_client_id and settings.google_client_secret)}


@router.get("/yo")
def yo(email: str = Depends(current_user), db: Session = Depends(get_db)):
    return _yo(_actual(db, email))


@router.put("/yo")
def editar_yo(data: PerfilIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = _actual(db, email)
    nombre = data.nombre.strip()
    if not nombre:
        raise HTTPException(422, "Escribe tu nombre")
    u.nombre = nombre[:150]
    db.commit()
    return _yo(u)


@router.post("/password")
def cambiar(data: CambioIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = _actual(db, email)
    if not verify_password(data.actual, u.password_hash):
        raise HTTPException(422, "La contraseña actual no coincide")
    if len(data.nueva) < 8:
        raise HTTPException(422, "Mínimo 8 caracteres")
    u.password_hash = hash_password(data.nueva)
    db.commit()
    return {"ok": True}


@router.get("/usuarios", dependencies=[Depends(solo_admin)])
def usuarios(db: Session = Depends(get_db)):
    from ..models import Emisor
    emisores: dict[int, int] = {}
    for (uid,) in db.query(Emisor.usuario_id):
        emisores[uid] = emisores.get(uid, 0) + 1
    return [{"id": u.id, "email": u.email, "usuario": u.usuario, "nombre": u.nombre, "admin": u.admin, "activo": u.activo,
             "google": bool(u.google_sub), "emisores": emisores.get(u.id, 0)}
            for u in db.query(Usuario).order_by(Usuario.email)]


@router.post("/usuarios", dependencies=[Depends(solo_admin)])
def crear_usuario(data: UsuarioIn, db: Session = Depends(get_db)):
    correo = data.email.strip().lower()
    usuario = (data.usuario or "").strip().lower() or None
    if "@" not in correo:
        raise HTTPException(422, "Escribe un correo válido")
    if usuario and not USUARIO_RE.match(usuario):
        raise HTTPException(422, "El nombre de usuario lleva de 3 a 40 letras minúsculas, números, punto o guion.")
    if len(data.password) < 8:
        raise HTTPException(422, "La contraseña lleva mínimo 8 caracteres")
    if db.query(Usuario).filter(or_(Usuario.email == correo, Usuario.usuario == (usuario or "\0"))).first():
        raise HTTPException(409, "Ese correo o nombre de usuario ya existe")
    db.add(Usuario(email=correo, usuario=usuario, nombre=data.nombre, password_hash=hash_password(data.password), admin=data.admin))
    db.commit()
    return {"ok": True}


class ActivoIn(BaseModel):
    activo: bool


@router.put("/usuarios/{uid}/activo", dependencies=[Depends(solo_admin)])
def activar(uid: int, data: ActivoIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuario no existe")
    if u.email == email and not data.activo:
        raise HTTPException(422, "No puedes desactivar tu propia cuenta")
    u.activo = data.activo
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Google
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"


def _estado(accion: str, uid: int | None = None) -> str:
    """`state` firmado: evita que un tercero inyecte un regreso de Google que no pedimos."""
    return jwt.encode({"a": accion, "u": uid, "n": secrets.token_urlsafe(8),
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, settings.jwt_secret, algorithm="HS256")


def _url_google(estado: str) -> str:
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(503, "El inicio de sesión con Google no está configurado en este Timbra.")
    return GOOGLE_AUTH + "?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": settings.google_redirect_uri, "response_type": "code",
        "scope": "openid email profile", "state": estado, "prompt": "select_account"})


@router.get("/google/entrar")
def google_entrar():
    """La pantalla de entrada manda aquí: regresa la dirección de Google a la que hay que ir."""
    return {"url": _url_google(_estado("entrar"))}


@router.get("/google/vincular")
def google_vincular(email: str = Depends(current_user), db: Session = Depends(get_db)):
    """Desde Mi perfil: conecta una cuenta de Google a la cuenta con la que ya entraste."""
    return {"url": _url_google(_estado("vincular", _actual(db, email).id))}


@router.delete("/google")
def google_desvincular(email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = _actual(db, email)
    u.google_sub = u.google_email = None
    db.commit()
    return _yo(u)


def _canjear(code: str) -> dict:
    """Cambia el código de Google por la identidad del usuario. El id_token viene directo de Google por HTTPS."""
    import httpx
    r = httpx.post(GOOGLE_TOKEN, timeout=20, data={
        "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri, "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise ValueError(f"Google no aceptó el código ({r.status_code})")
    datos = jwt.decode(r.json()["id_token"], options={"verify_signature": False})
    if datos.get("aud") != settings.google_client_id or datos.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        raise ValueError("La respuesta de Google no corresponde a este Timbra")
    return datos


def _regreso(**fragmento) -> RedirectResponse:
    # El token viaja en el fragmento (#), que el navegador no manda a ningún servidor ni queda en registros
    return RedirectResponse(f"{settings.front_url.rstrip('/')}/login/#{urlencode(fragmento)}", status_code=302)


@router.get("/google/callback")
def google_callback(code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    if error or not code or not state:
        return _regreso(error="No se completó el inicio de sesión con Google.")
    try:
        est = jwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return _regreso(error="La solicitud a Google caducó. Intenta de nuevo.")
    try:
        g = _canjear(code)
    except Exception as e:
        log.warning("Google: %s", e)
        return _regreso(error="Google no confirmó tu identidad. Intenta de nuevo.")
    sub, correo, verificado = g.get("sub"), (g.get("email") or "").lower(), g.get("email_verified")
    if not sub or not correo or not verificado:
        return _regreso(error="Tu cuenta de Google no tiene un correo verificado.")

    if est.get("a") == "vincular":
        u = db.get(Usuario, est.get("u"))
        if not u or not u.activo:
            return _regreso(error="Tu sesión de Timbra ya no es válida.")
        otro = db.query(Usuario).filter(Usuario.google_sub == sub, Usuario.id != u.id).first()
        if otro:
            return _regreso(error=f"Esa cuenta de Google ya está conectada a otro usuario de Timbra ({otro.email}).")
        u.google_sub, u.google_email = sub, correo
        db.commit()
        log.info("Google conectado a %s (%s)", u.email, correo)
        return _regreso(token=create_token(u.email), aviso=f"Google conectado: {correo}")

    u = db.query(Usuario).filter(Usuario.google_sub == sub).first() or db.query(Usuario).filter(Usuario.email == correo).first()
    if u is None:
        if not settings.registro_abierto:
            return _regreso(error=f"{correo} no tiene cuenta en Timbra. Entra con tu usuario y conéctala en Mi perfil, o pide acceso al administrador.")
        u = Usuario(email=correo, nombre=g.get("name"), password_hash=hash_password(secrets.token_urlsafe(24)))
        db.add(u)
    if not u.activo:
        return _regreso(error="Tu cuenta está desactivada.")
    u.google_sub, u.google_email = sub, correo
    db.commit()
    log.info("Entrada con Google: %s", u.email)
    return _regreso(token=create_token(u.email))
