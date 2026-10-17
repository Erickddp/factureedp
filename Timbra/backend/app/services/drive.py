"""Copia de los XML de cada cuenta a SU Google Drive.

Permiso drive.file (no sensible): Timbra sólo puede ver y tocar lo que él mismo crea en ese Drive, nunca lo demás.
Sólo XML: los bajados del SAT y los timbrados en Timbra. Nada de PDF (se generan cuando se piden), logos ni datos de la cuenta.

En el Drive queda:
    Timbra/{RFC}/{AAAAMM}/{emitidos|recibidos}/{UUID}.xml   ← descarga del SAT o XML leídos
    Timbra/{RFC}/timbrados/{AAAA-MM}/{UUID}.xml             ← facturas timbradas en Timbra (sin las de práctica)

Cada archivo se sube UNA vez (tabla drive_archivos). Borrar algo en Drive no lo vuelve a subir; para reponer todo se
desconecta y se vuelve a conectar. Corre en un hilo por cuenta: al conectar, con «Copiar ahora» y cada vuelta del programador.
"""
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
import jwt

from ..config import settings
from ..db import SessionLocal
from ..logs import log
from ..models import DriveArchivo, DriveConexion, Emisor, Factura, Usuario
from ..security import decrypt, encrypt
from .pdf import es_demo
from .xml_indice import carpeta_xml

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REVOCAR = "https://oauth2.googleapis.com/revoke"
ARCHIVOS = "https://www.googleapis.com/drive/v3/files"
SUBIR = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id"
ALCANCE = "https://www.googleapis.com/auth/drive.file"
CARPETA = "application/vnd.google-apps.folder"
RAIZ = "Timbra"
POR_VUELTA = 3000  # tope de archivos por corrida; lo que falte sigue en la siguiente

_EN_CURSO: set[int] = set()
_CANDADO = threading.Lock()


class DriveError(Exception):
    pass


def configurado() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


# ---------------------------------------------------------------- conectar
def url_conectar(uid: int) -> str:
    if not configurado():
        raise DriveError("Google no está configurado en este Timbra.")
    # El claim "a" hace que este state nunca sirva como sesión (security.current_user lo rechaza)
    estado = jwt.encode({"a": "drive", "u": uid, "n": secrets.token_urlsafe(8),
                         "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, settings.jwt_secret, algorithm="HS256")
    return AUTH + "?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": settings.google_redirect_uri, "response_type": "code",
        "scope": f"openid email {ALCANCE}", "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
        "state": estado})


def completar(db, uid: int, code: str) -> DriveConexion:
    """Regreso de Google: guarda el token de renovación (cifrado) de la cuenta uid."""
    u = db.get(Usuario, uid)
    if not u or not u.activo:
        raise DriveError("Tu sesión de Timbra ya no es válida.")
    r = httpx.post(TOKEN, timeout=20, data={
        "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri, "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise DriveError(f"Google no aceptó la autorización ({r.status_code}). Intenta de nuevo.")
    d = r.json()
    if ALCANCE not in (d.get("scope") or "").split():
        raise DriveError("No marcaste el permiso de Google Drive. Vuelve a conectar y acepta el acceso a los archivos que Timbra crea.")
    if not d.get("refresh_token"):
        raise DriveError("Google no entregó el permiso permanente. Vuelve a conectar.")
    correo = None
    if d.get("id_token"):
        try:
            correo = (jwt.decode(d["id_token"], options={"verify_signature": False}).get("email") or "").lower() or None
        except jwt.PyJWTError:
            pass
    con = db.query(DriveConexion).filter(DriveConexion.usuario_id == uid).first()
    if con is None:
        con = DriveConexion(usuario_id=uid)
        db.add(con)
    elif con.google_email and correo and con.google_email != correo:
        # Otro Drive: lo copiado antes vive en el anterior, así que en éste se sube todo de nuevo
        db.query(DriveArchivo).filter(DriveArchivo.usuario_id == uid).delete()
        con.carpeta_id, con.subidos = None, 0
    con.refresh_enc, con.google_email, con.estado, con.error = encrypt(d["refresh_token"]), correo, "activa", None
    db.commit()
    log.info("Drive conectado: cuenta %s → %s", uid, correo or "?")
    return con


def desconectar(db, uid: int) -> None:
    """Quita el permiso y olvida qué se subió. Lo que ya está en su Drive se queda ahí: es suyo."""
    con = db.query(DriveConexion).filter(DriveConexion.usuario_id == uid).first()
    if con is None:
        return
    if con.refresh_enc:
        try:
            httpx.post(REVOCAR, timeout=10, data={"token": decrypt(con.refresh_enc).decode()})
        except Exception:
            log.warning("Drive: no se pudo revocar el token de la cuenta %s (se borra igual)", uid)
    db.query(DriveArchivo).filter(DriveArchivo.usuario_id == uid).delete()
    db.delete(con)
    db.commit()


# ---------------------------------------------------------------- qué hay que subir
def pendientes(db, uid: int, ya: set[str] | None = None) -> list[tuple[str, object]]:
    """(ruta en Drive, origen) de los XML de la cuenta que aún no están en Drive. Origen: Path o id de Factura."""
    ya = ya if ya is not None else {r for (r,) in db.query(DriveArchivo.ruta).filter(DriveArchivo.usuario_id == uid)}
    out: list[tuple[str, object]] = []
    for e in db.query(Emisor).filter(Emisor.usuario_id == uid).order_by(Emisor.id):
        rfc = (e.rfc or "").upper()
        base = carpeta_xml(e.id)
        if base.is_dir():
            for p in sorted(base.rglob("*.xml")):
                partes = p.relative_to(base).parts
                if len(partes) == 3:  # «202610 EKU9» / emitidos|recibidos / UUID.xml
                    ruta = f"{RAIZ}/{rfc}/{partes[0].split()[0]}/{partes[1]}/{partes[2]}"
                else:
                    ruta = f"{RAIZ}/{rfc}/otros/{p.name}"
                if ruta not in ya:
                    out.append((ruta, p))
        for fid, uuid, fecha in (db.query(Factura.id, Factura.uuid, Factura.fecha)
                                 .filter(Factura.emisor_id == e.id, Factura.uuid.isnot(None), Factura.xml.isnot(None))):
            ruta = f"{RAIZ}/{rfc}/timbrados/{(fecha or datetime.now()):%Y-%m}/{uuid.upper()}.xml"
            if ruta not in ya:
                out.append((ruta, fid))
    return out


# ---------------------------------------------------------------- Google Drive
def _token(con: DriveConexion) -> str:
    r = httpx.post(TOKEN, timeout=20, data={
        "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "refresh_token": decrypt(con.refresh_enc).decode(), "grant_type": "refresh_token"})
    if r.status_code == 400 and "invalid_grant" in r.text:
        raise DriveError("Google retiró el permiso de Drive (lo quitaste en tu cuenta de Google o venció). Vuelve a conectar.")
    if r.status_code != 200:
        raise DriveError(f"Google no renovó el acceso a Drive ({r.status_code}). Se reintenta en la siguiente vuelta.")
    return r.json()["access_token"]


def _carpeta(cli: httpx.Client, db, uid: int, ruta: str, nombre: str, padre: str | None) -> str:
    clave = f"dir:{ruta}"
    hecho = db.query(DriveArchivo).filter(DriveArchivo.usuario_id == uid, DriveArchivo.ruta == clave).first()
    if hecho:
        return hecho.drive_id
    meta = {"name": nombre, "mimeType": CARPETA, **({"parents": [padre]} if padre else {})}
    r = cli.post(ARCHIVOS, params={"fields": "id"}, json=meta)
    if r.status_code >= 300:
        raise DriveError(f"Drive no dejó crear la carpeta {ruta} ({r.status_code}).")
    db.add(DriveArchivo(usuario_id=uid, ruta=clave, drive_id=r.json()["id"]))
    db.commit()  # la carpeta ya existe en Drive: si algo falla después, no se vuelve a crear repetida
    return r.json()["id"]


def _subir(cli: httpx.Client, nombre: str, datos: bytes, padre: str) -> httpx.Response:
    limite = "timbra" + secrets.token_hex(8)
    meta = json.dumps({"name": nombre, "parents": [padre], "mimeType": "application/xml"})
    cuerpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
              f"--{limite}\r\nContent-Type: application/xml\r\n\r\n").encode() + datos + f"\r\n--{limite}--".encode()
    return cli.post(SUBIR, content=cuerpo, headers={"Content-Type": f"multipart/related; boundary={limite}"})


def sincronizar(uid: int) -> dict:
    """Sube lo pendiente de la cuenta. Devuelve {"subidos": n, "faltan": m}. Nunca deja la conexión en «sincronizando»."""
    with SessionLocal() as db:
        con = db.query(DriveConexion).filter(DriveConexion.usuario_id == uid).first()
        if con is None or not con.refresh_enc or con.estado == "revocada":
            return {"subidos": 0, "faltan": 0}
        con.estado, con.error = "sincronizando", None
        db.commit()
        subidos = 0
        try:
            lista = pendientes(db, uid)
            if lista:
                with httpx.Client(timeout=60, headers={"Authorization": f"Bearer {_token(con)}"}) as cli:
                    if not con.carpeta_id:
                        con.carpeta_id = _carpeta(cli, db, uid, RAIZ, RAIZ, None)
                    for ruta, origen in lista[:POR_VUELTA]:
                        datos = origen.read_bytes() if isinstance(origen, Path) else db.get(Factura, origen).xml
                        if not datos or (not isinstance(origen, Path) and es_demo(datos)):
                            db.add(DriveArchivo(usuario_id=uid, ruta=ruta, drive_id="-"))  # de práctica o vacío: no va
                            continue
                        partes = ruta.split("/")
                        padre = con.carpeta_id
                        for i in range(1, len(partes) - 1):
                            padre = _carpeta(cli, db, uid, "/".join(partes[:i + 1]), partes[i], padre)
                        r = _subir(cli, partes[-1], datos, padre)
                        if r.status_code == 404:  # alguien borró la carpeta en Drive: se vuelve a crear la próxima vez
                            db.query(DriveArchivo).filter(DriveArchivo.usuario_id == uid, DriveArchivo.ruta.like("dir:%")).delete(
                                synchronize_session=False)
                            con.carpeta_id = None
                            db.commit()
                            raise DriveError("La carpeta «Timbra» ya no está en tu Drive; se vuelve a crear en la siguiente copia.")
                        if r.status_code >= 300:
                            raise DriveError(f"Drive rechazó {partes[-1]} ({r.status_code}).")
                        db.add(DriveArchivo(usuario_id=uid, ruta=ruta, drive_id=r.json()["id"]))
                        subidos += 1
                        con.subidos = (con.subidos or 0) + 1
                        if subidos % 50 == 0:
                            db.commit()
            con.estado, con.ultimo = "activa", datetime.now()
            faltan = max(0, len(lista) - POR_VUELTA)
        except DriveError as e:
            db.rollback()
            con = db.query(DriveConexion).filter(DriveConexion.usuario_id == uid).first()
            con.estado = "revocada" if "retiró el permiso" in str(e) else "error"
            con.error, faltan = str(e), -1
            log.warning("Drive · cuenta %s: %s", uid, e)
        except Exception as e:
            db.rollback()
            con = db.query(DriveConexion).filter(DriveConexion.usuario_id == uid).first()
            con.estado, con.error, faltan = "error", "No se pudo copiar a Drive; se reintenta en la siguiente vuelta.", -1
            log.exception("Drive · cuenta %s falló: %s", uid, e)
        db.commit()
        if subidos:
            log.info("Drive · cuenta %s: %s XML copiados", uid, subidos)
        return {"subidos": subidos, "faltan": faltan}


def lanzar(uid: int) -> bool:
    """Corre sincronizar(uid) en un hilo, uno a la vez por cuenta. False si ya estaba corriendo."""
    with _CANDADO:
        if uid in _EN_CURSO:
            return False
        _EN_CURSO.add(uid)

    def correr():
        try:
            sincronizar(uid)
        finally:
            with _CANDADO:
                _EN_CURSO.discard(uid)
    threading.Thread(target=correr, name=f"drive-{uid}", daemon=True).start()
    return True


def sincronizar_todos() -> int:
    """Programador: lanza la copia de cada cuenta conectada (sólo sube lo nuevo). Devuelve cuántas lanzó."""
    if not configurado():
        return 0
    with SessionLocal() as db:
        uids = [u for (u,) in db.query(DriveConexion.usuario_id).filter(DriveConexion.estado.in_(("activa", "error")))]
    return sum(1 for u in uids if lanzar(u))


def estado(db, uid: int) -> dict:
    con = db.query(DriveConexion).filter(DriveConexion.usuario_id == uid).first()
    if con is None:
        return {"configurado": configurado(), "conectado": False}
    subidos = db.query(DriveArchivo).filter(DriveArchivo.usuario_id == uid, ~DriveArchivo.ruta.like("dir:%"),
                                            DriveArchivo.drive_id != "-").count()
    return {"configurado": configurado(), "conectado": True, "correo": con.google_email,
            "estado": "sincronizando" if uid in _EN_CURSO else con.estado, "error": con.error,
            "subidos": subidos, "faltan": len(pendientes(db, uid)), "ultimo": con.ultimo.isoformat() if con.ultimo else None}
