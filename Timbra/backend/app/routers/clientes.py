from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Cliente
from ..schemas import ClienteIn, ClienteOut
from ..security import current_user

router = APIRouter(prefix="/clientes", tags=["clientes"], dependencies=[Depends(current_user)])


@router.get("", response_model=list[ClienteOut])
def listar(emisor_id: int, q: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    qs = db.query(Cliente).filter(Cliente.emisor_id == emisor_id)
    if q:
        like = f"%{q.upper()}%"
        qs = qs.filter(or_(Cliente.rfc.like(like), Cliente.nombre.like(like)))
    return qs.order_by(Cliente.nombre).limit(limit).all()


@router.get("/recientes")
def recientes(emisor_id: int, limit: int = 300, db: Session = Depends(get_db)):
    """Clientes guardados para elegir de una lista: primero a los que facturaste más recientemente."""
    from sqlalchemy import func

    from ..models import Factura
    uso = {cid: (n, ult) for cid, n, ult in db.query(Factura.cliente_id, func.count(Factura.id), func.max(Factura.fecha))
           .filter(Factura.emisor_id == emisor_id, Factura.cliente_id.isnot(None), Factura.estado != "error")
           .group_by(Factura.cliente_id)}
    out = []
    for c in db.query(Cliente).filter(Cliente.emisor_id == emisor_id):
        n, ult = uso.get(c.id, (0, None))
        out.append({**ClienteOut.model_validate(c).model_dump(mode="json"), "facturas": n, "ultima": ult.isoformat() if ult else None})
    out.sort(key=lambda x: (x["ultima"] is None, "" if x["ultima"] is None else -datetime.fromisoformat(x["ultima"]).timestamp(), x["nombre"]))
    return out[:limit]


@router.post("", response_model=ClienteOut)
def crear(data: ClienteIn, db: Session = Depends(get_db)):
    if db.query(Cliente).filter_by(emisor_id=data.emisor_id, rfc=data.rfc, nombre=data.nombre).first():
        raise HTTPException(409, f"{data.nombre} ({data.rfc}) ya está en tus clientes.")
    c = Cliente(**data.model_dump())
    db.add(c)
    db.commit()
    return c


@router.put("/{cliente_id}", response_model=ClienteOut)
def editar(cliente_id: int, data: ClienteIn, db: Session = Depends(get_db)):
    c = db.get(Cliente, cliente_id)
    if not c:
        raise HTTPException(404, "Cliente no existe")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return c


@router.delete("/{cliente_id}")
def borrar(cliente_id: int, db: Session = Depends(get_db)):
    c = db.get(Cliente, cliente_id)
    if c:
        db.delete(c)
        db.commit()
    return {"ok": True}


# ---------------- Importación masiva ----------------
from fastapi import File, Form, Response, UploadFile  # noqa: E402

from ..logs import log  # noqa: E402
from ..schemas import ImportarConfirmarIn  # noqa: E402
from ..services import clientes_io, importar  # noqa: E402


@router.get("/importar/plantilla")
def plantilla_importacion():
    return Response(importar.plantilla_xlsx(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="plantilla_clientes_timbra.xlsx"'})


@router.post("/importar/previsualizar")
async def importar_previsualizar(emisor_id: int = Form(...), uso_default: str = Form("auto"),
                                 texto: str | None = Form(None), archivo: UploadFile | None = File(None),
                                 db: Session = Depends(get_db)):
    contenido = await archivo.read() if archivo else None
    try:
        filas = importar.leer_tabla(archivo.filename if archivo else None, contenido, texto)
    except Exception as e:
        log.exception("No se pudo leer el archivo de clientes")
        raise HTTPException(422, f"No pude leer el archivo: {e}")
    existentes = {c.rfc: c.id for c in db.query(Cliente).filter(Cliente.emisor_id == emisor_id)}
    actuales = clientes_io.actuales_por_rfc(db, emisor_id)
    res = importar.previsualizar(filas, existentes, uso_default, actuales, clientes_io.nombres_por_rfc(actuales))
    log.info("Importación: %s filas leídas → %s", len(res["filas"]), res["resumen"])
    return res


@router.post("/importar/confirmar")
def importar_confirmar(data: ImportarConfirmarIn, db: Session = Depends(get_db)):
    """Cada fila puede traer `_accion` y `_resolucion` ("hoja" | "base") para los conflictos; sin decisión no se toca."""
    return clientes_io.confirmar(db, data.emisor_id, data.filas, data.modo)


# ---------------- Revisión, duplicados y lista 69-B ----------------
from pydantic import BaseModel  # noqa: E402


@router.get("/auditoria")
def auditoria(emisor_id: int, incluir_info: bool = False, db: Session = Depends(get_db)):
    """Clientes guardados con datos que el SAT rechazaría o que conviene corregir, con arreglo de un clic cuando es seguro."""
    return clientes_io.auditar(db, emisor_id, incluir_info)


class ArreglosIn(BaseModel):
    emisor_id: int
    arreglos: list[dict]


@router.post("/auditoria/arreglar")
def auditoria_arreglar(data: ArreglosIn, db: Session = Depends(get_db)):
    return clientes_io.aplicar_arreglos(db, data.emisor_id, data.arreglos)


@router.get("/duplicados")
def duplicados(emisor_id: int, db: Session = Depends(get_db)):
    return clientes_io.duplicados(db, emisor_id)


class FusionIn(BaseModel):
    emisor_id: int
    conservar_id: int
    fusionar_ids: list[int]


@router.post("/fusionar")
def fusionar(data: FusionIn, db: Session = Depends(get_db)):
    try:
        return clientes_io.fusionar(db, data.emisor_id, data.conservar_id, data.fusionar_ids)
    except ValueError as e:
        raise HTTPException(422, str(e))


class Verif69bIn(BaseModel):
    emisor_id: int
    rfcs: list[str] | None = None


@router.post("/verificar-69b")
def verificar_69b(data: Verif69bIn, db: Session = Depends(get_db)):
    """Cruza tus clientes con la lista 69-B del SAT (EFOS). Necesita internet la primera vez; después usa la copia guardada."""
    try:
        return clientes_io.verificar_69b(db, data.emisor_id, data.rfcs)
    except clientes_io.ListaNoDisponible as e:
        raise HTTPException(503, str(e))
