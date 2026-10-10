"""Investigar la clave de producto/servicio (c_ClaveProdServ) y la unidad antes de facturar.

El catálogo del SAT sólo trae clave + descripción. Aquí se le suma lo que hace útil la búsqueda:
- ranking (frase exacta > palabra completa > fragmento), sin acentos y con singular/plural,
- sinónimos del día a día ("renta" → alquiler/arrendamiento, "doctor" → médicos, "vitaminas" → suplementos),
- jerarquía por prefijo (clase, hermanas, relacionadas),
- avisos operativos (familia de medicamentos, claves que el emisor bloqueó, 01010101) y orientación fiscal breve.
La orientación fiscal es una ayuda, no asesoría: siempre se confirma con el contador.
"""
import re
import unicodedata
from bisect import bisect_left
from functools import lru_cache

from satcfdi.catalogs import select_all

TABLAS = {"prod_serv": "C756_c_ClaveProdServ", "unidad": "C756_c_ClaveUnidad"}

# palabra que escribe la gente → frases tal como las escribe el catálogo del SAT (sin acentos).
# Una frase exige TODAS sus palabras; las coincidencias por sinónimo pesan más que la palabra literal (la gente que escribe
# "contador" busca servicios contables, no un "tubo contador").
SINONIMOS: dict[str, list[str]] = {
    "doctor": ["servicios medicos", "doctores"], "doctora": ["servicios medicos", "doctores"],
    "medico": ["servicios medicos", "medicos de atencion"], "medica": ["servicios medicos", "medicos de atencion"],
    "dentista": ["servicios dentales"], "dental": ["servicios dentales"], "odontologo": ["servicios dentales"],
    "psicologo": ["servicios de psicologia"], "psicologa": ["servicios de psicologia"], "psicologia": ["servicios de psicologia"],
    "nutriologo": ["asuntos nutricionales"], "nutricion": ["asuntos nutricionales"], "fisioterapia": ["servicios de fisioterapia"],
    "fisioterapeuta": ["servicios de fisioterapia"], "terapia": ["servicios de fisioterapia"],
    "laboratorio": ["laboratorios medicos"], "analisis": ["laboratorios medicos"],
    "vitaminas": ["suplementos vitaminicos"], "vitamina": ["suplementos vitaminicos"], "suplemento": ["suplementos"],
    "medicamento": ["medicamento"], "medicina": ["medicamento"],
    "contador": ["servicios contables"], "contadora": ["servicios contables"], "contabilidad": ["servicios contables"],
    "contable": ["servicios contables"], "impuestos": ["preparacion de impuestos"], "fiscal": ["preparacion de impuestos"],
    "declaraciones": ["preparacion de impuestos"], "auditoria": ["servicios de auditoria"],
    "honorarios": ["consultoria de negocios"], "consultor": ["consultoria de negocios"],
    "consultoria": ["consultoria de negocios"], "asesoria": ["consultoria de negocios", "servicios legales"],
    "abogado": ["servicios legales"], "abogada": ["servicios legales"], "legal": ["servicios legales"],
    "renta": ["alquiler y arrendamiento"], "rentas": ["alquiler y arrendamiento"], "alquiler": ["alquiler y arrendamiento"],
    "arrendamiento": ["alquiler y arrendamiento"], "local": ["propiedades o edificaciones"],
    "oficina": ["propiedades o edificaciones"], "bodega": ["propiedades o edificaciones"], "casa": ["propiedades o edificaciones"],
    "flete": ["transporte de carga"], "fletes": ["transporte de carga"], "transporte": ["transporte de carga"],
    "envio": ["paqueteo y courrier"], "paqueteria": ["paqueteo y courrier"], "mensajeria": ["paqueteo y courrier"],
    "comida": ["servicios de comida"], "restaurante": ["servicios de comida"], "alimentos": ["servicios de comida"],
    "celular": ["telefonos moviles"], "telefono": ["telefonos moviles"], "laptop": ["computadores notebook"], "notebook": ["computadores notebook"],
    "computadora": ["computadores notebook", "computadores de escritorio"], "pc": ["computadores de escritorio"], "software": ["ingenieria de software", "servicios de sistemas"],
    "sistema": ["servicios de sistemas"], "programacion": ["ingenieria de software"], "pagina": ["servicios de internet"],
    "web": ["servicios de internet"], "hosting": ["servicios de internet"], "internet": ["servicios de internet"],
    "publicidad": ["publicidad en internet", "servicios de publicidad"], "marketing": ["publicidad en internet"],
    "capacitacion": ["servicios de capacitacion"], "curso": ["servicios de capacitacion"], "taller": ["servicios de capacitacion"],
    "limpieza": ["servicios de limpieza"], "vigilancia": ["servicios de seguridad", "vigilancia"],
    "seguridad": ["servicios de seguridad"], "hotel": ["hospedaje"], "hospedaje": ["hospedaje"],
    "gimnasio": ["gimnasios o centros de salud"], "reparacion": ["servicios de reparacion"], "mantenimiento": ["servicios de mantenimiento"],
    "construccion": ["apoyo para la construccion"], "seguro": ["servicios de seguros"], "seguros": ["servicios de seguros"],
    "comision": ["distribuidores por comision"], "comisiones": ["distribuidores por comision"],
    "factura": ["servicios de facturacion"], "facturacion": ["servicios de facturacion"], "anticipo": ["servicios de facturacion"],
    "traduccion": ["traduccion"], "fotografia": ["fotografia"], "evento": ["eventos"],
}

# prefijo de clave → orientación. nivel: "alerta" (revisar antes de facturar) | "info"
NOTAS: list[tuple[str, str, str]] = [
    ("01010101", "alerta", "01010101 «No existe en el catálogo» sólo se recomienda en factura global a público en general. "
                           "Para un cliente identificado usa la clave real de lo que vendes."),
    ("51", "alerta", "Esta clave es de la familia de medicamentos y productos farmacéuticos. Confirma que sea realmente lo que "
                     "vendes (un suplemento no es un medicamento) y que tengas lo necesario para venderlo."),
    ("5119", "info", "Los suplementos van en 51191900 (dietéticos) o 51191905 (vitamínicos). Un medicamento, aunque se venda en "
                     "el mismo consultorio, NO es un suplemento: su clave es otra y suele llevar tratamiento distinto."),
    ("8512", "info", "Servicios médicos: la exención de IVA depende de quién presta el servicio (persona física con título y "
                     "cédula). Una sociedad (S.A., S.A.S., etc.) causa IVA 16%. Confírmalo con tu contador."),
    ("85101", "info", "Consultorios y servicios de salud en establecimientos: revisa si quien factura es persona física o moral."),
    ("80131", "info", "Arrendamiento: captura la cuenta predial en el concepto. Si el arrendador es persona física y el inquilino "
                      "persona moral, hay retención de ISR (10%) y de IVA (2/3)."),
    ("7810", "info", "Transporte de carga: suele llevar retención de IVA del 4%. Si trasladas mercancía en vehículo, revisa si "
                     "corresponde el complemento Carta Porte."),
    ("8010", "info", "Servicios profesionales: de persona física a persona moral aplica retención de ISR 10% e IVA 2/3."),
    ("8411", "info", "Servicios contables y fiscales: de persona física a persona moral aplica retención de ISR 10% e IVA 2/3."),
    ("84111506", "info", "Servicios de facturación: es la clave que el SAT indica para facturar anticipos (unidad ACT)."),
]

UNIDADES_COMUNES: list[tuple[str, str]] = [
    ("E48", "Servicios (honorarios, consultas, rentas, mantenimiento, cualquier servicio)"),
    ("H87", "Productos que cuentas por pieza (la mayoría de mercancía)"),
    ("ACT", "Actividad: anticipos y cobros por una actividad (junto con 84111506)"),
    ("MON", "Mes: renta mensual, iguala mensual"),
    ("HUR", "Hora: servicios cobrados por hora"),
    ("DAY", "Día"),
    ("KGM", "Kilogramo"),
    ("LTR", "Litro"),
    ("MTR", "Metro"),
    ("MTK", "Metro cuadrado"),
    ("XBX", "Caja"),
    ("XPK", "Paquete"),
    ("SET", "Conjunto o juego"),
    ("PR", "Par"),
    ("C62", "Uno: cuando ninguna otra unidad aplica"),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _raiz(t: str) -> str:
    """Singular/plural muy simple: consultas → consulta, medicos → medico."""
    for suf in ("es", "s"):
        if len(t) > 4 and t.endswith(suf):
            return t[: -len(suf)]
    return t


@lru_cache
def _indice(tabla: str) -> tuple[tuple[str, str, str], ...]:
    out = []
    for k, v in select_all(tabla).items():
        clave = k if isinstance(k, str) else k[0]
        desc = str(v[0] if isinstance(v, (list, tuple)) else v)
        out.append((clave, desc, norm(desc)))
    return tuple(sorted(out))


@lru_cache
def _descripciones(tabla: str) -> dict[str, str]:
    return {c: d for c, d, _ in _indice(tabla)}


@lru_cache
def _vocab(tabla: str) -> tuple[dict[str, list[int]], list[str]]:
    """palabra → posiciones en el índice, y la lista ordenada de palabras (para buscar por inicio con bisect)."""
    voc: dict[str, list[int]] = {}
    for i, (_, _, nd) in enumerate(_indice(tabla)):
        for w in set(nd.split()):
            voc.setdefault(w, []).append(i)
    return voc, sorted(voc)


def descripcion(clave: str, tipo: str = "prod_serv") -> str | None:
    return _descripciones(TABLAS[tipo]).get(clave)


def _variantes(tok: str) -> list[tuple[str, float]]:
    """La palabra, sin plural y sin género (medica/medicos → medic), de más a menos exacta."""
    out = [(tok, 3.2)]
    r = _raiz(tok)
    if r != tok:
        out.append((r, 3.0))
    base = r
    if len(base) >= 5 and base[-1] in "aoe":
        out.append((base[:-1], 2.0))
    return out


def _ids_palabra(tabla: str, w: str, peso: float) -> dict[int, float]:
    voc, orden = _vocab(tabla)
    out: dict[int, float] = {}
    for i in voc.get(w, ()):
        out[i] = peso
    if len(w) >= 3:
        for p in orden[bisect_left(orden, w): bisect_left(orden, w + "\uffff")]:
            if p != w:
                for i in voc[p]:
                    if out.get(i, 0) < peso - 1.0:
                        out[i] = peso - 1.0
    return out


def _ids_frase(tabla: str, frase: str, peso: float) -> dict[int, float]:
    """Todas las palabras de la frase (cada una completa o como inicio). Sube si aparece la frase tal cual."""
    partes = [_ids_palabra(tabla, w, peso) for w in frase.split()]
    if not partes:
        return {}
    comunes = set(partes[0])
    for d in partes[1:]:
        comunes &= set(d)
    idx = _indice(tabla)
    return {i: min(d[i] for d in partes) + (1.0 if frase in idx[i][2] else 0.0) for i in comunes}


def _grupo(tabla: str, tok: str) -> dict[int, float]:
    """Entradas que cumplen esta palabra de la búsqueda → mejor puntaje (los sinónimos pesan +1.5)."""
    res: dict[int, float] = {}
    for alt, peso in _variantes(tok):
        for i, s in _ids_palabra(tabla, alt, peso).items():
            res[i] = max(res.get(i, 0), s)
    for sin in SINONIMOS.get(tok, []) + SINONIMOS.get(_raiz(tok), []):
        for i, s in _ids_frase(tabla, sin, 3.0).items():
            res[i] = max(res.get(i, 0), s + 1.5)
    return res


def _tipo(clave: str) -> str:
    return "Servicio" if clave[:2].isdigit() and int(clave[:2]) >= 70 else "Producto"


def alertas(clave: str, bloqueadas: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    out = []
    if clave in bloqueadas:
        out.append({"nivel": "bloqueo", "texto": f"⛔ La clave {clave} está BLOQUEADA en este emisor: no se puede timbrar con ella."})
    for pref, nivel, texto in NOTAS:
        if clave.startswith(pref) and nivel == "alerta":
            out.append({"nivel": "alerta", "texto": texto})
    return out


def notas(clave: str) -> list[dict]:
    return [{"nivel": n, "texto": t} for p, n, t in NOTAS if clave.startswith(p)]


def _item(clave: str, desc: str, bloqueadas, tipo: str = "prod_serv", parcial: bool = False) -> dict:
    if tipo == "unidad":
        return {"clave": clave, "descripcion": desc, "tipo": None, "nivel": "clave", "alertas": [], "bloqueada": False,
                "parcial": parcial}
    return {"clave": clave, "descripcion": desc, "tipo": _tipo(clave), "nivel": "clase" if clave.endswith("00") else "clave",
            "alertas": alertas(clave, bloqueadas), "bloqueada": clave in bloqueadas, "parcial": parcial}


def buscar(q: str, tipo: str = "prod_serv", limit: int = 30, bloqueadas: set[str] | frozenset[str] = frozenset()) -> list[dict]:
    tabla = TABLAS[tipo]
    idx = _indice(tabla)
    qn = norm(q)
    if not qn:
        return []
    compacto = qn.replace(" ", "")
    if compacto.isdigit() and tipo == "prod_serv":  # escribió (parte de) una clave
        return [_item(c, d, bloqueadas, tipo) for c, d, _ in idx if c.startswith(compacto)][:limit]
    if tipo == "unidad" and len(qn) <= 3:
        exactas = [(c, d) for c, d, _ in idx if c.lower() == qn]
        if exactas:
            return [_item(c, d, bloqueadas, tipo) for c, d in exactas]
    toks = qn.split()
    grupos = [_grupo(tabla, t) for t in toks]
    comunes = {c for c, _ in UNIDADES_COMUNES}
    todos = set(grupos[0]).intersection(*grupos[1:]) if grupos else set()
    puntuados = []
    for i in todos:
        clave, desc, nd = idx[i]
        pts = sum(g[i] for g in grupos)
        if len(toks) > 1 and qn in nd:
            pts += 4  # la frase completa tal cual; con una sola palabra mandan los sinónimos
        if nd.startswith("servicio"):
            pts += 0.6  # quien busca "dentista" quiere el servicio, no las fresas dentales
        if tipo == "unidad" and clave in comunes:
            pts += 2
        if tipo == "unidad" and clave.lower().startswith(qn):
            pts += 3
        puntuados.append((pts - len(nd) / 400, clave, desc))
    puntuados.sort(key=lambda x: (-x[0], len(x[2]), x[1]))
    res = [_item(c, d, bloqueadas, tipo) for _, c, d in puntuados[:limit]]
    if len(res) < min(limit, 8) and len(grupos) > 1:  # pocas coincidencias completas: sugiere parciales, marcadas
        parciales: dict[int, float] = {}
        for g in grupos:
            for i, s in g.items():
                if i not in todos:
                    parciales[i] = parciales.get(i, 0) + s
        orden = sorted(parciales.items(), key=lambda x: (-x[1], len(idx[x[0]][1]), idx[x[0]][0]))
        res += [_item(idx[i][0], idx[i][1], bloqueadas, tipo, parcial=True) for i, _ in orden[: min(4, limit - len(res))]]  # pocas y claramente marcadas: más sería ruido
    return res


def sugerir(texto: str, tipo: str = "prod_serv", limit: int = 3) -> list[dict]:
    """Clave probable para una descripción libre ("Renta de bodega CENTRO"): ignora las palabras que el catálogo no conoce
    (nombres propios, marcas, adjetivos) y busca con las demás. Sólo coincidencias completas."""
    tabla = TABLAS[tipo]
    utiles = [w for w in norm(texto).split() if len(w) > 2 and _grupo(tabla, w)]
    if not utiles:
        return []
    return [r for r in buscar(" ".join(utiles), tipo, limit) if not r["parcial"]]


def detalle(clave: str, bloqueadas: set[str] | frozenset[str] = frozenset()) -> dict | None:
    desc = descripcion(clave)
    if desc is None:
        return None
    idx = _indice(TABLAS["prod_serv"])
    es_clase = clave.endswith("00")
    base6, base4 = clave[:6], clave[:4]
    clase = f"{base6}00"
    jer = []
    if not es_clase and descripcion(clase):
        jer.append({"nivel": "Clase", "clave": clase, "descripcion": descripcion(clase)})
    hermanas = [{"clave": c, "descripcion": d} for c, d, _ in idx if c.startswith(base6) and c != clave and c != clase][:40]
    relacionadas = [{"clave": c, "descripcion": d} for c, d, _ in idx
                    if c.startswith(base4) and c.endswith("00") and c not in (clave, clase)][:30]
    return {**_item(clave, desc, bloqueadas), "jerarquia": jer, "hermanas": hermanas, "relacionadas": relacionadas,
            "notas": notas(clave)}


def unidades_comunes() -> list[dict]:
    return [{"clave": c, "descripcion": descripcion(c, "unidad") or c, "cuando": cuando} for c, cuando in UNIDADES_COMUNES]
