"""Las pruebas nunca hablan con servicios reales aunque el .env de la PC tenga llaves (Resend, Mercado Pago, respaldo).
Cada prueba que necesite una llave la pone ella misma con monkeypatch."""
import pytest


@pytest.fixture(autouse=True)
def _sin_servicios_reales(monkeypatch):
    from app.config import settings
    for llave in ("resend_api_key", "respaldo_correo", "mp_access_token", "mp_webhook_secret", "paquetes_timbres"):
        monkeypatch.setattr(settings, llave, None)
