from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Usuario
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class UsuarioIn(BaseModel):
    email: str
    nombre: str | None = None
    password: str
    admin: bool = False


class CambioIn(BaseModel):
    actual: str
    nueva: str


def asegurar_admin(db: Session):
    """Primer arranque: crea el admin del .env si no hay usuarios."""
    if not db.query(Usuario).count():
        db.add(Usuario(email=settings.admin_email.lower(), nombre="Administrador",
                       password_hash=hash_password(settings.admin_password), admin=True))
        db.commit()


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    u = db.query(Usuario).filter_by(email=data.email.strip().lower(), activo=True).first()
    if not u or not verify_password(data.password, u.password_hash):
        raise HTTPException(401, "Correo o contraseña incorrectos")
    return {"token": create_token(u.email), "nombre": u.nombre, "admin": u.admin}


@router.get("/yo")
def yo(email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = db.query(Usuario).filter_by(email=email).first()
    return {"email": u.email, "nombre": u.nombre, "admin": u.admin, "creado": u.creado}


class PerfilIn(BaseModel):
    nombre: str


@router.put("/yo")
def editar_yo(data: PerfilIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = db.query(Usuario).filter_by(email=email).first()
    nombre = data.nombre.strip()
    if not nombre:
        raise HTTPException(422, "Escribe tu nombre")
    u.nombre = nombre[:150]
    db.commit()
    return {"email": u.email, "nombre": u.nombre, "admin": u.admin, "creado": u.creado}


@router.post("/password")
def cambiar(data: CambioIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = db.query(Usuario).filter_by(email=email).first()
    if not verify_password(data.actual, u.password_hash):
        raise HTTPException(422, "La contraseña actual no coincide")
    if len(data.nueva) < 8:
        raise HTTPException(422, "Mínimo 8 caracteres")
    u.password_hash = hash_password(data.nueva)
    db.commit()
    return {"ok": True}


@router.get("/usuarios")
def usuarios(email: str = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": u.id, "email": u.email, "nombre": u.nombre, "admin": u.admin, "activo": u.activo}
            for u in db.query(Usuario).order_by(Usuario.email)]


@router.post("/usuarios")
def crear_usuario(data: UsuarioIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    yo_ = db.query(Usuario).filter_by(email=email).first()
    if not yo_.admin:
        raise HTTPException(403, "Sólo el admin da de alta usuarios")
    if db.query(Usuario).filter_by(email=data.email.lower()).first():
        raise HTTPException(409, "Ese correo ya existe")
    db.add(Usuario(email=data.email.lower(), nombre=data.nombre, password_hash=hash_password(data.password), admin=data.admin))
    db.commit()
    return {"ok": True}
