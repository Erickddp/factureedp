"use client";
import { API, ApiError, getSoporte, getToken } from "./api";
import { isoLocal } from "./format";

export type Efirma = { puesta: boolean; rfc?: string; nombre?: string; vence?: string; minutos?: number; en_uso?: boolean };

export type FilaXml = {
  id: number; uuid: string; tipo: "Emitido" | "Recibido"; fecha: string; clase: string; comprobante: string; serie: string; folio: string;
  rfc_emisor: string; nombre_emisor: string; rfc_receptor: string; nombre_receptor: string; subtotal: number; iva: number; total: number;
  moneda: string; metodo: string; estatus: "Vigente" | "Cancelado"; cancelado_el: string | null; origen: "sat" | "subido" | "aviso";
};

export type ListaXml = {
  total: number; suma: number; por_pagina: number; filas: FilaXml[]; cancelados: number;
  clases: Record<string, { n: number; total: number }>; meses: { mes: string; n: number }[];
};

export type Filtros = { emisor_id: number; mes: string; tipo: string; clase: string; estatus: string; q: string; ids?: number[] };

export type TrabajoXml = {
  id: number; clase: "sat" | "zip"; estado: "curso" | "listo" | "error" | "cancelado" | "interrumpido"; avance: number; total: number;
  mensaje: string; creado: string; terminado: string | null; descargable: boolean; registro?: string;
  params: { desde?: string; hasta?: string; tipo?: string; cancelados?: boolean; nombre?: string; n?: number; incluir?: string };
  resumen: {
    nuevos?: number; repetidos?: number; solicitudes?: number; errores?: string[]; avisos?: string[]; comprobantes?: number; pendientes?: string[];
    estatus?: { revisados: number; cancelados: number; nuevos_cancelados: number; sin_xml: number } | null;
  };
};

export type ResumenXml = {
  comprobantes: number; ingresos: number; gastos: number; diferencia: number; iva_a_cargo: number;
  clases: Record<string, { n: number; subtotal: number; iva: number; total: number }>;
  por_mes: { mes: string; ingresos: number; gastos: number; notas_emitidas: number; notas_recibidas: number; nomina: number; cobrado: number; pagado: number; n: number }[];
  impuestos: Record<string, number>;
  clientes: { rfc: string; nombre: string; total: number; n: number }[];
  proveedores: { rfc: string; nombre: string; total: number; n: number }[];
  cancelados: { n: number; total: number }; metodos: { PUE: number; PPD: number };
  nomina: { recibida: NominaLado; pagada: NominaLado };
};

type CifrasNomina = { recibos: number; percepciones: number; gravado: number; exento: number; deducciones: number; isr: number; imss: number;
  otras_deducciones: number; otros_pagos: number; subsidio: number; neto: number };
/** La nómina vista desde un lado: «recibida» (el contribuyente es el trabajador) o «pagada» (es el patrón). */
export type NominaLado = CifrasNomina & {
  por_quien: (CifrasNomina & { rfc: string; nombre: string })[]; por_mes: (CifrasNomina & { mes: string })[];
  percepciones_det: { concepto: string; tipo: string; gravado: number; exento: number }[];
  deducciones_det: { concepto: string; tipo: string; importe: number }[];
};

/** Lo que es cada comprobante para el contribuyente: letra, nombre y color fijos (los mismos del PDF). */
export const CLASES: Record<string, { nombre: string; plural: string; color: string }> = {
  I: { nombre: "Ingreso", plural: "Ingresos", color: "#1F9D57" },
  G: { nombre: "Gasto", plural: "Gastos", color: "#C7402F" },
  E: { nombre: "Nota de crédito", plural: "Notas de crédito", color: "#D9822B" },
  P: { nombre: "Pago", plural: "Pagos", color: "#2D6CDF" },
  N: { nombre: "Nómina", plural: "Nómina", color: "#7B4BC4" },
  T: { nombre: "Traslado", plural: "Traslados", color: "#6B7686" },
};
export const ORDEN_CLASES = ["I", "G", "E", "P", "N", "T"];

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
export const nombreMes = (m: string) => (m.length === 7 ? `${MESES[Number(m.slice(5, 7)) - 1]} ${m.slice(0, 4)}` : m);
export const mesCorto = (m: string) => MESES[Number(m.slice(5, 7)) - 1]?.slice(0, 3) ?? m;

/** «2026-10-01» → «01/10/2026», sin pasar por zonas horarias (una fecha sola no tiene hora). */
export const dia = (iso?: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

export type Periodo = { id: string; nombre: string; detalle: string; desde: string; hasta: string };

/** Los periodos de un clic. El mes y el año en curso llegan hasta hoy (el SAT no acepta fechas futuras). */
export function periodos(hoy = new Date()): Periodo[] {
  const a = hoy.getFullYear(), m = hoy.getMonth();
  const iso = (d: Date) => isoLocal(d);
  const finMesAnterior = new Date(a, m, 0);
  return [
    { id: "mes", nombre: "Este mes", detalle: `${MESES[m]} ${a}`, desde: iso(new Date(a, m, 1)), hasta: iso(hoy) },
    { id: "mes_anterior", nombre: "Mes anterior", detalle: `${MESES[finMesAnterior.getMonth()]} ${finMesAnterior.getFullYear()}`,
      desde: iso(new Date(finMesAnterior.getFullYear(), finMesAnterior.getMonth(), 1)), hasta: iso(finMesAnterior) },
    { id: "anio", nombre: "Este año", detalle: `enero a ${MESES[m]} ${a}`, desde: iso(new Date(a, 0, 1)), hasta: iso(hoy) },
    { id: "anio_pasado", nombre: "Año pasado", detalle: `todo ${a - 1}`, desde: iso(new Date(a - 1, 0, 1)), hasta: iso(new Date(a - 1, 11, 31)) },
  ];
}

function cabeceras(json = false): Record<string, string> {
  const s = getSoporte();
  return { Authorization: `Bearer ${getToken()}`, ...(json ? { "Content-Type": "application/json" } : {}), ...(s ? { "X-Soporte": String(s.id) } : {}) };
}

async function fallo(res: Response): Promise<never> {
  let msg = "No se pudo completar";
  try { msg = (await res.json()).detail ?? msg; } catch {}
  throw new ApiError(res.status, msg, res.headers.get("x-request-id") ?? undefined);
}

/** Pide un archivo con POST (Excel) y lo guarda con el nombre que manda el servidor. */
export async function bajarConPost(path: string, json: unknown, nombre: string) {
  const res = await fetch(`${API}${path}`, { method: "POST", headers: cabeceras(true), body: JSON.stringify(json) });
  if (!res.ok) await fallo(res);
  const cd = res.headers.get("content-disposition") || "";
  const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
  guardar(await res.blob(), m ? decodeURIComponent(m[1]) : nombre);
}

export function guardar(blob: Blob, nombre: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/** El PDF o el XML de un comprobante como blob (para verlo en pantalla o guardarlo). */
export async function blobDe(path: string): Promise<{ blob: Blob; nombre: string }> {
  const res = await fetch(`${API}${path}`, { headers: cabeceras() });
  if (!res.ok) await fallo(res);
  const m = /filename\*=UTF-8''([^;]+)/.exec(res.headers.get("content-disposition") || "");
  return { blob: await res.blob(), nombre: m ? decodeURIComponent(m[1]) : "cfdi" };
}

/** Texto de la tabla en el formato maestro. Se pide dentro del mismo clic para que el navegador deje copiar. */
export async function copiarTabla(f: Filtros): Promise<number> {
  const pedir = fetch(`${API}/xml/copiar`, { method: "POST", headers: cabeceras(true), body: JSON.stringify(f) })
    .then(async (r) => (r.ok ? r.text() : fallo(r)));
  let lineas = 0;
  const contar = pedir.then((t) => { lineas = Math.max(0, t.split("\n").length - 1); return t; });
  if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
    await navigator.clipboard.write([new ClipboardItem({ "text/plain": contar.then((t) => new Blob([t], { type: "text/plain" })) })]);
  } else {
    await navigator.clipboard.writeText(await contar);
  }
  await contar;
  return lineas;
}

/** Sube XML o ZIP por tandas (una carpeta puede traer miles). Avisa el avance con `paso`. */
export type Candidato = { rfc: string; nombre: string; veces: number };

export type ContribuyenteLeido = { emisor_id: number; rfc: string; nombre: string; creado: boolean; nuevos: number; repetidos: number };
export type Rechazado = { archivo: string; motivo: string };
/** Lo que se leyó de una carpeta: se queda en pantalla (y en la sesión) hasta que se cierre. */
export type ResultadoLectura = {
  cuando: string; leidos: number; total: number; nuevos: number; repetidos: number; rechazados: Rechazado[]; rechazados_total: number;
  contribuyentes: ContribuyenteLeido[]; error: string | null;
};

/** `actual`: el RFC en el que se está trabajando. `elegir`: se llama si los XML no dejan claro de quién son.
 *  Una carpeta puede traer XML de VARIOS contribuyentes: el servidor manda cada CFDI con su dueño (y da de alta los que
 *  falten). Aquí se juntan las tandas por RFC. */
export async function subirXml(archivos: File[], paso: (hechos: number, total: number) => void, actual = "",
  elegir: (c: Candidato[]) => Promise<string | null> = async () => null) {
  const utiles = archivos.filter((a) => /\.(xml|zip)$/i.test(a.name));
  const res = { nuevos: 0, repetidos: 0, ajenos: 0, invalidos: 0, total: utiles.length, emisor_id: 0, rfc: "", nombre: "", creado: false,
    contribuyentes: [] as ContribuyenteLeido[], rechazados: [] as Rechazado[], rechazados_total: 0, leidos: 0, error: null as string | null };
  const porRfc = new Map<string, ContribuyenteLeido>();
  let tanda: File[] = [], peso = 0, hechos = 0, elegido = "";
  const enviar = async () => {
    if (!tanda.length) return;
    const fd = new FormData();
    tanda.forEach((a) => fd.append("archivos", a, a.name));
    // Todas las tandas van a /xml/leer; tras la primera, el RFC principal desempata a su favor en las siguientes.
    const mandar = async () => {
      const ruta = `/xml/leer?actual=${encodeURIComponent(res.rfc || actual)}&rfc=${encodeURIComponent(elegido)}`;
      // nunca se queda «leyendo» para siempre: si el servidor no contesta en 3 minutos, se dice
      const corte = new AbortController();
      const reloj = setTimeout(() => corte.abort(), 180_000);
      try {
        const r = await fetch(`${API}${ruta}`, { method: "POST", headers: cabeceras(), body: fd, signal: corte.signal });
        if (!r.ok) await fallo(r);
        return await r.json();
      } catch (e) {
        if ((e as Error).name === "AbortError" || e instanceof TypeError)
          throw new ApiError(0, `El servidor no contestó al leer los XML ${hechos + 1} a ${hechos + tanda.length}. Lo anterior ya quedó guardado: vuelve a elegir la carpeta (lo repetido se ignora).`);
        throw e;
      } finally { clearTimeout(reloj); }
    };
    let j = await mandar();
    if (j.elegir) {  // ningún CFDI de esta tanda tiene dueño claro: se pregunta de quién son
      elegido = (await elegir(j.elegir as Candidato[])) ?? "";
      if (!elegido) throw new ApiError(0, "No se leyó nada: falta decir de quién son esos XML.");
      j = await mandar();
    }
    for (const c of (j.contribuyentes ?? []) as ContribuyenteLeido[]) {
      const ya = porRfc.get(c.rfc);
      if (ya) { ya.nuevos += c.nuevos; ya.repetidos += c.repetidos; ya.creado ||= c.creado; } else porRfc.set(c.rfc, { ...c });
    }
    res.nuevos += j.nuevos ?? 0; res.repetidos += j.repetidos ?? 0; res.ajenos += j.ajenos ?? 0; res.invalidos += j.invalidos ?? 0;
    res.rechazados_total += j.rechazados_total ?? 0;
    for (const x of (j.rechazados ?? []) as Rechazado[]) if (res.rechazados.length < 300) res.rechazados.push(x);
    res.contribuyentes = [...porRfc.values()].sort((a, b) => b.nuevos + b.repetidos - (a.nuevos + a.repetidos));
    const p = res.contribuyentes[0];
    if (p) { res.emisor_id = p.emisor_id; res.rfc = p.rfc; res.nombre = p.nombre; res.creado = p.creado; }
    hechos += tanda.length;
    res.leidos = hechos;
    paso(hechos, utiles.length);
    tanda = []; peso = 0;
  };
  // Si algo falla a la mitad no se pierde lo ya leído: se devuelve lo que se alcanzó con el error aparte
  try {
    for (const a of utiles) {
      if (tanda.length >= 150 || peso + a.size > 6 * 1024 * 1024) await enviar();  // tandas chicas: cada una contesta rápido
      tanda.push(a);
      peso += a.size;
    }
    await enviar();
  } catch (e) {
    res.error = (e as Error).message || "No se pudo terminar de leer la carpeta.";
  }
  if (!res.error && !res.nuevos && !res.repetidos) res.error = "Ahí no encontré ningún CFDI que se pueda guardar. Abajo ves el motivo de cada archivo.";
  return res;
}
