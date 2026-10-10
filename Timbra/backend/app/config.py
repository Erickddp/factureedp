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


settings = Settings()

import os as _os  # noqa: E402

_os.makedirs(settings.data_dir, exist_ok=True)
_os.makedirs(_os.path.join(settings.data_dir, "respaldo_xml"), exist_ok=True)
