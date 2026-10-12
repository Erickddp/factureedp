"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, FileArchive, FileSpreadsheet, FileUp, FolderCheck, FolderDown, Info, Pencil, Play, RotateCcw, Square, Trash2, XCircle } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { PerfilModal } from "@/components/perfil-lote";
import { Badge, Button, Cifra, Input, Kbd, Modal, PageHeader, Tabs, Vacio, cx, tabla } from "@/components/ui";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, fecha } from "@/lib/format";
import type { FilaLote, LoteDetalle, LoteResumen, PerfilLote } from "@/lib/types";

/** "2026-10-05" → "05/10/2026" sin pasar por Date (new Date("2026-10-05") es UTC y se vería un día antes en México). */
const fechaISO = (s?: string) => (s && /^\d{4}-\d{2}-\d{2}/.test(s) ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : s ?? "");
type Filtro = "todas" | "listas" | "pendientes" | "timbradas";
const ETIQUETAS: Record<string, string> = {
  folio: "Folio de la hoja", nombre: "Nombre", rfc: "RFC", cp: "CP fiscal", fecha: "Fecha de pago", monto: "Monto cobrado",
  forma: "Forma de pago", regimen: "Régimen fiscal", correo: "Correo o contacto", direccion: "Dirección", servicio: "Servicio (con IVA)",
};

function Estado({ f }: { f: FilaLote }) {
  if (f.estado === "timbrada") return <Badge tono="sello">Timbrada {f.folio_timbra}</Badge>;
  if (f.estado === "timbrando") return <Badge tono="cobalto">Timbrando…</Badge>;
  if (f.estado === "omitida") return <Badge>{f.resumen.ya_timbrada ? "Ya estaba timbrada" : "Omitida"}</Badge>;
  if (f.estado === "error") return <Badge tono="rojo">{f.etapa === "timbrado" ? "Rechazada" : "Por corregir"}</Badge>;
  return <Badge tono={f.avisos.some((a) => a.nivel === "aviso") ? "alerta" : "neutro"}>{f.avisos.some((a) => a.nivel === "aviso") ? "Lista · revisar" : "Lista"}</Badge>;
}

/** El servidor manda "Título. Qué hacer: … [Detalle del PAC: …]" cuando reconoce el error. */
function Explicacion({ texto }: { texto: string }) {
  const m = texto.match(/^(.*?)\. Qué hacer: (.*?)(?: \[Detalle del PAC: (.*)\])?$/s);
  if (!m) return <p className="text-rojo">{texto}</p>;
  return (
    <div className="grid gap-1 text-sm">
      <p className="font-medium text-rojo">{m[1]}</p>
      <p>{m[2]}</p>
      {m[3] && <p className="text-xs text-grafito">Detalle técnico: {m[3]}</p>}
    </div>
  );
}

export default function PaginaLotes() {
  return <Suspense><Lotes /></Suspense>;
}

function Lotes() {
  const { emisor } = useEmisor();
  const params = useSearchParams();
  const { data: perfiles = [], mutate: mPerfiles } = useSWR<PerfilLote[]>(emisor ? `/lotes/perfiles?emisor_id=${emisor.id}` : null, fetcher);
  const { data: lotes = [], mutate: mLotes } = useSWR<LoteResumen[]>(emisor ? `/lotes?emisor_id=${emisor.id}` : null, fetcher);
  const [perfilId, setPerfilId] = useState<number | null>(null);
  const [texto, setTexto] = useState("");
  const [creando, setCreando] = useState(false);
  const [loteId, setLoteId] = useState<number | null>(null);
  const [editarPerfil, setEditarPerfil] = useState<PerfilLote | "nuevo" | null>(null);
  const archivo = useRef<HTMLInputElement>(null);

  useEffect(() => { if (perfiles.length && !perfiles.some((p) => p.id === perfilId)) setPerfilId(perfiles[0].id); }, [perfiles, perfilId]);
  useEffect(() => { setLoteId(null); }, [emisor?.id]);
  useEffect(() => { const l = Number(params.get("lote")); if (l) setLoteId(l); }, [params]);  // desde la bandeja de pendientes

  const crear = async (file?: File) => {
    if (!emisor || !perfilId) return;
    if (!texto.trim() && !file) return toast.error("Pega las filas de tu tabla o sube un archivo.");
    setCreando(true);
    try {
      const fd = new FormData();
      fd.append("emisor_id", String(emisor.id));
      fd.append("perfil_id", String(perfilId));
      if (file) fd.append("archivo", file); else fd.append("texto", texto);
      const l = await api<LoteDetalle>("/lotes", { method: "POST", body: fd });
      setLoteId(l.id);
      setTexto("");
      mLotes();
      const mal = l.cuentas.error;
      toast.success(`${l.filas.length} filas revisadas${mal ? ` · ${mal} por corregir` : ""}`);
    } catch (e) { mostrarError(e); } finally { setCreando(false); }
  };

  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;
  if (loteId) return <Detalle loteId={loteId} volver={() => { setLoteId(null); mLotes(); }} />;

  const perfil = perfiles.find((p) => p.id === perfilId);
  return (
    <>
      <PageHeader title="Lotes de facturas" />
      <p className="-mt-3 mb-6 max-w-3xl text-sm text-grafito">
        Pega las filas de tu hoja (o sube un CSV/Excel): Timbra revisa cada una, arma los conceptos, cuadra el total al centavo y las timbra con el folio que tú pusiste.
        Las que tengan un problema quedan aparte con su folio apartado, listas para corregir.
      </p>
      {!perfiles.length ? (
        <Vacio titulo="Primero crea un perfil de importación">
          Le dices a Timbra qué columna es cada dato y cómo se arman los conceptos. Hay un ejemplo listo para editar (servicio + producto con IVA incluido).
          <div className="mt-4"><Button variant="primario" onClick={() => setEditarPerfil("nuevo")}>Crear perfil desde el ejemplo</Button></div>
        </Vacio>
      ) : (
        <section className="mb-8 grid gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
          <div className="flex flex-wrap items-end gap-3">
            <label className="grid min-w-56 gap-1.5"><span className="text-[13px] font-medium text-grafito">Perfil</span>
              <select value={perfilId ?? ""} onChange={(e) => setPerfilId(Number(e.target.value))} className="h-10 rounded-lg border border-linea bg-hoja px-2 text-sm focus:border-tinta focus:outline-none">
                {perfiles.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
              </select></label>
            <Button size="sm" variant="fantasma" onClick={() => perfil && setEditarPerfil(perfil)}><Pencil className="size-4" /> Editar</Button>
            <Button size="sm" variant="fantasma" onClick={() => setEditarPerfil("nuevo")}>Nuevo</Button>
            {perfil && <p className="ml-auto text-xs text-grafito">Serie {perfil.config.serie} · folio {perfil.config.folio_modo === "hoja" ? "de la hoja" : "consecutivo"} · {perfil.config.conceptos.length} concepto(s)</p>}
          </div>
          <textarea
            value={texto} onChange={(e) => setTexto(e.target.value)} rows={8}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); crear(); } }}
            placeholder={"Pega aquí las filas copiadas de tu hoja de cálculo (con o sin encabezados)\nC-30\tNOMBRE\tRFC\tCP\t05/10/2026\t750.00\t562.50 …"}
            className="w-full rounded-xl border border-linea bg-hoja p-3 font-mono text-xs leading-relaxed placeholder:text-grafito/60 focus:border-tinta focus:outline-none" />
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primario" onClick={() => crear()} loading={creando} disabled={!perfilId}>Revisar filas <Kbd>Ctrl ↵</Kbd></Button>
            <Button onClick={() => archivo.current?.click()} disabled={!perfilId || creando}><FileUp className="size-4" /> Subir CSV o Excel</Button>
            <input ref={archivo} type="file" accept=".csv,.tsv,.txt,.xlsx" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) crear(f); }} />
            <span className="text-xs text-grafito">No se timbra nada todavía: primero ves cada fila.</span>
          </div>
        </section>
      )}

      {lotes.length > 0 && (
        <>
          <h2 className="mb-3 font-semibold">Lotes recientes</h2>
          <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
            <table className={tabla.base}>
              <thead><tr><th className={tabla.th}>Lote</th><th className={tabla.th}>Creado</th><th className={cx(tabla.th, tabla.num)}>Timbradas</th>
                <th className={cx(tabla.th, tabla.num)}>Listas</th><th className={cx(tabla.th, tabla.num)}>Por corregir</th><th className={cx(tabla.th, tabla.num)}>Total timbrado</th></tr></thead>
              <tbody>
                {lotes.map((l) => (
                  <tr key={l.id} className="cursor-pointer hover:bg-tinta/[.02]" onClick={() => setLoteId(l.id)}>
                    <td className={cx(tabla.td, "font-medium")}>{l.nombre} {l.ejecutando && <Badge tono="cobalto">timbrando</Badge>}</td>
                    <td className={tabla.td}>{fecha(l.creado)}</td>
                    <td className={cx(tabla.td, tabla.num)}>{l.cuentas.timbrada}</td>
                    <td className={cx(tabla.td, tabla.num)}>{l.cuentas.listo}</td>
                    <td className={cx(tabla.td, tabla.num, l.cuentas.error > 0 && "font-medium text-rojo")}>{l.cuentas.error}</td>
                    <td className={cx(tabla.td, tabla.num)}>{dinero(l.total_timbrado)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <PerfilModal emisorId={emisor.id} perfil={editarPerfil} abierto={!!editarPerfil} cerrar={() => setEditarPerfil(null)}
        ok={(p) => { setEditarPerfil(null); setPerfilId(p.id); mPerfiles(); }} />
    </>
  );
}

function Detalle({ loteId, volver }: { loteId: number; volver: () => void }) {
  const [ejecutando, setEjecutando] = useState(false);
  const { data: l, mutate } = useSWR<LoteDetalle>(`/lotes/${loteId}`, fetcher, { refreshInterval: (d) => (d?.ejecutando || ejecutando ? 1200 : 0) });
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [ver, setVer] = useState<number | null>(null);
  const [corregir, setCorregir] = useState<FilaLote | null>(null);
  const [confirmar, setConfirmar] = useState(false);
  const [detenerEnError, setDetenerEnError] = useState(false);
  const corriendo = !!l?.ejecutando;
  useEffect(() => { if (ejecutando && l && !l.ejecutando) setEjecutando(false); }, [l, ejecutando]);

  const filas = l?.filas ?? [];
  const listas = filas.filter((f) => f.estado === "listo");
  const pendientes = filas.filter((f) => f.estado === "error");
  const timbradas = filas.filter((f) => f.estado === "timbrada");
  const lista = filas.filter((f) => filtro === "todas" || (filtro === "listas" && f.estado === "listo") || (filtro === "pendientes" && f.estado === "error") || (filtro === "timbradas" && f.estado === "timbrada"));
  const sumaListas = listas.reduce((s, f) => s + Number(f.resumen.monto || 0), 0);

  const ejecutar = useCallback(async (body: { ids?: number[]; primeras?: number }) => {
    try {
      const r = await api<{ iniciadas: number }>(`/lotes/${loteId}/ejecutar`, { method: "POST", json: { ...body, detener_en_error: detenerEnError } });
      if (!r.iniciadas) toast.message("No hay filas listas para timbrar.");
      else { setEjecutando(true); mutate(); }
    } catch (e) { mostrarError(e); }
  }, [loteId, detenerEnError, mutate]);

  const reintentar = async (ids: number[]) => {
    const listos: number[] = [];
    for (const id of ids) {
      try { const r = await api<FilaLote>(`/lotes/${loteId}/filas/${id}/revalidar`, { method: "POST" }); if (r.estado === "listo") listos.push(id); } catch (e) { mostrarError(e); }
    }
    await mutate();
    if (listos.length) ejecutar({ ids: listos });
    else toast.warning("Siguen con problemas. Abre la fila para ver qué falta.");
  };
  const [copiando, setCopiando] = useState(false);
  const aCarpeta = async () => {
    setCopiando(true);
    try {
      const r = await api<{ guardadas: number; timbradas: number; archivos_nuevos: number; errores: string[]; carpetas: string[] }>(`/lotes/${loteId}/carpeta`, { method: "POST" });
      if (r.errores.length) toast.error(r.errores[0], { description: r.errores.length > 1 ? `y ${r.errores.length - 1} más` : undefined });
      else toast.success(`${r.guardadas} de ${r.timbradas} facturas en tu carpeta`, { description: r.carpetas[0] });
      mutate();
    } catch (e) { mostrarError(e); } finally { setCopiando(false); }
  };
  const omitir = async (f: FilaLote) => {
    try { await api(`/lotes/${loteId}/filas/${f.id}/omitir`, { method: "POST" }); toast.success("Fila omitida; su folio quedó libre"); setVer(null); mutate(); } catch (e) { mostrarError(e); }
  };

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (document.querySelector("[role=dialog]")) return;
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && listas.length && !corriendo) { e.preventDefault(); setConfirmar(true); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [listas.length, corriendo]);

  if (!l) return <p className="text-sm text-grafito">Cargando…</p>;
  const fv = filas.find((f) => f.id === ver) ?? null;
  const yaHayTimbradas = timbradas.length > 0;

  return (
    <>
      <PageHeader title={l.nombre}>
        <Button variant="fantasma" onClick={volver}><ArrowLeft className="size-4" /> Lotes</Button>
      </PageHeader>

      {l.alertas?.map((a, i) => (
        <p key={i} className={cx("mb-2 flex gap-2 rounded-xl px-4 py-2.5 text-sm", a.nivel === "error" ? "bg-rojo-suave text-rojo" : a.nivel === "aviso" ? "bg-alerta-suave text-alerta" : "bg-tinta/5 text-grafito")}>
          {a.nivel === "info" ? <Info className="mt-0.5 size-4 shrink-0" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" />} {a.texto}</p>
      ))}
      <div className="mb-5 mt-3 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Cifra titulo="Filas" valor={filas.length} />
        <Cifra titulo="Listas" valor={listas.length} nota={dinero(sumaListas)} />
        <Cifra titulo="Por corregir" valor={pendientes.length} tono={pendientes.length ? "rojo" : undefined} nota={pendientes.length ? "con su folio apartado" : undefined} />
        <Cifra titulo="Timbradas" valor={timbradas.length} tono={timbradas.length ? "sello" : undefined} nota={dinero(l.total_timbrado)} />
        <Cifra titulo="Ya estaban / omitidas" valor={l.cuentas.omitida} />
      </div>

      <div className="sticky top-0 z-20 -mx-1 mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-hoja/95 p-3 ring-1 ring-linea backdrop-blur">
        {corriendo ? (
          <>
            <span className="flex items-center gap-2 text-sm text-cobalto"><span className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> {l.guardando ? "Ya timbradas. Guardando PDF y XML en tu carpeta…" : <>Timbrando… {l.cuentas.timbrada} de {l.cuentas.timbrada + l.cuentas.listo + l.cuentas.timbrando}</>}</span>
            <Button variant="peligro" size="sm" className={l.guardando ? "hidden" : undefined} onClick={() => api(`/lotes/${loteId}/detener`, { method: "POST" }).then(() => toast.message("Se detiene al terminar la factura en curso")).catch(mostrarError)}><Square className="size-3.5" /> Detener</Button>
          </>
        ) : (
          <>
            {listas.length > 0 && !yaHayTimbradas && (
              <Button onClick={() => ejecutar({ primeras: 1 })} title="Timbra sólo la primera para que la revises antes de seguir"><Play className="size-4" /> Timbrar la primera y revisar</Button>
            )}
            {listas.length > 0 && <Button variant="primario" onClick={() => setConfirmar(true)}><Play className="size-4" /> Timbrar {yaHayTimbradas ? "las demás" : "todas"} ({listas.length}) <Kbd>Ctrl ↵</Kbd></Button>}
            {pendientes.length > 0 && <Button onClick={() => reintentar(pendientes.map((f) => f.id))}><RotateCcw className="size-4" /> Reintentar pendientes ({pendientes.length})</Button>}
            <label className="ml-1 flex items-center gap-2 text-sm text-grafito"><input type="checkbox" checked={detenerEnError} onChange={(e) => setDetenerEnError(e.target.checked)} /> Detener al primer error</label>
          </>
        )}
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {l.entrega && l.entrega.timbradas > 0 && !corriendo && (
            l.entrega.guardadas >= l.entrega.timbradas
              ? <span className="flex items-center gap-1.5 text-sm text-sello" title={l.entrega.carpetas.join("\n")}><FolderCheck className="size-4" /> {l.entrega.guardadas} en tu carpeta</span>
              : <Button size="sm" disabled={copiando} onClick={aCarpeta} title={l.entrega.carpetas.join("\n")}><FolderDown className="size-4" /> {copiando ? "Guardando…" : `Guardar en carpeta (${l.entrega.timbradas - l.entrega.guardadas})`}</Button>
          )}
          <Button size="sm" variant="fantasma" onClick={() => descargar(`/lotes/${loteId}/registro.csv`, `registro_lote_${loteId}.csv`).catch(mostrarError)}><FileSpreadsheet className="size-4" /> Registro</Button>
          <Button size="sm" variant="fantasma" disabled={!timbradas.length} onClick={() => descargar(`/lotes/${loteId}/cfdi.zip`, `cfdi_lote_${loteId}.zip`).catch(mostrarError)}><FileArchive className="size-4" /> PDF + XML</Button>
        </span>
      </div>

      <Tabs value={filtro} onChange={setFiltro} items={[
        { id: "todas", label: "Todas", n: filas.length }, { id: "listas", label: "Listas", n: listas.length },
        { id: "pendientes", label: "Por corregir", n: pendientes.length }, { id: "timbradas", label: "Timbradas", n: timbradas.length }]} />

      <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
        <table className={tabla.base}>
          <thead><tr>
            <th className={tabla.th}>Folio</th><th className={tabla.th}>Cliente</th><th className={tabla.th}>Fecha</th>
            <th className={cx(tabla.th, tabla.num)}>Cobrado</th><th className={cx(tabla.th, tabla.num)}>CFDI</th><th className={tabla.th}>Estado</th><th className={tabla.th}>Notas</th><th className={tabla.th} />
          </tr></thead>
          <tbody>
            {lista.map((f) => (
              <tr key={f.id} onClick={() => setVer(f.id)} className={cx("cursor-pointer hover:bg-tinta/[.02]", (f.estado === "omitida") && "opacity-55")}>
                <td className={cx(tabla.td, "whitespace-nowrap font-medium")}>{f.referencia ?? `#${f.n}`}{f.estado === "error" && f.folio && <span className="ml-1 text-[11px] font-normal text-grafito" title="Folio apartado para esta factura">🔒</span>}</td>
                <td className={tabla.td}><p className="max-w-64 truncate">{f.resumen.nombre || f.datos.nombre}</p><p className="font-mono text-[11px] text-grafito">{f.resumen.rfc || f.datos.rfc}{f.resumen.cliente === "nuevo" && " · nuevo"}</p></td>
                <td className={cx(tabla.td, "whitespace-nowrap text-grafito")}>{f.resumen.fecha ? fechaISO(f.resumen.fecha) : f.datos.fecha}</td>
                <td className={cx(tabla.td, tabla.num)}>{f.resumen.monto ? dinero(f.resumen.monto) : "—"}</td>
                <td className={cx(tabla.td, tabla.num, f.resumen.total && f.resumen.total !== f.resumen.monto && Number(f.resumen.total) !== Number(f.resumen.monto) && "text-rojo")}>{f.resumen.total ? dinero(f.resumen.total) : "—"}</td>
                <td className={tabla.td}><Estado f={f} /></td>
                <td className={cx(tabla.td, "max-w-72")}>
                  {f.estado === "error" ? <p className="truncate text-xs text-rojo">{f.error}</p> : (
                    <span className="flex flex-wrap gap-1.5 text-xs text-grafito">
                      {f.resumen.ajuste && <span title={f.resumen.ajuste} className="rounded bg-tinta/5 px-1.5 py-0.5">ajuste de centavo</span>}
                      {f.avisos.filter((a) => a.nivel === "aviso").length > 0 && <span className="flex items-center gap-1 text-alerta"><AlertTriangle className="size-3.5" /> {f.avisos.filter((a) => a.nivel === "aviso").length}</span>}
                    </span>
                  )}
                </td>
                <td className={cx(tabla.td, "text-right")} onClick={(e) => e.stopPropagation()}>
                  {f.estado === "error" && <Button size="sm" variant="fantasma" onClick={() => setCorregir(f)}><Pencil className="size-3.5" /> Corregir</Button>}
                </td>
              </tr>
            ))}
            {!lista.length && <tr><td colSpan={8} className="px-4 py-10 text-center text-grafito">Nada en esta lista.</td></tr>}
          </tbody>
        </table>
      </div>

      {/* Revisar una fila */}
      <Modal open={!!fv} onClose={() => setVer(null)} title={fv ? `${fv.referencia ?? `Fila ${fv.n}`} · ${fv.resumen.nombre ?? ""}` : ""} wide
        footer={fv && <>
          {fv.estado !== "timbrada" && fv.estado !== "omitida" && <Button variant="peligro" onClick={() => omitir(fv)}><Trash2 className="size-4" /> Omitir fila</Button>}
          {fv.estado === "timbrada" && fv.factura_id && <>
            <Button onClick={() => descargar(`/facturas/${fv.factura_id}/pdf`, `${fv.uuid}.pdf`).catch(mostrarError)}>PDF</Button>
            <Button onClick={() => descargar(`/facturas/${fv.factura_id}/xml`, `${fv.uuid}.xml`).catch(mostrarError)}>XML</Button></>}
          {(fv.estado === "error" || fv.estado === "listo") && <Button onClick={() => { setCorregir(fv); setVer(null); }}><Pencil className="size-4" /> Corregir datos</Button>}
          {fv.estado === "listo" && !corriendo && <Button variant="primario" onClick={() => { setVer(null); ejecutar({ ids: [fv.id] }); }}><Play className="size-4" /> Timbrar sólo esta</Button>}
          {fv.estado === "error" && fv.etapa === "timbrado" && !corriendo && <Button variant="primario" onClick={() => { setVer(null); reintentar([fv.id]); }}><RotateCcw className="size-4" /> Reintentar</Button>}
        </>}>
        {fv && (
          <div className="grid gap-4 text-sm">
            <div className="flex flex-wrap items-center gap-2"><Estado f={fv} />
              {fv.folio && <span className="text-grafito">Folio {fv.serie}{fv.folio}{fv.estado === "error" ? " apartado" : ""}</span>}
              {fv.uuid && <span className="font-mono text-xs text-grafito">{fv.uuid}</span>}</div>
            {fv.estado === "error" && fv.error && <div className="rounded-xl bg-rojo-suave p-3">{fv.errores.length > 1 ? <ul className="grid gap-1">{fv.errores.map((e, i) => <li key={i} className="flex gap-2 text-rojo"><XCircle className="mt-0.5 size-4 shrink-0" /> {e}</li>)}</ul> : <Explicacion texto={fv.error} />}</div>}
            {fv.avisos.map((a, i) => (
              <p key={i} className={cx("flex gap-2 rounded-lg px-3 py-2", a.nivel === "aviso" ? "bg-alerta-suave text-alerta" : "bg-tinta/5 text-grafito")}>
                {a.nivel === "aviso" ? <AlertTriangle className="mt-0.5 size-4 shrink-0" /> : <Info className="mt-0.5 size-4 shrink-0" />} {a.texto}</p>
            ))}
            {fv.resumen.conceptos && (
              <div className="overflow-x-auto rounded-xl ring-1 ring-linea">
                <table className="w-full">
                  <thead><tr className="text-left text-[11px] uppercase tracking-[.06em] text-grafito"><th className="px-3 py-2">Concepto</th><th className="px-3 py-2">Clave</th><th className="px-3 py-2 text-right">Precio unit.</th><th className="px-3 py-2 text-right">Importe</th></tr></thead>
                  <tbody>{fv.resumen.conceptos.map((c, i) => (
                    <tr key={i} className="border-t border-linea align-top"><td className="max-w-md px-3 py-2">{c.descripcion}</td><td className="px-3 py-2 tabular-nums">{c.clave}<br /><span className="text-grafito">{c.unidad}</span></td>
                      <td className="px-3 py-2 text-right tabular-nums">{c.valor_unitario}</td><td className="px-3 py-2 text-right tabular-nums">{dinero(c.importe)}</td></tr>))}</tbody>
                </table>
              </div>
            )}
            <div className="flex flex-wrap justify-end gap-x-8 gap-y-1">
              <span className="text-grafito">Cobrado <b className="ml-1 text-tinta tabular-nums">{dinero(fv.resumen.monto)}</b></span>
              {fv.resumen.total && <span className="text-grafito">Total del CFDI <b className={cx("ml-1 tabular-nums", Number(fv.resumen.total) === Number(fv.resumen.monto) ? "text-sello" : "text-rojo")}>{dinero(fv.resumen.total)}</b></span>}
            </div>
          </div>
        )}
      </Modal>

      {/* Corregir los datos de una fila */}
      <CorregirFila loteId={loteId} fila={corregir} cerrar={() => setCorregir(null)} ok={(listo) => { setCorregir(null); mutate(); if (listo) toast.success("Fila lista para timbrar"); else toast.warning("Sigue con detalles"); }}
        timbrar={(id) => { setCorregir(null); mutate().then(() => ejecutar({ ids: [id] })); }} />

      {/* Confirmación antes de timbrar de verdad */}
      <Modal open={confirmar} onClose={() => setConfirmar(false)} title="Timbrar facturas"
        footer={<><Button onClick={() => setConfirmar(false)}>Cancelar</Button><Button variant="primario" data-autofocus onClick={() => { setConfirmar(false); ejecutar({}); }}>Timbrar {listas.length}</Button></>}>
        <div className="grid gap-3 text-sm">
          <p>Se van a timbrar <b>{listas.length} factura(s)</b> por <b>{dinero(sumaListas)}</b>, con el folio de tu tabla. Cada una gasta un timbre.</p>
          {listas.some((f) => f.avisos.some((a) => a.nivel === "aviso")) && <p className="flex gap-2 rounded-lg bg-alerta-suave px-3 py-2 text-alerta"><AlertTriangle className="size-4 shrink-0" /> {listas.filter((f) => f.avisos.some((a) => a.nivel === "aviso")).length} tienen avisos. Revisa los marcados "Lista · revisar".</p>}
          {pendientes.length > 0 && <p className="text-grafito">Las {pendientes.length} que tienen error no se timbran; quedan aparte con su folio apartado.</p>}
          {!yaHayTimbradas && <p className="text-grafito">Consejo: usa primero «Timbrar la primera y revisar».</p>}
        </div>
      </Modal>
    </>
  );
}

function CorregirFila({ loteId, fila, cerrar, ok, timbrar }: { loteId: number; fila: FilaLote | null; cerrar: () => void; ok: (listo: boolean) => void; timbrar: (id: number) => void }) {
  const [datos, setDatos] = useState<Record<string, string>>({});
  const [guardando, setGuardando] = useState(false);
  useEffect(() => { if (fila) setDatos(fila.datos); }, [fila]);
  if (!fila) return null;
  const guardar = async (despues: "nada" | "timbrar") => {
    setGuardando(true);
    try {
      const r = await api<FilaLote>(`/lotes/${loteId}/filas/${fila.id}`, { method: "PUT", json: { datos } });
      if (despues === "timbrar" && r.estado === "listo") timbrar(fila.id); else ok(r.estado === "listo");
    } catch (e) { mostrarError(e); } finally { setGuardando(false); }
  };
  return (
    <Modal open={!!fila} onClose={cerrar} title={`Corregir ${fila.referencia ?? `fila ${fila.n}`}`} wide
      footer={<><Button onClick={cerrar}>Cancelar</Button><Button onClick={() => guardar("nada")} loading={guardando}>Guardar y revisar</Button><Button variant="primario" onClick={() => guardar("timbrar")} loading={guardando}>Guardar y timbrar</Button></>}>
      {fila.error && <div className="mb-4 rounded-xl bg-rojo-suave p-3"><Explicacion texto={fila.error} /></div>}
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); guardar("nada"); }}>
        {Object.keys(datos).map((k) => (
          <label key={k} className={cx("grid gap-1.5", ["nombre", "direccion"].includes(k) && "sm:col-span-2")}>
            <span className="text-[13px] font-medium text-grafito">{ETIQUETAS[k] ?? k}</span>
            <Input value={datos[k] ?? ""} onChange={(e) => setDatos({ ...datos, [k]: e.target.value })} />
          </label>
        ))}
        <button type="submit" hidden />
      </form>
      <p className="mt-4 text-xs text-grafito">El folio {fila.folio ? `${fila.serie}${fila.folio}` : "de esta fila"} sigue apartado: al corregir sale con el mismo número.</p>
    </Modal>
  );
}
