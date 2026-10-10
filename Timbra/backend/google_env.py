"""Pasa las credenciales de Google al .env sin mostrarlas.

Uso: descarga el JSON del cliente de OAuth (botón "Descargar JSON" en Google Cloud) y corre
    python google_env.py            (lo busca en esta carpeta y en Descargas)
    python google_env.py ruta.json  (o dale la ruta)
Escribe GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET y GOOGLE_REDIRECT_URI en .env. El secreto no se imprime.
"""
import glob
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def buscar() -> str | None:
    if len(sys.argv) > 1:
        return sys.argv[1]
    candidatos = glob.glob(os.path.join(AQUI, "client_secret*.json")) + \
        glob.glob(os.path.join(os.path.expanduser("~"), "Downloads", "client_secret*.json"))
    return max(candidatos, key=os.path.getmtime) if candidatos else None


def main() -> int:
    ruta = buscar()
    if not ruta or not os.path.exists(ruta):
        print("No encontré el archivo client_secret_....json. Descárgalo de Google Cloud (Clientes → tu cliente → Descargar JSON).")
        return 1
    datos = json.load(open(ruta, encoding="utf-8"))
    c = datos.get("web") or datos.get("installed") or {}
    cid, secreto = c.get("client_id"), c.get("client_secret")
    if not cid or not secreto:
        print("Ese archivo no trae client_id y client_secret: ¿es el JSON del cliente de OAuth?")
        return 1
    redirect = next((u for u in c.get("redirect_uris", []) if "localhost" in u), None) or (c.get("redirect_uris") or [""])[0]
    env = os.path.join(AQUI, ".env")
    txt = open(env, encoding="utf-8").read() if os.path.exists(env) else ""
    for k, v in (("GOOGLE_CLIENT_ID", cid), ("GOOGLE_CLIENT_SECRET", secreto), ("GOOGLE_REDIRECT_URI", redirect)):
        if not v:
            continue
        linea = f"{k}={v}"
        txt = re.sub(rf"^{k}=.*$", lambda _m: linea, txt, flags=re.M) if re.search(rf"^{k}=", txt, flags=re.M) else txt.rstrip("\n") + "\n" + linea + "\n"
    open(env, "w", encoding="utf-8").write(txt)
    print(f"Listo. Cliente {cid[:12]}…{cid[-28:]} guardado en .env (el secreto no se muestra).")
    print(f"Redirección: {redirect or '(ninguna en el archivo)'}")
    print(f"Archivo leído: {ruta}. Ya puedes borrarlo o guardarlo en un lugar seguro; no lo dejes en Descargas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
