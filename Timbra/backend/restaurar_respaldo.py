"""Abre un respaldo cifrado de Timbra (.timbra, el que llega por correo cada día) y lo deja como .zip.

Uso (en Timbra\\backend, con el mismo .env del servidor, o sea la misma SECRET_KEY):
    .venv\\Scripts\\python restaurar_respaldo.py timbra_20261014.timbra

Deja timbra_20261014.zip junto al archivo. Adentro viene la carpeta `datos/` (timbra.db y los XML). Los pasos para
volver a ponerla en el servidor o en tu PC están en DESPLEGAR.md → «Restaurar un respaldo».
"""
import sys
import zipfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    origen = Path(sys.argv[1])
    if not origen.exists():
        print(f"No existe {origen}")
        return 1
    from cryptography.fernet import InvalidToken

    from app.security import decrypt
    try:
        datos = decrypt(origen.read_bytes())
    except InvalidToken:
        print("No se pudo abrir: la SECRET_KEY de tu .env no es la del servidor que hizo este respaldo.")
        return 2
    destino = origen.with_suffix(".zip")
    destino.write_bytes(datos)
    with zipfile.ZipFile(destino) as z:
        nombres = z.namelist()
        malo = z.testzip()
    if malo:
        print(f"El respaldo está dañado (falla en {malo}).")
        return 3
    print(f"Listo: {destino} ({len(nombres)} archivos, {destino.stat().st_size // 1024:,} KB).")
    print("Revisa que traiga datos/timbra.db:", "sí" if "datos/timbra.db" in nombres else "NO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
