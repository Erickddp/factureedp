"""Acceso: usuario o correo + contraseña, o cuenta de Google. Cada cuenta ve sólo sus emisores (ver app/db.py)."""
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import EN_WEB, settings
from ..legal import TERMINOS_VERSION, pendiente as terminos_pendientes
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
            "google_email": u.google_email, "timbres": None if u.admin else u.timbres,
            "terminos": {"vigente": TERMINOS_VERSION, "aceptada": u.terminos_version, "aceptados": u.terminos_aceptados,
                         "pendiente": terminos_pendientes(u)}}


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


# Freno a quien prueba contraseñas. Se cuenta por (equipo, cuenta): 6 fallos en 10 minutos y ese equipo espera, sin que
# un extraño pueda dejar fuera al dueño de la cuenta desde otro lado. Además, un mismo equipo no puede ir probando
# cuenta por cuenta (30 fallos en total) y una cuenta atacada desde muchos equipos también se frena (40).
_FALLOS: dict[str, list[float]] = {}
_VENTANA, _MAXIMO, _MAX_IP, _MAX_CUENTA = 600, 6, 30, 40


def _recientes(llave: str, ahora: float) -> list[float]:
    r = [t for t in _FALLOS.get(llave, []) if ahora - t < _VENTANA]
    if r:
        _FALLOS[llave] = r
    else:
        _FALLOS.pop(llave, None)
    return r


@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    quien = data.email.strip().lower()[:200]
    ip = request.client.host if request.client else "?"
    ahora = time.time()
    if len(_FALLOS) > 20000:  # nadie llena la memoria a punta de intentos
        for k in [k for k, v in _FALLOS.items() if not v or ahora - v[-1] >= _VENTANA]:
            _FALLOS.pop(k, None)
    llaves = {f"{ip}|{quien}": _MAXIMO, f"ip|{ip}": _MAX_IP, f"cuenta|{quien}": _MAX_CUENTA}
    for llave, tope in llaves.items():
        recientes = _recientes(llave, ahora)
        if len(recientes) >= tope:
            espera = int((_VENTANA - (ahora - recientes[0])) // 60) + 1
            raise HTTPException(429, f"Demasiados intentos fallidos. Espera {espera} min y vuelve a intentar.")
    u = db.query(Usuario).filter(or_(Usuario.email == quien, Usuario.usuario == quien), Usuario.activo.is_(True)).first()
    if not u or not verify_password(data.password, u.password_hash):
        for llave in llaves:
            _FALLOS[llave] = _FALLOS.get(llave, []) + [ahora]
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    _FALLOS.pop(f"{ip}|{quien}", None)
    if EN_WEB and data.password.lower() in DEBILES:
        raise HTTPException(403, "Esa contraseña de práctica no se permite en el servidor. Pide al administrador que la cambie.")
    return {"token": create_token(u.email, u.password_hash), "nombre": u.nombre, "admin": u.admin}


@router.get("/config")
def config():
    """Lo que la pantalla de entrada necesita saber sin haber entrado."""
    return {"google": bool(settings.google_client_id and settings.google_client_secret), "terminos": TERMINOS_VERSION}


@router.get("/yo")
def yo(email: str = Depends(current_user), db: Session = Depends(get_db)):
    return _yo(_actual(db, email))


class TerminosIn(BaseModel):
    version: str


@router.post("/terminos")
def aceptar_terminos(data: TerminosIn, request: Request, email: str = Depends(current_user), db: Session = Depends(get_db)):
    """Constancia de que la cuenta aceptó los términos de uso y el aviso de privacidad vigentes."""
    if data.version != TERMINOS_VERSION:
        raise HTTPException(409, "Los términos cambiaron mientras los leías. Recarga la página y revísalos otra vez.")
    u = _actual(db, email)
    u.terminos_version = TERMINOS_VERSION
    u.terminos_aceptados = datetime.now()
    u.terminos_ip = (request.client.host if request.client else None)
    db.commit()
    log.info("Cuenta %s aceptó términos y aviso de privacidad %s", u.id, TERMINOS_VERSION)
    return _yo(u)


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
    # las demás sesiones abiertas con la contraseña anterior dejan de valer; ésta sigue con un token nuevo
    return {"ok": True, "token": create_token(u.email, u.password_hash)}


# ---------------------------------------------------------------- timbres de cada cuenta
class RecargaIn(BaseModel):
    cantidad: int
    motivo: str | None = None


@router.post("/usuarios/{uid}/timbres", dependencies=[Depends(solo_admin)])
def recargar_timbres(uid: int, data: RecargaIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    """El administrador abona (o corrige, con número negativo) timbres a una cuenta. Queda anotado quién y por qué."""
    from ..services import timbres
    if not db.get(Usuario, uid):
        raise HTTPException(404, "Usuario no existe")
    if data.cantidad == 0 or abs(data.cantidad) > 100000:
        raise HTTPException(422, "Escribe cuántos timbres (por ejemplo 30).")
    saldo = timbres.recargar(db, uid, data.cantidad, data.motivo, _actual(db, email).id)
    log.warning("TIMBRES: %s abonó %s a la cuenta %s (saldo %s) · %s", email, data.cantidad, uid, saldo, data.motivo or "")
    return {"timbres": saldo}


@router.get("/timbres")
def mis_timbres(email: str = Depends(current_user), db: Session = Depends(get_db)):
    """Saldo y recargas de MI cuenta."""
    from ..models import MovimientoTimbres
    u = _actual(db, email)
    movs = db.query(MovimientoTimbres).filter_by(usuario_id=u.id).order_by(MovimientoTimbres.id.desc()).limit(30)
    return {"timbres": None if u.admin else u.timbres, "movimientos": [{"cuando": m.creado, "cantidad": m.cantidad, "saldo": m.saldo, "motivo": m.motivo} for m in movs]}


# ---------------------------------------------------------------- modo soporte
SOPORTE_HORAS = 2


class SoporteIn(BaseModel):
    motivo: str | None = None


@router.post("/soporte/{uid}", dependencies=[Depends(solo_admin)])
def soporte_entrar(uid: int, data: SoporteIn, request: Request, email: str = Depends(current_user), db: Session = Depends(get_db)):
    """El administrador entra a la cuenta de alguien para ayudarle. Queda anotado y el dueño de la cuenta lo ve."""
    from datetime import datetime, timedelta

    from ..models import AccesoSoporte
    yo, u = _actual(db, email), db.get(Usuario, uid)
    if not u or not u.activo:
        raise HTTPException(404, "Esa cuenta no existe o está desactivada.")
    if u.id == yo.id:
        raise HTTPException(422, "Ésa es tu propia cuenta.")
    ahora = datetime.now()
    acc = AccesoSoporte(admin_id=yo.id, usuario_id=u.id, motivo=(data.motivo or "").strip()[:200] or None,
                        ip=request.client.host if request.client else None, inicio=ahora, hasta=ahora + timedelta(hours=SOPORTE_HORAS))
    db.add(acc)
    db.commit()
    log.warning("MODO SOPORTE: %s entró a la cuenta de %s (%s)", yo.email, u.email, acc.motivo or "sin motivo")
    return {"id": u.id, "email": u.email, "nombre": u.nombre or u.usuario or u.email, "hasta": acc.hasta}


@router.delete("/soporte/{uid}", dependencies=[Depends(solo_admin)])
def soporte_salir(uid: int, email: str = Depends(current_user), db: Session = Depends(get_db)):
    from datetime import datetime

    from ..models import AccesoSoporte
    yo, ahora = _actual(db, email), datetime.now()
    for acc in db.query(AccesoSoporte).filter(AccesoSoporte.admin_id == yo.id, AccesoSoporte.usuario_id == uid, AccesoSoporte.hasta > ahora):
        acc.hasta = ahora
    db.commit()
    return {"ok": True}


@router.get("/soporte/accesos")
def soporte_accesos(email: str = Depends(current_user), db: Session = Depends(get_db)):
    """Las veces que soporte ha entrado a MI cuenta (transparencia para el dueño)."""
    from ..models import AccesoSoporte
    yo = _actual(db, email)
    nombres = {u.id: u.nombre or u.email for u in db.query(Usuario)}
    return [{"cuando": a.inicio, "hasta": a.hasta, "quien": nombres.get(a.admin_id, "Soporte"), "motivo": a.motivo}
            for a in db.query(AccesoSoporte).filter_by(usuario_id=yo.id).order_by(AccesoSoporte.id.desc()).limit(30)]


@router.get("/usuarios", dependencies=[Depends(solo_admin)])
def usuarios(db: Session = Depends(get_db)):
    from sqlalchemy import select

    from ..models import Emisor
    emisores: dict[int, int] = {}
    # conteo directo en la tabla: el administrador ya no ve los emisores ajenos, sólo cuántos tiene cada cuenta
    for (uid,) in db.execute(select(Emisor.__table__.c.usuario_id)):
        emisores[uid] = emisores.get(uid, 0) + 1
    return [{"id": u.id, "email": u.email, "usuario": u.usuario, "nombre": u.nombre, "admin": u.admin, "activo": u.activo,
             "google": bool(u.google_sub), "emisores": emisores.get(u.id, 0), "timbres": None if u.admin else u.timbres}
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
        return _regreso(token=create_token(u.email, u.password_hash), aviso=f"Google conectado: {correo}")

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
    return _regreso(token=create_token(u.email, u.password_hash))
