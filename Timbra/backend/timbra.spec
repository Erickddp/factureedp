# PyInstaller: empaqueta Timbra (Python + front compilado) en una carpeta con Timbra.exe.
# Uso: CONSTRUIR_INSTALADOR.bat (o: .venv\Scripts\pyinstaller timbra.spec --noconfirm)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [("static", "static"), ("migraciones", "migraciones"), ("alembic.ini", ".")]
datas += collect_data_files("satcfdi")   # catálogos SAT, XSLT, plantillas del PDF
datas += collect_data_files("tzdata")    # zona horaria America/Mexico_City
hidden = (collect_submodules("satcfdi") + collect_submodules("uvicorn") + collect_submodules("app")
          + ["alembic", "pystray._win32", "tkinter", "tkinter.filedialog", "tkinter.messagebox"])

a = Analysis(["timbra_app.py"], pathex=["."], datas=datas, hiddenimports=hidden,
             excludes=["pytest"], noarchive=False)  # weasyprint va incluido: satcfdi lo importa siempre
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Timbra", console=False,
          icon="../instalador/timbra.ico", version=None, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Timbra", upx=False)
