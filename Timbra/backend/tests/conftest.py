"""Configuración común de las pruebas.

1) Una sola carpeta de datos de prueba, limpia al empezar la corrida. Los archivos de prueba importan app.main (y entre sí) al
   recolectarse; si cada uno borrara _test_datos al importarse, en Linux se borra la BD que otro ya abrió ("unable to open
   database file"). En Windows el borrado fallaba en silencio porque la BD abierta está bloqueada, por eso allá pasaba.
2) Las pruebas nunca hablan con servicios reales aunque el .env de la PC tenga llaves (Resend, Mercado Pago, respaldo).
   Cada prueba que necesite una llave la pone ella misma con monkeypatch.
"""
import os
import shutil
import time

import pytest

shutil.rmtree("./_test_datos", ignore_errors=True)
os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"
# El administrador de las pruebas es siempre el de ejemplo, aunque el .env de la PC ya traiga el real (si no, ningún login sirve)
os.environ["ADMIN_EMAIL"] = "rick@erickddp.com"
os.environ["ADMIN_PASSWORD"] = "cambiame"
# Llave de prueba de 32+ bytes: la de ejemplo es corta y PyJWT avisa en cada token.
os.environ.setdefault("JWT_SECRET", "jwt-de-pruebas-" + "x" * 40)

# Mismo reloj que el servidor (Dockerfile: TZ=America/Mexico_City). Las pruebas comparan datetime.now() contra ahora_mx():
# en una máquina en UTC difieren 6 h y las recurrentes "de hoy" todavía no vencen.
os.environ["TZ"] = "America/Mexico_City"
if hasattr(time, "tzset"):
    time.tzset()


@pytest.fixture(autouse=True)
def _sin_servicios_reales(monkeypatch):
    from app.config import settings
    for llave in ("resend_api_key", "respaldo_correo", "correo_pruebas", "mp_access_token", "mp_webhook_secret", "paquetes_timbres",
                  "smtp_host", "smtp_user", "smtp_password", "smtp_from", "google_client_id", "google_client_secret"):
        monkeypatch.setattr(settings, llave, None)
    monkeypatch.setattr(settings, "registro_abierto", False)
