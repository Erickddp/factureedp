"""Catálogos oficiales del SAT (vienen dentro de satcfdi, no hay que descargarlos)."""
from functools import lru_cache

from fastapi import APIRouter
from satcfdi.catalogs import select, select_all

from ..services import claves

router = APIRouter(prefix="/catalogos", tags=["catalogos"])

SIMPLES = {
    "regimen_fiscal": "C756_c_RegimenFiscal",
    "uso_cfdi": "C756_c_UsoCFDI",
    "forma_pago": "C756_c_FormaPago",
    "metodo_pago": "C756_c_MetodoPago",
    "tipo_relacion": "C756_c_TipoRelacion",
    "objeto_imp": "C756_c_ObjetoImp",
    "exportacion": "C756_c_Exportacion",
    "periodicidad": "C756_c_Periodicidad",
    "meses": "C756_c_Meses",
    "tipo_comprobante": "C756_c_TipoDeComprobante",
    "pais": "C756_c_Pais",
}


@lru_cache
def _todo(nombre: str) -> list[dict]:
    out = []
    for k, v in select_all(nombre).items():
        desc = v[0] if isinstance(v, (list, tuple)) else v
        out.append({"clave": k if isinstance(k, str) else k[0], "descripcion": str(desc)})
    return sorted(out, key=lambda x: x["clave"])


@router.get("/{nombre}")
def catalogo(nombre: str):
    if nombre in SIMPLES:
        return _todo(SIMPLES[nombre])
    if nombre == "moneda":
        return _todo("C756_c_Moneda")
    return []


@router.get("/buscar/prod_serv")
def prod_serv(q: str, limit: int = 30):
    """Mismo formato de siempre (clave, descripcion) + tipo y alertas; ranking con sinónimos (ver services/claves.py)."""
    return claves.buscar(q, "prod_serv", min(limit, 100))


@router.get("/buscar/unidad")
def unidad(q: str, limit: int = 30):
    return claves.buscar(q, "unidad", min(limit, 100))


@router.get("/cp/{cp}")
def codigo_postal(cp: str):
    r = select("C756_c_CodigoPostal", cp)
    return {"valido": r is not None, "cp": cp, "estado": r[0] if r else None}
