export type Impuesto = {
  tipo: "traslado" | "retencion";
  impuesto: "001" | "002" | "003";
  factor: "Tasa" | "Cuota" | "Exento";
  tasa: string | null;
};

export type Serie = { id: number; serie: string; tipo: string; siguiente_folio: number; default: boolean };

export type Emisor = {
  id: number;
  rfc: string;
  nombre: string;
  regimen_fiscal: string;
  lugar_expedicion: string;
  email: string | null;
  color: string | null;
  pac_id: number | null;
  no_certificado: string | null;
  csd_vence: string | null;
  region_fronteriza?: boolean;
  logo_b64?: string | null;
  registro_patronal?: string | null;
  curp?: string | null;
  fiel_vence?: string | null;
  portal_activo?: boolean;
  portal_clave?: string | null;
  portal_config?: Record<string, string>;
  cobranza_auto?: boolean;
  activo: boolean;
  series: Serie[];
  modo_demo?: boolean;
  ambiente?: "produccion" | "pruebas" | "demo";  // sólo producción vale ante el SAT (models.Emisor.ambiente)
};

export type Cliente = {
  id: number;
  emisor_id: number;
  rfc: string;
  nombre: string;
  regimen_fiscal: string;
  codigo_postal: string;
  uso_cfdi: string;
  forma_pago: string | null;
  metodo_pago: string | null;
  emails: string[];
  telefono?: string | null;
  direccion?: string | null;
  addenda_id: number | null;
  addenda_defaults: Record<string, string>;
  notas: string | null;
  dias_credito?: number;
};

export type Producto = {
  id: number;
  emisor_id: number;
  descripcion: string;
  clave_prod_serv: string;
  clave_unidad: string;
  unidad: string | null;
  no_identificacion: string | null;
  precio: string;
  objeto_imp: string;
  impuestos: Impuesto[];
};

export type Concepto = {
  key: string;
  producto_id?: number | null;
  clave_prod_serv: string;
  clave_unidad: string;
  unidad?: string | null;
  descripcion: string;
  cantidad: string;
  valor_unitario: string;
  descuento?: string;
  objeto_imp: string;
  impuestos: Impuesto[];
  ver_descuento?: boolean;
  ver_extra?: boolean;
  a_cuenta_terceros?: { rfc: string; nombre: string; regimen_fiscal: string; codigo_postal: string } | null;
  cuenta_predial?: string | null;
  informacion_aduanera?: string[];
};

export type Factura = {
  id: number;
  emisor_id: number;
  cliente_id: number | null;
  tipo: "I" | "E" | "T" | "P" | "N";
  estado: "borrador" | "timbrada" | "cancelacion_pendiente" | "cancelada" | "error";
  serie: string | null;
  folio: string | null;
  uuid: string | null;
  fecha: string | null;
  moneda: string;
  metodo_pago: string | null;
  forma_pago: string | null;
  subtotal: string;
  total: string;
  saldo: string;
  parcialidades: number;
  error: string | null;
  receptor_nombre: string | null;
  receptor_rfc: string | null;
  demo?: boolean;
};

export type Addenda = {
  id: number;
  nombre: string;
  descripcion: string | null;
  plantilla: string;
  campos: { name: string; label: string; required?: boolean }[];
};

export type Pac = {
  id: number; nombre: string; proveedor: string; usuario: string | null; pruebas: boolean; extra: Record<string, string>;
  timbres_contratados?: number | null; timbres_desde?: string | null; timbres_alerta?: number;
  plataforma?: boolean; // con este PAC timbran todas las cuentas
  propio?: boolean; // false = es el de la plataforma: esta cuenta lo usa pero no lo administra
};

export type Cat = { clave: string; descripcion: string };

export type Totales = { subtotal: string; descuento: string; traslados: string; retenciones: string; total: string };

export type Plantilla = {
  id: number; emisor_id: number; cliente_id: number | null; nombre: string; usos: number; cliente_nombre: string | null;
  payload: Record<string, any>; favorita?: number | null; recurrente?: boolean; dia?: number; proxima?: string | null;
  auto_timbrar?: boolean; enviar_email?: boolean; ultima_factura_id?: number | null; ultimo_error?: string | null;
};

export type TimbresPac = {
  pac_id: number; nombre: string; proveedor: string; pruebas: boolean; usados_mes: number; usados_paquete?: number;
  contratados: number | null; desde: string | null; alerta: number; restantes: number | null; nivel: "ok" | "aviso" | "error";
  texto: string | null; nota?: string | null; pac?: { saldo: number | null; usados: number | null; ilimitado: boolean; vence: string | null }; pac_error?: string;
};

export type Empleado = {
  id: number; emisor_id: number; num_empleado: string; rfc: string; curp: string; nombre: string; codigo_postal: string;
  nss: string | null; tipo_contrato: string; tipo_regimen: string; tipo_jornada: string | null; periodicidad_pago: string;
  clave_ent_fed: string; fecha_inicio: string | null; departamento: string | null; puesto: string | null;
  riesgo_puesto: string | null; banco: string | null; cuenta_bancaria: string | null; salario_diario: string;
  sdi: string | null; emails: string[]; receta: Record<string, any>; activo: boolean;
};

export type LineaNomina = { tipo: string; clave: string; concepto: string; gravado?: string; exento?: string; importe?: string; subsidio_causado?: string | null };
export type Recibo = {
  empleado_id: number; tipo_nomina: "O" | "E"; fecha_inicial: string; fecha_final: string; fecha_pago: string; dias: string;
  percepciones: LineaNomina[]; deducciones: LineaNomina[]; otros_pagos: LineaNomina[];
};

export type ClienteCobranza = {
  cliente_id: number; cliente: string; rfc: string; saldo: string; vencido: string; facturas: number; max_dias: number;
  emails: string[]; ultimo_recordatorio: string | null; corriente: string; "1-30": string; "31-60": string; "61-90": string; "+90": string;
};

export type CfdiSat = {
  id: number; uuid: string; direccion: "recibido" | "emitido"; tipo: string | null; fecha: string | null; rfc: string; nombre: string | null;
  subtotal: string; iva: string; iva_retenido: string; isr_retenido: string; total: string; estado: string;
  metodo_pago: string | null; uso_cfdi: string | null; tiene_xml: boolean; en_timbra: boolean;
  lista_69b?: string | null; aviso_69b?: string | null;
};

export type SolicitudSat = {
  id: number; id_solicitud: string | null; direccion: string; tipo: string; desde: string; hasta: string; estado: string;
  mensaje: string | null; descargados: number; creado: string; actualizado: string | null;
};

export type Ticket = { id: number; folio: string; fecha: string; total: string; forma_pago: string; factura_id: number | null };

export type Tercero = { id: number; emisor_id: number; rfc: string; nombre: string; regimen_fiscal: string; codigo_postal: string; alias: string | null; concepto: Record<string, any>; usos: number };

export type CampoFacturar = "clave_sat" | "unidad" | "descuento" | "pago" | "moneda" | "relacionados" | "condiciones" | "addenda" | "locales" | "terceros" | "predial" | "aduana" | "plantillas" | "repetir_ultima";
export type PerfilFacturar = {
  id: string; nombre: string; modo?: "I" | "G" | "E" | "T"; metodo?: string; forma?: string; impuesto?: string | null; uso_cfdi?: string | null;
  concepto?: { descripcion?: string; clave_prod_serv?: string; clave_unidad?: string; valor_unitario?: string } | null; tercero_id?: number | null;
};
export type ConfigFacturar = {
  nivel: "simple" | "estandar" | "completo"; campos: Partial<Record<CampoFacturar, boolean>>; visibles: Record<CampoFacturar, boolean>;
  modos: ("I" | "G" | "E" | "T")[]; tras_timbrar: "quedarse" | "nueva"; avanzado_abierto: boolean; perfiles: PerfilFacturar[];
  claves_bloqueadas?: string[];
  defaults: { modo: "I" | "G" | "E" | "T"; metodo: string; forma: string; impuesto: string | null; clave_prod_serv: string; clave_unidad: string; enviar_email: boolean };
};

export type ConceptoPerfil = {
  descripcion: string; clave_prod_serv: string; clave_unidad: string; no_identificacion?: string;
  cantidad: string; valor: string; impuestos: Impuesto[];
};
export type PerfilLoteCfg = {
  serie: string; folio_modo: "hoja" | "consecutivo"; uso_cfdi: string; metodo_pago: string; regimen_default: string;
  columnas: Record<string, number>; nombres_columnas: Record<string, string>; forma_map: Record<string, string>;
  conceptos: ConceptoPerfil[]; iva_permitido: string[]; claves_bloqueadas: string[]; ajuste_centavos: number;
  carpeta?: string; // sólo Timbra instalado: dónde dejar PDF y XML al terminar el lote
};
export type PerfilLote = { id: number; emisor_id: number; nombre: string; config: PerfilLoteCfg; usos: number };
export type AvisoFila = { nivel: "aviso" | "info"; texto: string };
export type FilaLote = {
  id: number; n: number; estado: "listo" | "error" | "timbrando" | "timbrada" | "omitida"; etapa: string | null;
  serie: string | null; folio: string | null; referencia: string | null; datos: Record<string, string>;
  resumen: {
    nombre?: string; rfc?: string; monto?: string; total?: string; subtotal?: string; fecha?: string; ajuste?: string; cliente?: string;
    bloqueo?: boolean; critico?: boolean; diagnostico?: string | null; ya_timbrada?: number;
    conceptos?: { descripcion: string; clave: string; unidad: string; cantidad: string; valor_unitario: string; importe: string }[];
  };
  errores: string[]; avisos: AvisoFila[]; error: string | null; intentos: number; factura_id: number | null;
  uuid: string | null; folio_timbra: string | null;
};
export type LoteResumen = {
  id: number; nombre: string; estado: string; creado: string; perfil_id: number | null; ejecutando: boolean;
  cuentas: Record<"listo" | "error" | "timbrando" | "timbrada" | "omitida", number>; total_timbrado: string; total_listo: string;
  guardando?: boolean; entrega?: { carpetas: string[]; guardadas: number; timbradas: number } | null;
};
export type LoteDetalle = LoteResumen & { filas: FilaLote[]; config: PerfilLoteCfg; alertas: { nivel: "error" | "aviso" | "info"; texto: string }[] };

export type AlertaClave = { nivel: "alerta" | "bloqueo" | "info"; texto: string };
export type ClaveItem = {
  clave: string; descripcion: string; tipo: "Producto" | "Servicio" | null; nivel: "clase" | "clave"; alertas: AlertaClave[];
  bloqueada: boolean; parcial: boolean; en_catalogo?: boolean; usos?: number; fuentes?: string[];
};
export type ClaveDetalle = ClaveItem & {
  jerarquia: { nivel: string; clave: string; descripcion: string }[];
  hermanas: { clave: string; descripcion: string }[]; relacionadas: { clave: string; descripcion: string }[];
  notas: AlertaClave[]; productos?: { id: number; descripcion: string; precio: string }[];
};
export type UnidadComun = { clave: string; descripcion: string; cuando: string };
export type PackProductos = {
  id: string; nombre: string; descripcion: string; nota?: string | null; ya_tiene?: number;
  productos: { descripcion: string; clave: string; unidad: string; impuestos: string }[];
};
export type FilaImportProducto = {
  n: number; estado: "nuevo" | "actualiza" | "error"; descripcion: string; clave: string; clave_sugerida: boolean; unidad: string;
  precio: string; sku: string; errores: string[]; avisos: string[];
};

export type AuditoriaCliente = {
  cliente_id: number; nombre: string; rfc: string; gravedad: "error" | "aviso" | "info";
  problemas: { campo: string; nivel: "error" | "aviso" | "info"; mensaje: string; arreglo: Record<string, string> | null }[];
};
export type GrupoDuplicados = {
  tipo: "mismo_rfc" | "mismo_nombre"; clave: string; sugerido: number | null; fusionable: boolean;
  clientes: { id: number; nombre: string; rfc: string; codigo_postal: string; regimen_fiscal: string; emails: string[]; facturas: number }[];
};
export type Verificacion69b = {
  revisados: number; consultado: string;
  en_lista: { cliente_id: number; nombre: string; rfc: string; estatus: string; nivel: "rojo" | "alerta" | "info" }[];
};
export type ItemPendiente = { id: string; titulo: string; detalle: string; nivel: "error" | "aviso" | "info"; accion: { texto: string; ruta: string } };
export type Pendientes = { total: number; errores: number; grupos: { clave: string; titulo: string; items: ItemPendiente[] }[] };
