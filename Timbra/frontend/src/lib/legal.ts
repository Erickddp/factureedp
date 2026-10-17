/**
 * Datos de los términos de uso y del aviso de privacidad (pantallas en app/legal/*).
 * VERSION debe ser igual a TERMINOS_VERSION de backend/app/legal.py: si cambias algo de fondo en los textos, sube las dos
 * y cada cuenta los aceptará otra vez al entrar.
 * Datos del responsable tomados de la Constancia de Situación Fiscal (16-mar-2026): la ley pide nombre y domicilio.
 */
export const VERSION = "2026-10-16";
export const VIGENTE_DESDE = "16 de octubre de 2026";

export const RESPONSABLE = {
  marca: "Timbra",
  nombre: "Erick Dominguez del Prado",
  rfc: "DOPE000620F8A",
  domicilio: "Avenida Puerto México 19, interior 19, colonia Zentlapatl, C.P. 05010, Cuajimalpa de Morelos, Ciudad de México",
  correo: "privacidad@erickddp.com",
  sitio: "erickddp.com",
};

export const PENDIENTE = (s: string) => s.startsWith("⟨");
