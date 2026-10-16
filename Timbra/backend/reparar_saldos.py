"""Recalcula saldo y parcialidades de las facturas PPD a partir de sus complementos de pago (REP) VIGENTES.

Sirve para facturas que quedaron mal con la versión anterior a 2.14.1 (cancelar un REP no regresaba el saldo).
Por omisión sólo MUESTRA lo que cambiaría; para aplicarlo:  .venv\\Scripts\\python reparar_saldos.py --aplicar
"""
import sys
from collections import defaultdict
from decimal import Decimal

from app.db import SessionLocal
from app.models import Factura


def main() -> int:
    aplicar = "--aplicar" in sys.argv
    with SessionLocal() as db:
        pagado, veces = defaultdict(Decimal), defaultdict(int)
        for rep in db.query(Factura).filter(Factura.tipo == "P", Factura.estado != "cancelada", Factura.uuid.isnot(None)):
            for d in (rep.payload or {}).get("documentos", []):
                if d.get("factura_id"):
                    pagado[int(d["factura_id"])] += Decimal(str(d.get("imp_pagado") or 0))
                    veces[int(d["factura_id"])] += 1
        cambios = 0
        for f in db.query(Factura).filter(Factura.tipo == "I", Factura.metodo_pago == "PPD", Factura.uuid.isnot(None)):
            saldo = Decimal(0) if f.estado == "cancelada" else max(Decimal(0), Decimal(f.total) - pagado[f.id])
            parcialidades = veces[f.id]
            if Decimal(f.saldo) != saldo or (f.parcialidades or 0) != parcialidades:
                cambios += 1
                print(f"{f.serie or ''}{f.folio or ''} (id {f.id}): saldo {f.saldo} -> {saldo} · parcialidades {f.parcialidades} -> {parcialidades}")
                if aplicar:
                    f.saldo, f.parcialidades = saldo, parcialidades
        if aplicar:
            db.commit()
        print(f"{cambios} factura(s) {'corregidas' if aplicar else 'por corregir (nada se cambió; usa --aplicar)'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
