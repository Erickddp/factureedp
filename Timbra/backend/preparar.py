"""Primer arranque a prueba de todo: revisa Python, crea .env con llaves únicas y checa el puerto."""
import secrets
import socket
import sys
from pathlib import Path

AQUI = Path(__file__).parent

if sys.version_info < (3, 10):
    print(f"[X] Tienes Python {sys.version.split()[0]}. Timbra necesita 3.10 o más nuevo (recomendado 3.12).")
    sys.exit(1)

env = AQUI / ".env"
if not env.exists():
    txt = (AQUI / ".env.ejemplo").read_text(encoding="utf-8")
    txt = txt.replace("SECRET_KEY=\n", f"SECRET_KEY={secrets.token_urlsafe(48)}\n")
    txt = txt.replace("JWT_SECRET=\n", f"JWT_SECRET={secrets.token_urlsafe(48)}\n")
    env.write_text(txt, encoding="utf-8")
    print("[OK] Se creó backend\\.env con llaves únicas. RESPÁLDALO junto con la carpeta datos.")

(AQUI / "datos").mkdir(exist_ok=True)

s = socket.socket()
try:
    s.bind(("127.0.0.1", 8000))
except OSError:
    print("[i] Timbra ya está corriendo (el puerto 8000 está ocupado). Abriendo el navegador...")
    sys.exit(2)
finally:
    s.close()
print("[OK] Todo listo.")
