from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Factura, LoteFila, Serie

# Estados de una fila de lote que APARTAN su folio (mientras no se timbre ni se omita)
APARTAN = ("listo", "error", "timbrando")


class FolioError(Exception):
    pass


def _serie(db: Session, emisor_id: int, tipo: str, serie: str | None) -> Serie:
    q = select(Serie).where(Serie.emisor_id == emisor_id)
    if serie:
        q = q.where(Serie.serie == serie)
    else:
        q = q.where(Serie.tipo == tipo).order_by(Serie.default.desc())
    s = db.execute(q.with_for_update()).scalars().first()
    if s is None:
        # Sin serie configurada: la creamos al vuelo
        nombre = serie or {"I": "A", "E": "NC", "T": "T", "P": "P", "N": "N"}.get(tipo, "A")
        s = Serie(emisor_id=emisor_id, serie=nombre, tipo=tipo, siguiente_folio=1, default=True)
        db.add(s)
        db.flush()
    return s


def usado_por(db: Session, emisor_id: int, serie: str | None, folio: str, excepto_fila: int | None = None) -> str | None:
    """Quién tiene ese folio: una factura ya emitida (aunque esté cancelada: el folio se consumió) o una fila de lote
    que lo apartó. None = libre."""
    f = db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.serie == serie, Factura.folio == folio,
                                 Factura.uuid.isnot(None)).first()
    if f:
        return f"la factura {serie or ''}{folio} ya emitida"
    r = db.query(LoteFila).filter(LoteFila.emisor_id == emisor_id, LoteFila.serie == serie, LoteFila.folio == folio,
                                  LoteFila.estado.in_(APARTAN), LoteFila.id != (excepto_fila or 0)).first()
    if r:
        return f"la fila {r.n} del lote {r.lote_id} (folio apartado)"
    return None


def siguiente(db: Session, emisor_id: int, tipo: str, serie: str | None) -> tuple[str | None, str]:
    """Siguiente folio consecutivo. Salta los que tiene apartados una fila de lote pendiente de corrección."""
    s = _serie(db, emisor_id, tipo, serie)
    for _ in range(10_000):
        # Incremento atómico en la BD: dos timbrados a la vez (pantalla + programador) nunca toman el mismo folio
        nuevo = db.execute(update(Serie).where(Serie.id == s.id).values(siguiente_folio=Serie.siguiente_folio + 1)
                           .returning(Serie.siguiente_folio)).scalar_one()
        folio = str(nuevo - 1)
        if usado_por(db, emisor_id, s.serie, folio) is None:
            db.refresh(s)
            return s.serie, folio
    raise FolioError("No encontré un folio libre en la serie.")


def tomar(db: Session, emisor_id: int, tipo: str, serie: str | None, folio: str,
          fila_id: int | None = None) -> tuple[str | None, str]:
    """Usa EXACTAMENTE ese folio (el de tu hoja). Falla si ya lo tiene otra factura u otra fila apartada.
    El contador consecutivo se adelanta para que las facturas normales sigan después del último usado."""
    s = _serie(db, emisor_id, tipo, serie)
    folio = str(int(folio))
    f = db.query(Factura).filter(Factura.emisor_id == emisor_id, Factura.serie == s.serie, Factura.folio == folio,
                                 Factura.uuid.isnot(None)).first()
    if f:
        raise FolioError(f"El folio {s.serie}{folio} ya lo tiene la factura emitida {f.id}.")
    otra = db.query(LoteFila).filter(LoteFila.emisor_id == emisor_id, LoteFila.serie == s.serie,
                                     LoteFila.folio == folio, LoteFila.estado.in_(APARTAN),
                                     LoteFila.id != (fila_id or 0)).first()
    if otra:
        raise FolioError(f"El folio {s.serie}{folio} está apartado por la fila {otra.n} del lote {otra.lote_id}.")
    db.execute(update(Serie).where(Serie.id == s.id, Serie.siguiente_folio <= int(folio))
               .values(siguiente_folio=int(folio) + 1))
    db.refresh(s)
    return s.serie, folio
