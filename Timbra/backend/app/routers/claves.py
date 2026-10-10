"""Investigar claves SAT antes de facturar: búsqueda con ranking, detalle con jerarquía/avisos, unidades y las más usadas."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Emisor, Factura, PerfilLote, Producto
from ..security import current_user
from ..services import claves as svc

router = APIRouter(prefix="/claves", tags=["claves"], dependencies=[Depends(current_user)])


def bloqueadas_de(db: Session, emisor_id: int | None) -> frozenset[str]:
    e = db.get(Emisor, emisor_id) if emisor_id else None
    return frozenset(str(x) for x in ((e.config_facturar or {}).get("claves_bloqueadas") or [])) if e else frozenset()


@router.get("/buscar")
def buscar(q: str, tipo: str = "prod_serv", limit: int = 30, emisor_id: int | None = None, db: Session = Depends(get_db)):
    if tipo not in svc.TABLAS:
        raise HTTPException(422, "tipo debe ser prod_serv o unidad")
    res = svc.buscar(q, tipo, min(limit, 100), bloqueadas_de(db, emisor_id))
    if emisor_id and tipo == "prod_serv":
        en_catalogo = {c for (c,) in db.query(Producto.clave_prod_serv).filter(Producto.emisor_id == emisor_id)}
        for r in res:
            r["en_catalogo"] = r["clave"] in en_catalogo
    return res


@router.get("/unidades")
def unidades():
    return svc.unidades_comunes()


@router.get("/frecuentes")
def frecuentes(emisor_id: int, limit: int = 12, db: Session = Depends(get_db)):
    """Las claves que más usa este emisor: su catálogo, sus últimas facturas y sus perfiles de lote."""
    cuenta: Counter = Counter()
    fuentes: dict[str, set] = {}

    def sumar(clave, peso, fuente):
        if clave and svc.descripcion(clave):
            cuenta[clave] += peso
            fuentes.setdefault(clave, set()).add(fuente)

    for (c,) in db.query(Producto.clave_prod_serv).filter(Producto.emisor_id == emisor_id):
        sumar(c, 2, "catálogo")
    for (p,) in db.query(Factura.payload).filter(Factura.emisor_id == emisor_id, Factura.tipo.in_(("I", "E"))) \
            .order_by(Factura.id.desc()).limit(300):
        for c in (p or {}).get("conceptos", []) or []:
            sumar(c.get("clave_prod_serv"), 1, "facturas")
    for (cfg,) in db.query(PerfilLote.config).filter(PerfilLote.emisor_id == emisor_id):
        for c in (cfg or {}).get("conceptos", []) or []:
            sumar(c.get("clave_prod_serv"), 3, "perfiles")
    bloq = bloqueadas_de(db, emisor_id)
    return [{**svc._item(c, svc.descripcion(c), bloq), "usos": n, "fuentes": sorted(fuentes[c])}
            for c, n in cuenta.most_common(limit)]


@router.get("/{clave}")
def detalle(clave: str, emisor_id: int | None = None, db: Session = Depends(get_db)):
    d = svc.detalle(clave, bloqueadas_de(db, emisor_id))
    if d is None:
        raise HTTPException(404, f"La clave {clave} no existe en el catálogo vigente del SAT.")
    if emisor_id:
        d["productos"] = [{"id": p.id, "descripcion": p.descripcion, "precio": str(p.precio)}
                          for p in db.query(Producto).filter_by(emisor_id=emisor_id, clave_prod_serv=clave).limit(10)]
    return d
