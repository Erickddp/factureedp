from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Producto, Serie
from ..services.semillas import a_frontera, productos_base
from ..schemas import EmisorIn, EmisorOut, SerieIn, SerieOut
from ..security import current_user
from ..services.signer import CsdError, cargar_csd

router = APIRouter(prefix="/emisores", tags=["emisores"], dependencies=[Depends(current_user)])


def _get(db, emisor_id) -> Emisor:
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe")
    return e


@router.get("", response_model=list[EmisorOut])
def listar(db: Session = Depends(get_db)):
    return db.query(Emisor).order_by(Emisor.nombre).all()


@router.get("/{emisor_id}", response_model=EmisorOut)
def ver(emisor_id: int, db: Session = Depends(get_db)):
    return _get(db, emisor_id)


@router.post("", response_model=EmisorOut)
def crear(data: EmisorIn, db: Session = Depends(get_db)):
    if db.query(Emisor).filter_by(rfc=data.rfc).first():
        raise HTTPException(409, f"{data.rfc} ya está dado de alta")
    if db.connection().execute(select(Emisor.__table__.c.id).where(Emisor.__table__.c.rfc == data.rfc)).first():
        raise HTTPException(409, f"{data.rfc} ya está registrado en otra cuenta de Timbra. Si es tuyo, pide al administrador que lo libere.")
    e = Emisor(**data.model_dump())
    e.series = [Serie(serie="A", tipo="I", default=True), Serie(serie="NC", tipo="E", default=True),
                Serie(serie="P", tipo="P", default=True), Serie(serie="T", tipo="T", default=True),
                Serie(serie="N", tipo="N", default=True)]
    db.add(e)
    db.flush()
    db.add_all(Producto(**p) for p in productos_base(e.id, e.region_fronteriza))  # catálogo base listo para usar
    db.commit()
    return e


@router.put("/{emisor_id}", response_model=EmisorOut)
def editar(emisor_id: int, data: EmisorIn, db: Session = Depends(get_db)):
    e = _get(db, emisor_id)
    for k, v in data.model_dump(exclude_unset=True).items():  # sin logo en el payload = se conserva
        setattr(e, k, v)
    db.commit()
    return e


@router.post("/{emisor_id}/csd", response_model=EmisorOut)
async def subir_csd(emisor_id: int, cer: UploadFile = File(...), key: UploadFile = File(...),
                    password: str = Form(...), db: Session = Depends(get_db)):
    e = _get(db, emisor_id)
    try:
        cargar_csd(e, await cer.read(), await key.read(), password)
    except CsdError as ex:
        raise HTTPException(422, str(ex))
    db.commit()
    return e


@router.post("/{emisor_id}/series", response_model=SerieOut)
def crear_serie(emisor_id: int, data: SerieIn, db: Session = Depends(get_db)):
    e = _get(db, emisor_id)
    if any(s.serie == data.serie for s in e.series):
        raise HTTPException(409, f"La serie {data.serie} ya existe en {e.rfc}.")
    if data.default:
        for s in e.series:
            if s.tipo == data.tipo:
                s.default = False
    s = Serie(emisor_id=e.id, **data.model_dump())
    db.add(s)
    db.commit()
    return s


@router.post("/{emisor_id}/productos-a-frontera")
def productos_a_frontera(emisor_id: int, db: Session = Depends(get_db)):
    """Pasa el catálogo del emisor de IVA 16% a 8% (y retención 10.6667% → 5.3333%)."""
    e = _get(db, emisor_id)
    n = 0
    for p in db.query(Producto).filter(Producto.emisor_id == e.id):
        nuevos = a_frontera(p.impuestos or [])
        if nuevos != p.impuestos:
            p.impuestos = nuevos
            n += 1
    db.commit()
    return {"actualizados": n}


@router.get("/{emisor_id}/config-facturar")
def ver_config(emisor_id: int, db: Session = Depends(get_db)):
    from ..services.config_facturar import efectiva
    return efectiva(_get(db, emisor_id).config_facturar)


@router.put("/{emisor_id}/config-facturar")
def guardar_config(emisor_id: int, data: dict, db: Session = Depends(get_db)):
    """Nivel, campos visibles, valores por defecto y perfiles rápidos de la barra de Facturar."""
    from ..services.config_facturar import efectiva, limpiar
    e = _get(db, emisor_id)
    e.config_facturar = {**(e.config_facturar or {}), **limpiar(data)}
    db.commit()
    return efectiva(e.config_facturar)


# ---------------- Facturas de práctica (modo demo) ----------------
def _de_practica(db: Session, emisor_id: int):
    from ..models import Factura
    from ..services.pdf import es_demo
    return [f for f in db.query(Factura).filter(Factura.emisor_id == emisor_id) if es_demo(f.xml)]


@router.delete("/{emisor_id}")
def eliminar(emisor_id: int, confirmar: str = "", db: Session = Depends(get_db)):
    """Elimina el emisor con TODO lo suyo (clientes, productos, facturas de prueba, lotes, plantillas…).
    No se permite si timbró con un PAC de producción: esos CFDI tienen validez fiscal y hay que conservarlos.
    Los XML no se destruyen: su carpeta se mueve a datos/eliminados."""
    import os
    import shutil
    from datetime import datetime

    from sqlalchemy import delete

    from ..config import settings
    from ..db import Base
    from ..logs import log
    from ..models import Factura
    from ..services import lotes as lotes_svc
    from ..services.pdf import es_demo

    e = _get(db, emisor_id)
    if confirmar.strip().upper() != e.rfc.upper():
        raise HTTPException(422, f"Para eliminarlo escribe su RFC ({e.rfc}) como confirmación.")
    if any(lotes_svc.en_ejecucion(lid) for (lid,) in db.query(lotes_svc.Lote.id).filter_by(emisor_id=e.id)):
        raise HTTPException(409, "Este emisor tiene un lote timbrándose. Espera a que termine.")
    timbradas = [f for f in db.query(Factura).filter(Factura.emisor_id == e.id, Factura.uuid.isnot(None))]
    produccion = e.pac is not None and e.pac.proveedor != "demo" and not e.pac.pruebas
    reales = [f for f in timbradas if not es_demo(f.xml)] if produccion else []
    if reales:
        raise HTTPException(409, f"{e.rfc} tiene {len(reales)} factura(s) timbradas ante el SAT. Tienen validez fiscal y debes "
                                 "conservarlas (5 años): este emisor no se puede eliminar.")
    rfc, nombre = e.rfc, e.nombre
    cuenta = {}
    for tabla in reversed(Base.metadata.sorted_tables):  # primero lo que depende de lo demás (filas, lotes, facturas…)
        if tabla.name != "emisores" and "emisor_id" in tabla.c:
            n = db.execute(delete(tabla).where(tabla.c.emisor_id == emisor_id)).rowcount
            if n:
                cuenta[tabla.name] = n
    db.delete(e)
    db.commit()
    origen = os.path.join(settings.data_dir, "respaldo_xml", rfc.upper())
    if os.path.isdir(origen):
        destino = os.path.join(settings.data_dir, "eliminados", f"{rfc.upper()}_{datetime.now():%Y%m%d_%H%M%S}")
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.move(origen, destino)
        except OSError as x:
            log.warning("No se pudo mover el respaldo XML de %s: %s", rfc, x)
    log.warning("Emisor %s (%s) eliminado con: %s", rfc, nombre, cuenta or "nada más")
    return {"ok": True, "rfc": rfc, "borrado": cuenta}


@router.get("/{emisor_id}/practica")
def practica(emisor_id: int, db: Session = Depends(get_db)):
    """Cuántas facturas de práctica (timbradas con el PAC demo, sin validez fiscal) tiene el emisor."""
    _get(db, emisor_id)
    return {"facturas": len(_de_practica(db, emisor_id))}


@router.post("/{emisor_id}/practica/borrar")
def borrar_practica(emisor_id: int, db: Session = Depends(get_db)):
    """Antes de timbrar de verdad: quita SÓLO las facturas del PAC demo y regresa los folios. Las reales no se tocan.
    Sus XML no se destruyen: se mueven a datos/practica_xml por si se quieren consultar."""
    import os
    import shutil

    from ..config import settings
    from ..logs import log
    from ..models import Factura, LoteFila, Plantilla, Ticket
    from ..services import respaldo

    e = _get(db, emisor_id)
    demo = _de_practica(db, emisor_id)
    ids = [f.id for f in demo]
    if ids:
        db.query(LoteFila).filter(LoteFila.factura_id.in_(ids)).update({LoteFila.factura_id: None}, synchronize_session=False)
        db.query(Ticket).filter(Ticket.factura_id.in_(ids)).update({Ticket.factura_id: None}, synchronize_session=False)
        db.query(Plantilla).filter(Plantilla.ultima_factura_id.in_(ids)).update({Plantilla.ultima_factura_id: None}, synchronize_session=False)
    destino = os.path.join(settings.data_dir, "practica_xml", e.rfc.upper())
    uuids = {(f.uuid or "").upper() for f in demo}
    movidos = 0
    for p in list(respaldo.todos()):
        if os.path.splitext(os.path.basename(p))[0].upper() in uuids:
            os.makedirs(destino, exist_ok=True)
            try:
                shutil.move(p, os.path.join(destino, os.path.basename(p)))
                movidos += 1
            except OSError:
                pass
    for f in demo:
        db.delete(f)
    db.flush()
    # Folios: cada serie continúa después de la última factura REAL (o desde 1 si no hay ninguna)
    folios = {}
    for s in e.series:
        usados = [int(x) for (x,) in db.query(Factura.folio).filter(Factura.emisor_id == e.id, Factura.serie == s.serie) if x and str(x).isdigit()]
        s.siguiente_folio = max(usados) + 1 if usados else 1
        folios[s.serie] = s.siguiente_folio
    db.commit()
    log.warning("Facturas de práctica de %s borradas: %s (XML movidos: %s). Folios: %s", e.rfc, len(ids), movidos, folios)
    return {"borradas": len(ids), "xml_movidos": movidos, "folios": folios}
