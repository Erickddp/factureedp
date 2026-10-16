"""Configuración de la barra de Facturar por emisor: de lo más simple a lo más completo.

- nivel "simple":   cliente + descripción + precio. Clave SAT, unidad, pago e impuestos salen de los valores por defecto.
- nivel "estandar": lo de siempre (clave, unidad, descuento, moneda, relacionados, addenda, impuestos locales).
- nivel "completo": además a cuenta de terceros, cuenta predial y pedimentos, con opciones avanzadas abiertas.
`campos` permite prender o apagar cualquier campo encima del nivel. `perfiles` son botones de un clic que llenan
tipo, pago, impuestos y el concepto típico (p. ej. "Honorarios PF → PM", "Renta a cuenta del dueño").
"""
from copy import deepcopy

CAMPOS = ("clave_sat", "unidad", "descuento", "pago", "moneda", "relacionados", "condiciones", "addenda", "locales",
          "terceros", "predial", "aduana", "plantillas", "repetir_ultima")

NIVELES = {
    "simple": {"clave_sat": False, "unidad": False, "descuento": False, "pago": True, "moneda": False,
               "relacionados": False, "condiciones": False, "addenda": False, "locales": False, "terceros": False,
               "predial": False, "aduana": False, "plantillas": True, "repetir_ultima": True},
    "estandar": {"clave_sat": True, "unidad": True, "descuento": True, "pago": True, "moneda": True,
                 "relacionados": True, "condiciones": True, "addenda": True, "locales": True, "terceros": False,
                 "predial": False, "aduana": False, "plantillas": True, "repetir_ultima": True},
    "completo": {c: True for c in CAMPOS},
}

DEFAULT = {
    "nivel": "estandar",
    "campos": {},
    "modos": ["I", "G", "E", "T"],
    "defaults": {"modo": "I", "metodo": "PUE", "forma": "03", "impuesto": None, "clave_prod_serv": "84111506",
                 "clave_unidad": "E48", "enviar_email": False},
    "perfiles": [],
    "tras_timbrar": "nueva",  # nueva (limpia al instante: un segundo clic no repite la factura) | quedarse (ver resultado)
    "avanzado_abierto": False,
    "claves_bloqueadas": [],  # claves SAT que NO se pueden timbrar en este emisor (medicamentos, etc.)
}


def efectiva(guardada: dict | None) -> dict:
    """Configuración guardada + valores por defecto + campos resueltos por nivel (lo que usa el front)."""
    c = deepcopy(DEFAULT)
    g = guardada or {}
    for k, v in g.items():
        if k == "defaults" and isinstance(v, dict):
            c["defaults"].update(v)
        elif k in c:
            c[k] = v
    if c["nivel"] not in NIVELES:
        c["nivel"] = "estandar"
    c["visibles"] = {**NIVELES[c["nivel"]], **{k: bool(v) for k, v in (c.get("campos") or {}).items() if k in CAMPOS}}
    c["modos"] = [m for m in c["modos"] if m in ("I", "G", "E", "T")] or ["I"]
    return c


def limpiar(entrada: dict) -> dict:
    """Sólo guarda llaves conocidas (evita basura en la BD)."""
    out = {k: entrada[k] for k in ("nivel", "campos", "modos", "defaults", "perfiles", "tras_timbrar", "avanzado_abierto",
                                   "claves_bloqueadas") if k in entrada}
    if "claves_bloqueadas" in out:
        out["claves_bloqueadas"] = sorted({str(x).strip() for x in (out["claves_bloqueadas"] or [])
                                           if str(x).strip().isdigit() and len(str(x).strip()) == 8})
    perfiles = []
    for p in out.get("perfiles") or []:
        if isinstance(p, dict) and str(p.get("nombre", "")).strip():
            perfiles.append({k: p.get(k) for k in ("id", "nombre", "modo", "metodo", "forma", "impuesto", "concepto",
                                                    "tercero_id", "uso_cfdi")})
    if "perfiles" in out:
        out["perfiles"] = perfiles[:12]
    return out
