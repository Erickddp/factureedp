"""La e.firma para bajar del SAT: se pone cada vez y NUNCA se guarda.

La e.firma equivale a la firma autógrafa del contribuyente. Por eso aquí no toca el disco ni la base de datos: se
valida, se deja abierta EN MEMORIA sólo para hablar con el SAT, y se borra al terminar la descarga, al pasar el tiempo
de espera, al pedirlo el usuario o al reiniciar el servidor. No hay forma de recuperarla después: se vuelve a poner.
"""
import threading
import time
from datetime import datetime, timezone

from cryptography import x509

from ..xmlsat.certificado import RE_RFC

ESPERA = 2 * 60 * 60    # puesta y sin usar: 2 horas y se olvida
MAXIMO = 3 * 60 * 60    # ni con una descarga larga vive más de 3 horas

_candado = threading.Lock()
_vivas: dict[int, dict] = {}  # emisor_id -> {fiel, rfc, nombre, vence, hasta, tope, usuario_id, ocupada}


class EfirmaError(ValueError):
    """Mensaje listo para mostrarse a quien subió los archivos."""


def leer(cer: bytes, llave: bytes, clave: str) -> dict:
    """Revisa que .cer, .key y contraseña sean una e.firma vigente y pareja. Devuelve rfc, nombre, vencimiento y la firma
    abierta (objeto en memoria)."""
    if not cer or not llave or len(cer) > 64 * 1024 or len(llave) > 64 * 1024:
        raise EfirmaError("Sube el .cer y el .key de tu e.firma tal como los entrega el SAT (pesan unos cuantos KB).")
    try:
        cert = x509.load_der_x509_certificate(cer)
    except Exception:
        raise EfirmaError("El .cer no es un certificado válido. Sube el archivo .cer de tu e.firma tal como lo entrega el SAT.")
    valores = [str(a.value).strip() for a in cert.subject]
    rfc = next((m.group(1) for m in (RE_RFC.search(v.upper()) for v in valores) if m), None)
    if not rfc:
        raise EfirmaError("No encontré el RFC dentro del .cer. ¿Es el certificado de la e.firma?")
    nombre = next((v for v in valores if len(v) > 3 and " " in v and not RE_RFC.search(v.upper())), "")
    try:
        uso = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        if not (uso.key_agreement or uso.data_encipherment):
            raise EfirmaError("Ese certificado es un CSD (el sello para facturar). Para descargar del SAT se necesita la e.firma (FIEL).")
    except x509.ExtensionNotFound:
        pass
    vence = cert.not_valid_after_utc
    if vence < datetime.now(timezone.utc):
        raise EfirmaError(f"Esa e.firma venció el {vence:%d/%m/%Y}. Renuévala en el SAT y pon la nueva.")
    if not clave:
        raise EfirmaError("Falta la contraseña de la llave privada.")
    try:
        from cfdiclient import Fiel
        fiel = Fiel(cer, llave, clave)
    except Exception:
        raise EfirmaError("No abrió la llave: la contraseña no coincide con el .key, o ese archivo no es el .key de la e.firma.")
    if fiel.key.n != cert.public_key().public_numbers().n:
        raise EfirmaError("El .cer y el .key no son pareja: pertenecen a e.firmas distintas.")
    return {"rfc": rfc, "nombre": nombre, "vence": vence.date().isoformat(), "fiel": fiel}


def _limpiar(ahora: float) -> None:
    for k in [k for k, v in _vivas.items() if ahora >= (v["tope"] if v["ocupada"] else v["hasta"])]:
        _vivas.pop(k, None)


def poner(emisor_id: int, usuario_id: int | None, datos: dict) -> dict:
    """Deja la e.firma abierta en memoria para este emisor. `datos` es lo que devuelve leer()."""
    ahora = time.time()
    with _candado:
        _limpiar(ahora)
        _vivas[emisor_id] = {"fiel": datos["fiel"], "rfc": datos["rfc"], "nombre": datos["nombre"], "vence": datos["vence"],
                             "hasta": ahora + ESPERA, "tope": ahora + MAXIMO, "usuario_id": usuario_id, "ocupada": False}
    return estado(emisor_id)


def tomar(emisor_id: int):
    """La firma abierta (o None si no hay o ya se olvidó). Usarla le da otras 2 horas (nunca más allá del tope)."""
    ahora = time.time()
    with _candado:
        _limpiar(ahora)
        v = _vivas.get(emisor_id)
        if not v:
            return None
        v["hasta"] = min(ahora + ESPERA, v["tope"])
        return v["fiel"]


def ocupar(emisor_id: int, ocupada: bool) -> None:
    """Mientras corre una descarga no se olvida por inactividad (sí por el tope de 3 horas)."""
    with _candado:
        v = _vivas.get(emisor_id)
        if v:
            v["ocupada"] = ocupada
            v["hasta"] = min(time.time() + ESPERA, v["tope"])


def olvidar(emisor_id: int) -> bool:
    with _candado:
        return _vivas.pop(emisor_id, None) is not None


def estado(emisor_id: int) -> dict:
    """Lo que la pantalla puede saber: si hay e.firma puesta, de quién, y cuánto le queda. Nunca la firma misma."""
    ahora = time.time()
    with _candado:
        _limpiar(ahora)
        v = _vivas.get(emisor_id)
        if not v:
            return {"puesta": False}
        resta = (v["tope"] if v["ocupada"] else v["hasta"]) - ahora
        return {"puesta": True, "rfc": v["rfc"], "nombre": v["nombre"], "vence": v["vence"], "minutos": max(1, int(resta // 60)),
                "en_uso": v["ocupada"]}


def olvidar_todas() -> None:
    with _candado:
        _vivas.clear()
