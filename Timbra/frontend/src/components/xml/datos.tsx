"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { dinero } from "@/lib/format";
import type { Emisor } from "@/lib/types";
import { CLASES, type ListaXml, type NominaLado, ORDEN_CLASES, type ResumenXml, mesCorto, nombreMes } from "@/lib/xml";
import { ArrowDownRight, ArrowUpRight, ChevronDown, Lightbulb } from "lucide-react";
import { Button, Select, cx, tabla } from "@/components/ui";
import { Letra } from "./comprobantes";

const corto = (n: number) => (Math.abs(n) >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : Math.abs(n) >= 1e3 ? `${Math.round(n / 1e3)} k` : String(Math.round(n)));
const COLOR_SUELDOS = CLASES.N.color;

type Totales = Record<"deducible" | "no_deducible" | "revisar" | "personal", { n: number; total: number; iva: number }>;

/** Rango de fechas (AAAA-MM-DD) del periodo elegido: un mes «2026-10», un año «2026» o todo (""). */
function rango(mes: string): [string, string] {
  if (mes.length === 7) { const [a, m] = mes.split("-").map(Number); return [`${mes}-01`, `${mes}-${String(new Date(a, m, 0).getDate()).padStart(2, "0")}`]; }
  if (mes.length === 4) return [`${mes}-01-01`, `${mes}-12-31`];
  return ["", ""];
}
/** El periodo contra el que se compara: el mes anterior o el año anterior. */
function anterior(mes: string): string {
  if (mes.length === 7) { const [a, m] = mes.split("-").map(Number); return m === 1 ? `${a - 1}-12` : `${a}-${String(m - 1).padStart(2, "0")}`; }
  if (mes.length === 4) return String(Number(mes) - 1);
  return "";
}
// RESICO persona física: tasa mensual de ISR sobre los ingresos del mes (art. 113-E LISR). Es una estimación.
const tasaResico = (ingresos: number) => (ingresos <= 25000 ? 0.01 : ingresos <= 50000 ? 0.011 : ingresos <= 83333.33 ? 0.015 : ingresos <= 208333.33 ? 0.02 : ingresos <= 291666.67 ? 0.025 : 0);

export function Datos({ emisor, version, alGastos }: { emisor: Emisor; version: number; alGastos?: () => void }) {
  const [mes, setMes] = useState("");
  const [detalle, setDetalle] = useState(false);
  useEffect(() => setMes(""), [emisor.id]);
  const { data: lista } = useSWR<ListaXml>(`/xml/cfdi?emisor_id=${emisor.id}&estatus=&pagina=1&v=${version}`, (u: string) => api<ListaXml>(u.replace(/&v=\d+$/, "")));
  const { data: r } = useSWR<ResumenXml>(["xml-resumen", emisor.id, mes, version],
    () => api<ResumenXml>("/xml/resumen", { method: "POST", json: { emisor_id: emisor.id, mes, estatus: "" } }), { keepPreviousData: true });
  const antes = anterior(mes);
  const { data: prev } = useSWR<ResumenXml>(antes ? ["xml-resumen", emisor.id, antes, version] : null,
    () => api<ResumenXml>("/xml/resumen", { method: "POST", json: { emisor_id: emisor.id, mes: antes, estatus: "" } }));
  const [desde, hasta] = rango(mes);
  const { data: gastos } = useSWR<{ totales: Totales; constancia: { regimenes: string[] } | null }>(["xml-gastos-resumen", emisor.id, mes, version],
    () => api(`/deducibles?emisor_id=${emisor.id}&desde=${desde}&hasta=${hasta}&limite=1`));
  const anios = [...new Set((lista?.meses ?? []).map((m) => m.mes.slice(0, 4)))];

  if (lista && !lista.meses.length)
    return <p className="rounded-3xl bg-hoja px-6 py-16 text-center text-grafito ring-1 ring-linea">Todavía no hay XML. Descarga del SAT o lee una carpeta en la pestaña «Descargar».</p>;
  if (!r) return <p className="py-16 text-center text-grafito">Calculando…</p>;

  const i = r.impuestos;
  const sueldos = r.nomina.recibida, pagada = r.nomina.pagada;
  const haySueldos = sueldos.recibos > 0;
  const sueldoDe = (m: string) => sueldos.por_mes.find((x) => x.mes === m)?.percepciones ?? 0;
  const maxMes = Math.max(1, ...r.por_mes.flatMap((m) => [m.ingresos, m.gastos, sueldoDe(m.mes)]));
  const margen = r.ingresos > 0 ? (r.diferencia / r.ingresos) * 100 : null;
  const delta = (a: number, b?: number) => (b && Math.abs(b) > 0 ? ((a - b) / Math.abs(b)) * 100 : null);

  // Lo que Timbra ve en tus números (cada línea dice qué hacer): sólo lo que sí hay en los XML
  const avisos: { tono: "sello" | "alerta" | "rojo" | "info"; texto: string; accion?: { texto: string; ir: () => void } }[] = [];
  const dIng = delta(r.ingresos, prev?.ingresos);
  if (dIng !== null && Math.abs(dIng) >= 10 && prev)
    avisos.push({ tono: dIng > 0 ? "sello" : "alerta", texto: `Tus ingresos ${dIng > 0 ? "subieron" : "bajaron"} ${Math.abs(dIng).toFixed(0)}% contra ${nombreMes(antes)} (${dinero(prev.ingresos)}).` });
  const totalCli = r.clientes.reduce((x, c) => x + c.total, 0);
  if (r.clientes[0] && totalCli > 0 && r.clientes[0].total / totalCli >= 0.4 && r.clientes.length > 1)
    avisos.push({ tono: "alerta", texto: `${r.clientes[0].nombre || r.clientes[0].rfc} concentra el ${Math.round((r.clientes[0].total / totalCli) * 100)}% de tus ventas: si se va, lo notas.` });
  const totalProv = r.proveedores.reduce((x, c) => x + c.total, 0);
  if (r.proveedores[0] && totalProv > 0 && r.proveedores[0].total / totalProv >= 0.4 && r.proveedores.length > 1)
    avisos.push({ tono: "info", texto: `${r.proveedores[0].nombre || r.proveedores[0].rfc} es el ${Math.round((r.proveedores[0].total / totalProv) * 100)}% de tus compras.` });
  const credito = r.metodos.PPD / Math.max(1, r.metodos.PUE + r.metodos.PPD);
  if (credito >= 0.3) avisos.push({ tono: "info", texto: `${Math.round(credito * 100)}% de lo que facturas es a crédito (PPD): da seguimiento a los pagos y pide su complemento.` });
  if (gastos) {
    const g = gastos.totales;
    if (!gastos.constancia) avisos.push({ tono: "info", texto: "Sube tu constancia fiscal para que Timbra clasifique tus gastos en deducibles y no deducibles.", accion: alGastos && { texto: "Subir constancia", ir: alGastos } });
    else if (g.revisar.n > 0) avisos.push({ tono: "alerta", texto: `${g.revisar.n} ${g.revisar.n === 1 ? "gasto espera" : "gastos esperan"} tu decisión (${dinero(g.revisar.total)}).`, accion: alGastos && { texto: "Revisar", ir: alGastos } });
    else if (g.deducible.n > 0) avisos.push({ tono: "sello", texto: `${dinero(g.deducible.total)} en gastos deducibles${g.deducible.iva ? ` y ${dinero(g.deducible.iva)} de IVA acreditable` : ""}.` });
  }
  if (mes.length === 7 && r.iva_a_cargo > 0) avisos.push({ tono: "info", texto: `IVA a cargo estimado de ${nombreMes(mes)}: ${dinero(r.iva_a_cargo)}. Se paga a más tardar el 17 del mes siguiente.` });
  const resico = (gastos?.constancia?.regimenes ?? []).includes("626") && emisor.rfc.length === 13;
  if (resico && mes.length === 7 && r.ingresos > 0)
    avisos.push({ tono: "info", texto: `ISR RESICO estimado de ${nombreMes(mes)}: ${dinero(r.ingresos * tasaResico(r.ingresos))} (${(tasaResico(r.ingresos) * 100).toFixed(2)}% de tus ingresos). Es una estimación: confírmala con tu contador.` });
  if (r.cancelados.n > 0) avisos.push({ tono: "info", texto: `${r.cancelados.n} ${r.cancelados.n === 1 ? "comprobante cancelado" : "comprobantes cancelados"} (${dinero(r.cancelados.total)}) no se cuentan arriba.` });

  return (
    <div className="grid gap-5 sm:gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-hoja px-4 py-3 ring-1 ring-linea sm:px-5">
        <p className="text-sm text-grafito"><b className="tabular-nums text-tinta">{r.comprobantes.toLocaleString("es-MX")}</b> comprobantes en tus XML</p>
        <Select value={mes} onChange={(e) => setMes(e.target.value)} className="h-11! w-full! text-base! sm:w-auto!" aria-label="Periodo">
          <option value="">Todo lo que tengo</option>
          {anios.map((a) => <option key={a} value={a}>Todo {a}</option>)}
          {(lista?.meses ?? []).map((m) => <option key={m.mes} value={m.mes}>{nombreMes(m.mes)}</option>)}
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Kpi titulo="Ingresos" valor={r.ingresos} color={CLASES.I.color} cambio={dIng} nota={`${r.clases.I.n} facturas emitidas`} />
        <Kpi titulo="Gastos" valor={r.gastos} color={CLASES.G.color} cambio={delta(r.gastos, prev?.gastos)} malo="sube" nota={`${r.clases.G.n} facturas recibidas`} />
        <Kpi titulo="Te queda" valor={r.diferencia} cambio={delta(r.diferencia, prev?.diferencia)} nota={margen === null ? "ingresos menos gastos" : `${margen.toFixed(0)}% de tus ingresos`} />
        <Kpi titulo={r.iva_a_cargo >= 0 ? "IVA a cargo" : "IVA a favor"} valor={Math.abs(r.iva_a_cargo)} nota="trasladado menos acreditable y retenido" />
      </div>
      {haySueldos && (
        <p className="rounded-2xl bg-hoja px-4 py-3 text-sm ring-1 ring-linea sm:px-5">
          <i className="mr-2 inline-block size-2.5 rounded-full align-middle" style={{ background: COLOR_SUELDOS }} />
          <b>Sueldos recibidos {dinero(sueldos.percepciones)}</b> <span className="text-grafito">· {sueldos.recibos} recibos · neto {dinero(sueldos.neto)} · ISR retenido {dinero(sueldos.isr)}</span>
        </p>
      )}

      {avisos.length > 0 && (
        <section className="rounded-3xl bg-hoja p-4 ring-1 ring-linea sm:p-6">
          <h3 className="mb-3 flex items-center gap-2 text-base font-semibold sm:text-lg"><Lightbulb className="size-4 text-acento" /> Lo que veo en tus números</h3>
          <ul className="grid gap-2">
            {avisos.slice(0, 6).map((a, k) => (
              <li key={k} className={cx("flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl px-3.5 py-2.5 text-sm",
                a.tono === "sello" ? "bg-sello-suave text-sello" : a.tono === "alerta" ? "bg-alerta-suave text-alerta" : a.tono === "rojo" ? "bg-rojo-suave text-rojo" : "bg-tinta/[.04] text-tinta")}>
                <span className="min-w-0 flex-1">{a.texto}</span>
                {a.accion && <Button size="sm" variant="secundario" onClick={a.accion.ir}>{a.accion.texto}</Button>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <Panel titulo="Mes por mes" extra={<>
        <Leyenda color={CLASES.I.color} texto="Ingresos" />{haySueldos && <Leyenda color={COLOR_SUELDOS} texto="Sueldos" />}<Leyenda color={CLASES.G.color} texto="Gastos" /></>}>
        <div className="flex h-56 items-end gap-2 overflow-x-auto pb-1 sm:h-72 sm:gap-5">
          {r.por_mes.map((m) => (
            <div key={m.mes} className="flex h-full min-w-14 flex-1 flex-col items-center justify-end gap-2"
              title={`${nombreMes(m.mes)}\nIngresos ${dinero(m.ingresos)}${haySueldos ? `\nSueldos ${dinero(sueldoDe(m.mes))}` : ""}\nGastos ${dinero(m.gastos)}\nCobrado con REP ${dinero(m.cobrado)}`}>
              <div className="flex w-full flex-1 items-end justify-center gap-1">
                <Barra alto={m.ingresos / maxMes} color={CLASES.I.color} texto={corto(m.ingresos)} />
                {haySueldos && <Barra alto={sueldoDe(m.mes) / maxMes} color={COLOR_SUELDOS} texto={corto(sueldoDe(m.mes))} />}
                <Barra alto={m.gastos / maxMes} color={CLASES.G.color} texto={corto(m.gastos)} />
              </div>
              <span className="text-xs text-grafito">{mesCorto(m.mes)} {m.mes.slice(2, 4)}</span>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid gap-5 sm:gap-6 lg:grid-cols-2">
        <Ranking titulo="A quién más le vendes" datos={r.clientes.slice(0, 5)} color={CLASES.I.color} />
        <Ranking titulo="A quién más le compras" datos={r.proveedores.slice(0, 5)} color={CLASES.G.color} />
      </div>

      {haySueldos && <Nomina n={sueldos} titulo="Nómina recibida" sub="Lo que le pagaron a este contribuyente como trabajador" quien="Quién le paga" />}
      {pagada.recibos > 0 && <Nomina n={pagada} titulo="Nómina pagada" sub="Lo que este contribuyente pagó a sus trabajadores" quien="A quién le paga" />}

      <button type="button" onClick={() => setDetalle((d) => !d)} aria-expanded={detalle}
        className="flex items-center justify-between rounded-2xl bg-hoja px-4 py-3.5 text-left text-sm font-medium ring-1 ring-linea hover:ring-grafito/40 sm:px-5">
        Impuestos y desglose completo <ChevronDown className={cx("size-4 text-grafito transition-transform", detalle && "rotate-180")} />
      </button>
      {detalle && (
        <div className="grid gap-5 sm:gap-6 lg:grid-cols-2">
          <Panel titulo="Impuestos de sus facturas">
            <dl className="divide-y divide-linea text-sm">
              <Linea k="IVA trasladado (lo que cobró)" v={i.iva_trasladado} />
              <Linea k="IVA acreditable (lo que le cobraron)" v={i.iva_acreditable} />
              <Linea k="IVA que le retuvieron" v={i.iva_retenido_a_mi} />
              <Linea k="ISR que le retuvieron" v={i.isr_retenido_a_mi} />
              <Linea k="IVA que retuvo" v={i.iva_retenido_por_mi} />
              <Linea k="ISR que retuvo" v={i.isr_retenido_por_mi} />
              {(i.ieps_trasladado > 0 || i.ieps_pagado > 0) && <Linea k="IEPS trasladado / pagado" v={i.ieps_trasladado} extra={dinero(i.ieps_pagado)} />}
            </dl>
            <h4 className="mb-2 mt-6 text-sm font-semibold">Ventas por tasa de IVA</h4>
            <Tasas datos={[["16%", i.base_16], ["8%", i.base_8], ["0%", i.base_0], ["Exento", i.base_exento]]} />
          </Panel>
          <Panel titulo="Qué hay">
            <ul className="grid gap-3">
              {ORDEN_CLASES.filter((c) => r.clases[c].n > 0).map((c) => (
                <li key={c} className="flex items-center gap-3">
                  <Letra clase={c} />
                  <span className="flex-1">{CLASES[c].plural}</span>
                  <b className="text-lg tabular-nums">{r.clases[c].n}</b>
                  <span className="w-28 text-right tabular-nums text-grafito sm:w-36">{dinero(r.clases[c].total)}</span>
                </li>
              ))}
              <li className={cx("flex items-center gap-3", !r.cancelados.n && "opacity-50")}>
                <span className="grid size-7 place-items-center rounded-lg bg-rojo-suave text-xs font-semibold text-rojo">✕</span>
                <span className="flex-1">Cancelados (no cuentan arriba)</span>
                <b className="text-lg tabular-nums">{r.cancelados.n}</b>
                <span className="w-28 text-right tabular-nums text-grafito sm:w-36">{dinero(r.cancelados.total)}</span>
              </li>
            </ul>
            {(r.metodos.PUE > 0 || r.metodos.PPD > 0) && <>
              <h4 className="mb-2 mt-6 text-sm font-semibold">Cómo te pagan lo que facturas</h4>
              <Tasas datos={[["De contado (PUE)", r.metodos.PUE], ["A crédito (PPD)", r.metodos.PPD]]} />
            </>}
          </Panel>
        </div>
      )}
    </div>
  );
}

/** El desglose de la nómina: totales, quién paga, mes por mes y concepto por concepto. */
function Nomina({ n, titulo, sub, quien }: { n: NominaLado; titulo: string; sub: string; quien: string }) {
  const [ver, setVer] = useState<"mes" | "quien" | "conceptos">("mes");
  const num = cx(tabla.td, tabla.num);
  const fila = (clave: string, etiqueta: React.ReactNode, x: { recibos: number; percepciones: number; gravado: number; exento: number; isr: number; imss: number; otras_deducciones: number; neto: number }) => (
    <tr key={clave}>
      <td className={cx(tabla.td, "font-medium")}>{etiqueta}</td><td className={num}>{x.recibos}</td><td className={num}>{dinero(x.percepciones)}</td>
      <td className={cx(num, "text-grafito")}>{dinero(x.gravado)}</td><td className={cx(num, "text-grafito")}>{dinero(x.exento)}</td>
      <td className={cx(num, "text-rojo")}>{dinero(x.isr)}</td><td className={num}>{dinero(x.imss)}</td><td className={num}>{dinero(x.otras_deducciones)}</td>
      <td className={cx(num, "font-semibold")}>{dinero(x.neto)}</td>
    </tr>
  );
  const cabecera = (primera: string) => (
    <thead><tr>
      <th className={tabla.th}>{primera}</th><th className={cx(tabla.th, tabla.num)}>Recibos</th><th className={cx(tabla.th, tabla.num)}>Percepciones</th>
      <th className={cx(tabla.th, tabla.num)}>Gravado</th><th className={cx(tabla.th, tabla.num)}>Exento</th><th className={cx(tabla.th, tabla.num)}>ISR retenido</th>
      <th className={cx(tabla.th, tabla.num)}>Seg. social</th><th className={cx(tabla.th, tabla.num)}>Otras deduc.</th><th className={cx(tabla.th, tabla.num)}>Neto</th>
    </tr></thead>
  );
  const maxP = Math.max(1, ...n.percepciones_det.map((p) => p.gravado + p.exento));
  const maxD = Math.max(1, ...n.deducciones_det.map((d) => d.importe));
  return (
    <section className="overflow-hidden rounded-3xl bg-hoja ring-1 ring-linea">
      <div className="flex flex-wrap items-center gap-4 px-6 pt-6 sm:px-7">
        <Letra clase="N" grande />
        <div className="min-w-0 flex-1"><h3 className="text-xl font-semibold">{titulo}</h3><p className="text-sm text-grafito">{sub} · {n.recibos} recibos</p></div>
        <div role="tablist" className="flex gap-1 rounded-xl bg-papel p-1 ring-1 ring-linea">
          {([["mes", "Mes por mes"], ["quien", quien], ["conceptos", "Por concepto"]] as const).map(([id, t]) => (
            <button key={id} role="tab" aria-selected={ver === id} onClick={() => setVer(id)}
              className={cx("h-9 rounded-lg px-3.5 text-sm font-medium", ver === id ? "bg-primario text-sobre-primario" : "text-grafito hover:text-tinta")}>{t}</button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 px-6 py-6 sm:grid-cols-3 sm:px-7 xl:grid-cols-6">
        <Dato k="Percepciones" v={n.percepciones} />
        <Dato k="Gravado" v={n.gravado} sub={n.percepciones ? `${Math.round((n.gravado / n.percepciones) * 100)}% del total` : undefined} />
        <Dato k="Exento" v={n.exento} />
        <Dato k="ISR retenido" v={n.isr} tono="text-rojo" sub={n.gravado ? `${((n.isr / n.gravado) * 100).toFixed(1)}% de lo gravado` : undefined} />
        <Dato k="Seguridad social y otras" v={n.imss + n.otras_deducciones} sub={`seg. social ${dinero(n.imss)}`} />
        <Dato k="Neto pagado" v={n.neto} tono="text-sello" sub={n.otros_pagos ? `incluye otros pagos ${dinero(n.otros_pagos)}` : undefined} />
      </div>
      {ver !== "conceptos" ? (
        <div className="overflow-x-auto border-t border-linea">
          <table className={tabla.base}>
            {cabecera(ver === "mes" ? "Mes" : quien)}
            <tbody>
              {ver === "mes" ? n.por_mes.map((m) => fila(m.mes, <span className="capitalize">{nombreMes(m.mes)}</span>, m))
                : n.por_quien.map((q) => fila(q.rfc, <><span className="block max-w-72 truncate">{q.nombre || q.rfc}</span><span className="font-mono text-[11px] font-normal text-grafito">{q.rfc}</span></>, q))}
              {fila("total", "Total", n)}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="grid gap-8 border-t border-linea px-6 py-6 sm:px-7 lg:grid-cols-2">
          <div>
            <h4 className="mb-3 text-sm font-semibold">Percepciones</h4>
            <ul className="grid gap-2.5">
              {n.percepciones_det.map((p) => (
                <li key={p.concepto}>
                  <div className="flex items-baseline justify-between gap-3 text-sm"><span className="min-w-0 truncate" title={p.tipo}>{p.concepto}</span>
                    <b className="shrink-0 tabular-nums">{dinero(p.gravado + p.exento)}</b></div>
                  <div className="mt-1 flex h-1.5 overflow-hidden rounded-full bg-tinta/[.07]">
                    <i className="block h-full" style={{ width: `${(p.gravado / maxP) * 100}%`, background: COLOR_SUELDOS }} />
                    <i className="block h-full opacity-45" style={{ width: `${(p.exento / maxP) * 100}%`, background: COLOR_SUELDOS }} />
                  </div>
                  {p.exento > 0 && <p className="mt-0.5 text-[11px] text-grafito">gravado {dinero(p.gravado)} · exento {dinero(p.exento)}</p>}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="mb-3 text-sm font-semibold">Deducciones</h4>
            <ul className="grid gap-2.5">
              {n.deducciones_det.map((d) => (
                <li key={d.concepto}>
                  <div className="flex items-baseline justify-between gap-3 text-sm"><span className="min-w-0 truncate" title={d.tipo}>{d.concepto} {d.tipo && <span className="text-xs text-grafito">· {d.tipo}</span>}</span>
                    <b className="shrink-0 tabular-nums">{dinero(d.importe)}</b></div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-tinta/[.07]"><i className="block h-full rounded-full bg-rojo" style={{ width: `${(d.importe / maxD) * 100}%` }} /></div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}

function Panel({ titulo, extra, children }: { titulo: string; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-3xl bg-hoja p-4 ring-1 ring-linea sm:p-7">
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-1"><h3 className="text-xl font-semibold">{titulo}</h3>{extra}</div>
      {children}
    </section>
  );
}

const Leyenda = ({ color, texto }: { color: string; texto: string }) => (
  <span className="flex items-center gap-1.5 text-sm text-grafito"><i className="size-3 rounded-sm" style={{ background: color }} /> {texto}</span>
);

function Dato({ k, v, sub, tono }: { k: string; v: number; sub?: string; tono?: string }) {
  return <div><p className="text-[11px] font-medium uppercase tracking-[.1em] text-grafito">{k}</p><p className={cx("mt-1 text-2xl font-semibold tabular-nums", tono)}>{dinero(v)}</p>{sub && <p className="text-xs text-grafito">{sub}</p>}</div>;
}

/** Cifra grande con su cambio contra el periodo anterior. `malo`: qué dirección es mala (los gastos que suben, no los ingresos). */
function Kpi({ titulo, valor, nota, color, cambio, malo = "baja" }: { titulo: string; valor: number; nota: string; color?: string; cambio?: number | null; malo?: "sube" | "baja" }) {
  const sube = (cambio ?? 0) > 0, mal = cambio != null && Math.abs(cambio) >= 1 && (malo === "sube" ? sube : !sube);
  return (
    <div className="min-w-0 rounded-2xl bg-hoja p-4 ring-1 ring-linea sm:rounded-3xl sm:p-6">
      <p className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[.12em] text-grafito">{color && <i className="size-2.5 shrink-0 rounded-full" style={{ background: color }} />}<span className="truncate">{titulo}</span></p>
      <p className={cx("mt-1.5 truncate text-xl font-semibold tracking-tight tabular-nums sm:mt-2 sm:text-3xl", valor < 0 && "text-rojo")}>{dinero(valor)}</p>
      <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-grafito">
        {cambio != null && Math.abs(cambio) >= 1 && (
          <span className={cx("inline-flex items-center gap-0.5 font-medium", mal ? "text-rojo" : "text-sello")}>{sube ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}{Math.abs(cambio).toFixed(0)}%</span>
        )}
        <span className="min-w-0">{nota}</span>
      </p>
    </div>
  );
}

function Grande({ titulo, valor, nota, color }: { titulo: string; valor: number; nota: string; color?: string }) {
  return (
    <div className="rounded-3xl bg-hoja p-6 ring-1 ring-linea">
      <p className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[.14em] text-grafito">{color && <i className="size-2.5 rounded-full" style={{ background: color }} />}{titulo}</p>
      <p className={cx("mt-2 text-3xl font-semibold tracking-tight tabular-nums xl:text-[34px]", valor < 0 && "text-rojo")}>{dinero(valor)}</p>
      <p className="mt-1 text-xs text-grafito">{nota}</p>
    </div>
  );
}

function Barra({ alto, color, texto }: { alto: number; color: string; texto: string }) {
  return (
    <div className="flex h-full w-full max-w-10 flex-col items-center justify-end gap-1">
      <span className="text-[10px] tabular-nums text-grafito">{alto > 0 ? texto : ""}</span>
      <div className="w-full rounded-t-md transition-[height] duration-500" style={{ height: `${Math.max(alto > 0 ? 2 : 0, alto * 84)}%`, background: color }} />
    </div>
  );
}

function Linea({ k, v, extra }: { k: string; v: number; extra?: string }) {
  return <div className="flex justify-between gap-3 py-2.5"><dt className="text-grafito">{k}</dt><dd className="font-medium tabular-nums">{dinero(v)}{extra ? ` / ${extra}` : ""}</dd></div>;
}

function Tasas({ datos }: { datos: [string, number][] }) {
  const total = datos.reduce((s, [, v]) => s + Math.max(0, v), 0) || 1;
  return (
    <ul className="grid gap-2 text-sm">
      {datos.map(([k, v]) => (
        <li key={k} className={cx("grid grid-cols-[7.5rem_minmax(0,1fr)_7rem] items-center gap-3", v <= 0 && "opacity-45")}>
          <span>{k}</span>
          <span className="h-2 overflow-hidden rounded-full bg-tinta/[.07]"><i className="block h-full rounded-full bg-acento" style={{ width: `${(Math.max(0, v) / total) * 100}%` }} /></span>
          <span className="text-right tabular-nums">{dinero(v)}</span>
        </li>
      ))}
    </ul>
  );
}

function Ranking({ titulo, datos, color }: { titulo: string; datos: { rfc: string; nombre: string; total: number; n: number }[]; color: string }) {
  const max = Math.max(1, ...datos.map((d) => d.total));
  return (
    <Panel titulo={titulo}>
      {!datos.length && <p className="text-sm text-grafito">Sin datos en este periodo.</p>}
      <ul className="grid gap-3">
        {datos.map((d) => (
          <li key={d.rfc}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate" title={d.nombre || d.rfc}>{d.nombre || d.rfc} <span className="text-xs text-grafito">· {d.n}</span></span>
              <b className="shrink-0 tabular-nums">{dinero(d.total)}</b>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-tinta/[.07]"><i className="block h-full rounded-full" style={{ width: `${(d.total / max) * 100}%`, background: color }} /></div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
