"use client";
/**
 * Gastos: los CFDI RECIBIDOS clasificados en deducibles / no deducibles / por revisar / personales según el régimen y la actividad de la
 * constancia. La sugerencia nunca es definitiva: tú la confirmas o la cambias y Timbra aprende de eso (backend services/deducibles.py).
 * Orientación, no asesoría: confirma con tu contador.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Brain, Check, ChevronDown, Info, Undo2, X } from "lucide-react";
import { api } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, fecha } from "@/lib/format";
import type { Emisor } from "@/lib/types";
import { Badge, Button, Input, Modal, Tabs, cx } from "@/components/ui";
import { TarjetaConstancia, type Constancia, type Diferencia } from "@/components/constancia";

type Grupo = "deducible" | "no_deducible" | "revisar" | "personal";
type Motivo = { regla: string; texto: string; peso: string };
type Fila = {
  uuid: string; fecha: string; serie: string; folio: string; proveedor: string; rfc: string; total: number; iva: number; moneda: string;
  uso: string; forma: string; metodo: string; estatus: string; descripcion: string; sugerencia: Grupo; porcentaje_sug: number | null;
  motivos: Motivo[]; efecto: string; decision: Grupo | null; porcentaje: number | null; nota: string | null; final: Grupo;
};
type Respuesta = {
  filas: Fila[]; coinciden: number; totales: Record<Grupo, { n: number; total: number; iva: number }>;
  constancia: { rfc: string; emitida_el: string | null; regimenes: string[]; actividades: string[] } | null; regimenes: string[];
  solo_iva: boolean; permitido: boolean; lista_69b: boolean;
};
type Aprendido = { id: number; tipo: "rfc" | "clave"; valor: string; si: number; no: number; manda: Grupo | null };

const GRUPOS: { id: Grupo; texto: string; ayuda: string }[] = [
  { id: "revisar", texto: "Por revisar", ayuda: "Timbra no está seguro: tú decides" },
  { id: "deducible", texto: "Deducibles", ayuda: "Gastos del negocio" },
  { id: "no_deducible", texto: "No deducibles", ayuda: "No se pueden restar" },
  { id: "personal", texto: "Personales", ayuda: "Deducciones de la anual" },
];
const TONO: Record<Grupo, "sello" | "rojo" | "alerta" | "cobalto"> = { deducible: "sello", no_deducible: "rojo", revisar: "alerta", personal: "cobalto" };
const ETIQUETA: Record<Grupo, string> = { deducible: "Deducible", no_deducible: "No deducible", revisar: "Por revisar", personal: "Personal" };

const hoy = new Date();
const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const PERIODOS = [
  { id: "mes", texto: "Este mes", rango: () => [ymd(new Date(hoy.getFullYear(), hoy.getMonth(), 1)), ymd(new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0))] },
  { id: "anterior", texto: "Mes anterior", rango: () => [ymd(new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1)), ymd(new Date(hoy.getFullYear(), hoy.getMonth(), 0))] },
  { id: "anio", texto: "Este año", rango: () => [`${hoy.getFullYear()}-01-01`, `${hoy.getFullYear()}-12-31`] },
  { id: "pasado", texto: "Año pasado", rango: () => [`${hoy.getFullYear() - 1}-01-01`, `${hoy.getFullYear() - 1}-12-31`] },
  { id: "todo", texto: "Todo", rango: () => ["", ""] },
] as const;

export function Gastos({ emisor, version }: { emisor: Emisor; version: number }) {
  const [periodo, setPeriodo] = useState<(typeof PERIODOS)[number]["id"]>("anio");
  const [grupo, setGrupo] = useState<Grupo>("revisar");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [abierta, setAbierta] = useState<string | null>(null);
  const [aprender, setAprender] = useState(true);
  const [aprendido, setAprendido] = useState(false);
  const [tick, setTick] = useState(0);
  const [elegido, setElegido] = useState(false);  // ya se escogió la pestaña inicial
  const [desde, hasta] = useMemo(() => PERIODOS.find((p) => p.id === periodo)!.rango(), [periodo]);

  const { data: d, isLoading } = useSWR<Respuesta>(["deducibles", emisor.id, desde, hasta, grupo, q, version, tick],
    () => api<Respuesta>(`/deducibles?emisor_id=${emisor.id}&desde=${desde}&hasta=${hasta}&grupo=${grupo}&q=${encodeURIComponent(q)}&limite=300`), { keepPreviousData: true });
  const { data: csf, mutate: mutCsf } = useSWR<{ constancia: Constancia | null; diferencias?: Diferencia[]; avisos?: string[] }>(["constancia", emisor.id], () => api(`/constancia/${emisor.id}`));
  const refrescar = useCallback(() => { setTick((t) => t + 1); setSel(new Set()); }, []);

  useEffect(() => { setSel(new Set()); setElegido(false); }, [emisor.id, periodo]);
  // Empieza en lo que pide tu atención: «Por revisar» si hay algo; si no, «Deducibles»
  useEffect(() => {
    if (!d || elegido) return;
    setElegido(true);
    if (!d.totales.revisar.n && grupo === "revisar") setGrupo(d.totales.deducible.n ? "deducible" : "no_deducible");
  }, [d, elegido, grupo]);

  const filas = d?.filas ?? [];
  const marcar = useCallback(async (decision: Grupo, uuids: string[], porcentajes?: Record<string, number | null>) => {
    if (!uuids.length || (decision !== "deducible" && decision !== "no_deducible")) return;
    try {
      // los restaurantes llevan su 8.5%: se manda por separado de lo demás
      const conPct = uuids.filter((u) => decision === "deducible" && porcentajes?.[u]);
      const sinPct = uuids.filter((u) => !conPct.includes(u));
      if (sinPct.length) await api("/deducibles/decidir", { method: "POST", json: { emisor_id: emisor.id, uuids: sinPct, decision, aprender } });
      for (const p of new Set(conPct.map((u) => porcentajes![u]))) {
        await api("/deducibles/decidir", { method: "POST", json: { emisor_id: emisor.id, uuids: conPct.filter((u) => porcentajes![u] === p), decision, porcentaje: p, aprender } });
      }
      toast.success(`${uuids.length} ${uuids.length === 1 ? "gasto" : "gastos"} → ${ETIQUETA[decision].toLowerCase()}${aprender ? ". Timbra lo recuerda." : "."}`);
      refrescar();
    } catch (e) { mostrarError(e); }
  }, [emisor.id, aprender, refrescar]);
  const deshacer = useCallback(async (uuids: string[]) => {
    try { await api("/deducibles/deshacer", { method: "POST", json: { emisor_id: emisor.id, uuids } }); toast.success("Vuelve a valer la sugerencia"); refrescar(); }
    catch (e) { mostrarError(e); }
  }, [emisor.id, refrescar]);
  const confirmarSugeridas = async () => {
    const elegidas = filas.filter((f) => sel.has(f.uuid) && !f.decision);
    const pct = Object.fromEntries(elegidas.map((f) => [f.uuid, f.porcentaje_sug]));
    await marcar("deducible", elegidas.filter((f) => f.sugerencia === "deducible").map((f) => f.uuid), pct);
    await marcar("no_deducible", elegidas.filter((f) => f.sugerencia === "no_deducible").map((f) => f.uuid));
  };

  // Sin mouse: D deducible · N no deducible · U volver a la sugerencia (sobre lo seleccionado)
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.ctrlKey || e.metaKey || e.altKey || !sel.size || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || document.querySelector("[role=dialog]")) return;
      const uu = [...sel], pct = Object.fromEntries(filas.map((f) => [f.uuid, f.porcentaje_sug]));
      if (e.key === "d") { e.preventDefault(); marcar("deducible", uu, pct); }
      else if (e.key === "n") { e.preventDefault(); marcar("no_deducible", uu); }
      else if (e.key === "u") { e.preventDefault(); deshacer(uu); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [sel, filas, marcar, deshacer]);

  const todas = filas.length > 0 && filas.every((f) => sel.has(f.uuid));
  const t = d?.totales;
  const ivaAcreditable = t?.deducible.iva ?? 0;

  return (
    <div className="grid gap-6">
      <TarjetaConstancia emisorId={emisor.id} constancia={csf?.constancia ?? null} diferencias={csf?.diferencias ?? []} avisos={csf?.avisos ?? []}
        alCambiar={() => { mutCsf(); refrescar(); }} />

      {d && !d.permitido && (
        <p className="flex gap-2.5 rounded-xl bg-alerta-suave px-4 py-3 text-sm text-alerta ring-1 ring-alerta/25"><Info className="mt-0.5 size-4 shrink-0" />
          Tus regímenes vigentes ({d.regimenes.join(", ")}) no tienen una actividad de la que se resten gastos: aquí sólo cuentan las deducciones personales.</p>
      )}
      {d?.solo_iva && (
        <p className="flex gap-2.5 rounded-xl bg-cobalto-suave px-4 py-3 text-sm text-cobalto ring-1 ring-cobalto/20"><Info className="mt-0.5 size-4 shrink-0" />
          RESICO persona física: el ISR se paga sobre tus ingresos y no admite deducciones. Los gastos «deducibles» de abajo te sirven para <b>acreditar el IVA</b>.</p>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {GRUPOS.map((g) => (
          <button key={g.id} onClick={() => setGrupo(g.id)} aria-pressed={grupo === g.id}
            className={cx("rounded-2xl bg-hoja p-4 text-left ring-1 transition-shadow", grupo === g.id ? "ring-2 ring-acento" : "ring-linea hover:ring-grafito/40")}>
            <p className="text-[11px] font-medium uppercase tracking-[.08em] text-grafito">{g.texto}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{dinero(t?.[g.id].total ?? 0)}</p>
            <p className="text-xs text-grafito">{t?.[g.id].n ?? 0} {t?.[g.id].n === 1 ? "comprobante" : "comprobantes"}{g.id === "deducible" && ivaAcreditable ? ` · IVA ${dinero(ivaAcreditable)}` : ""}</p>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={periodo} onChange={setPeriodo} items={PERIODOS.map((p) => ({ id: p.id, label: p.texto }))} />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar proveedor, RFC o folio" className="ml-auto h-9 w-full max-w-64" />
      </div>

      <section className="overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea">
        <div className="flex flex-wrap items-center gap-2 border-b border-linea px-4 py-3">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={todas} onChange={() => setSel(todas ? new Set() : new Set(filas.map((f) => f.uuid)))} aria-label="Seleccionar todos" />
            {sel.size ? `${sel.size} elegidos` : GRUPOS.find((g) => g.id === grupo)!.ayuda}</label>
          {sel.size > 0 && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secundario" onClick={() => marcar("deducible", [...sel], Object.fromEntries(filas.map((f) => [f.uuid, f.porcentaje_sug])))}><Check className="size-4 text-sello" /> Deducible <kbd className="text-[10px] opacity-60">D</kbd></Button>
              <Button size="sm" variant="secundario" onClick={() => marcar("no_deducible", [...sel])}><X className="size-4 text-rojo" /> No deducible <kbd className="text-[10px] opacity-60">N</kbd></Button>
              <Button size="sm" variant="fantasma" onClick={confirmarSugeridas}>Confirmar como sugerido</Button>
              <Button size="sm" variant="fantasma" onClick={() => deshacer([...sel])}><Undo2 className="size-4" /> Volver a la sugerencia <kbd className="text-[10px] opacity-60">U</kbd></Button>
            </div>
          )}
          <div className="ml-auto flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-grafito" title="Si la apagas, esta decisión vale sólo para ese comprobante">
              <input type="checkbox" checked={aprender} onChange={(e) => setAprender(e.target.checked)} /> Que Timbra aprenda
            </label>
            <Button size="sm" variant="fantasma" onClick={() => setAprendido(true)}><Brain className="size-4" /> Lo que aprendió</Button>
          </div>
        </div>

        {isLoading && !d ? <p className="px-5 py-12 text-center text-grafito">Clasificando…</p>
          : !filas.length ? <p className="px-5 py-12 text-center text-grafito">{d?.totales && Object.values(d.totales).every((x) => !x.n) ? "No hay comprobantes recibidos en este periodo. Descarga del SAT en la otra pestaña." : "Nada en este grupo."}</p>
          : filas.map((f) => (
            <div key={f.uuid} className={cx("border-b border-linea last:border-0", sel.has(f.uuid) && "bg-acento-suave/40")}>
              <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 px-4 py-3 @container sm:grid-cols-[auto_5rem_1fr_7rem_auto_auto]">
                <input type="checkbox" checked={sel.has(f.uuid)} aria-label={`Elegir ${f.proveedor}`}
                  onChange={() => setSel((s) => { const n = new Set(s); n.has(f.uuid) ? n.delete(f.uuid) : n.add(f.uuid); return n; })} />
                <span className="hidden text-sm tabular-nums text-grafito sm:block">{fecha(f.fecha)}</span>
                <div className="min-w-0">
                  <p className="truncate font-medium">{f.proveedor || f.rfc}</p>
                  <p className="truncate text-xs text-grafito"><span className="font-mono">{f.rfc}</span>{f.descripcion ? ` · ${f.descripcion}` : ""}</p>
                </div>
                <span className="text-right text-sm font-semibold tabular-nums">{dinero(f.total, f.moneda || "MXN")}</span>
                <button onClick={() => setAbierta(abierta === f.uuid ? null : f.uuid)} aria-expanded={abierta === f.uuid} className="flex items-center gap-1.5 justify-self-end" title="¿Por qué?">
                  <Badge punto tono={TONO[f.final]}>{ETIQUETA[f.final]}{f.final === "deducible" && (f.porcentaje ?? f.porcentaje_sug) ? ` ${f.porcentaje ?? f.porcentaje_sug}%` : ""}</Badge>
                  <span className="text-[11px] text-grafito">{f.decision ? "confirmado" : "sugerido"}</span>
                  <ChevronDown className={cx("size-3.5 text-grafito transition-transform", abierta === f.uuid && "rotate-180")} />
                </button>
                <div className="flex gap-1 justify-self-end">
                  <button title="Marcar deducible" aria-label="Marcar deducible" onClick={() => marcar("deducible", [f.uuid], { [f.uuid]: f.porcentaje_sug })}
                    className={cx("grid size-8 place-items-center rounded-lg ring-1 ring-linea hover:bg-sello-suave hover:text-sello", f.decision === "deducible" && "bg-sello-suave text-sello")}><Check className="size-4" /></button>
                  <button title="Marcar no deducible" aria-label="Marcar no deducible" onClick={() => marcar("no_deducible", [f.uuid])}
                    className={cx("grid size-8 place-items-center rounded-lg ring-1 ring-linea hover:bg-rojo-suave hover:text-rojo", f.decision === "no_deducible" && "bg-rojo-suave text-rojo")}><X className="size-4" /></button>
                </div>
              </div>
              {abierta === f.uuid && (
                <div className="grid gap-2 bg-papel/60 px-5 py-3 text-sm">
                  {f.decision && (
                    <p className="flex flex-wrap items-center gap-2"><b>Tú decidiste: {ETIQUETA[f.decision].toLowerCase()}</b>{f.nota ? <span className="text-grafito">«{f.nota}»</span> : null}
                      <button className="text-cobalto hover:underline" onClick={() => deshacer([f.uuid])}>Volver a la sugerencia</button></p>
                  )}
                  <p className="text-xs font-medium uppercase tracking-[.08em] text-grafito">{f.decision ? `Timbra sugería: ${ETIQUETA[f.sugerencia].toLowerCase()}` : "Por qué lo sugiere"}</p>
                  <ul className="grid gap-1">{f.motivos.map((m, i) => (
                    <li key={i} className={cx("flex gap-2", m.peso === "bloqueo" ? "text-rojo" : m.peso === "duda" ? "text-alerta" : m.peso === "aprendido" ? "text-cobalto" : "text-grafito")}>
                      <span aria-hidden>•</span><span>{m.texto}</span></li>))}
                    {!f.motivos.length && <li className="text-grafito">Sin observaciones.</li>}
                  </ul>
                  <p className="text-xs text-grafito">Uso {f.uso || "—"} · forma de pago {f.forma || "—"} · {f.metodo || "—"} · IVA {dinero(f.iva)}{f.estatus === "Cancelado" ? " · cancelado" : ""}</p>
                </div>
              )}
            </div>
          ))}
        {d && d.coinciden > filas.length && <p className="px-5 py-3 text-center text-sm text-grafito">Se muestran {filas.length} de {d.coinciden}. Afina con el periodo o la búsqueda.</p>}
      </section>

      <p className="text-xs leading-relaxed text-grafito">
        Es orientación, no asesoría fiscal: la sugerencia usa tu régimen y tus actividades de la constancia, las reglas generales de la LISR y lo que tú has decidido antes.
        Confírmala con tu contador.{d && !d.lista_69b ? " (La lista 69-B del SAT aún no se consulta; se intenta en segundo plano.)" : ""}
      </p>
      <ModalAprendido emisorId={emisor.id} abierto={aprendido} cerrar={() => setAprendido(false)} alCambiar={refrescar} />
    </div>
  );
}

function ModalAprendido({ emisorId, abierto, cerrar, alCambiar }: { emisorId: number; abierto: boolean; cerrar: () => void; alCambiar: () => void }) {
  const { data, mutate } = useSWR<Aprendido[]>(abierto ? ["aprendido", emisorId] : null, () => api<Aprendido[]>(`/deducibles/aprendido?emisor_id=${emisorId}`));
  const olvidar = async (id: number) => {
    try { await api(`/deducibles/aprendido/${id}`, { method: "DELETE" }); mutate(); alCambiar(); } catch (e) { mostrarError(e); }
  };
  return (
    <Modal open={abierto} onClose={cerrar} title="Lo que Timbra aprendió de tus decisiones">
      <p className="mb-4 text-sm text-grafito">Cada vez que decides, Timbra recuerda al proveedor y el tipo de producto. Con eso sugiere los siguientes. Si algo ya no aplica, olvídalo.</p>
      {!data?.length ? <p className="py-8 text-center text-grafito">Todavía no ha aprendido nada. Marca algunos gastos como deducibles o no deducibles.</p> : (
        <ul className="divide-y divide-linea rounded-xl ring-1 ring-linea">
          {data.map((p) => (
            <li key={p.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              <span className="w-24 shrink-0 text-xs uppercase tracking-wide text-grafito">{p.tipo === "rfc" ? "Proveedor" : "Producto"}</span>
              <span className="min-w-0 flex-1 truncate font-mono">{p.tipo === "clave" ? `${p.valor}…` : p.valor}</span>
              <span className="tabular-nums text-grafito">{p.si} sí · {p.no} no</span>
              {p.manda ? <Badge tono={TONO[p.manda]}>{ETIQUETA[p.manda]}</Badge> : <Badge>sin consenso</Badge>}
              <button onClick={() => olvidar(p.id)} className="text-cobalto hover:underline">Olvidar</button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
