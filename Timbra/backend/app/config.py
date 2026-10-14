from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: str = "./datos"
    database_url: str = "sqlite:///./datos/timbra.db"
    # Llave Fernet para cifrar CSD y contraseñas de PAC en la BD.
    # Genérala con: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
    secret_key: str = "CAMBIA-ESTO-cK1r0Z7Yq3dX9mB2vN5wL8tH4sF6gJ0aP1uE3iO7yR2e="
    jwt_secret: str = "cambia-este-secreto-jwt"
    admin_email: str = "rick@erickddp.com"
    admin_password: str = "cambiame"
    cors_origins: str = "http://localhost:3000"
    timezone: str = "America/Mexico_City"
    debug: bool = True  # errores con traza completa en la consola de depuración
    programador: bool = True  # recurrentes, descarga SAT, cobranza y respaldo diario en segundo plano

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    # En el servidor (Railway Hobby bloquea SMTP): correo por la API HTTPS de Resend. Si hay llave, se usa en vez de SMTP.
    resend_api_key: str | None = None
    correo_remitente: str = "facturas@erickddp.com"  # dirección del dominio verificado en Resend
    respaldo_correo: str | None = None  # a dónde mandar cada día el respaldo cifrado (fuera del servidor)

    # Inicio de sesión con Google, Drive y Sheets (cliente de OAuth del proyecto de Google Cloud "Timbra").
    # Se llenan con: python google_env.py  (lee el JSON descargado de Google; el secreto nunca va al repositorio)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    front_url: str = ""  # sólo si las pantallas viven en otra dirección (Vercel): a dónde regresar tras Google
    registro_abierto: bool = False  # True = cualquiera con Google crea su cuenta; False = sólo cuentas que dé de alta el admin


settings = Settings()

# ---- Candados para cuando Timbra corre en internet (Railway u otro servidor) ----
# En tu PC no aplican. En web, arrancar con las llaves o la contraseña de ejemplo dejaría los CSD al alcance de cualquiera.
import os as _os0  # noqa: E402

EN_WEB = bool(_os0.environ.get("RAILWAY_ENVIRONMENT") or _os0.environ.get("ENTORNO", "").lower() == "web")
if EN_WEB:
    _faltas = []
    if settings.secret_key.startswith("CAMBIA-ESTO") or len(settings.secret_key) < 32:
        _faltas.append("SECRET_KEY (llave que cifra los CSD): pon una larga y aleatoria, y guárdala; sin ella no se descifran")
    if settings.jwt_secret == "cambia-este-secreto-jwt" or len(settings.jwt_secret) < 32:
        _faltas.append("JWT_SECRET: pon otra cadena larga y aleatoria")
    if settings.admin_password == "cambiame" or len(settings.admin_password) < 10:
        _faltas.append("ADMIN_PASSWORD: la contraseña inicial no puede ser la de ejemplo (mínimo 10 caracteres)")
    if _faltas:
        raise SystemExit("Timbra NO arranca en web con valores de ejemplo. Define estas variables en el servidor:\n  - " + "\n  - ".join(_faltas))
    settings.debug = _os0.environ.get("DEBUG", "false").lower() == "true"  # en web, sin trazas a menos que se pidan

import os as _os  # noqa: E402

_os.makedirs(settings.data_dir, exist_ok=True)
_os.makedirs(_os.path.join(settings.data_dir, "respaldo_xml"), exist_ok=True)
