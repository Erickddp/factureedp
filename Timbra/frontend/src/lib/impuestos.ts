/** Motor de cálculo de impuestos (mismo redondeo que el CFDI: cada impuesto por concepto a 2 decimales). */
import type { Impuesto } from "./types";

type Imp = Pick<Impuesto, "tipo" | "impuesto" | "factor"> & { tasa: string | null };
export type Modo = "base" | "con_iva" | "neto";
export type Desglose = { base: number; iva: number; ieps: number; isr: number; ivaRet: number; total: number; conIva: number };

const r2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100;
const tasa = (i: Imp) => (i.factor === "Exento" ? 0 : Number(i.tasa ?? 0));

export function desglose(base: number, imps: readonly Imp[]): Desglose {
  let iva = 0, ieps = 0, isr = 0, ivaRet = 0;
  // El IVA trasladado se calcula sobre el valor más el IEPS (igual que el CFDI). El IEPS por cuota depende de la cantidad: aquí no entra.
  for (const i of imps) if (i.tipo === "traslado" && i.impuesto === "003" && i.factor === "Tasa") ieps += r2(base * tasa(i));
  for (const i of imps) {
    if (i.tipo === "traslado") {
      if (i.impuesto !== "003") iva += r2((base + ieps) * tasa(i));
    } else {
      const imp = r2(base * tasa(i));
      i.impuesto === "001" ? (isr += imp) : (ivaRet += imp);
    }
  }
  const b = r2(base);
  return { base: b, iva: r2(iva), ieps: r2(ieps), isr: r2(isr), ivaRet: r2(ivaRet), conIva: r2(b + iva + ieps), total: r2(b + iva + ieps - isr - ivaRet) };
}

/** Del monto que tienes (sin IVA, con IVA o lo que te depositan) saca la base exacta al centavo. */
export function baseDesde(monto: number, modo: Modo, imps: readonly Imp[]): { d: Desglose; diferencia: number } {
  if (modo === "base") return { d: desglose(monto, imps), diferencia: 0 };
  const tIeps = imps.filter((i) => i.tipo === "traslado" && i.impuesto === "003" && i.factor === "Tasa").reduce((s, i) => s + tasa(i), 0);
  const tIva = imps.filter((i) => i.tipo === "traslado" && i.impuesto !== "003").reduce((s, i) => s + tasa(i), 0);
  const tr = tIeps + tIva * (1 + tIeps);
  const rt = imps.filter((i) => i.tipo === "retencion").reduce((s, i) => s + tasa(i), 0);
  const factor = modo === "con_iva" ? 1 + tr : 1 + tr - rt;
  const valor = (d: Desglose) => (modo === "con_iva" ? d.conIva : d.total);
  const inicio = r2(monto / factor);
  let mejor = desglose(inicio, imps);
  for (let c = -5; c <= 5; c++) {
    const d = desglose(r2(inicio + c / 100), imps);
    if (Math.abs(valor(d) - monto) < Math.abs(valor(mejor) - monto) - 1e-9) mejor = d;
  }
  return { d: mejor, diferencia: r2(valor(mejor) - monto) };
}

export function suma(ds: Desglose[]): Desglose {
  const s = (k: keyof Desglose) => r2(ds.reduce((a, d) => a + d[k], 0));
  return { base: s("base"), iva: s("iva"), ieps: s("ieps"), isr: s("isr"), ivaRet: s("ivaRet"), conIva: s("conIva"), total: s("total") };
}
