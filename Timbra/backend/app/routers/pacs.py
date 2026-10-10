from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Pac
from ..schemas import PacIn, PacOut
from ..security import current_user, encrypt

router = APIRouter(prefix="/pacs", tags=["pacs"], dependencies=[Depends(current_user)])


@router.get("", response_model=list[PacOut])
def listar(db: Session = Depends(get_db)):
    return db.query(Pac).order_by(Pac.nombre).all()


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
    db.commit()
    return p


@router.put("/{pac_id}", response_model=PacOut)
def editar(pac_id: int, data: PacIn, db: Session = Depends(get_db)):
    p = db.get(Pac, pac_id)
    if not p:
        raise HTTPException(404, "PAC no existe")
    p.nombre, p.proveedor, p.usuario, p.extra, p.pruebas = data.nombre, data.proveedor, data.usuario, data.extra, data.pruebas
    for k in ("timbres_contratados", "timbres_desde", "timbres_alerta"):  # sólo si vienen: el formulario viejo no los manda
        if k in data.model_fields_set:
            setattr(p, k, getattr(data, k))
    if data.password:
        p.password_enc = encrypt(data.password)
    if data.token:
        p.token_enc = encrypt(data.token)
    db.commit()
    return p


@router.post("/{pac_id}/probar")
def probar(pac_id: int, emisor_id: int, ciclo: bool = False, db: Session = Depends(get_db)):
    """Timbrado de prueba real contra el sandbox del PAC con el CSD del emisor elegido.
    ciclo=true: timbra, cancela y consulta estatus (lo que revisa el PAC para dar producción)."""
    from ..services import pac as pac_svc
    from ..services.signer import CsdError, signer_de

    pac, emisor = db.get(Pac, pac_id), db.get(Emisor, emisor_id)
    if not pac or not emisor:
        raise HTTPException(404, "PAC o emisor no existe")
    try:
        return pac_svc.probar(pac, emisor, signer_de(emisor, permitir_vencido=True), ciclo=ciclo)
    except (pac_svc.PacError, CsdError) as e:
        raise HTTPException(422, str(e))
