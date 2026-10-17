/**
 * FUENTE ÚNICA de los datos legales de Timbra: las páginas de /legal/* leen de aquí (nada de repetir datos en cada texto).
 * VERSION debe ser igual a TERMINOS_VERSION de backend/app/legal.py (lo vigila tests/test_w17_legal.py): si cambias algo de
 * fondo en los textos, sube las dos, agrega la entrada de HISTORIAL y cada cuenta los aceptará otra vez al entrar.
 * Datos del responsable tomados de la Constancia de Situación Fiscal (16-mar-2026): la ley pide nombre y domicilio.
 */
export const VERSION = "2026-10-17";
export const VIGENTE_DESDE = "17 de octubre de 2026";

export const RESPONSABLE = {
  marca: "Timbra",
  nombre: "Erick Dominguez del Prado",
  rfc: "DOPE000620F8A",
  // Lo que se ve en el Aviso y los Términos: sólo alcaldía y ciudad. El domicilio completo vive aparte (domicilioCompleto).
  domicilio: "Cuajimalpa de Morelos, Ciudad de México, C.P. 05010",
  // Sólo se muestra en /legal/responsable (sin enlace desde el menú, fuera de buscadores). Si usas domicilio de despacho u oficina
  // virtual para notificaciones, cámbialo aquí y listo.
  domicilioCompleto: "Avenida Puerto México 19, interior 19, colonia Zentlapatl, C.P. 05010, Cuajimalpa de Morelos, Ciudad de México",
  correo: "privacidad@erickddp.com",
  sitio: "erickddp.com",
};

/** Quién recibe qué (apartado «Con quién los compartimos» del Aviso). Si agregas un proveedor que reciba datos, agrégalo aquí. */
export const PROVEEDORES = [
  { nombre: "SAT", para: "Recibe cada CFDI para validarlo, y es de donde bajas tus XML", donde: "México", obligatorio: true },
  { nombre: "Finkok (PAC)", para: "Timbra, valida y cancela tus CFDI", donde: "México", obligatorio: true },
  { nombre: "Railway", para: "Aloja el servidor y la base de datos de Timbra", donde: "Estados Unidos", obligatorio: false },
  { nombre: "Resend", para: "Envía los correos (confirmación de cuenta, facturas, avisos)", donde: "Estados Unidos", obligatorio: false },
  { nombre: "Mercado Pago", para: "Cobra los timbres. Timbra no ve ni guarda los datos de tu tarjeta", donde: "México", obligatorio: false },
  { nombre: "Google", para: "Inicio de sesión y, si tú lo activas, la copia de tus XML en tu Drive", donde: "Estados Unidos", obligatorio: false },
] as const;

/** Qué cambió en cada versión (se muestra en el Centro legal). La más nueva va primero. */
export const HISTORIAL = [
  { version: "2026-10-17", fecha: "17 de octubre de 2026", cambios: [
    "Crear cuenta con correo y contraseña, y confirmar tu correo para recibir los 3 timbres de regalo.",
    "Entrar con Google ahora guarda también tu foto de perfil (sólo se muestra en tu avatar).",
    "Copia opcional de tus XML en tu Google Drive (permiso limitado a lo que Timbra crea).",
    "Constancia de Situación Fiscal: qué se guarda y para qué.",
    "Modo invitado: cuenta temporal de 1 hora, sin datos personales.",
    "La e.firma es personal e intransferible: para bajar XML de un cliente necesitas su autorización por escrito.",
    "Domicilio del responsable: se muestra sólo la ciudad; el completo está en su propia página.",
    "Aviso de novedades: ahora es una casilla opcional. Puedes cerrar tu cuenta tú mismo en Mi perfil → Mis datos.",
  ] },
  { version: "2026-10-16", fecha: "16 de octubre de 2026", cambios: ["Primera versión publicada: Términos de uso y Aviso de privacidad."] },
] as const;

export const PENDIENTE = (s: string) => s.startsWith("⟨");
