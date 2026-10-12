"""Arma el CFDI 4.0 con satcfdi (cadena original, sello, totales e impuestos)."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from satcfdi.cfdi import CFDI
from satcfdi.create.cfd import cfdi40, implocal10

from ..config import settings
from ..models import Cliente, Emisor
from ..schemas import ConceptoIn, FacturaIn, ReceptorIn

PUBLICO_GENERAL_RFC = "XAXX010101000"
EXTRANJERO_RFC = "XEXX010101000"


class CfdiError(Exception):
    pass



def pedimento_normal(p: str) -> str:
    from .validacion import pedimento_normal as _n
    return _n(p)

# Husos del catálogo c_CodigoPostal del SAT → zona IANA. El PAC valida la Fecha contra el huso del CP de expedición.
HUSOS = {"Tiempo del Centro": "America/Mexico_City", "Tiempo del Centro en Frontera": "America/Matamoros",
         "Tiempo del Pacífico": "America/Mazatlan", "Tiempo del Noroeste": "America/Tijuana", "Tiempo del Sureste": "America/Cancun"}


def zona_de(cp: str | None) -> ZoneInfo:
    """Zona horaria del código postal de expedición según el SAT; sin CP o si no está en el catálogo, la de la configuración."""
    if cp:
        try:
            from satcfdi import catalogs
            return ZoneInfo(HUSOS[catalogs.select("C756_c_CodigoPostal", cp)[4]])
        except Exception:
            pass
    return ZoneInfo(settings.timezone)


def ahora_mx(cp: str | None = None) -> datetime:
    """Hora local del lugar de expedición, sin zona (así la pide el CFDI).

    Un CFDI con Fecha en el futuro lo rechaza el PAC; con Fecha un poco atrás, no. Por eso, si el reloj de esta PC va
    atrás de la hora del catálogo (municipios cuyo huso cambió, como Cd. Juárez, o PC en otra zona) pero a menos de
    2 horas, se usa el de la PC: es la hora real del lugar y nunca queda adelantada.
    """
    oficial = datetime.now(zona_de(cp)).replace(tzinfo=None, microsecond=0)
    if cp:
        local = datetime.now().replace(microsecond=0)
        if local < oficial and (oficial - local).total_seconds() <= 2 * 3600 + 300:
            return local
    return oficial


SEIS = Decimal("0.000001")


def _tasa(t) -> Decimal | None:
    """c_TasaOCuota exige 6 decimales exactos (0.160000, 0.080000, 0.106667). "0.16" lo rechaza el PAC."""
    return None if t is None else Decimal(str(t)).quantize(SEIS)


def _impuestos(c: ConceptoIn):
    if c.objeto_imp != "02" or not c.impuestos:
        return None
    tras, ret = [], []
    # Con IEPS trasladado satcfdi no alcanza: la cuota se cobra por unidad (base = cantidad) y el IVA se calcula
    # sobre el valor MÁS el IEPS (art. 12 LIVA). Aquí se fijan base e importe a mano, con su mismo redondeo.
    ieps = [i for i in c.impuestos if i.tipo == "traslado" and i.impuesto == "003" and i.factor != "Exento"]
    if ieps:
        valor = round(c.cantidad * c.valor_unitario, 2) - (c.descuento or Decimal(0))
        total_ieps = Decimal(0)
        for i in ieps:
            base = c.cantidad if i.factor == "Cuota" else valor
            importe = round(base * _tasa(i.tasa), 2)
            total_ieps += importe
            tras.append(cfdi40.Traslado(impuesto="003", tipo_factor=i.factor, tasa_o_cuota=_tasa(i.tasa), base=base, importe=importe))
        for i in c.impuestos:
            if i.tipo == "traslado" and i.impuesto != "003":
                if i.factor == "Exento":
                    tras.append(cfdi40.Traslado(impuesto=i.impuesto, tipo_factor="Exento", base=valor + total_ieps))
                else:
                    tras.append(cfdi40.Traslado(impuesto=i.impuesto, tipo_factor=i.factor, tasa_o_cuota=_tasa(i.tasa),
                                                base=valor + total_ieps, importe=round((valor + total_ieps) * _tasa(i.tasa), 2)))
    for i in c.impuestos:
        if i.tipo == "traslado":
            if ieps:
                continue
            if i.factor == "Exento":
                tras.append(cfdi40.Traslado(impuesto=i.impuesto, tipo_factor="Exento"))
            else:
                tras.append(cfdi40.Traslado(impuesto=i.impuesto, tipo_factor=i.factor, tasa_o_cuota=_tasa(i.tasa)))
        else:
            ret.append(cfdi40.Retencion(impuesto=i.impuesto, tipo_factor=i.factor, tasa_o_cuota=_tasa(i.tasa)))
    return cfdi40.Impuestos(traslados=tras or None, retenciones=ret or None)


def _concepto(c: ConceptoIn, tipo: str) -> cfdi40.Concepto:
    kw = dict(
        clave_prod_serv=c.clave_prod_serv,
        cantidad=c.cantidad,
        clave_unidad=c.clave_unidad,
        unidad=c.unidad,
        no_identificacion=c.no_identificacion,
        descripcion=c.descripcion,
        valor_unitario=Decimal(0) if tipo == "T" and not c.valor_unitario else c.valor_unitario,
        descuento=round(c.descuento, 2) if c.descuento else None,  # siempre 2 decimales: Finkok rechaza otra cosa (CFDI40112)
        objeto_imp=c.objeto_imp,
        impuestos=None if tipo == "T" else _impuestos(c),
        cuenta_predial=[x.strip() for x in c.cuenta_predial.split(",") if x.strip()] or None if c.cuenta_predial else None,
        informacion_aduanera=[pedimento_normal(p) for p in c.informacion_aduanera] or None,  # 15 dígitos → formato SAT
    )
    if c.a_cuenta_terceros:
        t = c.a_cuenta_terceros
        kw["a_cuenta_terceros"] = cfdi40.ACuentaTerceros(
            rfc_a_cuenta_terceros=t["rfc"], nombre_a_cuenta_terceros=t["nombre"],
            regimen_fiscal_a_cuenta_terceros=t["regimen_fiscal"],
            domicilio_fiscal_a_cuenta_terceros=t["codigo_postal"],
        )
    return cfdi40.Concepto(**kw)


def receptor_de(emisor: Emisor, data: FacturaIn, cliente: Cliente | None) -> cfdi40.Receptor:
    if data.publico_general:
        return cfdi40.Receptor(
            rfc=PUBLICO_GENERAL_RFC, nombre="PUBLICO EN GENERAL",
            domicilio_fiscal_receptor=emisor.lugar_expedicion,
            regimen_fiscal_receptor="616", uso_cfdi="S01",
        )
    r: Cliente | ReceptorIn | None = cliente or data.receptor
    if r is None:
        raise CfdiError("Falta el receptor: manda cliente_id, receptor o publico_general.")
    cp = r.codigo_postal
    if r.rfc == EXTRANJERO_RFC:
        cp = emisor.lugar_expedicion  # regla SAT para extranjeros
    uso = data.uso_cfdi or r.uso_cfdi
    if data.tipo == "T":
        uso = "S01"
    return cfdi40.Receptor(
        rfc=r.rfc, nombre=r.nombre, domicilio_fiscal_receptor=cp,
        regimen_fiscal_receptor=r.regimen_fiscal, uso_cfdi=uso,
        residencia_fiscal=r.residencia_fiscal, num_reg_id_trib=r.num_reg_id_trib,
    )


def _implocal(data: FacturaIn):
    if not data.impuestos_locales:
        return None, Decimal(0)
    tras = [implocal10.TrasladosLocales(imp_loc_trasladado=i.nombre, tasa_de_traslado=i.tasa, importe=i.importe)
            for i in data.impuestos_locales if i.tipo == "traslado"]
    ret = [implocal10.RetencionesLocales(imp_loc_retenido=i.nombre, tasa_de_retencion=i.tasa, importe=i.importe)
           for i in data.impuestos_locales if i.tipo == "retencion"]
    tt = sum((i.importe for i in data.impuestos_locales if i.tipo == "traslado"), Decimal(0))
    tr = sum((i.importe for i in data.impuestos_locales if i.tipo == "retencion"), Decimal(0))
    if len(tras) > 1 or len(ret) > 1:
        # satcfdi serializa un solo nodo de cada tipo. TODO(claude-code): soportar varios.
        raise CfdiError("Por ahora: máximo un traslado local y una retención local por factura.")
    comp = implocal10.ImpuestosLocales(
        total_de_retenciones=tr, total_de_traslados=tt,
        retenciones_locales=ret[0] if ret else None, traslados_locales=tras[0] if tras else None,
    )
    return comp, tt - tr


def construir(emisor: Emisor, data: FacturaIn, cliente: Cliente | None,
              serie: str | None, folio: str | None) -> cfdi40.Comprobante:
    if not data.conceptos:
        raise CfdiError("La factura necesita al menos un concepto.")
    tipo = data.tipo
    if data.publico_general and not data.informacion_global:
        hoy = ahora_mx()
        data.informacion_global = {"periodicidad": "04", "meses": f"{hoy.month:02d}", "ano": hoy.year}
    ig = data.informacion_global
    if ig is not None and not isinstance(ig, dict):
        ig = ig.model_dump()

    implocal, ajuste_total = _implocal(data)
    kw = dict(
        emisor=cfdi40.Emisor(rfc=emisor.rfc, nombre=emisor.nombre, regimen_fiscal=emisor.regimen_fiscal),
        lugar_expedicion=emisor.lugar_expedicion,
        receptor=receptor_de(emisor, data, cliente),
        conceptos=[_concepto(c, tipo) for c in data.conceptos],
        tipo_de_comprobante=tipo,
        moneda="XXX" if tipo == "T" else data.moneda,
        tipo_cambio=data.tipo_cambio if data.moneda not in ("MXN", "XXX") else None,
        exportacion=data.exportacion,
        serie=serie,
        folio=folio,
        forma_pago=None if tipo == "T" else data.forma_pago,
        metodo_pago=None if tipo == "T" else data.metodo_pago,
        condiciones_de_pago=data.condiciones_pago,
        informacion_global=cfdi40.InformacionGlobal(**ig) if ig else None,
        cfdi_relacionados=[cfdi40.CfdiRelacionados(tipo_relacion=r.tipo_relacion, cfdi_relacionado=r.uuids)
                           for r in data.relacionados] or None,
        complemento=implocal,
        fecha=data.fecha or ahora_mx(emisor.lugar_expedicion),
    )
    # Regla SAT: PPD siempre con forma de pago 99
    if kw["metodo_pago"] == "PPD":
        kw["forma_pago"] = "99"
    comp = cfdi40.Comprobante(**kw)
    if ajuste_total:
        comp["Total"] = comp["Total"] + ajuste_total
    return comp


def totales(comp) -> dict:
    imp = comp.get("Impuestos") or {}
    return {
        "subtotal": comp["SubTotal"],
        "descuento": comp.get("Descuento") or Decimal(0),
        "traslados": imp.get("TotalImpuestosTrasladados") or Decimal(0),
        "retenciones": imp.get("TotalImpuestosRetenidos") or Decimal(0),
        "total": comp["Total"],
    }


def construir_pago(emisor: Emisor, cliente: Cliente, docs: list[tuple[bytes, int, Decimal, Decimal]],
                   fecha_pago: datetime, forma_pago: str, serie: str | None, folio: str | None,
                   tipo_cambio: Decimal | None = None):
    """docs = [(xml_timbrado, num_parcialidad, saldo_anterior, importe_pagado)]"""
    comprobantes = [
        # La BD guarda dinero con 6 decimales; el complemento de pago exige los de la moneda (CRP20240)
        cfdi40.PagoComprobante(comprobante=CFDI.from_string(x), num_parcialidad=n,
                               imp_saldo_ant=round(Decimal(sa), 2), imp_pagado=round(Decimal(ip), 2))
        for x, n, sa, ip in docs
    ]
    receptor = cfdi40.Receptor(
        rfc=cliente.rfc, nombre=cliente.nombre, domicilio_fiscal_receptor=cliente.codigo_postal,
        regimen_fiscal_receptor=cliente.regimen_fiscal, uso_cfdi="CP01",
    )
    return cfdi40.Comprobante.pago_comprobantes(
        comprobantes=comprobantes, fecha_pago=fecha_pago, forma_pago=forma_pago,
        emisor=cfdi40.Emisor(rfc=emisor.rfc, nombre=emisor.nombre, regimen_fiscal=emisor.regimen_fiscal),
        lugar_expedicion=emisor.lugar_expedicion, receptor=receptor,
        tipo_cambio=tipo_cambio, serie=serie, folio=folio, fecha=ahora_mx(emisor.lugar_expedicion),
    )
