"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, Ban, BookmarkPlus, Check, Copy, Info, Search } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { OpcionesImpuestos } from "@/components/impuestos";
import { Badge, Button, Field, Input, Kbd, Modal, PageHeader, Select, Tabs, Vacio, cx } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { PRESETS_IMPUESTOS, presetPorDefecto } from "@/lib/format";
import type { ClaveDetalle, ClaveItem, ConfigFacturar, Impuesto, UnidadComun } from "@/lib/types";

export default function Pagina() {
  return <Suspense><Claves /></Suspense>;
}

function useDebounce<T>(v: T, ms: number) {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

function Claves() {
  const { emisor } = useEmisor();
  const params = useSearchParams();
  const [vista, setVista] = useState<"claves" | "unidades">("claves");
  const [q, setQ] = useState(params.get("q") ?? "");
  const dq = useDebounce(q.trim(), 140);
  const [sel, setSel] = useState<string | null>(params.get("clave"));
  const [act, setAct] = useState(0);
  const entrada = useRef<HTMLInputElement>(null);
  const emq = emisor ? `&emisor_id=${emisor.id}` : "";

  const { data: res = [], isLoading } = useSWR<ClaveItem[]>(vista === "claves" && dq.length >= 2 ? `/claves/buscar?q=${encodeURIComponent(dq)}&limit=40${emq}` : null, fetcher, { keepPreviousData: true });
  const { data: freq = [] } = useSWR<ClaveItem[]>(emisor ? `/claves/frecuentes?emisor_id=${emisor.id}` : null, fetcher);
  const { data: det, mutate: mDet } = useSWR<ClaveDetalle>(sel ? `/claves/${sel}?${emq.slice(1)}` : null, fetcher);
  const { data: cfg, mutate: mCfg } = useSWR<ConfigFacturar>(emisor ? `/emisores/${emisor.id}/config-facturar` : null, fetcher);
  const [agregar, setAgregar] = useState<ClaveDetalle | null>(null);

  useEffect(() => { setAct(0); }, [dq]);
  useEffect(() => { entrada.current?.focus(); }, [vista]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && !document.querySelector("[role=dialog]")) { e.preventDefault(); entrada.current?.focus(); } };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  const copiar = (c: string) => { navigator.clipboard.writeText(c); toast.success(`Clave ${c} copiada`); };
  const bloqueadas = cfg?.claves_bloqueadas ?? [];
  const alternarBloqueo = async (clave: string) => {
    if (!emisor) return;
    const nuevas = bloqueadas.includes(clave) ? bloqueadas.filter((x) => x !== clave) : [...bloqueadas, clave];
    try {
      await api(`/emisores/${emisor.id}/config-facturar`, { method: "PUT", json: { claves_bloqueadas: nuevas } });
      toast.success(nuevas.includes(clave) ? `${clave} bloqueada en ${emisor.rfc}: no se podrá timbrar con ella` : `${clave} desbloqueada`);
      mCfg(); mDet();
    } catch (e) { mostrarError(e); }
  };

  return (
    <>
      <PageHeader title="Claves SAT" />
      <p className="-mt-3 mb-5 max-w-3xl text-sm text-grafito">
        Busca por lo que haces o vendes (“consulta médica”, “renta local”, “vitaminas”) o por clave. Antes de facturar ves qué es, qué avisos tiene
        y la guardas en tu catálogo.
      </p>
      <Tabs value={vista} onChange={setVista} items={[{ id: "claves", label: "Productos y servicios" }, { id: "unidades", label: "Unidades" }]} />

      {vista === "unidades" ? <Unidades /> : (
        <div className="grid gap-6 @container lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
          <div className="min-w-0">
            <div className="relative mb-4">
              <Search className="pointer-events-none absolute left-4 top-4 size-5 text-grafito" />
              <Input ref={entrada} value={q} onChange={(e) => setQ(e.target.value)} placeholder="¿Qué vendes o qué servicio das?  ( / )"
                className="h-14 pl-12 text-base" aria-label="Buscar clave" autoComplete="off"
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") { e.preventDefault(); setAct((a) => Math.min(a + 1, res.length - 1)); }
                  if (e.key === "ArrowUp") { e.preventDefault(); setAct((a) => Math.max(a - 1, 0)); }
                  if (e.key === "Enter" && res[act]) { e.preventDefault(); setSel(res[act].clave); }
                }} />
            </div>

            {dq.length < 2 ? (
              <div className="grid gap-6">
                {freq.length > 0 && (
                  <section>
                    <h2 className="mb-2 text-sm font-medium text-grafito">Las que más usa {emisor?.rfc}</h2>
                    <div className="flex flex-wrap gap-2">
                      {freq.map((f) => (
                        <button key={f.clave} onClick={() => setSel(f.clave)} className="rounded-xl bg-hoja px-3 py-2 text-left text-sm ring-1 ring-linea transition hover:ring-tinta/40">
                          <span className="font-mono text-xs">{f.clave}</span> <span className="block max-w-56 truncate text-grafito">{f.descripcion}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}
                <section className="rounded-2xl bg-hoja p-5 ring-1 ring-linea">
                  <h2 className="mb-2 font-semibold">Cómo encontrar la clave correcta</h2>
                  <ul className="grid gap-1.5 text-sm text-grafito">
                    <li>• Escribe lo que haces, no el nombre técnico: <b className="text-tinta">dentista</b>, <b className="text-tinta">contador</b>, <b className="text-tinta">flete</b>, <b className="text-tinta">pagina web</b>.</li>
                    <li>• Si ves una <b className="text-tinta">Clase</b> (termina en 00) y dentro hay claves más específicas, usa la más específica.</li>
                    <li>• Los avisos ⚠ te dicen cuándo conviene revisar con tu contador (IVA, retenciones, medicamentos).</li>
                    <li>• Para un servicio la unidad suele ser <b className="text-tinta">E48</b>; para mercancía, <b className="text-tinta">H87</b> (pestaña Unidades).</li>
                  </ul>
                </section>
              </div>
            ) : !res.length && !isLoading ? (
              <Vacio titulo={`Nada para “${dq}”`}>Prueba con otra palabra más general (“médico” en vez de “pediatra”).</Vacio>
            ) : (
              <ul className="overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea" role="listbox">
                {res.map((r, i) => (
                  <li key={r.clave} role="option" aria-selected={sel === r.clave}>
                    <button onClick={() => setSel(r.clave)} onMouseEnter={() => setAct(i)}
                      className={cx("flex w-full items-start gap-3 border-b border-linea px-4 py-3 text-left last:border-0 hover:bg-papel", (i === act || sel === r.clave) && "bg-papel", sel === r.clave && "ring-1 ring-inset ring-tinta/30")}>
                      <span className="mt-0.5 w-20 shrink-0 font-mono text-sm font-semibold tabular-nums">{r.clave}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block">{r.descripcion}</span>
                        <span className="mt-1 flex flex-wrap gap-1.5">
                          {r.tipo && <Badge>{r.tipo}</Badge>}
                          {r.nivel === "clase" && <Badge tono="cobalto">Clase</Badge>}
                          {r.parcial && <Badge tono="alerta">Parecida</Badge>}
                          {r.en_catalogo && <Badge tono="sello">En tu catálogo</Badge>}
                          {r.bloqueada && <Badge tono="rojo">Bloqueada</Badge>}
                          {!r.bloqueada && r.alertas.length > 0 && <Badge tono="alerta">Revisar</Badge>}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Detalle */}
          <aside className="min-w-0 lg:sticky lg:top-6 lg:self-start">
            {!sel || !det ? (
              <div className="hidden rounded-2xl border border-dashed border-linea p-8 text-center text-sm text-grafito lg:block">Elige una clave para ver el detalle.</div>
            ) : (
              <div className="grid gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea animate-entrar">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-3xl font-semibold tracking-tight tabular-nums">{det.clave}</p>
                    <p className="mt-1">{det.descripcion}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">{det.tipo && <Badge>{det.tipo}</Badge>}{det.nivel === "clase" && <Badge tono="cobalto">Clase</Badge>}{det.bloqueada && <Badge tono="rojo">Bloqueada en {emisor?.rfc}</Badge>}</div>
                  </div>
                  <Button size="sm" variant="fantasma" onClick={() => copiar(det.clave)} aria-label="Copiar clave"><Copy className="size-4" /></Button>
                </div>

                {[...det.alertas.filter((a) => a.nivel !== "info"), ...det.notas.filter((n) => !det.alertas.some((a) => a.texto === n.texto))].map((n, i) => (
                  <p key={i} className={cx("flex gap-2 rounded-lg px-3 py-2 text-sm", n.nivel === "bloqueo" ? "bg-rojo-suave text-rojo" : n.nivel === "alerta" ? "bg-alerta-suave text-alerta" : "bg-tinta/5 text-grafito")}>
                    {n.nivel === "bloqueo" ? <Ban className="mt-0.5 size-4 shrink-0" /> : n.nivel === "alerta" ? <AlertTriangle className="mt-0.5 size-4 shrink-0" /> : <Info className="mt-0.5 size-4 shrink-0" />} {n.texto}
                  </p>
                ))}

                {det.productos && det.productos.length > 0 && (
                  <div className="rounded-lg bg-sello-suave px-3 py-2 text-sm text-sello"><p className="flex items-center gap-1.5 font-medium"><Check className="size-4" /> Ya está en tu catálogo</p>
                    <ul className="mt-1 text-xs">{det.productos.map((p) => <li key={p.id}>{p.descripcion}</li>)}</ul></div>
                )}

                <div className="flex flex-wrap gap-2">
                  <Button variant="primario" onClick={() => setAgregar(det)}><BookmarkPlus className="size-4" /> Agregar a mi catálogo</Button>
                  <Button onClick={() => alternarBloqueo(det.clave)}><Ban className="size-4" /> {bloqueadas.includes(det.clave) ? "Desbloquear" : "Bloquear en este emisor"}</Button>
                </div>

                {det.jerarquia.length > 0 && (
                  <div><p className="mb-1 text-xs font-medium uppercase tracking-[.06em] text-grafito">Clase</p>
                    {det.jerarquia.map((j) => <button key={j.clave} onClick={() => setSel(j.clave)} className="block text-left text-sm hover:underline"><span className="font-mono">{j.clave}</span> {j.descripcion}</button>)}</div>
                )}
                {det.hermanas.length > 0 && (
                  <div><p className="mb-1 text-xs font-medium uppercase tracking-[.06em] text-grafito">Claves hermanas ({det.hermanas.length})</p>
                    <ul className="grid max-h-56 gap-0.5 overflow-auto text-sm">{det.hermanas.map((h) => <li key={h.clave}><button onClick={() => setSel(h.clave)} className="w-full text-left hover:underline"><span className="font-mono text-xs">{h.clave}</span> {h.descripcion}</button></li>)}</ul></div>
                )}
                {det.relacionadas.length > 0 && (
                  <div><p className="mb-1 text-xs font-medium uppercase tracking-[.06em] text-grafito">Otras clases de la misma familia</p>
                    <ul className="grid max-h-40 gap-0.5 overflow-auto text-sm">{det.relacionadas.map((h) => <li key={h.clave}><button onClick={() => { setSel(h.clave); }} className="w-full text-left hover:underline"><span className="font-mono text-xs">{h.clave}</span> {h.descripcion}</button></li>)}</ul></div>
                )}
              </div>
            )}
          </aside>
        </div>
      )}
      <AgregarCatalogo clave={agregar} cerrar={() => setAgregar(null)} ok={() => { setAgregar(null); mDet(); }} />
    </>
  );
}

function AgregarCatalogo({ clave, cerrar, ok }: { clave: ClaveDetalle | null; cerrar: () => void; ok: () => void }) {
  const { emisor } = useEmisor();
  const [f, setF] = useState({ descripcion: "", unidad: "E48", precio: "", preset: "IVA 16%" });
  const [guardando, setGuardando] = useState(false);
  useEffect(() => {
    if (!clave) return;
    setF({ descripcion: clave.descripcion, unidad: clave.tipo === "Servicio" ? "E48" : "H87", precio: "", preset: presetPorDefecto(emisor?.region_fronteriza) });
  }, [clave, emisor?.region_fronteriza]);
  if (!clave || !emisor) return null;
  const guardar = async () => {
    setGuardando(true);
    try {
      const imps = PRESETS_IMPUESTOS[f.preset as keyof typeof PRESETS_IMPUESTOS] as readonly Impuesto[];
      await api("/productos", { method: "POST", json: { emisor_id: emisor.id, descripcion: f.descripcion, clave_prod_serv: clave.clave, clave_unidad: f.unidad.toUpperCase(),
        precio: f.precio || "0", objeto_imp: imps.length ? "02" : "01", impuestos: imps } });
      toast.success("Agregada a tu catálogo");
      ok();
    } catch (e) { mostrarError(e); } finally { setGuardando(false); }
  };
  return (
    <Modal open={!!clave} onClose={cerrar} title={`Agregar ${clave.clave} a mi catálogo`}
      footer={<><Button onClick={cerrar}>Cancelar</Button><Button variant="primario" onClick={guardar} loading={guardando}>Guardar</Button></>}>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); guardar(); }}>
        <Field label="Cómo lo llamas tú" className="sm:col-span-2" hint="Es el texto que saldrá en la factura; edítalo con tus palabras."><Input autoFocus value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} /></Field>
        <Field label="Unidad" hint="E48 servicio · H87 pieza"><Input value={f.unidad} maxLength={3} onChange={(e) => setF({ ...f, unidad: e.target.value.toUpperCase() })} /></Field>
        <Field label="Precio sin IVA (opcional)"><Input inputMode="decimal" value={f.precio} onChange={(e) => setF({ ...f, precio: e.target.value })} /></Field>
        <Field label="Impuestos" className="sm:col-span-2">
          <Select value={f.preset} onChange={(e) => setF({ ...f, preset: e.target.value })}><OpcionesImpuestos frontera={!!emisor.region_fronteriza} /></Select>
        </Field>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

function Unidades() {
  const [q, setQ] = useState("");
  const dq = useDebounce(q.trim(), 140);
  const { data: comunes = [] } = useSWR<UnidadComun[]>("/claves/unidades", fetcher);
  const { data: res = [] } = useSWR<ClaveItem[]>(dq ? `/claves/buscar?tipo=unidad&q=${encodeURIComponent(dq)}&limit=30` : null, fetcher);
  const copiar = useCallback((c: string) => { navigator.clipboard.writeText(c); toast.success(`Unidad ${c} copiada`); }, []);
  return (
    <div className="grid gap-5">
      <div className="relative max-w-xl">
        <Search className="pointer-events-none absolute left-4 top-3.5 size-4 text-grafito" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Busca otra unidad: kilo, litro, hora, caja…" className="pl-11" aria-label="Buscar unidad" />
      </div>
      {dq ? (
        <ul className="overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea">
          {res.map((u) => (
            <li key={u.clave}><button onClick={() => copiar(u.clave)} className="flex w-full items-center gap-3 border-b border-linea px-4 py-2.5 text-left last:border-0 hover:bg-papel">
              <span className="w-14 font-mono font-semibold">{u.clave}</span><span>{u.descripcion}</span><Copy className="ml-auto size-4 text-grafito" /></button></li>
          ))}
          {!res.length && <li className="px-4 py-8 text-center text-sm text-grafito">Sin resultados.</li>}
        </ul>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {comunes.map((u) => (
            <button key={u.clave} onClick={() => copiar(u.clave)} className="flex items-start gap-3 rounded-xl bg-hoja p-3.5 text-left ring-1 ring-linea transition hover:ring-tinta/40">
              <span className="w-12 shrink-0 font-mono text-lg font-semibold">{u.clave}</span>
              <span className="min-w-0"><span className="block font-medium">{u.descripcion}</span><span className="block text-sm text-grafito">{u.cuando}</span></span>
            </button>
          ))}
        </div>
      )}
      <p className="text-xs text-grafito">Toca una unidad para copiar su clave. <Kbd>/</Kbd> enfoca la búsqueda en la otra pestaña.</p>
    </div>
  );
}
