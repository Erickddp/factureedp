import smtplib
from email.message import EmailMessage

from ..config import settings


def enviar(para: list[str], asunto: str, cuerpo: str, adjuntos: list[tuple[str, bytes, str]]):
    if not settings.smtp_host:
        raise RuntimeError("Configura SMTP_HOST/SMTP_USER/SMTP_PASSWORD en .env para mandar correos.")
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = ", ".join(para)
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    for nombre, data, mime in adjuntos:
        main, sub = mime.split("/")
        msg.add_attachment(data, maintype=main, subtype=sub, filename=nombre)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
