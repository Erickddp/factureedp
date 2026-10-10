from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Producto
from ..schemas import ProductoIn, ProductoOut
from ..security import current_user
from ..services import importar, productos_io

router = APIRouter(prefix="/productos", tags=["productos"], dependencies=[Depends(current_user)])


@router.get("", response_model=list[ProductoOut])
def listar(emisor_id: int, q: str | None = None, db: Session = Depends(get_db)):
    qs = db.query(Producto).filter(Producto.emisor_id == emisor_id)
    if q:
        qs = qs.filter(Producto.descripcion.ilike(f"%{q}%"))
    return qs.order_by(Producto.descripcion).limit(500).all()


@router.get("/sugerencias")
def sugerencias(emisor_id: int, q: str = "", sat: bool = True, db: Session = Depends(get_db)):
    """Para la descripción del concepto: tu catálogo, lo que ya facturaste y (con texto) el catálogo completo del SAT."""
    from ..models import Factura
    from ..services import claves as claves_svc
    from .claves import bloqueadas_de

    t = q.strip().lower()
    qs = db.query(Producto).filter(Producto.emisor_id == emisor_id)
    if t:
        qs = qs.filter(Producto.descripcion.ilike(f"%{t}%"))
    prods = qs.order_by(Producto.descripcion).limit(200 if not t else 12).all()
    vistos = {(p.descripcion.strip().lower(), p.clave_prod_serv) for p in
              (prods if not t else db.query(Producto).filter(Producto.emisor_id == emisor_id))}
    facturados: dict[tuple, dict] = {}
    for (payload,) in db.query(Factura.payload).filter(Factura.emisor_id == emisor_id, Factura.tipo.in_(("I", "E")),
                                                      Factura.estado != "error").order_by(Factura.id.desc()).limit(400):
        for c in (payload or {}).get("conceptos", []) or []:
            d = (c.get("descripcion") or "").strip()
            k = (d.lower(), c.get("clave_prod_serv"))
            if not d or k in vistos or (t and t not in d.lower()):
                continue
            if k in facturados:
                facturados[k]["usos"] += 1
            else:
                facturados[k] = {"descripcion": d, "clave_prod_serv": c.get("clave_prod_serv"), "clave_unidad": c.get("clave_unidad"),
                                 "unidad": c.get("unidad"), "valor_unitario": str(c.get("valor_unitario") or ""),
                                 "impuestos": c.get("impuestos") or [], "objeto_imp": c.get("objeto_imp") or "02", "usos": 1}
    del_sat = []
    if sat and len(t) >= 3:
        propias = {p.clave_prod_serv for p in prods}
        del_sat = [r for r in claves_svc.buscar(t, "prod_serv", 8, bloqueadas_de(db, emisor_id))
                   if r["clave"] not in propias and not r.get("bloqueada")]
    return {"productos": [ProductoOut.model_validate(p).model_dump(mode="json") for p in prods],
            "facturados": sorted(facturados.values(), key=lambda x: -x["usos"])[:100 if not t else 6], "sat": del_sat}


@router.post("", response_model=ProductoOut)
def crear(data: ProductoIn, db: Session = Depends(get_db)):
    p = Producto(**data.model_dump(mode="json"))
    db.add(p)
    db.commit()
    return p


@router.put("/{producto_id}", response_model=ProductoOut)
def editar(producto_id: int, data: ProductoIn, db: Session = Depends(get_db)):
    p = db.get(Producto, producto_id)
    if not p:
        raise HTTPException(404, "Producto no existe")
    for k, v in data.model_dump(mode="json").items():
        setattr(p, k, v)
    db.commit()
    return p


@router.delete("/{producto_id}")
def borrar(producto_id: int, db: Session = Depends(get_db)):
    p = db.get(Producto, producto_id)
    if p:
        db.delete(p)
        db.commit()
    return {"ok": True}


@router.get("/packs")
def packs(emisor_id: int | None = None, db: Session = Depends(get_db)):
    """Catálogos sugeridos por giro. Con emisor_id indica cuántos ya tiene."""
    out = productos_io.packs()
    if emisor_id:
        ya = {(x.descripcion.strip().lower(), x.clave_prod_serv) for x in db.query(Producto).filter_by(emisor_id=emisor_id)}
        for p in out:
            p["ya_tiene"] = sum(1 for x in p["productos"] if (x["descripcion"].strip().lower(), x["clave"]) in ya)
    return out


@router.post("/packs/{pack_id}")
def agregar_pack(pack_id: str, emisor_id: int, db: Session = Depends(get_db)):
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe")
    try:
        return productos_io.aplicar_pack(db, e, pack_id)
    except ValueError as ex:
        raise HTTPException(404, str(ex))


@router.post("/importar")
async def importar_productos(emisor_id: int = Form(...), confirmar: bool = Form(False), aceptar_sugeridas: bool = Form(False),
                             texto: str | None = Form(None), archivo: UploadFile | None = File(None),
                             db: Session = Depends(get_db)):
    """Pega o sube una tabla (descripción, clave, unidad, precio, impuesto). Sin confirmar: sólo vista previa."""
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe")
    contenido = await archivo.read() if archivo else None
    filas = importar.leer_tabla(archivo.filename if archivo else None, contenido, texto)
    if confirmar:
        try:
            return productos_io.confirmar(db, e, filas, aceptar_sugeridas)
        except ValueError as ex:
            raise HTTPException(422, str(ex))
    return productos_io.previsualizar(db, e, filas)
