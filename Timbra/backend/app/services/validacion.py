"""Validaciones previas al timbrado (CFDI 4.0, Anexo 20 y catálogos vigentes que trae satcfdi).

Todo lo que el PAC o el SAT rechazarían se detecta aquí ANTES de gastar un timbre.
Devuelve {"errores": [...], "avisos": [...]} con mensajes listos para mostrar.
"""
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from satcfdi.catalogs import select

from ..models import Addenda, Cliente, Emisor
from ..schemas import FacturaIn

RFC_RE = re.compile(r"^([A-ZÑ&]{3,4})(\d{2})(\d{2})(\d{2})([A-Z\d]{2})([A\d])$")
UUID_RE = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$", re.I)
GENERICOS = {"XAXX010101000", "XEXX010101000"}

# c_RegimenFiscal: a qué tipo de persona aplica
REG_FISICA = {"605", "606", "607", "608", "610", "611", "612", "614", "615", "616", "621", "625", "626"}
REG_MORAL = {"601", "603", "610", "620", "622", "623", "624", "626"}

# c_UsoCFDI: regímenes del receptor con los que es compatible cada uso
_EMPRESARIAL = {"601", "603", "606", "612", "620", "621", "622", "623", "624", "625", "626"}
_DEDUCCIONES = {"605", "606", "608", "611", "612", "614", "607", "615", "625"}
_TODOS = {"601", "603", "605", "606", "608", "610", "611", "612", "614", "616", "620", "621", "622",
          "623", "624", "607", "615", "625", "626"}
USO_REGIMEN = {
    **{u: _EMPRESARIAL for u in ("G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I07", "I08")},
    **{f"D{n:02d}": _DEDUCCIONES for n in range(1, 11)},
    "S01": _TODOS, "CP01": _TODOS, "CN01": {"605"},
}

SOCIETARIO = re.compile(
    r"[,\s]+(S\.?\s?A\.?\s?P\.?\s?I\.?|S\.?\s?A\.?\s?B\.?|S\.?\s?A\.?|S\.?\s?DE\s?R\.?\s?L\.?|S\.?\s?C\.?|A\.?\s?C\.?|"
    r"S\.?\s?A\.?\s?S\.?)(\s+DE\s+C\.?\s?V\.?)?\s*$", re.I)


def tipo_persona(rfc: str) -> str:
    return "moral" if len(rfc) == 12 else "fisica"


def digito_rfc_ok(rfc: str) -> bool:
    """Dígito verificador del RFC (homoclave). Los genéricos no aplican."""
    tabla = "0123456789ABCDEFGHIJKLMN&OPQRSTUVWXYZ Ñ"
    rfc = rfc.upper()
    base = rfc[:-1] if len(rfc) == 13 else " " + rfc[:-1]
    try:
        suma = sum(tabla.index(c) * (13 - i) for i, c in enumerate(base))
    except ValueError:
        return False
    m = suma % 11
    dv = "0" if m == 0 else ("A" if 11 - m == 10 else str(11 - m))
    return dv == rfc[-1]


def rfc_valido(rfc: str) -> bool:
    m = RFC_RE.match(rfc or "")
    if not m:
        return False
    mes, dia = int(m.group(3)), int(m.group(4))
    return 1 <= mes <= 12 and 1 <= dia <= 31


def nombre_sin_societario(nombre: str) -> str:
    return SOCIETARIO.sub("", nombre).strip(" ,.")


def usos_permitidos(regimen: str) -> list[str]:
    return [u for u, regs in USO_REGIMEN.items() if regimen in regs]


def quitar_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _d(v) -> Decimal | None:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError):
        return None


class Resultado:
    def __init__(self):
        self.errores: list[dict] = []
        self.avisos: list[dict] = []

    def error(self, campo: str, mensaje: str, sugerencia: str | None = None):
        self.errores.append({"campo": campo, "mensaje": mensaje, "sugerencia": sugerencia})

    def aviso(self, campo: str, mensaje: str, sugerencia: str | None = None):
        self.avisos.append({"campo": campo, "mensaje": mensaje, "sugerencia": sugerencia})

    def dict(self):
        return {"errores": self.errores, "avisos": self.avisos}


def validar_receptor_datos(r: Resultado, rfc: str, nombre: str, regimen: str, cp: str, uso: str | None,
                           prefijo: str = "receptor", tipo_cfdi: str = "I"):
    rfc = (rfc or "").upper()
    if not rfc_valido(rfc):
        r.error(f"{prefijo}.rfc", f"RFC {rfc or '(vacío)'} con formato inválido.")
        return
    if rfc not in GENERICOS and not digito_rfc_ok(rfc):
        r.aviso(f"{prefijo}.rfc", f"El dígito verificador de {rfc} no cuadra. Revisa contra la constancia.")
    if not nombre or not nombre.strip():
        r.error(f"{prefijo}.nombre", "Falta el nombre o razón social.")
    elif SOCIETARIO.search(nombre):
        r.aviso(f"{prefijo}.nombre", "El nombre parece incluir el régimen societario (SA DE CV, SC…). En CFDI 4.0 va sin él.",
                nombre_sin_societario(nombre))
    if not re.fullmatch(r"\d{5}", cp or ""):
        r.error(f"{prefijo}.codigo_postal", "El código postal debe tener 5 dígitos.")
    elif select("C756_c_CodigoPostal", cp) is None:
        r.error(f"{prefijo}.codigo_postal", f"El CP {cp} no existe en el catálogo del SAT.")
    if rfc == "XAXX010101000":
        if regimen != "616":
            r.error(f"{prefijo}.regimen_fiscal", "Con RFC genérico XAXX el régimen debe ser 616 (Sin obligaciones fiscales).")
        if uso and uso != "S01":
            r.error(f"{prefijo}.uso_cfdi", "Con RFC genérico XAXX el uso debe ser S01 (Sin efectos fiscales).")
        return
    if not regimen or select("C756_c_RegimenFiscal", regimen) is None:
        r.error(f"{prefijo}.regimen_fiscal", "Falta el régimen fiscal del receptor o no existe.")
        return
    persona = tipo_persona(rfc)
    if rfc not in GENERICOS and regimen not in (REG_MORAL if persona == "moral" else REG_FISICA):
        r.error(f"{prefijo}.regimen_fiscal",
                f"El régimen {regimen} no aplica a persona {persona} (RFC de {len(rfc)} caracteres).")
    if uso and tipo_cfdi in ("I", "E"):
        permitidos = usos_permitidos(regimen)
        if uso not in USO_REGIMEN:
            r.error(f"{prefijo}.uso_cfdi", f"Uso CFDI {uso} no existe.")
        elif uso not in permitidos:
            r.error(f"{prefijo}.uso_cfdi", f"El uso {uso} no es compatible con el régimen {regimen} del receptor.",
                    ", ".join(u for u in permitidos if u not in ("CP01", "CN01")))


IVA_TASAS = {Decimal("0.16"), Decimal("0.08"), Decimal("0")}
# Retención de IVA en honorarios/arrendamiento: 2/3 del IVA trasladado
DOS_TERCIOS = {Decimal("0.16"): Decimal("0.106667"), Decimal("0.08"): Decimal("0.053333")}
FIN_ESTIMULO_FRONTERA = datetime(2026, 12, 31, 23, 59, 59)  # DOF 31-dic-2025


def _impuestos_concepto(r, i: int, c, cp: str):
    iva_tras, exento = None, False
    for imp in c.impuestos:
        if imp.impuesto == "001" and imp.tipo == "traslado":
            r.error(cp, f"Concepto {i}: el ISR no se traslada, sólo se retiene.")
        if imp.factor == "Exento":
            if imp.tipo == "retencion":
                r.error(cp, f"Concepto {i}: una retención no puede ser exenta.")
            elif imp.impuesto == "002":
                exento = True
            continue
        t = _d(imp.tasa)
        if t is None:
            r.error(cp, f"Concepto {i}: falta la tasa del impuesto.")
            continue
        if imp.factor == "Cuota" and imp.impuesto != "003":
            r.error(cp, f"Concepto {i}: sólo el IEPS se cobra por cuota; IVA e ISR van por tasa.")
        if imp.impuesto == "003" and t <= 0:
            r.error(cp, f"Concepto {i}: la tasa o cuota de IEPS debe ser mayor a cero.")
        if imp.impuesto == "003" and imp.factor == "Tasa" and t > Decimal(3):
            r.error(cp, f"Concepto {i}: tasa de IEPS {t} fuera de rango. Se escribe en decimal: 8% = 0.08.")
        if imp.impuesto == "002" and imp.tipo == "traslado":
            if t not in IVA_TASAS:
                r.error(cp, f"Concepto {i}: tasa de IVA {t} inválida. Usa 16%, 8% (frontera) o 0%.")
            iva_tras = t
        if imp.impuesto == "002" and imp.tipo == "retencion" and not (Decimal(0) < t <= Decimal("0.16")):
            r.error(cp, f"Concepto {i}: retención de IVA fuera de rango (0 a 16%).")
        if imp.impuesto == "001" and imp.tipo == "retencion" and not (Decimal(0) < t <= Decimal("0.35")):
            r.error(cp, f"Concepto {i}: retención de ISR fuera de rango (0 a 35%).")
    for imp in c.impuestos:
        if not (imp.impuesto == "002" and imp.tipo == "retencion" and imp.factor != "Exento"):
            continue
        t = _d(imp.tasa)
        if t is None or t == Decimal("0.04"):  # fletes: 4% del valor, sin importar la tasa
            continue
        if exento or iva_tras in (None, Decimal(0)):
            r.error(cp, f"Concepto {i}: retienes IVA pero este concepto no traslada IVA (exento o 0%).")
        elif t > iva_tras:
            usual = f" Lo usual es 2/3 = {DOS_TERCIOS[iva_tras] * 100:.4f}%." if iva_tras in DOS_TERCIOS else ""
            r.error(cp, f"Concepto {i}: retienes {t * 100:.4f}% de IVA pero sólo trasladas {iva_tras * 100:.0f}%.{usual}")
        elif iva_tras in DOS_TERCIOS and abs(t - DOS_TERCIOS[iva_tras]) > Decimal("0.000002") and t not in (Decimal("0.06"), iva_tras):
            # Válidas: 2/3 (honorarios, arrendamiento), 6% (servicios especializados) y el IVA completo.
            esp = DOS_TERCIOS[iva_tras]
            r.aviso(cp, f"Concepto {i}: retención de IVA de {t * 100:.4f}% poco común. Lo usual con IVA al "
                        f"{iva_tras * 100:.0f}% es 2/3 = {esp * 100:.4f}%, 6% (servicios especializados) o el IVA completo.")


PREDIAL_RE = re.compile(r"^[0-9a-zA-Z]{1,150}$")
PEDIMENTO_RE = re.compile(r"^\d{2}  \d{2}  \d{4}  \d{7}$")


def pedimento_normal(p: str) -> str:
    """Acepta 15 dígitos con o sin espacios/guiones y lo deja como pide el SAT: 'AA  AA  AAAA  AAAAAAA'."""
    d = re.sub(r"\D", "", p or "")
    return f"{d[:2]}  {d[2:4]}  {d[4:8]}  {d[8:]}" if len(d) == 15 else (p or "")


def _terceros_predial_aduana(r, i: int, c, cp: str, emisor: Emisor):
    t = c.a_cuenta_terceros
    if t:
        rfc = str(t.get("rfc", "")).upper().strip()
        if not rfc_valido(rfc) or rfc in GENERICOS:
            r.error(cp, f"Concepto {i}: RFC del tercero {rfc or '(vacío)'} inválido (no se permiten genéricos).")
        elif rfc == emisor.rfc:
            r.error(cp, f"Concepto {i}: el tercero no puede ser el mismo emisor. Quita «a cuenta de terceros».")
        else:
            reg = str(t.get("regimen_fiscal", ""))
            if reg not in (REG_MORAL if tipo_persona(rfc) == "moral" else REG_FISICA):
                r.error(cp, f"Concepto {i}: el régimen {reg or '(vacío)'} del tercero no aplica a persona {tipo_persona(rfc)}.")
        if not str(t.get("nombre", "")).strip():
            r.error(cp, f"Concepto {i}: falta el nombre del tercero (como en su constancia).")
        elif nombre_sin_societario(str(t["nombre"])) != str(t["nombre"]).strip().upper():
            r.aviso(cp, f"Concepto {i}: el nombre del tercero lleva régimen societario; el SAT lo pide sin él.",
                    nombre_sin_societario(str(t["nombre"])))
        cp_t = str(t.get("codigo_postal", ""))
        if select("C756_c_CodigoPostal", cp_t) is None:
            r.error(cp, f"Concepto {i}: el CP fiscal del tercero {cp_t or '(vacío)'} no existe.")
    if c.cuenta_predial:
        for x in [x.strip() for x in c.cuenta_predial.split(",") if x.strip()]:
            if not PREDIAL_RE.match(x):
                r.error(cp, f"Concepto {i}: cuenta predial «{x}» sólo admite letras y números, sin espacios ni guiones.")
    for p in c.informacion_aduanera or []:
        if not PEDIMENTO_RE.match(pedimento_normal(p)):  # con 15 dígitos se acomoda solo al timbrar
            r.error(cp, f"Concepto {i}: el pedimento «{p}» debe tener 15 dígitos (AA AA AAAA AAAAAAA).")


def validar(db, emisor: Emisor, data: FacturaIn, cliente: Cliente | None) -> dict:
    r = Resultado()
    tipo = data.tipo

    # --- Emisor -----------------------------------------------------------
    if not emisor.cer:
        r.error("emisor.csd", f"{emisor.rfc} no tiene CSD cargado. Súbelo en Emisores y CSD.")
    elif emisor.csd_vence and emisor.csd_vence < datetime.now(timezone.utc).replace(tzinfo=None):
        modo_prueba = emisor.pac is None or emisor.pac.proveedor == "demo" or emisor.pac.pruebas
        (r.aviso if modo_prueba else r.error)("emisor.csd", f"El CSD de {emisor.rfc} venció el {emisor.csd_vence:%d/%m/%Y}.")
    if emisor.pac is None or emisor.pac.proveedor == "demo":
        r.aviso("emisor.pac", "Modo demo: se sella pero NO se timbra ante el SAT.")
    elif emisor.pac.pruebas:
        r.aviso("emisor.pac", f"{emisor.pac.nombre} está en ambiente de pruebas: el CFDI no tiene validez fiscal.")
    persona_emisor = tipo_persona(emisor.rfc)
    if emisor.regimen_fiscal not in (REG_MORAL if persona_emisor == "moral" else REG_FISICA):
        r.error("emisor.regimen_fiscal", f"El régimen {emisor.regimen_fiscal} no aplica a persona {persona_emisor}.")
    if select("C756_c_CodigoPostal", emisor.lugar_expedicion) is None:
        r.error("emisor.lugar_expedicion", f"El CP de expedición {emisor.lugar_expedicion} no existe en el catálogo.")

    # --- Receptor ---------------------------------------------------------
    rfc_receptor = None
    if data.publico_general:
        rfc_receptor = "XAXX010101000"
        ig = data.informacion_global
        if ig is not None:
            ig = ig if isinstance(ig, dict) else ig.model_dump()
            per, mes, ano = str(ig.get("periodicidad")), str(ig.get("meses")), int(ig.get("ano") or 0)
            hoy = datetime.now()
            if per == "05" and mes not in {str(m) for m in range(13, 19)}:
                r.error("global.meses", "Periodicidad bimestral usa meses 13 a 18 (13 = enero-febrero).")
            if per != "05" and mes not in {f"{m:02d}" for m in range(1, 13)}:
                r.error("global.meses", "Los meses van de 01 a 12.")
            if ano not in (hoy.year, hoy.year - 1):
                r.error("global.ano", f"El año de la factura global debe ser {hoy.year} o {hoy.year - 1}.")
    else:
        rec = cliente or data.receptor
        if rec is None:
            r.error("receptor", "Falta el receptor: elige un cliente o captura uno nuevo.")
        else:
            rfc_receptor = rec.rfc.upper()
            validar_receptor_datos(r, rec.rfc, rec.nombre, rec.regimen_fiscal,
                                   emisor.lugar_expedicion if rfc_receptor == "XEXX010101000" else rec.codigo_postal,
                                   data.uso_cfdi or rec.uso_cfdi, tipo_cfdi=tipo)

    # --- Pago y moneda ----------------------------------------------------
    if tipo in ("I", "E"):
        if not data.metodo_pago:
            r.error("metodo_pago", "Falta el método de pago (PUE o PPD).")
        if data.metodo_pago == "PUE" and (not data.forma_pago or data.forma_pago == "99"):
            r.error("forma_pago", "En PUE la forma de pago no puede ser 99 (Por definir). Elige cómo te pagaron.")
        if data.forma_pago and select("C756_c_FormaPago", data.forma_pago) is None:
            r.error("forma_pago", f"Forma de pago {data.forma_pago} no existe.")
        if data.moneda not in ("MXN", "XXX"):
            if select("C756_c_Moneda", data.moneda) is None:
                r.error("moneda", f"Moneda {data.moneda} no existe en el catálogo.")
            if not data.tipo_cambio or data.tipo_cambio <= 0:
                r.error("tipo_cambio", f"Con moneda {data.moneda} necesitas el tipo de cambio.")
    if data.exportacion != "01":
        r.error("exportacion", "Exportación distinta de 01 requiere complemento de comercio exterior (no incluido).")

    # --- Conceptos --------------------------------------------------------
    if not data.conceptos:
        r.error("conceptos", "Agrega al menos un concepto.")
    hay_retenciones = False
    usa_8 = False
    for i, c in enumerate(data.conceptos, start=1):
        cp = f"conceptos.{i}"
        if not (c.descripcion or "").strip():
            r.error(cp, f"Concepto {i}: falta la descripción.")
        cant, vu, desc = _d(c.cantidad), _d(c.valor_unitario), _d(c.descuento or 0)
        if cant is None or cant <= 0:
            r.error(cp, f"Concepto {i}: la cantidad debe ser mayor a 0.")
        if vu is None or vu < 0 or (vu == 0 and tipo in ("I", "E")):
            r.error(cp, f"Concepto {i}: el precio debe ser mayor a 0.")
        if cant and vu and desc and desc > cant * vu:
            r.error(cp, f"Concepto {i}: el descuento es mayor que el importe.")
        if not c.clave_prod_serv or select("C756_c_ClaveProdServ", c.clave_prod_serv) is None:
            r.error(cp, f"Concepto {i}: clave SAT {c.clave_prod_serv or '(vacía)'} no existe en el catálogo vigente.")
        if not c.clave_unidad or select("C756_c_ClaveUnidad", c.clave_unidad) is None:
            r.error(cp, f"Concepto {i}: clave de unidad {c.clave_unidad or '(vacía)'} no existe.")
        if tipo != "T":
            if c.objeto_imp == "02" and not c.impuestos:
                r.error(cp, f"Concepto {i}: objeto de impuesto 02 requiere al menos un impuesto.")
            if c.objeto_imp == "01" and c.impuestos:
                r.error(cp, f"Concepto {i}: objeto 01 (no objeto) no lleva impuestos.")
        if tipo != "T":
            _impuestos_concepto(r, i, c, cp)
            if any(_d(x.tasa) == Decimal("0.08") for x in c.impuestos if x.impuesto == "002" and x.tipo == "traslado"):
                usa_8 = True
        if any(x.tipo == "retencion" for x in c.impuestos):
            hay_retenciones = True
        _terceros_predial_aduana(r, i, c, cp, emisor)
        bloq = {str(x) for x in ((getattr(emisor, "config_facturar", None) or {}).get("claves_bloqueadas") or [])}
        if c.clave_prod_serv in bloq:
            r.error(cp, f"Concepto {i}: ⛔ la clave {c.clave_prod_serv} está bloqueada en este emisor "
                        "(medicamento u otra regla). Revísala antes de timbrar.")
        elif str(c.clave_prod_serv).startswith("51"):
            r.aviso(cp, f"Concepto {i}: la clave {c.clave_prod_serv} es de la familia de medicamentos y productos "
                        "farmacéuticos: confirma que sea lo que vendes (un suplemento no es un medicamento).")
        if c.clave_prod_serv == "01010101" and tipo == "I" and not data.publico_general:
            r.aviso(cp, f"Concepto {i}: 01010101 (no existe en catálogo) sólo se recomienda en factura global.")

    if usa_8:
        if not getattr(emisor, "region_fronteriza", False):
            r.aviso("impuestos", "IVA 8%: sólo si estás en el padrón del estímulo de región fronteriza. "
                                 "Si aplica, márcalo en Emisores y CSD.")
        if (data.fecha or datetime.now()).replace(tzinfo=None) > FIN_ESTIMULO_FRONTERA:
            r.aviso("impuestos", "El estímulo de IVA 8% está prorrogado hasta el 31/12/2026: confirma si hubo nueva prórroga.")

    if hay_retenciones and rfc_receptor and tipo_persona(rfc_receptor) == "fisica" and rfc_receptor not in GENERICOS:
        r.aviso("impuestos", "Hay retenciones y el receptor es persona física: normalmente sólo retienen las personas morales.")
    if hay_retenciones and persona_emisor == "moral":
        r.aviso("impuestos", "Emisor persona moral con retenciones de ISR/IVA: revisa que de verdad apliquen.")

    # --- Relacionados -----------------------------------------------------
    for rel in data.relacionados:
        if select("C756_c_TipoRelacion", rel.tipo_relacion) is None:
            r.error("relacionados", f"Tipo de relación {rel.tipo_relacion} no existe.")
        for u in rel.uuids:
            if not UUID_RE.match(u.strip()):
                r.error("relacionados", f"UUID relacionado inválido: {u}")
    if tipo == "E" and not data.relacionados:
        r.aviso("relacionados", "Nota de crédito sin CFDI relacionado: normalmente se relaciona la factura con tipo 01.")

    # --- Addenda ----------------------------------------------------------
    add_id = data.addenda.addenda_id if data.addenda else (cliente.addenda_id if cliente and tipo == "I" else None)
    if add_id:
        tpl = db.get(Addenda, add_id)
        if tpl is None:
            r.error("addenda", "La addenda elegida ya no existe.")
        else:
            datos = {**((cliente.addenda_defaults if cliente else {}) or {}), **(data.addenda.datos if data.addenda else {})}
            for campo in tpl.campos or []:
                if campo.get("required") and not str(datos.get(campo["name"], "")).strip():
                    r.error("addenda", f"Addenda {tpl.nombre}: falta «{campo.get('label', campo['name'])}».")
    return r.dict()
