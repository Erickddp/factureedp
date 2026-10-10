"""Nómina 1.2 (CFDI 4.0): recetas preconfiguradas, validación SAT y armado del comprobante.

Los importes (ISR, IMSS) los decide el contador: aquí no se calcula ISR con tablas, sólo se valida la estructura.
"""
import re
from datetime import date, datetime
from decimal import Decimal

from satcfdi.create.cfd import cfdi40, nomina12

from ..models import Emisor, Empleado
from .cfdi import CfdiError

DOS = Decimal("0.01")
SEPARACION = {"022", "023", "025", "039", "044"}  # requieren nodos que aún no se capturan
CURP_RE = re.compile(r"^[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[0-9A-Z]\d$")

# Recetas: lo que lleva cada recibo. "base": "sueldo" = salario_diario × días; None = se captura.
RECETAS = {
    "sueldo": {
        "nombre": "Sueldos y salarios", "tipo_regimen": "02", "tipo_contrato": "01", "tipo_nomina": "O",
        "percepciones": [{"tipo": "001", "clave": "001", "concepto": "Sueldo", "base": "sueldo"}],
        "deducciones": [{"tipo": "002", "clave": "002", "concepto": "ISR"},
                        {"tipo": "001", "clave": "001", "concepto": "Seguridad social (IMSS)"}],
        "otros_pagos": [],
    },
    "asimilados": {
        "nombre": "Asimilados a salarios", "tipo_regimen": "13", "tipo_contrato": "99", "tipo_nomina": "O",
        "percepciones": [{"tipo": "046", "clave": "046", "concepto": "Ingresos asimilados a salarios", "base": "sueldo"}],
        "deducciones": [{"tipo": "002", "clave": "002", "concepto": "ISR"}],
        "otros_pagos": [],
    },
    "asimilados_honorarios": {
        "nombre": "Honorarios asimilados", "tipo_regimen": "11", "tipo_contrato": "99", "tipo_nomina": "O",
        "percepciones": [{"tipo": "046", "clave": "046", "concepto": "Honorarios asimilados a salarios", "base": "sueldo"}],
        "deducciones": [{"tipo": "002", "clave": "002", "concepto": "ISR"}],
        "otros_pagos": [],
    },
    "aguinaldo": {
        "nombre": "Aguinaldo (extraordinaria)", "tipo_nomina": "E",
        "percepciones": [{"tipo": "002", "clave": "002", "concepto": "Aguinaldo"}],
        "deducciones": [{"tipo": "002", "clave": "002", "concepto": "ISR"}],
        "otros_pagos": [],
    },
    "vacaciones": {
        "nombre": "Prima vacacional", "tipo_nomina": "O",
        "percepciones": [{"tipo": "021", "clave": "021", "concepto": "Prima vacacional"}],
        "deducciones": [{"tipo": "002", "clave": "002", "concepto": "ISR"}],
        "otros_pagos": [],
    },
}

DIAS_PERIODO = {"01": 1, "02": 7, "03": 14, "04": 15, "05": 30, "10": 10}


def _d(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(DOS)


def antiguedad(inicio: date, fin: date) -> str:
    """Formato SAT en semanas: P{n}W (semanas completas entre inicio de relación laboral y fin del periodo)."""
    return f"P{max(((fin - inicio).days + 1) // 7, 0)}W"


def validar(emisor: Emisor, emp: Empleado, data) -> list[str]:
    e = []
    if not CURP_RE.match((emp.curp or "").upper()):
        e.append(f"CURP de {emp.nombre} inválida (18 caracteres).")
    if not re.match(r"^\d{5}$", emp.codigo_postal or ""):
        e.append(f"CP de {emp.nombre}: debe ser el de su constancia (5 dígitos).")
    if len(emisor.rfc) == 13 and not emisor.curp:
        e.append(f"{emisor.rfc} es persona física: captura su CURP en Emisores para timbrar nómina.")
    sueldos = emp.tipo_regimen in ("02", "03", "04")
    if emp.tipo_contrato in {f"0{i}" for i in range(1, 9)} and not sueldos:
        e.append("Contrato 01-08 (laboral) exige régimen 02, 03 o 04 (sueldos).")
    if emp.tipo_contrato in ("09", "10", "99") and sueldos:
        e.append("Contrato 09/10/99 (sin relación laboral) no puede ir con régimen de sueldos 02-04.")
    if sueldos and not emisor.registro_patronal:
        e.append(f"Régimen de sueldos: captura el registro patronal de {emisor.rfc} en Emisores.")
    if emisor.registro_patronal:
        for campo, txt in (("nss", "NSS"), ("fecha_inicio", "fecha de ingreso"), ("riesgo_puesto", "riesgo de puesto"),
                           ("sdi", "salario diario integrado")):
            if not getattr(emp, campo):
                e.append(f"Con registro patronal falta {txt} de {emp.nombre}.")
    if data.fecha_inicial > data.fecha_final:
        e.append("La fecha inicial del periodo es posterior a la final.")
    if not data.percepciones and not data.otros_pagos:
        e.append("El recibo necesita al menos una percepción u otro pago.")
    for p in data.percepciones:
        if p.tipo in SEPARACION:
            e.append(f"Percepción {p.tipo} (separación/jubilación) aún no se soporta en Timbra.")
        if _d(p.gravado) < 0 or _d(p.exento) < 0:
            e.append(f"Percepción {p.concepto}: importes negativos.")
    for o in data.otros_pagos:
        if o.tipo == "002" and o.subsidio_causado is None:
            e.append("Subsidio para el empleo (002) requiere el subsidio causado.")
    neto = (sum((_d(p.gravado) + _d(p.exento) for p in data.percepciones), Decimal(0))
            + sum((_d(o.importe) for o in data.otros_pagos), Decimal(0))
            - sum((_d(x.importe) for x in data.deducciones), Decimal(0)))
    if neto < 0:
        e.append(f"El neto de {emp.nombre} sale negativo ({neto}).")
    return e


def construir(emisor: Emisor, emp: Empleado, data, serie, folio, fecha: datetime) -> cfdi40.Comprobante:
    errores = validar(emisor, emp, data)
    if errores:
        raise CfdiError("No timbré la nómina, corrige esto: " + " · ".join(errores))
    rec = dict(
        curp=emp.curp.upper(), tipo_contrato=emp.tipo_contrato, tipo_regimen=emp.tipo_regimen,
        num_empleado=emp.num_empleado, periodicidad_pago="99" if data.tipo_nomina == "E" else emp.periodicidad_pago,
        clave_ent_fed=emp.clave_ent_fed, tipo_jornada=emp.tipo_jornada, departamento=emp.departamento,
        puesto=emp.puesto, banco=emp.banco, cuenta_bancaria=emp.cuenta_bancaria or None,
    )
    if emisor.registro_patronal:
        rec.update(num_seguridad_social=emp.nss, fecha_inicio_rel_laboral=emp.fecha_inicio.date(),
                   antiguedad=antiguedad(emp.fecha_inicio.date(), data.fecha_final), riesgo_puesto=emp.riesgo_puesto,
                   salario_base_cot_apor=_d(emp.sdi), salario_diario_integrado=_d(emp.sdi))
    percepciones = None
    if data.percepciones:
        percepciones = nomina12.Percepciones(percepcion=[
            nomina12.Percepcion(tipo_percepcion=p.tipo, clave=p.clave, concepto=p.concepto,
                                importe_gravado=_d(p.gravado), importe_exento=_d(p.exento))
            for p in data.percepciones])
    deds = [nomina12.Deduccion(tipo_deduccion=x.tipo, clave=x.clave, concepto=x.concepto, importe=_d(x.importe))
            for x in data.deducciones if _d(x.importe) > 0]
    otros = [nomina12.OtroPago(tipo_otro_pago=o.tipo, clave=o.clave, concepto=o.concepto, importe=_d(o.importe),
                               subsidio_al_empleo=_d(o.subsidio_causado) if o.tipo == "002" else None)
             for o in data.otros_pagos] or None
    emisor_nom = None
    if emisor.registro_patronal or emisor.curp:
        emisor_nom = nomina12.Emisor(registro_patronal=emisor.registro_patronal or None,
                                     curp=emisor.curp if len(emisor.rfc) == 13 else None)
    nom = nomina12.Nomina(
        tipo_nomina=data.tipo_nomina, fecha_pago=data.fecha_pago, fecha_inicial_pago=data.fecha_inicial,
        fecha_final_pago=data.fecha_final, num_dias_pagados=Decimal(str(data.dias)).quantize(Decimal("0.001")),
        receptor=nomina12.Receptor(**rec), emisor=emisor_nom, percepciones=percepciones,
        deducciones=nomina12.Deducciones(deduccion=deds), otros_pagos=otros,
    )
    # satcfdi siempre pone Deducciones y totales en 0; el SAT no los quiere si no aplican
    d = nom["Deducciones"]
    for k in ("TotalSeparacionIndemnizacion", "TotalJubilacionPensionRetiro"):
        d.pop(k, None)
    if not deds:
        nom["Deducciones"] = None
        nom["TotalDeducciones"] = None
    else:
        for k in ("TotalOtrasDeducciones", "TotalImpuestosRetenidos"):
            if not d.get(k):
                d.pop(k, None)
    return cfdi40.Comprobante.nomina(
        emisor=cfdi40.Emisor(rfc=emisor.rfc, nombre=emisor.nombre, regimen_fiscal=emisor.regimen_fiscal),
        lugar_expedicion=emisor.lugar_expedicion,
        receptor=cfdi40.Receptor(rfc=emp.rfc.upper(), nombre=emp.nombre.upper(), domicilio_fiscal_receptor=emp.codigo_postal,
                                 regimen_fiscal_receptor="605", uso_cfdi="CN01"),
        complemento_nomina=nom, serie=serie, folio=folio, fecha=fecha,
    )


def payload_de_receta(emp: Empleado, receta_id: str | None, desde: date, hasta: date, dias=None) -> dict:
    """Recibo listo para editar: receta del empleado (o la indicada) con el sueldo del periodo ya calculado."""
    base = emp.receta if (emp.receta and not receta_id) else RECETAS.get(receta_id or "sueldo", RECETAS["sueldo"])
    dias = Decimal(str(dias if dias is not None else DIAS_PERIODO.get(emp.periodicidad_pago, (hasta - desde).days + 1)))
    sueldo = _d(Decimal(emp.salario_diario or 0) * dias)

    def imp(x):
        return str(sueldo) if x.get("base") == "sueldo" else str(x.get("importe") or x.get("gravado") or "0")
    return {
        "empleado_id": emp.id, "tipo_nomina": base.get("tipo_nomina", "O"), "fecha_inicial": str(desde),
        "fecha_final": str(hasta), "fecha_pago": str(hasta), "dias": str(dias),
        "percepciones": [{"tipo": p["tipo"], "clave": p["clave"], "concepto": p["concepto"], "gravado": imp(p),
                          "exento": str(p.get("exento") or "0")} for p in base.get("percepciones", [])],
        "deducciones": [{"tipo": x["tipo"], "clave": x["clave"], "concepto": x["concepto"],
                         "importe": str(x.get("importe") or "0")} for x in base.get("deducciones", [])],
        "otros_pagos": [{"tipo": o["tipo"], "clave": o["clave"], "concepto": o["concepto"],
                         "importe": str(o.get("importe") or "0"), "subsidio_causado": o.get("subsidio_causado")}
                        for o in base.get("otros_pagos", [])],
    }
