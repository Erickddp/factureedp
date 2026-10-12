const mxn = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });

export function dinero(v: string | number | null | undefined, moneda = "MXN") {
  const n = Number(v ?? 0);
  if (moneda === "MXN" || moneda === "XXX") return mxn.format(n);
  return new Intl.NumberFormat("es-MX", { style: "currency", currency: moneda }).format(n);
}

/** Fecha AAAA-MM-DD en la hora de ESTA computadora. `toISOString()` da la de Londres: de noche en México ya es «mañana». */
export function isoLocal(d: Date = new Date()) {
  const l = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return l.toISOString().slice(0, 10);
}

export function fecha(v: string | null | undefined) {
  if (!v) return "—";
  const d = new Date(v);
  return d.toLocaleDateString("es-MX", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export const TIPOS: Record<string, string> = { I: "Ingreso", E: "Nota de crédito", T: "Traslado", P: "Pago", N: "Nómina" };

export const ESTADOS: Record<string, string> = {
  borrador: "Borrador",
  timbrada: "Timbrada",
  cancelacion_pendiente: "Cancelación en espera",
  cancelada: "Cancelada",
  error: "Error",
};

export const RFC_RE = /^([A-ZÑ&]{3,4})(\d{6})([A-Z\d]{3})$/;

const T = (tasa: string) => ({ tipo: "traslado", impuesto: "002", factor: "Tasa", tasa }) as const;
export const IVA16 = T("0.16");
export const IVA8 = T("0.08");
const IVA0 = T("0.000000");
const EXENTO = { tipo: "traslado", impuesto: "002", factor: "Exento", tasa: null } as const;
const ISR10 = { tipo: "retencion", impuesto: "001", factor: "Tasa", tasa: "0.100000" } as const;
const ISR125 = { tipo: "retencion", impuesto: "001", factor: "Tasa", tasa: "0.012500" } as const;
const RET16 = { tipo: "retencion", impuesto: "002", factor: "Tasa", tasa: "0.106667" } as const; // 2/3 de 16%
const RET8 = { tipo: "retencion", impuesto: "002", factor: "Tasa", tasa: "0.053333" } as const; // 2/3 de 8%
const FLETE = { tipo: "retencion", impuesto: "002", factor: "Tasa", tasa: "0.040000" } as const;
const RET6 = { tipo: "retencion", impuesto: "002", factor: "Tasa", tasa: "0.060000" } as const; // servicios especializados (art. 1-A fr. IV LIVA)
const RETIVA16 = { tipo: "retencion", impuesto: "002", factor: "Tasa", tasa: "0.160000" } as const;
const IEPS = (tasa: string) => ({ tipo: "traslado", impuesto: "003", factor: "Tasa", tasa }) as const;

type Imp = { readonly tipo: string; readonly impuesto: string; readonly factor: string; readonly tasa: string | null };

/** Combinaciones que un contador usa diario. La retención de IVA siempre es 2/3 del IVA trasladado. */
export const GRUPOS_IMPUESTOS: { grupo: string; items: Record<string, readonly Imp[]> }[] = [
  { grupo: "Sólo IVA", items: { "IVA 16%": [IVA16], "IVA 8% frontera": [IVA8], "IVA 0%": [IVA0], "Exento": [EXENTO] } },
  { grupo: "Honorarios o ARRENDAMIENTO · PF → persona moral (mismas retenciones)", items: {
    "Honorarios PF → PM · IVA 16% (ret. ISR 10%, IVA 10.6667%)": [IVA16, ISR10, RET16],
    "Honorarios PF → PM · IVA 8% frontera (ret. ISR 10%, IVA 5.3333%)": [IVA8, ISR10, RET8],
    "Honorarios médicos PF → PM · exento (ret. ISR 10%)": [EXENTO, ISR10],
  } },
  { grupo: "RESICO persona física → persona moral", items: {
    "RESICO → PM · IVA 16% (ret. ISR 1.25%, IVA 10.6667%)": [IVA16, ISR125, RET16],
    "RESICO → PM · IVA 8% frontera (ret. ISR 1.25%, IVA 5.3333%)": [IVA8, ISR125, RET8],
    "RESICO → PM · exento (ret. ISR 1.25%)": [EXENTO, ISR125],
  } },
  { grupo: "Otras retenciones de IVA", items: {
    "Servicios especializados · IVA 16% (ret. IVA 6%)": [IVA16, RET6],
    "IVA 16% con retención total de IVA": [IVA16, RETIVA16],
    "Fletes · IVA 16% (ret. IVA 4%)": [IVA16, FLETE],
  } },
  // Sólo tasas de IEPS estables; tabaco, refrescos y combustibles cambian cada año: van por «Otro impuesto o tasa…»
  { grupo: "IEPS (el IVA se calcula sobre precio + IEPS)", items: {
    "IEPS 8% alimentos de alta densidad calórica · IVA 0%": [IEPS("0.080000"), IVA0],
    "IEPS 8% alimentos de alta densidad calórica · IVA 16%": [IEPS("0.080000"), IVA16],
    "IEPS 26.5% cerveza y alcohol hasta 14° · IVA 16%": [IEPS("0.265000"), IVA16],
    "IEPS 30% alcohol de 14° a 20° · IVA 16%": [IEPS("0.300000"), IVA16],
    "IEPS 53% alcohol de más de 20° · IVA 16%": [IEPS("0.530000"), IVA16],
    "IEPS 25% bebidas energetizantes · IVA 16%": [IEPS("0.250000"), IVA16],
  } },
  { grupo: "Otros", items: { "Sin impuestos (objeto 01)": [] } },
];

export const PRESETS_IMPUESTOS: Record<string, readonly Imp[]> = Object.assign({}, ...GRUPOS_IMPUESTOS.map((g) => g.items));
export const presetPorDefecto = (frontera?: boolean) => (frontera ? "IVA 8% frontera" : "IVA 16%");
