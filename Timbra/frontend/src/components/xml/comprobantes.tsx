"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, ClipboardCopy, Download, FileArchive, FileSpreadsheet, FileText, Loader2, Search, Trash2, X } from "lucide-react";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero } from "@/lib/format";
import type { Emisor } from "@/lib/types";
import { CLASES, type FilaXml, type Filtros, type ListaXml, ORDEN_CLASES, type TrabajoXml, bajarConPost, blobDe, copiarTabla, guardar, nombreMes } from "@/lib/xml";
import { Button, Input, Menu, Select, cx, tabla } from "@/components/ui";

export function Letra({ clase, grande }: { clase: string; grande?: boolean }) {
  const c = CLASES[clase];
  return (
    <span title={c?.nombre} className={cx("grid shrink-0 place-items-center rounded-lg font-semibold text-white", grande ? "size-12 text-xl" : "size-7 text-xs")}
      style={{ background: c?.color ?? "#6B7686" }}>{clase || "?"}</span>
  );
}

export function Comprobantes({ emisor, version }: { emisor: Emisor; version: number }) {
  const [mes, setMes] = useState("");
  const [tipo, setTipo] = useState("");
  const [clase, setClase] = useState("");
  const [estatus, setEstatus] = useState("");  // todo, como en la tabla de siempre; los cancelados van marcados
  const [q, setQ] = useState("");
  const [buscar, setBuscar] = useState("");
  const [pagina, setPagina] = useState(1);
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [ver, setVer] = useState<number | null>(null);
  const [zip, setZip] = useState<number | null>(null);
  const [ocupado, setOcupado] = useState("");

  useEffect(() => { const t = setTimeout(() => setBuscar(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  useEffect(() => { setPagina(1); setMarcados(new Set()); }, [emisor.id, mes, tipo, clase, estatus, buscar]);
  useEffect(() => { setMes(""); setClase(""); setTipo(""); setQ(""); }, [emisor.id]);

  const url = `/xml/cfdi?emisor_id=${emisor.id}&mes=${mes}&tipo=${tipo}&clase=${clase}&estatus=${estatus}&q=${encodeURIComponent(buscar)}&pagina=${pagina}`;
  const { data, mutate, isLoading } = useSWR<ListaXml>(url, fetcher, { keepPreviousData: true });
  useEffect(() => { mutate(); }, [version, mutate]);

  const filtros: Filtros = useMemo(() => ({ emisor_id: emisor.id, mes, tipo, clase, estatus, q: buscar, ids: [...marcados] }), [emisor.id, mes, tipo, clase, estatus, buscar, marcados]);
  const filas = data?.filas ?? [];
  const cuantos = marcados.size || data?.total || 0;
  const paginas = Math.max(1, Math.ceil((data?.total ?? 0) / (data?.por_pagina ?? 100)));
  const hayAlgo = (data?.meses.length ?? 0) > 0;

  const copiar = async () => {
    setOcupado("copiar");
    try {
      const n = await copiarTabla(filtros);
      toast.success(`${n.toLocaleString("es-MX")} renglones copiados`, { description: "Pégalos en tu hoja con Ctrl+V. 65 columnas, en el orden de siempre." });
    } catch (e) { mostrarError(e); } finally { setOcupado(""); }
  };
  const excel = async () => {
    setOcupado("excel");
    try { await bajarConPost("/xml/excel", filtros, "CFDI.xlsx"); } catch (e) { mostrarError(e); } finally { setOcupado(""); }
  };
  const armarZip = async (incluir: string) => {
    try {
      const r = await api<{ id: number }>("/xml/zip", { method: "POST", json: { filtros, incluir } });
      setZip(r.id);
    } catch (e) { mostrarError(e); }
  };
  const borrar = async () => {
    if (!window.confirm(`Se van a quitar de Timbra ${cuantos.toLocaleString("es-MX")} comprobante(s) de lo que estás viendo.\n\nNo se toca nada en el SAT: los puedes volver a bajar o a leer de tu carpeta. ¿Continuar?`)) return;
    try {
      const r = await api<{ borrados: number }>("/xml/borrar", { method: "POST", json: filtros });
      toast.success(`${r.borrados} comprobantes quitados`);
      setMarcados(new Set());
      mutate();
    } catch (e) { mostrarError(e); }
  };
  const marcar = (id: number) => setMarcados((m) => { const n = new Set(m); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const todosMarcados = filas.length > 0 && filas.every((f) => marcados.has(f.id));

  if (!hayAlgo && !isLoading)
    return <p className="rounded-3xl bg-hoja px-6 py-12 text-center text-grafito ring-1 ring-linea">Aquí van a aparecer tus comprobantes en cuanto descargues del SAT o leas una carpeta.</p>;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Lo que tienes</h2>
          <p className="text-sm text-grafito tabular-nums">{(data?.total ?? 0).toLocaleString("es-MX")} comprobantes · {dinero(data?.suma ?? 0)}
            {!!data?.cancelados && estatus !== "Cancelado" && <button className="ml-2 text-rojo underline-offset-2 hover:underline" onClick={() => setEstatus(estatus === "" ? "Vigente" : "")}>{estatus === "" ? `incluye ${data.cancelados} cancelados · quitarlos` : `${data.cancelados} cancelados fuera · incluirlos`}</button>}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {marcados.size > 0 && <span className="text-sm text-cobalto">{marcados.size} marcados <button className="underline" onClick={() => setMarcados(new Set())}>quitar</button></span>}
          <Button variant="primario" onClick={copiar} loading={ocupado === "copiar"} disabled={!cuantos} title="Las 65 columnas del formato maestro, listas para pegar"><ClipboardCopy className="size-4" /> Copiar tabla</Button>
          <Button onClick={excel} loading={ocupado === "excel"} disabled={!cuantos}><FileSpreadsheet className="size-4" /> Excel</Button>
          <Menu label="Descargar PDF y XML" items={[
            { label: `PDF y XML (${cuantos})`, icon: <FileArchive className="size-4" />, onClick: () => armarZip("ambos") },
            { label: "Sólo PDF", icon: <FileText className="size-4" />, onClick: () => armarZip("pdf") },
            { label: "Sólo XML", icon: <Download className="size-4" />, onClick: () => armarZip("xml") },
            { label: "Quitar de Timbra lo que veo…", icon: <Trash2 className="size-4" />, onClick: borrar, peligro: true },
          ]} />
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button onClick={() => setClase("")} className={cx("rounded-full px-3.5 py-1.5 text-sm ring-1", !clase ? "bg-primario text-sobre-primario ring-primario" : "ring-linea hover:ring-grafito/40")}>Todo</button>
        {ORDEN_CLASES.filter((c) => data?.clases[c]).map((c) => (
          <button key={c} onClick={() => setClase(clase === c ? "" : c)}
            className={cx("flex items-center gap-2 rounded-full py-1 pl-1 pr-3.5 text-sm ring-1 transition-colors", clase === c ? "bg-tinta/[.06] ring-grafito/50" : "ring-linea hover:ring-grafito/40")}>
            <Letra clase={c} /> {CLASES[c].plural} <b className="tabular-nums">{data?.clases[c].n}</b>
          </button>
        ))}
      </div>
      <div className="mb-4 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
        <label className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-grafito" />
          <Input className="pl-9" placeholder="Nombre, RFC, folio, UUID o descripción" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <Select value={mes} onChange={(e) => setMes(e.target.value)} aria-label="Mes">
          <option value="">Todos los meses</option>
          {[...new Set((data?.meses ?? []).map((m) => m.mes.slice(0, 4)))].map((a) => <option key={a} value={a}>Todo {a}</option>)}
          {(data?.meses ?? []).map((m) => <option key={m.mes} value={m.mes}>{nombreMes(m.mes)} ({m.n})</option>)}
        </Select>
        <Select value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Emitidos o recibidos">
          <option value="">Emitidos y recibidos</option><option value="Emitido">Emitidos</option><option value="Recibido">Recibidos</option>
        </Select>
        <Select value={estatus} onChange={(e) => setEstatus(e.target.value)} aria-label="Estatus">
          <option value="">Vigentes y cancelados</option><option value="Vigente">Sólo vigentes</option><option value="Cancelado">Sólo cancelados</option>
        </Select>
      </div>

      <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
        <table className={tabla.base}>
          <thead><tr>
            <th className={cx(tabla.th, "w-10")}><input type="checkbox" aria-label="Marcar los de esta página" checked={todosMarcados}
              onChange={() => setMarcados((m) => { const n = new Set(m); filas.forEach((f) => (todosMarcados ? n.delete(f.id) : n.add(f.id))); return n; })} /></th>
            <th className={tabla.th} /><th className={tabla.th}>Fecha</th><th className={tabla.th}>Folio</th><th className={tabla.th}>Con quién</th>
            <th className={cx(tabla.th, tabla.num)}>Subtotal</th><th className={cx(tabla.th, tabla.num)}>IVA</th><th className={cx(tabla.th, tabla.num)}>Total</th>
          </tr></thead>
          <tbody>
            {filas.map((f) => {
              const otro = f.tipo === "Emitido" ? [f.nombre_receptor, f.rfc_receptor] : [f.nombre_emisor, f.rfc_emisor];
              return (
                <tr key={f.id} onClick={() => setVer(f.id)} className={cx("cursor-pointer hover:bg-tinta/[.03]", f.estatus === "Cancelado" && "opacity-60")}>
                  <td className={tabla.td} onClick={(e) => e.stopPropagation()}><input type="checkbox" aria-label="Marcar" checked={marcados.has(f.id)} onChange={() => marcar(f.id)} /></td>
                  <td className={tabla.td}><Letra clase={f.clase} /></td>
                  <td className={cx(tabla.td, "whitespace-nowrap tabular-nums text-grafito")}>{f.fecha.slice(0, 10).split("-").reverse().join("/")}</td>
                  <td className={cx(tabla.td, "whitespace-nowrap font-medium")}>{f.serie}{f.folio || (f.origen === "aviso" ? "—" : "")}
                    {f.estatus === "Cancelado" && <span className="ml-2 rounded bg-rojo-suave px-1.5 py-0.5 text-[11px] font-medium text-rojo">Cancelado</span>}</td>
                  <td className={tabla.td}><p className="max-w-80 truncate">{otro[0] || "—"}</p><p className="font-mono text-[11px] text-grafito">{otro[1]} · {f.tipo.toLowerCase()}{f.metodo ? ` · ${f.metodo}` : ""}</p></td>
                  <td className={cx(tabla.td, tabla.num)}>{dinero(f.subtotal)}</td>
                  <td className={cx(tabla.td, tabla.num, "text-grafito")}>{dinero(f.iva)}</td>
                  <td className={cx(tabla.td, tabla.num, "font-semibold")}>{dinero(f.total)}{f.moneda && f.moneda !== "MXN" && f.moneda !== "XXX" && <span className="ml-1 text-[11px] font-normal text-grafito">{f.moneda}</span>}</td>
                </tr>
              );
            })}
            {!filas.length && <tr><td colSpan={8} className="px-4 py-12 text-center text-grafito">{isLoading ? "Cargando…" : "Nada con esos filtros."}</td></tr>}
          </tbody>
        </table>
      </div>
      {paginas > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-sm text-grafito">
          <Button size="sm" variant="fantasma" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}><ChevronLeft className="size-4" /></Button>
          Página {pagina} de {paginas}
          <Button size="sm" variant="fantasma" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}><ChevronRight className="size-4" /></Button>
        </div>
      )}

      {ver !== null && <Visor filas={filas} id={ver} ir={setVer} />}
      {zip !== null && <AvanceZip id={zip} cerrar={() => setZip(null)} />}
    </section>
  );
}

/** El PDF propio a pantalla completa: ← → para pasar al siguiente, Esc para cerrar. */
function Visor({ filas, id, ir }: { filas: FilaXml[]; id: number; ir: (id: number | null) => void }) {
  const i = filas.findIndex((f) => f.id === id);
  const f = filas[i];
  const [pdf, setPdf] = useState<{ url: string; nombre: string; blob: Blob } | null>(null);
  const [error, setError] = useState("");
  const actual = useRef(0);

  useEffect(() => {
    if (!f) return;
    const turno = ++actual.current;
    setPdf(null); setError("");
    let url = "";
    blobDe(`/xml/cfdi/${f.id}/pdf`).then(({ blob, nombre }) => {
      if (turno !== actual.current) return;
      url = URL.createObjectURL(blob);
      setPdf({ url, nombre, blob });
    }).catch((e) => turno === actual.current && setError(e instanceof Error ? e.message : String(e)));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [f]);

  const mover = useCallback((d: number) => { const s = filas[i + d]; if (s) ir(s.id); }, [filas, i, ir]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") ir(null);
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); mover(1); }
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); mover(-1); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [ir, mover]);

  if (!f) return null;
  const otro = f.tipo === "Emitido" ? f.nombre_receptor : f.nombre_emisor;
  return (
    <div role="dialog" aria-modal className="fixed inset-0 z-[70] flex flex-col bg-black/70 p-3 backdrop-blur-sm sm:p-6" onClick={() => ir(null)}>
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col overflow-hidden rounded-2xl bg-hoja shadow-flotante" onClick={(e) => e.stopPropagation()}>
        <header className="flex flex-wrap items-center gap-3 border-b border-linea px-4 py-3">
          <Letra clase={f.clase} grande />
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{CLASES[f.clase]?.nombre ?? f.comprobante} {f.serie}{f.folio} · {dinero(f.total)}{f.estatus === "Cancelado" && <span className="ml-2 text-rojo">Cancelado{f.cancelado_el ? ` el ${f.cancelado_el.slice(0, 10).split("-").reverse().join("/")}` : ""}</span>}</p>
            <p className="truncate text-sm text-grafito">{otro} · <span className="font-mono text-xs">{f.uuid}</span></p>
          </div>
          <Button size="sm" variant="fantasma" disabled={i <= 0} onClick={() => mover(-1)} aria-label="Anterior"><ChevronLeft className="size-4" /></Button>
          <Button size="sm" variant="fantasma" disabled={i >= filas.length - 1} onClick={() => mover(1)} aria-label="Siguiente"><ChevronRight className="size-4" /></Button>
          <Button size="sm" disabled={!pdf} onClick={() => pdf && guardar(pdf.blob, pdf.nombre)}><FileText className="size-4" /> PDF</Button>
          <Button size="sm" disabled={f.origen === "aviso"} onClick={() => descargar(`/xml/cfdi/${f.id}/xml`, `${f.uuid}.xml`).catch(mostrarError)}><Download className="size-4" /> XML</Button>
          <Button size="sm" variant="fantasma" onClick={() => ir(null)} aria-label="Cerrar"><X className="size-4" /></Button>
        </header>
        <div className="grid flex-1 place-items-center bg-papel">
          {pdf ? <iframe src={pdf.url} title="PDF del comprobante" className="size-full" />
            : error ? <p className="max-w-md px-6 text-center text-sm text-grafito">{error}</p>
              : <Loader2 className="size-7 animate-spin text-grafito" />}
        </div>
      </div>
    </div>
  );
}

function AvanceZip({ id, cerrar }: { id: number; cerrar: () => void }) {
  const { data: t } = useSWR<TrabajoXml>(`/xml/trabajos/${id}`, fetcher, { refreshInterval: (d) => (!d || d.estado === "curso" ? 800 : 0) });
  const bajado = useRef(false);
  useEffect(() => {
    if (t?.estado === "listo" && t.descargable && !bajado.current) {
      bajado.current = true;
      descargar(`/xml/trabajos/${id}/archivo`, t.params.nombre || "cfdi.zip").then(() => {
        const n = t.resumen.avisos?.length ?? 0;
        if (n) toast.warning(`Listo, pero ${n} no se pudieron pintar`, { description: t.resumen.avisos?.[0] });
        else toast.success(`ZIP con ${t.resumen.comprobantes} comprobantes`);
      }).catch(mostrarError).finally(cerrar);
    } else if (t && t.estado !== "curso" && t.estado !== "listo") {
      toast.error(t.resumen.errores?.[0] || "No se pudo armar el ZIP");
      cerrar();
    }
  }, [t, id, cerrar]);
  const pct = t?.total ? Math.round((t.avance / t.total) * 100) : 0;
  return (
    <div className="fixed bottom-5 left-1/2 z-[60] w-[min(92vw,26rem)] -translate-x-1/2 rounded-2xl bg-primario p-4 text-sobre-primario shadow-flotante">
      <p className="flex items-center gap-2 text-sm font-medium"><Loader2 className="size-4 animate-spin" /> Armando tu ZIP… {t?.mensaje}
        <button className="ml-auto text-xs underline opacity-80" onClick={() => api(`/xml/trabajos/${id}/cancelar`, { method: "POST" }).finally(cerrar)}>Cancelar</button></p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/20"><div className="h-full rounded-full bg-white transition-[width] duration-300" style={{ width: `${pct}%` }} /></div>
    </div>
  );
}
