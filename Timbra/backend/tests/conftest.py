"""Una sola carpeta de datos de prueba, limpia al empezar la corrida.

Los archivos de prueba importan app.main (y entre sí) al recolectarse; si cada uno borrara _test_datos al importarse,
en Linux se borra la BD que otro ya abrió ("unable to open database file"). En Windows el borrado fallaba en silencio
porque la BD abierta está bloqueada, por eso allá pasaba.
"""
import os
import shutil
import time

shutil.rmtree("./_test_datos", ignore_errors=True)
os.environ.setdefault("DATA_DIR", "./_test_datos")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_datos/timbra.db")
os.environ["PROGRAMADOR"] = "False"

# Mismo reloj que el servidor (Dockerfile: TZ=America/Mexico_City). Las pruebas comparan datetime.now() contra ahora_mx():
# en una máquina en UTC difieren 6 h y las recurrentes "de hoy" todavía no vencen.
os.environ["TZ"] = "America/Mexico_City"
if hasattr(time, "tzset"):
    time.tzset()
