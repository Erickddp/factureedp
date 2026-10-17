"""Modelo de datos de Timbra.

Multi-emisor: un despacho (tú) factura a nombre de varios RFC (tus clientes).
Cada Emisor tiene su CSD, sus series/folios y su PAC.
Cada Cliente (receptor) pertenece a un Emisor.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(18, 6)


class Pac(Base):
    """Credenciales de un PAC. Lo compras, lo das de alta aquí y listo."""
    __tablename__ = "pacs"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)  # dueño de la cuenta (ver db.py)
    nombre: Mapped[str] = mapped_column(String(80))
    # finkok | swsapien | diverza | prodigia | facturama | comerciodigital | mysuite | demo
    proveedor: Mapped[str] = mapped_column(String(30))
    usuario: Mapped[str | None] = mapped_column(String(200))
    password_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)  # contrato, rfc integrador, etc.
    pruebas: Mapped[bool] = mapped_column(Boolean, default=True)
    # PAC de la plataforma: con él timbran TODAS las cuentas (sus emisores se dan de alta solos en el PAC). Sus credenciales
    # sólo las ve y edita su dueño (el administrador); a cada cuenta se le descuenta de su saldo de timbres.
    plataforma: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Control de timbres: paquete comprado (None = pospago tipo Finkok), desde cuándo cuenta y aviso
    timbres_contratados: Mapped[int | None] = mapped_column(Integer)
    timbres_desde: Mapped[datetime | None] = mapped_column(DateTime)
    timbres_alerta: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Emisor(Base):
    __tablename__ = "emisores"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)  # dueño de la cuenta (ver db.py)
    rfc: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(300))
    regimen_fiscal: Mapped[str] = mapped_column(String(3))
    lugar_expedicion: Mapped[str] = mapped_column(String(5))  # CP
    email: Mapped[str | None] = mapped_column(String(200))
    logo_b64: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(9))
    # CSD cifrado
    cer: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_password_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    no_certificado: Mapped[str | None] = mapped_column(String(20))
    csd_vence: Mapped[datetime | None] = mapped_column(DateTime)
    pac_id: Mapped[int | None] = mapped_column(ForeignKey("pacs.id"))
    pac: Mapped[Pac | None] = relationship()

    @property
    def modo_demo(self) -> bool:
        """Sin PAC real asignado: lo que se timbre es simulado y no vale ante el SAT."""
        return self.pac is None or self.pac.proveedor == "demo"

    @property
    def ambiente(self) -> str:
        """demo (sin PAC o PAC demo), pruebas (PAC en ambiente de pruebas) o produccion. Sólo producción vale ante el SAT y
        gasta timbres reales: las pantallas lo marcan en el selector de emisor y piden confirmar antes de timbrar."""
        if self.modo_demo:
            return "demo"
        return "pruebas" if self.pac.pruebas else "produccion"
    # Estímulo IVA 8% región fronteriza norte/sur (requiere estar en el padrón del SAT)
    region_fronteriza: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # HEREDADO, SIEMPRE VACÍO: la e.firma ya no se guarda (migración 0009 la borró). Para bajar del SAT se pone cada vez
    # y vive sólo en memoria mientras dura la descarga (services/xml_firma.py).
    fiel_cer: Mapped[bytes | None] = mapped_column(LargeBinary)
    fiel_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    fiel_password_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    fiel_vence: Mapped[datetime | None] = mapped_column(DateTime)
    registro_patronal: Mapped[str | None] = mapped_column(String(20))  # nómina de sueldos (régimen 02)
    curp: Mapped[str | None] = mapped_column(String(18))  # emisor persona física que timbra nómina
    # Portal de autofactura: clave pública de la liga y concepto por defecto de los tickets
    portal_activo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    portal_clave: Mapped[str | None] = mapped_column(String(40), unique=True)
    portal_config: Mapped[dict] = mapped_column(JSON, default=dict)
    cobranza_auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Barra de Facturar: nivel (simple/estándar/completo), campos visibles, valores por defecto y perfiles rápidos
    config_facturar: Mapped[dict] = mapped_column(JSON, default=dict)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    series: Mapped[list["Serie"]] = relationship(back_populates="emisor", cascade="all, delete-orphan")


class Serie(Base):
    __tablename__ = "series"
    __table_args__ = (UniqueConstraint("emisor_id", "serie"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"))
    emisor: Mapped[Emisor] = relationship(back_populates="series")
    serie: Mapped[str] = mapped_column(String(25))
    tipo: Mapped[str] = mapped_column(String(1), default="I")  # I E T P N
    siguiente_folio: Mapped[int] = mapped_column(Integer, default=1)
    default: Mapped[bool] = mapped_column(Boolean, default=False)


class Cliente(Base):
    """Receptor. Pertenece a un emisor."""
    __tablename__ = "clientes"
    __table_args__ = (UniqueConstraint("emisor_id", "rfc", "nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    rfc: Mapped[str] = mapped_column(String(13), index=True)
    nombre: Mapped[str] = mapped_column(String(300))
    regimen_fiscal: Mapped[str] = mapped_column(String(3))
    codigo_postal: Mapped[str] = mapped_column(String(5))
    uso_cfdi: Mapped[str] = mapped_column(String(4), default="G03")
    forma_pago: Mapped[str | None] = mapped_column(String(2))
    metodo_pago: Mapped[str | None] = mapped_column(String(3))
    residencia_fiscal: Mapped[str | None] = mapped_column(String(3))
    num_reg_id_trib: Mapped[str | None] = mapped_column(String(40))
    emails: Mapped[list] = mapped_column(JSON, default=list)
    telefono: Mapped[str | None] = mapped_column(String(60))
    direccion: Mapped[str | None] = mapped_column(String(400))
    addenda_id: Mapped[int | None] = mapped_column(ForeignKey("addendas.id"))
    addenda_defaults: Mapped[dict] = mapped_column(JSON, default=dict)  # no. proveedor, etc.
    notas: Mapped[str | None] = mapped_column(Text)
    dias_credito: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ultimo_recordatorio: Mapped[datetime | None] = mapped_column(DateTime)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Producto(Base):
    __tablename__ = "productos"
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    descripcion: Mapped[str] = mapped_column(String(1000))
    clave_prod_serv: Mapped[str] = mapped_column(String(8))
    clave_unidad: Mapped[str] = mapped_column(String(3))
    unidad: Mapped[str | None] = mapped_column(String(20))
    no_identificacion: Mapped[str | None] = mapped_column(String(100))
    precio: Mapped[Decimal] = mapped_column(Money, default=0)
    objeto_imp: Mapped[str] = mapped_column(String(2), default="02")
    # Lista de impuestos: [{"tipo":"traslado","impuesto":"002","factor":"Tasa","tasa":"0.16"}, ...]
    impuestos: Mapped[list] = mapped_column(JSON, default=list)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Addenda(Base):
    """Plantilla Jinja2 de addenda. Se inyecta DESPUÉS del timbrado (no va sellada)."""
    __tablename__ = "addendas"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None] = mapped_column(Text)
    plantilla: Mapped[str] = mapped_column(Text)
    # Campos que el usuario llena: [{"name":"orden_compra","label":"Orden de compra","required":true}]
    campos: Mapped[list] = mapped_column(JSON, default=list)


class Factura(Base):
    __tablename__ = "facturas"
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    emisor: Mapped[Emisor] = relationship()
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), index=True)
    cliente: Mapped[Cliente | None] = relationship()
    empleado_id: Mapped[int | None] = mapped_column(ForeignKey("empleados.id"), index=True)
    # Folio de la hoja de cálculo de origen (p. ej. "C-30"): liga cada factura con tu control externo
    referencia: Mapped[str | None] = mapped_column(String(60), index=True)
    tipo: Mapped[str] = mapped_column(String(1), default="I")  # I E T P N
    # borrador | timbrada | cancelacion_pendiente | cancelada | error
    estado: Mapped[str] = mapped_column(String(30), default="borrador", index=True)
    serie: Mapped[str | None] = mapped_column(String(25))
    folio: Mapped[str | None] = mapped_column(String(40))
    uuid: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    fecha: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_timbrado: Mapped[datetime | None] = mapped_column(DateTime)
    moneda: Mapped[str] = mapped_column(String(3), default="MXN")
    tipo_cambio: Mapped[Decimal | None] = mapped_column(Money)
    metodo_pago: Mapped[str | None] = mapped_column(String(3))
    forma_pago: Mapped[str | None] = mapped_column(String(2))
    subtotal: Mapped[Decimal] = mapped_column(Money, default=0)
    descuento: Mapped[Decimal] = mapped_column(Money, default=0)
    total: Mapped[Decimal] = mapped_column(Money, default=0)
    saldo: Mapped[Decimal] = mapped_column(Money, default=0)  # para PPD / REP
    parcialidades: Mapped[int] = mapped_column(Integer, default=0)
    # Payload completo con el que se armó (para clonar / reintentar)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    xml: Mapped[bytes | None] = mapped_column(LargeBinary)
    acuse_cancelacion: Mapped[bytes | None] = mapped_column(LargeBinary)
    motivo_cancelacion: Mapped[str | None] = mapped_column(String(2))
    error: Mapped[str | None] = mapped_column(Text)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Plantilla(Base):
    """Factura guardada como formato reutilizable (la iguala mensual de un cliente, etc.)."""
    __tablename__ = "plantillas"
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(150))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    usos: Mapped[int] = mapped_column(Integer, default=0)
    favorita: Mapped[int | None] = mapped_column(Integer)  # 1-9: atajo Alt+Shift+número
    # Recurrente: el día indicado de cada mes se timbra sola (auto_timbrar) o aparece en "Por timbrar hoy"
    recurrente: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    dia: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    proxima: Mapped[datetime | None] = mapped_column(DateTime)
    auto_timbrar: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    enviar_email: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    ultima_factura_id: Mapped[int | None] = mapped_column(Integer)
    ultimo_error: Mapped[str | None] = mapped_column(Text)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    usuario: Mapped[str | None] = mapped_column(String(60), unique=True, index=True)  # para entrar sin correo
    nombre: Mapped[str | None] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(String(300))
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)  # identidad de Google conectada
    google_email: Mapped[str | None] = mapped_column(String(200))
    foto: Mapped[str | None] = mapped_column(Text)  # foto de perfil de Google como imagen pequeña (data:image/...;base64,...)
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Saldo de timbres para facturar con el PAC de la plataforma. Cada cuenta nueva trae 3 de regalo.
    timbres: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    # False = se registró sola con correo y contraseña y aún no confirma que el correo es suyo: sus timbres de regalo llegan al
    # confirmar. Las cuentas que da de alta el administrador y las que entran con Google (correo ya verificado) nacen en True.
    correo_verificado: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Términos de uso y aviso de privacidad aceptados (app/legal.py): versión, cuándo y desde qué IP. Es la constancia.
    terminos_version: Mapped[str | None] = mapped_column(String(20))
    terminos_aceptados: Mapped[datetime | None] = mapped_column(DateTime)
    terminos_ip: Mapped[str | None] = mapped_column(String(45))
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class MovimientoTimbres(Base):
    """Cada recarga (o ajuste) de timbres a una cuenta: quién, cuántos y por qué. El consumo se ve en las facturas."""
    __tablename__ = "movimientos_timbres"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)
    saldo: Mapped[int] = mapped_column(Integer)  # como quedó después
    motivo: Mapped[str | None] = mapped_column(String(200))
    admin_id: Mapped[int | None] = mapped_column(Integer)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Una recarga es un «lote» que vence a los 12 meses: `restantes` baja con cada timbre (se gasta primero lo que vence
    # antes) y lo que quede al vencer se descuenta. None = movimiento que no es lote (consumo, corrección, vencimiento).
    vence: Mapped[datetime | None] = mapped_column(DateTime)
    restantes: Mapped[int | None] = mapped_column(Integer)
    pago_id: Mapped[int | None] = mapped_column(Integer)


class Pago(Base):
    """Compra de timbres en línea (Mercado Pago). Se acredita UNA sola vez, al confirmarse con la API de Mercado Pago."""
    __tablename__ = "pagos"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    paquete: Mapped[str] = mapped_column(String(20))
    timbres: Mapped[int] = mapped_column(Integer)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | aprobado | rechazado | cancelado
    preferencia: Mapped[str | None] = mapped_column(String(80))
    mp_pago: Mapped[str | None] = mapped_column(String(40), unique=True)
    detalle: Mapped[str | None] = mapped_column(String(200))
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    acreditado: Mapped[datetime | None] = mapped_column(DateTime)


class AccesoSoporte(Base):
    """Cada vez que el administrador entra a la cuenta de alguien para darle soporte. El dueño de la cuenta lo ve."""
    __tablename__ = "accesos_soporte"
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    motivo: Mapped[str | None] = mapped_column(String(200))
    ip: Mapped[str | None] = mapped_column(String(60))
    inicio: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    hasta: Mapped[datetime] = mapped_column(DateTime)  # el permiso vence solo


class Empleado(Base):
    """Trabajador o asimilado. `receta` = percepciones/deducciones de cada periodo (se ajustan al timbrar)."""
    __tablename__ = "empleados"
    __table_args__ = (UniqueConstraint("emisor_id", "num_empleado"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    num_empleado: Mapped[str] = mapped_column(String(15))
    rfc: Mapped[str] = mapped_column(String(13))
    curp: Mapped[str] = mapped_column(String(18))
    nombre: Mapped[str] = mapped_column(String(300))
    codigo_postal: Mapped[str] = mapped_column(String(5))
    nss: Mapped[str | None] = mapped_column(String(15))
    tipo_contrato: Mapped[str] = mapped_column(String(2), default="01")
    tipo_regimen: Mapped[str] = mapped_column(String(2), default="02")
    tipo_jornada: Mapped[str | None] = mapped_column(String(2))
    periodicidad_pago: Mapped[str] = mapped_column(String(2), default="04")
    clave_ent_fed: Mapped[str] = mapped_column(String(3))
    fecha_inicio: Mapped[datetime | None] = mapped_column(DateTime)
    departamento: Mapped[str | None] = mapped_column(String(100))
    puesto: Mapped[str | None] = mapped_column(String(100))
    riesgo_puesto: Mapped[str | None] = mapped_column(String(2))
    banco: Mapped[str | None] = mapped_column(String(3))
    cuenta_bancaria: Mapped[str | None] = mapped_column(String(18))
    salario_diario: Mapped[Decimal] = mapped_column(Money, default=0)
    sdi: Mapped[Decimal | None] = mapped_column(Money)
    emails: Mapped[list] = mapped_column(JSON, default=list)
    receta: Mapped[dict] = mapped_column(JSON, default=dict)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class CfdiSat(Base):
    """HEREDADO (módulo SAT anterior a 2.11). Lo que tenía se pasa solo a `xml_cfdi` al arrancar; ya no se escribe aquí."""
    __tablename__ = "cfdi_sat"
    __table_args__ = (UniqueConstraint("emisor_id", "uuid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    uuid: Mapped[str] = mapped_column(String(36), index=True)
    direccion: Mapped[str] = mapped_column(String(10))  # recibido | emitido
    tipo: Mapped[str | None] = mapped_column(String(1))
    fecha: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    rfc_emisor: Mapped[str] = mapped_column(String(13))
    nombre_emisor: Mapped[str | None] = mapped_column(String(300))
    rfc_receptor: Mapped[str] = mapped_column(String(13))
    nombre_receptor: Mapped[str | None] = mapped_column(String(300))
    subtotal: Mapped[Decimal] = mapped_column(Money, default=0)
    descuento: Mapped[Decimal] = mapped_column(Money, default=0)
    iva: Mapped[Decimal] = mapped_column(Money, default=0)
    iva_retenido: Mapped[Decimal] = mapped_column(Money, default=0)
    isr_retenido: Mapped[Decimal] = mapped_column(Money, default=0)
    total: Mapped[Decimal] = mapped_column(Money, default=0)
    moneda: Mapped[str | None] = mapped_column(String(3))
    metodo_pago: Mapped[str | None] = mapped_column(String(3))
    forma_pago: Mapped[str | None] = mapped_column(String(2))
    uso_cfdi: Mapped[str | None] = mapped_column(String(4))
    estado: Mapped[str] = mapped_column(String(12), default="Vigente")
    xml: Mapped[bytes | None] = mapped_column(LargeBinary)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class XmlCfdi(Base):
    """Índice de un CFDI bajado del SAT o leído de un XML. El XML vive en disco (datos/xml/{emisor}/…); aquí van sus
    renglones ya leídos en el formato maestro (un pago trae un renglón por documento pagado)."""
    __tablename__ = "xml_cfdi"
    __table_args__ = (UniqueConstraint("emisor_id", "uuid", "tipo"), Index("ix_xml_cfdi_emisor_fecha", "emisor_id", "fecha"))
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    uuid: Mapped[str] = mapped_column(String(40))
    tipo: Mapped[str] = mapped_column(String(10))  # Emitido | Recibido (quién es el contribuyente en este CFDI)
    fecha: Mapped[str] = mapped_column(String(19), default="")  # AAAA-MM-DD HH:MM:SS, como en la tabla
    clase: Mapped[str] = mapped_column(String(1), default="")  # I ingreso · G gasto · N nómina · P pago · E nota · T traslado
    comprobante: Mapped[str] = mapped_column(String(12), default="")
    serie: Mapped[str] = mapped_column(String(40), default="")
    folio: Mapped[str] = mapped_column(String(60), default="")
    rfc_emisor: Mapped[str] = mapped_column(String(13), default="")
    nombre_emisor: Mapped[str] = mapped_column(String(300), default="")
    rfc_receptor: Mapped[str] = mapped_column(String(13), default="")
    nombre_receptor: Mapped[str] = mapped_column(String(300), default="")
    subtotal: Mapped[float] = mapped_column(Float, default=0)
    iva: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)
    moneda: Mapped[str] = mapped_column(String(3), default="")
    metodo: Mapped[str] = mapped_column(String(3), default="")
    estatus: Mapped[str] = mapped_column(String(10), default="Vigente")  # Vigente | Cancelado (lo dice el SAT)
    cancelado_el: Mapped[str | None] = mapped_column(String(19))
    origen: Mapped[str] = mapped_column(String(8), default="sat")  # sat | subido | aviso (sólo se sabe que existe, sin XML)
    archivo: Mapped[str] = mapped_column(String(200), default="")  # ruta relativa del XML dentro de datos/xml/{emisor}
    filas: Mapped[list] = mapped_column(JSON, default=list)
    busca: Mapped[str] = mapped_column(Text, default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class XmlTrabajo(Base):
    """Lo que tarda (bajar del SAT, armar un ZIP) corre en segundo plano y deja aquí su avance."""
    __tablename__ = "xml_trabajos"
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    clase: Mapped[str] = mapped_column(String(6))  # sat | zip
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    estado: Mapped[str] = mapped_column(String(14), default="curso")  # curso | listo | error | cancelado | interrumpido
    avance: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    mensaje: Mapped[str] = mapped_column(String(300), default="")
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)
    registro: Mapped[str] = mapped_column(Text, default="")
    archivo: Mapped[str] = mapped_column(String(120), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    terminado: Mapped[datetime | None] = mapped_column(DateTime)


class SolicitudSat(Base):
    """Solicitud de descarga masiva. El SAT tarda de minutos a horas: el programador la revisa sola."""
    __tablename__ = "solicitudes_sat"
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    id_solicitud: Mapped[str | None] = mapped_column(String(60))
    direccion: Mapped[str] = mapped_column(String(10))
    tipo: Mapped[str] = mapped_column(String(10), default="CFDI")
    desde: Mapped[datetime] = mapped_column(DateTime)
    hasta: Mapped[datetime] = mapped_column(DateTime)
    # pendiente | en_proceso | terminada | sin_datos | error
    estado: Mapped[str] = mapped_column(String(15), default="pendiente")
    mensaje: Mapped[str | None] = mapped_column(Text)
    paquetes: Mapped[list] = mapped_column(JSON, default=list)
    descargados: Mapped[int] = mapped_column(Integer, default=0)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    actualizado: Mapped[datetime | None] = mapped_column(DateTime)


class Ticket(Base):
    """Venta de mostrador que el cliente factura él mismo en el portal (folio + total)."""
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("emisor_id", "folio"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    folio: Mapped[str] = mapped_column(String(40))
    fecha: Mapped[datetime] = mapped_column(DateTime)
    total: Mapped[Decimal] = mapped_column(Money)
    forma_pago: Mapped[str] = mapped_column(String(2), default="01")
    conceptos: Mapped[list] = mapped_column(JSON, default=list)  # vacío = concepto del portal_config
    factura_id: Mapped[int | None] = mapped_column(ForeignKey("facturas.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Tercero(Base):
    """Contribuyente a cuenta del que se factura (nodo ACuentaTerceros del concepto, CFDI 4.0).
    Ej.: el despacho cobra honorarios de otro contador, una inmobiliaria cobra la renta del dueño, un comisionista."""
    __tablename__ = "terceros"
    __table_args__ = (UniqueConstraint("emisor_id", "rfc"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    rfc: Mapped[str] = mapped_column(String(13))
    nombre: Mapped[str] = mapped_column(String(300))
    regimen_fiscal: Mapped[str] = mapped_column(String(3))
    codigo_postal: Mapped[str] = mapped_column(String(5))
    alias: Mapped[str | None] = mapped_column(String(80))
    # Valores que suele llevar el concepto de este tercero (clave SAT, unidad, descripción, impuestos)
    concepto: Mapped[dict] = mapped_column(JSON, default=dict)
    usos: Mapped[int] = mapped_column(Integer, default=0)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class PerfilLote(Base):
    """Perfil de importación de facturas en lote: cómo leer tu tabla y qué conceptos armar (ver services/lotes.py)."""
    __tablename__ = "perfiles_lote"
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    usos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Lote(Base):
    __tablename__ = "lotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    perfil_id: Mapped[int | None] = mapped_column(ForeignKey("perfiles_lote.id"))
    nombre: Mapped[str] = mapped_column(String(150))
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # copia del perfil al crear: el lote no cambia si editas el perfil
    estado: Mapped[str] = mapped_column(String(15), default="borrador")  # borrador | en_proceso | detenido | terminado
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class LoteFila(Base):
    """Una factura por fila. El folio queda RESERVADO mientras la fila no esté timbrada ni omitida."""
    __tablename__ = "lote_filas"
    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    emisor_id: Mapped[int] = mapped_column(ForeignKey("emisores.id"), index=True)
    n: Mapped[int] = mapped_column(Integer)  # posición en la tabla pegada
    datos: Mapped[dict] = mapped_column(JSON, default=dict)  # celdas ya con nombre (folio, nombre, rfc, monto…)
    # listo | error | timbrando | timbrada | omitida
    estado: Mapped[str] = mapped_column(String(12), default="listo", index=True)
    etapa: Mapped[str | None] = mapped_column(String(12))  # validacion | timbrado (dónde se atoró)
    serie: Mapped[str | None] = mapped_column(String(25))
    folio: Mapped[str | None] = mapped_column(String(40))
    referencia: Mapped[str | None] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # FacturaIn ya armado
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)  # total, ajuste, cliente, conceptos para mostrar
    errores: Mapped[list] = mapped_column(JSON, default=list)
    avisos: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    factura_id: Mapped[int | None] = mapped_column(ForeignKey("facturas.id"))
    intentos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    actualizado: Mapped[datetime | None] = mapped_column(DateTime)


class DriveConexion(Base):
    """Google Drive de una cuenta (permiso drive.file): ahí se copian sus XML. El token de renovación va cifrado como los CSD.
    Sin emisor_id a propósito: es de la cuenta, y services/drive.py siempre filtra por usuario_id."""
    __tablename__ = "drive_conexiones"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), unique=True, index=True)
    google_email: Mapped[str | None] = mapped_column(String(200))
    refresh_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    carpeta_id: Mapped[str | None] = mapped_column(String(120))  # carpeta raíz «Timbra» en su Drive
    estado: Mapped[str] = mapped_column(String(14), default="activa")  # activa | sincronizando | error | revocada
    error: Mapped[str | None] = mapped_column(Text)
    subidos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ultimo: Mapped[datetime | None] = mapped_column(DateTime)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class DriveArchivo(Base):
    """Lo que ya se copió a Drive (o la carpeta que ya existe): así cada XML se sube una sola vez."""
    __tablename__ = "drive_archivos"
    __table_args__ = (UniqueConstraint("usuario_id", "ruta"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    ruta: Mapped[str] = mapped_column(String(400))  # «Timbra/RFC/202610/recibidos/UUID.xml» o «dir:Timbra/RFC/202610»
    drive_id: Mapped[str] = mapped_column(String(120))
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
