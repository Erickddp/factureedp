"""«Mis datos»: qué guarda Timbra de la cuenta, el aviso de novedades (opcional) y cerrar la cuenta uno mismo."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..logs import log
from ..models import Cliente, Emisor, Factura, Plantilla, Usuario, XmlCfdi
from ..security import current_user

router = APIRouter(prefix="/mis-datos", tags=["mis-datos"], dependencies=[Depends(current_user)])


def _propia(db: Session, email: str) -> Usuario:
    if db.info.get("soporte"):
        raise HTTPException(403, "En modo soporte esto no se puede: es una decisión de la persona dueña de la cuenta.")
    u = db.query(Usuario).filter_by(email=email, activo=True).first()
    if not u:
        raise HTTPException(401, "Tu sesión ya no es válida. Vuelve a entrar.")
    return u


@router.get("")
def ver(email: str = Depends(current_user), db: Session = Depends(get_db)):
    from ..legal import TERMINOS_VERSION
    u = _propia(db, email)
    n = lambda m: db.query(func.count(m.id)).scalar() or 0  # noqa: E731 — cada cuenta cuenta sólo lo suyo (filtro de db.py)
    return {
        "cuenta": {"email": u.email, "nombre": u.nombre, "creado": u.creado, "google": u.google_email, "correo_verificado": bool(u.correo_verificado)},
        "aceptacion": {"version": u.terminos_version, "vigente": TERMINOS_VERSION, "cuando": u.terminos_aceptados, "ip": u.terminos_ip},
        "novedades": bool(u.novedades),
        "guardado": {"emisores": n(Emisor), "clientes": n(Cliente), "facturas": n(Factura), "plantillas": n(Plantilla), "xml": n(XmlCfdi)},
        "admin": bool(u.admin),
    }


class NovedadesIn(BaseModel):
    acepta: bool


@router.put("/novedades")
def novedades(data: NovedadesIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    u = _propia(db, email)
    u.novedades = data.acepta
    db.commit()
    return {"ok": True, "novedades": u.novedades}


class CierreIn(BaseModel):
    confirmar: str  # el correo de la cuenta, escrito a mano


@router.post("/cerrar")
def cerrar(data: CierreIn, email: str = Depends(current_user), db: Session = Depends(get_db)):
    """Cierra la cuenta de inmediato (ya no se puede entrar) y deja constancia para borrar los datos dentro de los 90 días que
    promete el Aviso de privacidad. Los CFDI que la ley obliga a conservar se guardan bloqueados (ver Aviso, apartado 7)."""
    u = _propia(db, email)
    if u.admin:
        raise HTTPException(403, "La cuenta de administración no se cierra desde aquí.")
    if data.confirmar.strip().lower() != u.email.lower():
        raise HTTPException(422, "Escribe el correo de tu cuenta tal como aparece arriba para confirmar.")
    u.activo, u.cierre_solicitado = False, datetime.now()
    db.commit()
    log.warning("CIERRE DE CUENTA solicitado: usuario %s (%s). Borrar sus datos antes de 90 días, conservando los CFDI que exige el CFF art. 30.", u.id, u.email)
    try:
        from ..services import mailer
        if settings.respaldo_correo:
            mailer.enviar([settings.respaldo_correo], "Timbra: cierre de cuenta solicitado",
                          f"La cuenta {u.email} (id {u.id}) pidió cerrarse el {u.cierre_solicitado:%d/%m/%Y %H:%M}.\n"
                          "Borra sus datos antes de 90 días y conserva bloqueados los CFDI que exige la ley (5 años).", [], nombre="Timbra")
    except Exception as e:  # noqa: BLE001 — el aviso al administrador nunca impide cerrar la cuenta
        log.warning("No salió el aviso de cierre de cuenta: %s", e)
    return {"ok": True}
