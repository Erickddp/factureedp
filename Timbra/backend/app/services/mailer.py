"""Correo de salida. La cuenta se configura desde la app (Configuración → PAC y usuarios → Correo de envío) y se guarda en
datos/correo.json con la contraseña cifrada; si no existe, se usan los SMTP_* del .env (compatibilidad)."""
import base64
import json
import os
import re
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


def por_api() -> bool:
    """En el servidor web el correo sale por la API de Resend (Railway bloquea los puertos SMTP en el plan Hobby)."""
    return bool(settings.resend_api_key)


def publica() -> dict:
    """Lo que se puede mostrar en pantalla: nunca la contraseña."""
    if por_api():
        return {"configurado": True, "host": "api.resend.com", "port": 443, "user": settings.correo_remitente, "remitente": settings.correo_remitente,
                "nombre": "", "tiene_password": True, "origen": "resend"}
    c = config()
    return {"configurado": bool(c["host"] and c["user"] and c["password"]), "host": c["host"] or "", "port": c["port"], "user": c["user"] or "",
            "remitente": c["remitente"] or "", "nombre": c["nombre"], "tiene_password": bool(c["password"]), "origen": c["origen"]}


def guardar(host: str, port: int, user: str, password: str | None, remitente: str | None, nombre: str | None) -> dict:
    previo = config()
    pw = (password or "").replace(" ", "") or (previo["password"] if previo.get("user") == user else None)
    if not pw:
        raise CorreoError("Escribe la contraseña de aplicación del correo.")
    if "gmail" in host and password and not (len(pw) == 16 and pw.isalpha()):
        raise CorreoError("Esa no es una contraseña de aplicación de Gmail: son 16 letras que genera Google en "
                          "myaccount.google.com/apppasswords (necesitas tener activada la verificación en 2 pasos). "
                          "La contraseña normal de tu cuenta no funciona aquí.")
    os.makedirs(settings.data_dir, exist_ok=True)
    with open(_ruta(), "w", encoding="utf-8") as fh:
        json.dump({"host": host.strip(), "port": int(port), "user": user.strip(), "remitente": (remitente or user).strip(),
                   "nombre": (nombre or "").strip(), "password_enc": base64.b64encode(encrypt(pw)).decode()}, fh)
    return publica()


def quitar() -> dict:
    try:
        os.remove(_ruta())
    except FileNotFoundError:
        pass
    return publica()


GMAIL_APP = ("Gmail no aceptó la contraseña. No sirve la de tu cuenta: necesitas una «contraseña de aplicación» de 16 letras "
             "(myaccount.google.com/apppasswords, con la verificación en 2 pasos activada). Cámbiala en «Cambiar cuenta».")


def _explica(e: Exception, c: dict, paso: str = "") -> str:
    t = str(e)
    gmail = "gmail" in (c["host"] or "")
    # Gmail a veces corta la conexión en lugar de contestar "contraseña incorrecta"
    if paso == "entrar" and isinstance(e, smtplib.SMTPServerDisconnected):
        return GMAIL_APP if gmail else "El servidor cortó la conexión al iniciar sesión: revisa usuario y contraseña."
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "El servidor rechazó la dirección del destinatario. Revisa que el correo esté bien escrito."
    if isinstance(e, smtplib.SMTPAuthenticationError):
        if gmail:
            return GMAIL_APP
        return "El servidor de correo no aceptó el usuario o la contraseña."
    if isinstance(e, (TimeoutError, OSError)) and not isinstance(e, smtplib.SMTPException):
        return f"No pude conectar con {c['host']}:{c['port']}. Revisa tu internet y el servidor de correo."
    return f"El correo no salió: {t}"


CORREO_OK = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


def _limpios(correos: list[str]) -> list[str]:
    # sin comas, espacios ni vacíos (una coma de más hacía que el servidor cortara la conexión), y sin el punto o la
    # coma que se cuela al final al copiar de un texto («cliente@gmail.com.»)
    return [x for x in (re.sub(r"[\s,;<>]+", "", p or "").strip(".") for p in correos) if "@" in x]


def destinatarios(emisor, para: list[str]) -> list[str]:
    """A quién se manda un comprobante de este emisor. Si timbra en PRUEBAS (PAC demo o ambiente de pruebas), su correo
    NUNCA llega al cliente: va a CORREO_PRUEBAS, o no sale. Así una prueba no le manda una factura sin validez a un
    cliente real (ni rebota en direcciones inventadas y daña la reputación del dominio)."""
    pac = getattr(emisor, "pac", None)
    if pac is not None and pac.proveedor != "demo" and not pac.pruebas:
        return para
    if settings.correo_pruebas:
        return [settings.correo_pruebas]
    raise CorreoError("Es un comprobante de PRUEBAS (el emisor timbra en modo demo o con un PAC en ambiente de pruebas): "
                      "no se manda al cliente. Para probar el correo de envío pon la variable CORREO_PRUEBAS con tu correo "
                      "(en el .env de tu PC o en Railway) y te llegará a ti.")


# Dominios que no existen: los reservados para ejemplos (RFC 2606) y los de relleno en español. Un correo ahí rebota, y
# cada rebote le baja la reputación a facturas@erickddp.com (con muchos, los correos de verdad empiezan a caer en spam).
RELLENO = re.compile(r"@(?:[\w-]+\.)*(?:example|ejemplo|dominio|tudominio|midominio)\.[a-z.]+$|\.(?:test|example|invalid|localhost)$", re.I)


def _validos(para: list[str]) -> list[str]:
    malos = [x for x in para if not CORREO_OK.match(x)]
    if malos:
        raise CorreoError(f"Revisa {'el correo' if len(malos) == 1 else 'los correos'} {', '.join(malos)}: "
                          "no tiene la forma nombre@dominio.com.")
    falsos = [x for x in para if RELLENO.search(x)]
    if falsos:
        raise CorreoError(f"{', '.join(falsos)} {'es una dirección' if len(falsos) == 1 else 'son direcciones'} de ejemplo que no "
                          "existe: el correo rebotaría y eso daña la reputación de tu dominio de envío. Pon el correo real del cliente.")
    return para


def _resend(para: list[str], asunto: str, cuerpo: str, adjuntos: list[tuple[str, bytes, str]], nombre: str | None, responder_a: str | None):
    """Envío por https://api.resend.com: sale de la dirección de Timbra con el nombre del emisor, y las respuestas
    le llegan al emisor (reply_to)."""
    import requests
    nombre = re.sub(r'[<>"]', "", nombre or "Timbra").strip() or "Timbra"
    cuerpo_json = {"from": f"{nombre} <{settings.correo_remitente}>", "to": para, "subject": asunto, "text": cuerpo,
                   "attachments": [{"filename": n, "content": base64.b64encode(d).decode()} for n, d, _m in adjuntos]}
    responder = _limpios([responder_a or ""])
    if responder:
        cuerpo_json["reply_to"] = responder
    try:
        r = requests.post("https://api.resend.com/emails", json=cuerpo_json, timeout=30,
                          headers={"Authorization": f"Bearer {settings.resend_api_key}"})
    except requests.RequestException as e:
        raise CorreoError(f"No pude conectar con el servicio de correo: {e}") from e
    if r.status_code >= 300:
        try:
            detalle = r.json().get("message") or r.text
        except ValueError:
            detalle = r.text
        propio = re.search(r"own email address \(([^)]+)\)", detalle)
        if propio:  # cuenta de Resend sin dominio verificado: sólo deja mandar al correo con que se abrió
            detalle = (f"Resend sigue en modo de prueba y sólo deja enviar a {propio.group(1)}. Verifica tu dominio en "
                       f"resend.com/domains para enviar a cualquier cliente")
        elif r.status_code in (401, 403) and "domain" in detalle.lower():
            detalle = f"el dominio de {settings.correo_remitente} aún no está verificado en Resend ({detalle})"
        elif r.status_code in (401, 403):
            detalle = f"la llave RESEND_API_KEY no es válida ({detalle})"
        elif r.status_code == 429:
            detalle = "se alcanzó el límite de envíos del plan de Resend; reintenta más tarde"
        raise CorreoError(f"El correo no salió: {detalle}")


def enviar(para: list[str], asunto: str, cuerpo: str, adjuntos: list[tuple[str, bytes, str]],
           nombre: str | None = None, responder_a: str | None = None):
    """nombre: con qué nombre aparece el remitente (el del emisor). responder_a: a dónde llegan las respuestas."""
    para = _limpios(para)
    if not para:
        raise CorreoError("No hay un correo de destino válido.")
    _validos(para)
    if por_api():
        return _resend(para, asunto, cuerpo, adjuntos, nombre, responder_a)
    c = config()
    if not (c["host"] and c["user"] and c["password"]):
        raise CorreoError("Falta configurar el correo de envío: Configuración → PAC y usuarios → Correo de envío.")
    msg = EmailMessage()
    if responder_a and _limpios([responder_a]):
        msg["Reply-To"] = _limpios([responder_a])[0]
    msg["From"] = formataddr((c["nombre"], c["remitente"])) if c["nombre"] else c["remitente"]
    msg["To"] = ", ".join(para)
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    for nombre, data, mime in adjuntos:
        main, sub = mime.split("/")
        msg.add_attachment(data, maintype=main, subtype=sub, filename=nombre)
    paso = "conectar"
    try:
        if c["port"] == 465:
            s = smtplib.SMTP_SSL(c["host"], c["port"], timeout=25)
        else:
            s = smtplib.SMTP(c["host"], c["port"], timeout=25)
            s.starttls()
        with s:
            paso = "entrar"
            s.login(c["user"], c["password"])
            paso = "enviar"
            s.send_message(msg, to_addrs=para)
    except Exception as e:
        raise CorreoError(_explica(e, c, paso)) from e
