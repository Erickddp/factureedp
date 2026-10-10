from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Impuestos ----------
class ImpuestoIn(BaseModel):
    tipo: Literal["traslado", "retencion"] = "traslado"
    impuesto: Literal["001", "002", "003"] = "002"  # ISR, IVA, IEPS
    factor: Literal["Tasa", "Cuota", "Exento"] = "Tasa"
    tasa: Decimal | None = Decimal("0.16")


# ---------- PAC ----------
class PacIn(BaseModel):
    nombre: str
    proveedor: Literal["demo", "finkok", "swsapien", "diverza", "prodigia", "facturama", "comerciodigital", "mysuite"]
    usuario: str | None = None
    password: str | None = None
    token: str | None = None
    extra: dict = {}
    pruebas: bool = True
    timbres_contratados: int | None = None
    timbres_desde: datetime | None = None
    timbres_alerta: int = 50


class PacOut(ORM):
    id: int
    nombre: str
    proveedor: str
    usuario: str | None
    extra: dict
    pruebas: bool
    timbres_contratados: int | None = None
    timbres_desde: datetime | None = None
    timbres_alerta: int = 50


# ---------- Emisor ----------
class SerieIn(BaseModel):
    serie: str
    tipo: Literal["I", "E", "T", "P", "N"] = "I"
    siguiente_folio: int = 1
    default: bool = False


class SerieOut(ORM, SerieIn):
    id: int


class EmisorIn(BaseModel):
    rfc: str
    nombre: str
    regimen_fiscal: str
    lugar_expedicion: str
    email: str | None = None
    logo_b64: str | None = None
    color: str | None = None
    pac_id: int | None = None
    region_fronteriza: bool = False
    registro_patronal: str | None = None
    curp: str | None = None
    portal_config: dict = {}
    cobranza_auto: bool = False

    @field_validator("rfc")
    @classmethod
    def up(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("nombre")
    @classmethod
    def nombre_up(cls, v: str) -> str:
        # CFDI 4.0: nombre tal cual la CSF, sin régimen societario (SA DE CV)
        return v.strip().upper()


class EmisorOut(ORM):
    id: int
    rfc: str
    nombre: str
    regimen_fiscal: str
    lugar_expedicion: str
    email: str | None
    color: str | None
    pac_id: int | None
    no_certificado: str | None
    csd_vence: datetime | None
    region_fronteriza: bool = False
    logo_b64: str | None = None
    registro_patronal: str | None = None
    curp: str | None = None
    fiel_vence: datetime | None = None
    portal_activo: bool = False
    portal_clave: str | None = None
    portal_config: dict = {}
    cobranza_auto: bool = False
    config_facturar: dict = {}
    activo: bool
    series: list[SerieOut] = []
    modo_demo: bool = False  # sin PAC real asignado: lo que timbre NO vale ante el SAT


# ---------- Cliente ----------
class ClienteIn(BaseModel):
    emisor_id: int
    rfc: str
    nombre: str
    regimen_fiscal: str
    codigo_postal: str
    uso_cfdi: str = "G03"
    forma_pago: str | None = None
    metodo_pago: str | None = None
    residencia_fiscal: str | None = None
    num_reg_id_trib: str | None = None
    emails: list[str] = []
    telefono: str | None = None
    direccion: str | None = None
    addenda_id: int | None = None
    addenda_defaults: dict = {}
    notas: str | None = None
    dias_credito: int = 0

    @field_validator("rfc", "nombre")
    @classmethod
    def up(cls, v: str) -> str:
        return v.strip().upper()


class ClienteOut(ORM, ClienteIn):
    id: int


# ---------- Producto ----------
class ProductoIn(BaseModel):
    emisor_id: int
    descripcion: str
    clave_prod_serv: str
    clave_unidad: str
    unidad: str | None = None
    no_identificacion: str | None = None
    precio: Decimal = Decimal(0)
    objeto_imp: str = "02"
    impuestos: list[ImpuestoIn] = Field(default_factory=lambda: [ImpuestoIn()])


class ProductoOut(ORM, ProductoIn):
    id: int


# ---------- Addenda ----------
class AddendaIn(BaseModel):
    nombre: str
    descripcion: str | None = None
    plantilla: str
    campos: list[dict] = []


class AddendaOut(ORM, AddendaIn):
    id: int


# ---------- Factura ----------
class ConceptoIn(BaseModel):
    producto_id: int | None = None
    clave_prod_serv: str
    clave_unidad: str
    unidad: str | None = None
    no_identificacion: str | None = None
    descripcion: str
    cantidad: Decimal = Decimal(1)
    valor_unitario: Decimal
    descuento: Decimal | None = None
    objeto_imp: str = "02"
    impuestos: list[ImpuestoIn] = Field(default_factory=lambda: [ImpuestoIn()])
    cuenta_predial: str | None = None
    informacion_aduanera: list[str] = []
    a_cuenta_terceros: dict | None = None  # rfc, nombre, regimen, domicilio


class ReceptorIn(BaseModel):
    """Receptor al vuelo (sin darlo de alta)."""
    rfc: str
    nombre: str
    regimen_fiscal: str
    codigo_postal: str
    uso_cfdi: str = "G03"
    residencia_fiscal: str | None = None
    num_reg_id_trib: str | None = None
    guardar: bool = True


class RelacionIn(BaseModel):
    tipo_relacion: str  # 01 nota crédito, 04 sustitución, 07 anticipo...
    uuids: list[str]


class GlobalIn(BaseModel):
    periodicidad: str = "04"  # 04 = mensual
    meses: str
    ano: int


class ImpLocalIn(BaseModel):
    tipo: Literal["traslado", "retencion"]
    nombre: str  # "ISH", "Cedular"...
    tasa: Decimal
    importe: Decimal


class AddendaUso(BaseModel):
    addenda_id: int
    datos: dict = {}


class FacturaIn(BaseModel):
    emisor_id: int
    cliente_id: int | None = None
    receptor: ReceptorIn | None = None
    publico_general: bool = False
    tipo: Literal["I", "E", "T"] = "I"
    serie: str | None = None
    moneda: str = "MXN"
    tipo_cambio: Decimal | None = None
    forma_pago: str | None = "99"
    metodo_pago: str | None = "PPD"
    condiciones_pago: str | None = None
    exportacion: str = "01"
    conceptos: list[ConceptoIn]
    relacionados: list[RelacionIn] = []
    informacion_global: GlobalIn | None = None
    impuestos_locales: list[ImpLocalIn] = []
    addenda: AddendaUso | None = None
    fecha: datetime | None = None
    enviar_email: bool = False
    # Para lotes: folio explícito (el de tu hoja) y la referencia que liga la factura con tu control externo
    folio: str | None = None
    referencia: str | None = None


class TotalesOut(BaseModel):
    subtotal: Decimal
    descuento: Decimal
    traslados: Decimal
    retenciones: Decimal
    total: Decimal
    xml_preview: str | None = None


class FacturaOut(ORM):
    id: int
    emisor_id: int
    cliente_id: int | None
    tipo: str
    estado: str
    serie: str | None
    folio: str | None
    uuid: str | None
    fecha: datetime | None
    fecha_timbrado: datetime | None
    moneda: str
    metodo_pago: str | None
    forma_pago: str | None
    subtotal: Decimal
    total: Decimal
    saldo: Decimal
    parcialidades: int
    motivo_cancelacion: str | None
    error: str | None
    empleado_id: int | None = None
    referencia: str | None = None
    receptor_nombre: str | None = None
    receptor_rfc: str | None = None
    demo: bool = False  # timbrada con el PAC demo: sin validez fiscal


class CancelarIn(BaseModel):
    motivo: Literal["01", "02", "03", "04"] = "02"
    uuid_sustitucion: str | None = None


class DocPagoIn(BaseModel):
    factura_id: int
    imp_pagado: Decimal


class PagoIn(BaseModel):
    emisor_id: int
    cliente_id: int
    fecha_pago: datetime
    forma_pago: str = "03"
    serie: str | None = None
    tipo_cambio: Decimal | None = None
    documentos: list[DocPagoIn]
    enviar_email: bool = False


class EnviarIn(BaseModel):
    para: list[str] = []
    mensaje: str | None = None
    guardar: bool = False  # agrega estos correos al cliente


class ImportarConfirmarIn(BaseModel):
    emisor_id: int
    filas: list[dict]
    modo: Literal["actualizar", "omitir"] = "actualizar"


# ---------- Nómina ----------
class EmpleadoIn(BaseModel):
    emisor_id: int
    num_empleado: str
    rfc: str
    curp: str
    nombre: str
    codigo_postal: str
    nss: str | None = None
    tipo_contrato: str = "01"
    tipo_regimen: str = "02"
    tipo_jornada: str | None = None
    periodicidad_pago: str = "04"
    clave_ent_fed: str
    fecha_inicio: datetime | None = None
    departamento: str | None = None
    puesto: str | None = None
    riesgo_puesto: str | None = None
    banco: str | None = None
    cuenta_bancaria: str | None = None
    salario_diario: Decimal = Decimal(0)
    sdi: Decimal | None = None
    emails: list[str] = []
    receta: dict = {}
    activo: bool = True

    @field_validator("rfc", "curp", "nombre")
    @classmethod
    def up(cls, v: str) -> str:
        return v.strip().upper()


class EmpleadoOut(ORM, EmpleadoIn):
    id: int


class PercepcionIn(BaseModel):
    tipo: str
    clave: str
    concepto: str
    gravado: Decimal = Decimal(0)
    exento: Decimal = Decimal(0)


class DeduccionIn(BaseModel):
    tipo: str
    clave: str
    concepto: str
    importe: Decimal = Decimal(0)


class OtroPagoIn(BaseModel):
    tipo: str
    clave: str
    concepto: str
    importe: Decimal = Decimal(0)
    subsidio_causado: Decimal | None = None


class ReciboIn(BaseModel):
    empleado_id: int
    tipo_nomina: Literal["O", "E"] = "O"
    fecha_pago: date
    fecha_inicial: date
    fecha_final: date
    dias: Decimal
    percepciones: list[PercepcionIn] = []
    deducciones: list[DeduccionIn] = []
    otros_pagos: list[OtroPagoIn] = []


class NominaIn(BaseModel):
    emisor_id: int
    serie: str | None = None
    recibos: list[ReciboIn]
    enviar_email: bool = False


# ---------- Portal / tickets ----------
class TicketIn(BaseModel):
    emisor_id: int
    folio: str
    fecha: datetime
    total: Decimal
    forma_pago: str = "01"
    conceptos: list[ConceptoIn] = []


class AutofacturaIn(BaseModel):
    folio: str
    total: Decimal
    rfc: str
    nombre: str
    regimen_fiscal: str
    codigo_postal: str
    uso_cfdi: str = "G03"
    email: str | None = None

    @field_validator("rfc", "nombre", "folio")
    @classmethod
    def up(cls, v: str) -> str:
        return v.strip().upper()


# ---------- A cuenta de terceros ----------
class TerceroIn(BaseModel):
    emisor_id: int
    rfc: str
    nombre: str
    regimen_fiscal: str
    codigo_postal: str
    alias: str | None = None
    concepto: dict = {}

    @field_validator("rfc", "nombre")
    @classmethod
    def up(cls, v: str) -> str:
        return v.strip().upper()


class TerceroOut(ORM, TerceroIn):
    id: int
    usos: int = 0
