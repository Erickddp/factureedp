from datetime import datetime, timezone

from satcfdi.models import Signer

from ..logs import log
from ..models import Emisor
from ..security import decrypt, encrypt


class CsdError(Exception):
    pass


def motivo(e: Exception, que: str) -> str:
    """Traduce el error de abrir un .cer/.key a algo que se pueda corregir. `que` = "CSD" o "e.firma"."""
    otro = "e.firma" if que == "CSD" else "CSD"
    t = str(e).lower()
    if "password" in t or "decrypt" in t or "bad decrypt" in t:
        return (f"La contraseña no abre ese archivo .key. Revisa mayúsculas y que sea la contraseña de la clave privada "
                f"del {que} (no la del {otro} ni la del portal del SAT).")
    if "match" in t or "mismatch" in t:
        return f"El .cer y el .key no son pareja: sube los dos archivos del mismo {que}."
    if "asn1" in t or "parse" in t or "load" in t or "der" in t or "pem" in t:
        return f"No pude leer los archivos. Sube el .cer y el .key originales del SAT del {que}, sin renombrar ni convertir."
    return f"No pude abrir el {que}: {e}"


def cargar_csd(emisor: Emisor, cer: bytes, key: bytes, password: str) -> Signer:
    try:
        s = Signer.load(certificate=cer, key=key, password=password)
    except Exception as e:
        log.warning("CSD rechazado para %s: %s: %s", emisor.rfc, type(e).__name__, e)
        raise CsdError(motivo(e, "CSD")) from e
    if s.rfc.upper() != emisor.rfc.upper():
        raise CsdError(f"El CSD es de {s.rfc}, no de {emisor.rfc}. Aguas.")
    if getattr(s, "type", None) is not None and s.type.name.upper() != "CSD":
        raise CsdError("Eso es una e.firma (FIEL), no un CSD. Sube el Certificado de Sello Digital.")
    emisor.cer = cer
    emisor.key_enc = encrypt(key)
    emisor.key_password_enc = encrypt(password)
    emisor.no_certificado = s.certificate_number
    emisor.csd_vence = _vence(s)
    log.info("CSD cargado para %s · No. %s · vence %s", emisor.rfc, s.certificate_number, emisor.csd_vence)
    return s


def _vence(s: Signer) -> datetime | None:
    cert = s.certificate
    if hasattr(cert, "get_notAfter"):  # pyOpenSSL
        return datetime.strptime(cert.get_notAfter().decode()[:14], "%Y%m%d%H%M%S")
    if hasattr(cert, "not_valid_after_utc"):  # cryptography
        return cert.not_valid_after_utc.replace(tzinfo=None)
    return None


def signer_de(emisor: Emisor, permitir_vencido: bool = False) -> Signer:
    """permitir_vencido=True sólo en modo demo/pruebas (los CSD de prueba del SAT ya vencieron)."""
    if not emisor.cer or not emisor.key_enc:
        raise CsdError(f"{emisor.rfc} no tiene CSD cargado.")
    if not permitir_vencido and emisor.csd_vence and emisor.csd_vence < datetime.now(timezone.utc).replace(tzinfo=None):
        raise CsdError(f"El CSD de {emisor.rfc} ya venció ({emisor.csd_vence:%d/%m/%Y}).")
    return Signer.load(
        certificate=emisor.cer,
        key=decrypt(emisor.key_enc),
        password=decrypt(emisor.key_password_enc).decode(),
    )
