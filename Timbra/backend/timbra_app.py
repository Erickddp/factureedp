"""Timbra para Windows: arranca el servidor en segundo plano y deja un ícono junto al reloj.

- Datos y llaves en %LOCALAPPDATA%\\Timbra (no se tocan al actualizar ni al desinstalar).
- Sólo escucha en 127.0.0.1: nadie de fuera entra a tu facturación.
- Una sola instancia: si ya está abierto, sólo abre el navegador.
"""
import os
import secrets
import shutil
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

HOME = Path(os.environ.get("TIMBRA_HOME") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Timbra")
PUERTOS = (8000, 8010, 8020)


def _ocupado(puerto: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def _es_timbra(puerto: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/health", timeout=2) as r:
            return b'"ok":true' in r.read()
    except Exception:
        return False


def preparar() -> None:
    """Carpeta de datos y .env con llaves únicas (sólo la primera vez; nunca se regeneran)."""
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "datos").mkdir(exist_ok=True)
    env = HOME / ".env"
    if not env.exists():
        env.write_text(
            "# Llaves de Timbra. RESPÁLDALO: sin SECRET_KEY no se descifran los CSD guardados.\n"
            f"SECRET_KEY={secrets.token_urlsafe(48)}\nJWT_SECRET={secrets.token_urlsafe(48)}\n"
            "ADMIN_EMAIL=rick@erickddp.com\nADMIN_PASSWORD=cambiame\nDEBUG=False\n"
            "DATA_DIR=./datos\nDATABASE_URL=sqlite:///./datos/timbra.db\n"
            "SMTP_HOST=\nSMTP_PORT=587\nSMTP_USER=\nSMTP_PASSWORD=\nSMTP_FROM=\n",
            encoding="utf-8",
        )
    os.chdir(HOME)  # config.py lee .env y ./datos desde aquí


def importar_anterior(origen: Path) -> str:
    """Trae .env y datos de la versión con INICIAR.bat (carpeta backend). Sólo si aquí no hay facturas."""
    if not (origen / ".env").exists() or not (origen / "datos").exists():
        return "Esa carpeta no tiene .env y datos. Elige la carpeta 'backend' de tu Timbra anterior."
    db = HOME / "datos" / "timbra.db"
    if db.exists() and db.stat().st_size > 200_000:
        return "Ya hay datos en esta instalación; no los sobrescribo. Respáldalos y bórralos primero."
    shutil.copy2(origen / ".env", HOME / ".env")
    shutil.copytree(origen / "datos", HOME / "datos", dirs_exist_ok=True)
    return "Listo. Cierra Timbra y vuelve a abrirlo para usar tus datos."


def servidor(puerto: int):
    import uvicorn

    from app.main import app  # importa después de chdir: así toma el .env de HOME

    cfg = uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="warning", log_config=None)
    return uvicorn.Server(cfg)


def bandeja(srv, url: str):
    """Ícono junto al reloj. Si pystray no está, Timbra corre igual sin ícono."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        while not srv.should_exit:
            time.sleep(1)
        return

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(11, 11, 12, 255))
    d.text((14, 20), "ED", fill=(255, 255, 255, 255))

    def respaldar(_icon=None, _item=None):
        from app.services import programador
        z = programador.respaldo_diario(HOME / "Respaldos") or "ya había respaldo de hoy"
        _icon.notify(f"Respaldo: {z}", "Timbra")

    def importar(_icon=None, _item=None):
        try:
            import tkinter as tk
            from tkinter import filedialog, messagebox
            root = tk.Tk()
            root.withdraw()
            carpeta = filedialog.askdirectory(title="Carpeta 'backend' de tu Timbra anterior")
            if carpeta:
                messagebox.showinfo("Timbra", importar_anterior(Path(carpeta)))
            root.destroy()
        except Exception as e:
            _icon.notify(f"No se pudo importar: {e}", "Timbra")

    def salir(icon, _item=None):
        srv.should_exit = True
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Abrir Timbra", lambda *_: webbrowser.open(url), default=True),
        pystray.MenuItem("Respaldar ahora", respaldar),
        pystray.MenuItem("Abrir carpeta de datos", lambda *_: os.startfile(HOME)),
        pystray.MenuItem("Importar datos de la versión anterior…", importar),
        pystray.MenuItem("Salir", salir),
    )
    pystray.Icon("Timbra", img, "Timbra · EDDP", menu).run()


def main():
    for p in PUERTOS:
        if _ocupado(p) and _es_timbra(p):
            webbrowser.open(f"http://localhost:{p}")
            return
    puerto = next((p for p in PUERTOS if not _ocupado(p)), None)
    if puerto is None:
        raise SystemExit("Los puertos 8000, 8010 y 8020 están ocupados.")
    preparar()
    srv = servidor(puerto)
    hilo = threading.Thread(target=srv.run, daemon=True)
    hilo.start()
    url = f"http://localhost:{puerto}"
    for _ in range(60):
        if srv.started:
            break
        time.sleep(0.5)
    if "--sin-navegador" not in sys.argv:
        webbrowser.open(url)
    bandeja(srv, url)
    hilo.join(timeout=10)


if __name__ == "__main__":
    main()
