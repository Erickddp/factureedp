from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Pac
from ..schemas import PacIn, PacOut
from ..security import current_user, encrypt

router = APIRouter(prefix="/pacs", tags=["pacs"], dependencies=[Depends(current_user)])


def _mio(db: Session, p: Pac) -> bool:
    return p.usuario_id == db.info.get("uid_real") or (p.usuario_id is None and db.info.get("es_admin"))


def _publico(db: Session, p: Pac) -> dict:
    """El PAC de la plataforma se ve en todas las cuentas, pero su usuario y sus datos sólo los ve su dueño."""
    mio = _mio(db, p)
    return {"id": p.id, "nombre": p.nombre if mio else "Timbrado incluido en Timbra", "proveedor": p.proveedor, "usuario": p.usuario if mio else None,
            "extra": p.extra if mio else {}, "pruebas": p.pruebas, "plataforma": p.plataforma, "propio": mio,
            "timbres_contratados": p.timbres_contratados if mio else None, "timbres_desde": p.timbres_desde if mio else None,
            "timbres_alerta": p.timbres_alerta}


def _plataforma(db: Session, p: Pac, quiere: bool) -> None:
    """Marca (o desmarca) el PAC con el que timbran todas las cuentas. Sólo el administrador, y sólo uno a la vez.
    Al marcarlo, los emisores que no tenían PAC (modo demo) pasan a timbrar con él, y los de otras cuentas que timbraban
    con el anterior (p. ej. el de pruebas) se cambian al nuevo: el anterior deja de ser visible para ellas y, sin este
    cambio, sus emisores quedarían en modo demo sin que nadie lo note. Al desmarcarlo, esos emisores quedan sin PAC."""
    from sqlalchemy import select, update
    if quiere == bool(p.plataforma):
        return
    if not db.info.get("es_admin") or not _mio(db, p):
        raise HTTPException(403, "Sólo el administrador puede poner su PAC al servicio de todas las cuentas.")
    admin = db.info.get("uid_real")
    ajenos = Emisor.usuario_id != admin  # los del administrador los cambia él, uno por uno (pueden ser de prueba)
    if quiere:
        anteriores = [i for (i,) in db.execute(select(Pac.__table__.c.id).where(Pac.__table__.c.plataforma.is_(True), Pac.__table__.c.id != p.id))]
        db.execute(update(Pac).where(Pac.id != p.id).values(plataforma=False))
        db.flush()
        db.execute(update(Emisor).where(Emisor.pac_id.is_(None)).values(pac_id=p.id))
        if anteriores:
            db.execute(update(Emisor).where(Emisor.pac_id.in_(anteriores), ajenos).values(pac_id=p.id))
    else:
        db.execute(update(Emisor).where(Emisor.pac_id == p.id, ajenos).values(pac_id=None))
    p.plataforma = quiere


@router.get("", response_model=list[PacOut])
def listar(db: Session = Depends(get_db)):
    return [_publico(db, p) for p in db.query(Pac).order_by(Pac.nombre)]


@router.get("/timbres")
def timbres(en_vivo: bool = False, db: Session = Depends(get_db)):
    """Consumo y saldo por PAC. en_vivo=true consulta el saldo real en SW."""
    from ..services import timbres as svc
    return svc.resumen(db, en_vivo)


@router.post("", response_model=PacOut)
def crear(data: PacIn, db: Session = Depends(get_db)):
    p = Pac(nombre=data.nombre, proveedor=data.proveedor, usuario=data.usuario,
            password_enc=encrypt(data.password), token_enc=encrypt(data.token),
            extra=data.extra, pruebas=data.pruebas, timbres_contratados=data.timbres_contratados,
            timbres_desde=data.timbres_desde, timbres_alerta=data.timbres_alerta)
    db.add(p)
    db.flush()
    _plataforma(db, p, data.plataforma)
    db.commit()
    return _publico(db, p)


@router.put("/{pac_id}", response_model=PacOut)
def editar(pac_id: int, data: PacIn, db: Session = Depends(get_db)):
    p = db.get(Pac, pac_id)
    if not p or not _mio(db, p):
        raise HTTPException(404, "PAC no existe")
    p.nombre, p.proveedor, p.usuario, p.extra, p.pruebas = data.nombre, data.proveedor, data.usuario, data.extra, data.pruebas
    if "plataforma" in data.model_fields_set:
        _plataforma(db, p, data.plataforma)
    for k in ("timbres_contratados", "timbres_desde", "timbres_alerta"):  # sólo si vienen: el formulario viejo no los manda
        if k in data.model_fields_set:
            setattr(p, k, getattr(data, k))
    if data.password:
        p.password_enc = encrypt(data.password)
    if data.token:
        p.token_enc = encrypt(data.token)
    db.commit()
    return _publico(db, p)


@router.post("/{pac_id}/alta")
def alta(pac_id: int, emisor_id: int, db: Session = Depends(get_db)):
    """Finkok en producción: comprueba las credenciales dando de alta el RFC del emisor en la cuenta (no timbra ni gasta
    nada; si ya estaba, Finkok lo dice). Es la forma de probar el PAC productivo sin hacer una factura real."""
    from ..services import pac as pac_svc

    pac, emisor = db.get(Pac, pac_id), db.get(Emisor, emisor_id)
    if not pac or not emisor or not _mio(db, pac):
        raise HTTPException(404, "PAC o emisor no existe")
    try:
        return {"ok": True, "rfc": emisor.rfc, "mensaje": pac_svc.registrar_emisor(pac, emisor.rfc)}
    except pac_svc.PacError as e:
        raise HTTPException(422, str(e))


@router.post("/{pac_id}/probar")
def probar(pac_id: int, emisor_id: int, ciclo: bool = False, db: Session = Depends(get_db)):
    """Timbrado de prueba real contra el sandbox del PAC con el CSD del emisor elegido.
    ciclo=true: timbra, cancela y consulta estatus (lo que revisa el PAC para dar producción)."""
    from ..services import pac as pac_svc
    from ..services.signer import CsdError, signer_de

    pac, emisor = db.get(Pac, pac_id), db.get(Emisor, emisor_id)
    if not pac or not emisor or not _mio(db, pac):
        raise HTTPException(404, "PAC o emisor no existe")
    try:
        return pac_svc.probar(pac, emisor, signer_de(emisor, permitir_vencido=True), ciclo=ciclo)
    except (pac_svc.PacError, CsdError) as e:
        raise HTTPException(422, str(e))
