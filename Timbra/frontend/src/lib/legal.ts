/**
 * Datos de los términos de uso y del aviso de privacidad (pantallas en app/legal/*).
 * VERSION debe ser igual a TERMINOS_VERSION de backend/app/legal.py: si cambias algo de fondo en los textos, sube las dos
 * y cada cuenta los aceptará otra vez al entrar.
 * Lo marcado con ⟨…⟩ lo llena Rick antes de abrir el registro: la ley pide nombre y domicilio del responsable.
 */
export const VERSION = "2026-10-16";
export const VIGENTE_DESDE = "16 de octubre de 2026";

export const RESPONSABLE = {
  marca: "Timbra",
  nombre: "⟨Nombre o razón social del titular de EDDP Servicios⟩",
  rfc: "⟨RFC⟩",
  domicilio: "⟨Calle, número, colonia, código postal, municipio y estado⟩",
  correo: "privacidad@erickddp.com",
  sitio: "erickddp.com",
};

export const PENDIENTE = (s: string) => s.startsWith("⟨");
