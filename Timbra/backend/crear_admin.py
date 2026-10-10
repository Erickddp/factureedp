"""Crea (o restablece) una cuenta de administrador para PRUEBAS en esta PC.

Uso:  python crear_admin.py [usuario] [contraseña]      (sin argumentos: admin / admin)

Antes de tocar nada respalda la base en datos/. En un servidor, Timbra no deja entrar con contraseñas de práctica
(admin, cambiame…): ahí usa una contraseña de verdad.
"""
import os
import sqlite3
import sys
from datetime import datetime

from app.config import settings
from app.db import SessionLocal
from app.main import migrar
from app.models import Usuario
from app.security import hash_password


def main() -> int:
    usuario = (sys.argv[1] if len(sys.argv) > 1 else "admin").strip().lower()
    clave = sys.argv[2] if len(sys.argv) > 2 else "admin"
    if settings.database_url.startswith("sqlite"):
        origen = settings.database_url.split("///", 1)[1]
        if os.path.exists(origen):
            copia = os.path.join(settings.data_dir, f"timbra_antes_de_cuentas_{datetime.now():%Y%m%d_%H%M%S}.db")
            a, b = sqlite3.connect(origen), sqlite3.connect(copia)
            with b:
                a.backup(b)
            a.close(); b.close()
            print(f"Respaldo: {copia}")
    migrar()
    with SessionLocal() as db:
        u = db.query(Usuario).filter(Usuario.usuario == usuario).first()
        if u is None:
            u = Usuario(email=f"{usuario}@timbra.local", usuario=usuario, nombre="Administrador", admin=True,
                        password_hash=hash_password(clave))
            db.add(u)
            hecho = "creada"
        else:
            u.password_hash, u.admin, u.activo = hash_password(clave), True, True
            hecho = "restablecida"
        db.commit()
        print(f"Cuenta de administrador {hecho}: usuario «{usuario}». Total de cuentas: {db.query(Usuario).count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
