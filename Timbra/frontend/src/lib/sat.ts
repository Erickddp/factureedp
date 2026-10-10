/** Reglas SAT del lado del navegador (espejo de backend/app/services/validacion.py) para guiar antes de validar. */
const EMPRESARIAL = ["601", "603", "606", "612", "620", "621", "622", "623", "624", "625", "626"];
const DEDUCCIONES = ["605", "606", "608", "611", "612", "614", "607", "615", "625"];
const TODOS = ["601", "603", "605", "606", "608", "610", "611", "612", "614", "616", "620", "621", "622", "623", "624", "607", "615", "625", "626"];

export const USO_REGIMEN: Record<string, string[]> = {
  ...Object.fromEntries(["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I07", "I08"].map((u) => [u, EMPRESARIAL])),
  ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [`D${String(i + 1).padStart(2, "0")}`, DEDUCCIONES])),
  S01: TODOS,
  CP01: TODOS,
  CN01: ["605"],
};

export const REG_FISICA = ["605", "606", "607", "608", "610", "611", "612", "614", "615", "616", "621", "625", "626"];
export const REG_MORAL = ["601", "603", "610", "620", "622", "623", "624", "626"];

export const usoPermitido = (uso: string, regimen: string) => !regimen || (USO_REGIMEN[uso] ?? []).includes(regimen);
export const regimenPermitido = (regimen: string, rfc: string) =>
  !rfc || rfc.length < 12 || (rfc.length === 12 ? REG_MORAL : REG_FISICA).includes(regimen);

/** Uso sugerido al elegir régimen: G03 si se puede; si no D01 (asalariados); si no S01. */
export function usoSugerido(regimen: string, actual?: string) {
  if (actual && usoPermitido(actual, regimen)) return actual;
  for (const u of ["G03", "D01", "S01"]) if (usoPermitido(u, regimen)) return u;
  return "S01";
}

/** Limpia montos ("$1,500.00") y resuelve operaciones ("=14500/1.16"). Devuelve null si no es número. */
export function evaluarMonto(v: string): string | null {
  const s = (v ?? "").trim().replace(/^=/, "").replace(/[$,\s]/g, "");
  if (s === "") return "";
  if (/^\d*\.?\d+$/.test(s) || /^\d+\.$/.test(s)) return s.replace(/\.$/, "");
  if (!/^[\d.+\-*/()]+$/.test(s)) return null;
  try {
    // Sólo dígitos y operadores (validado arriba): seguro de evaluar
    const r = Function(`"use strict";return (${s})`)() as number;
    if (!Number.isFinite(r)) return null;
    return String(Math.round(r * 1e6) / 1e6);
  } catch {
    return null;
  }
}
