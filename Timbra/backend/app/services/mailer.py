"""Correo de salida. La cuenta se configura desde la app (Configuración → PAC y usuarios → Correo de envío) y se guarda en
datos/correo.json con la contraseña cifrada; si no existe, se usan los SMTP_* del .env (compatibilidad)."""
import base64
import json
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from ..config import settings
from ..security import decrypt, encrypt

PRESETS = {
    "gmail": {"host": "smtp.gmail.com", "port": 587},
    "outlook": {"host": "smtp.office365.com", "port": 587},
}


class CorreoError(RuntimeError):
    pass


def _ruta() -> str:
    return os.path.join(settings.data_dir, "correo.json")


def config() -> dict:
    """host, port, user, password (en claro, sólo en memoria), remitente, nombre."""
    try:
        with open(_ruta(), encoding="utf-8") as fh:
            c = json.load(fh)
        pw = decrypt(base64.b64decode(c["password_enc"])).decode() if c.get("password_enc") else None
        return {"host": c.get("host"), "port": int(c.get("port") or 587), "user": c.get("user"), "password": pw,
                "remitente": c.get("remitente") or c.get("user"), "nombre": c.get("nombre") or "", "origen": "app"}
    except FileNotFoundError:
        pass
    except Exception as e:  # archivo dañado o llave distinta: no se truena, se avisa al mandar
        return {"host": None, "port": 587, "user": None, "password": None, "remitente": None, "nombre": "", "origen": "app", "error": str(e)}
    return {"host": settings.smtp_host, "port": settings.smtp_port, "user": settings.smtp_user, "password": settings.smtp_password,
            "remitente": settings.smtp_from or settings.smtp_user, "nombre": "", "origen": "env" if settings.smtp_host else None}


def publica() -> dict:
    """Lo que se puede mostrar en pantalla: nunca la contraseña."""
    c = config()
    return {"configurado": bool(c["host"] and c["user"] and c["password"]), "host": c["host"] or "", "port": c["port"], "user": c["user"] or "",
            "remitente": c["remitente"] or "", "nombre": c["nombre"], "tiene_password": bool(c["password"]), "origen": c["origen"]}


def guardar(host: str, port: int, user: str, password: str | None, remitente: str | None, nombre: str | None) -> dict:
    previo = config()
    pw = password or (previo["password"] if previo.get("user") == user else None)
    if not pw:
        raise CorreoError("Escribe la contraseña de aplicación del correo.")
    os.makedirs(settings.data_dir, exist_ok=True)
    with open(_ruta(), "w", encoding="utf-8") as fh:
        json.dump({"host": host.strip(), "port": int(port), "user": user.strip(), "remitente": (remitente or user).strip(),
                   "nombre": (nombre or "").strip(), "password_enc": base64.b64encode(encrypt(pw.replace(" ", ""))).decode()}, fh)
    return publica()


def quitar() -> dict:
    try:
        os.remove(_ruta())
    except FileNotFoundError:
        pass
    return publica()


def _explica(e: Exception, c: dict) -> str:
    t = str(e)
    if isinstance(e, smtplib.SMTPAuthenticationError):
        if "gmail" in (c["host"] or ""):
            return ("Gmail no aceptó la contraseña. No sirve la de tu cuenta: necesitas una «contraseña de aplicación» "
                    "(Cuenta de Google → Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones).")
        return "El servidor de correo no aceptó el usuario o la contraseña."
    if isinstance(e, (TimeoutError, OSError)) and not isinstance(e, smtplib.SMTPException):
        return f"No pude conectar con {c['host']}:{c['port']}. Revisa tu internet y el servidor de correo."
    return f"El correo no salió: {t}"


def enviar(para: list[str], asunto: str, cuerpo: str, adjuntos: list[tuple[str, bytes, str]]):
    c = config()
    if not (c["host"] and c["user"] and c["password"]):
        raise CorreoError("Falta configurar el correo de envío: Configuración → PAC y usuarios → Correo de envío.")
    msg = EmailMessage()
    msg["From"] = formataddr((c["nombre"], c["remitente"])) if c["nombre"] else c["remitente"]
    msg["To"] = ", ".join(para)
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    for nombre, data, mime in adjuntos:
        main, sub = mime.split("/")
        msg.add_attachment(data, maintype=main, subtype=sub, filename=nombre)
    try:
        if c["port"] == 465:
            s = smtplib.SMTP_SSL(c["host"], c["port"], timeout=25)
        else:
            s = smtplib.SMTP(c["host"], c["port"], timeout=25)
            s.starttls()
        with s:
            s.login(c["user"], c["password"])
            s.send_message(msg)
    except Exception as e:
        raise CorreoError(_explica(e, c)) from e
