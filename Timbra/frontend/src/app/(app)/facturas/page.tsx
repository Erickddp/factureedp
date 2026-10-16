"use client";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import {
  BookmarkPlus, ChevronLeft, ChevronRight, Copy, Download, FileArchive, FileDown, FileSpreadsheet, Mail, Plus, Search, ShieldCheck, X, XCircle,
} from "lucide-react";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, ESTADOS, fecha, TIPOS } from "@/lib/format";
import type { Factura } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Field, Input, Menu, Modal, PageHeader, Select, Vacio, cx } from "@/components/ui";

const MOTIVOS = {
  "01": "01 · Con errores, con relación (ya timbraste la que sustituye)",
  "02": "02 · Con errores, sin relación",
  "03": "03 · No se llevó a cabo la operación",
  "04": "04 · Operación nominativa en factura global",
};
const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const tono = (e: Factura["estado"]) => (e === "timbrada" ? "sello" : e === "cancelada" ? "rojo" : "alerta");
const folioDe = (f: Factura) => `${f.serie ?? ""} ${f.folio ?? ""}`.trim() || "Sin folio";
const mesDe = (f: Factura) => Number((f.fecha ?? "").slice(5, 7)) - 1;  // del texto: sin brincos de zona horaria
const dosDig = (n: number) => String(n).padStart(2, "0");

export default function Page() {
  return (
    <Suspense>
      <Facturas />
    </Suspense>
  );
}

/** Visor de facturas emitidas: el año se carga una vez y todo lo demás (mes, búsqueda, filtros, selección) es inmediato. */
function Facturas() {
  const { emisor } = useEmisor();
  const router = useRouter();
  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [mes, setMes] = useState<number | null>(hoy.getMonth());  // null = todo el año
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("");
  const [tipo, setTipo] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [abierta, setAbierta] = useState(false);  // en celular: el detalle se abre encima
  const [cancelar, setCancelar] = useState<Factura | null>(null);

  const qs = emisor ? `emisor_id=${emisor.id}&desde=${anio}-01-01T00:00:00&hasta=${anio}-12-31T23:59:59&limit=5000` : null;
  const { data: delAnio = [], mutate, isLoading } = useSWR<Factura[]>(qs ? `/facturas?${qs}` : null, fetcher, { keepPreviousData: true });

  const porMes = useMemo(() => {
    const n = Array(12).fill(0);
    delAnio.forEach((f) => { const m = mesDe(f); if (m >= 0) n[m]++; });
    return n;
  }, [delAnio]);
  const lista = useMemo(() => {
    const t = q.trim().toUpperCase();
    return delAnio.filter((f) => (mes === null || mesDe(f) === mes) && (!estado || f.estado === estado) && (!tipo || f.tipo === tipo)
      && (!t || [f.receptor_nombre, f.receptor_rfc, f.uuid, `${f.serie ?? ""}${f.folio ?? ""}`, f.folio].some((x) => (x ?? "").toUpperCase().includes(t))));
  }, [delAnio, mes, q, estado, tipo]);
  const actual = lista.find((f) => f.id === sel) ?? null;

  // al cambiar de mes o filtro, queda seleccionada la primera (en pantalla ancha)
  useEffect(() => { if (!lista.some((f) => f.id === sel)) setSel(lista[0]?.id ?? null); }, [lista, sel]);

  // ↑ ↓ recorren la lista sin tocar el ratón
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (!["ArrowDown", "ArrowUp"].includes(e.key) || (e.target instanceof HTMLElement && e.target.closest("input,select,textarea"))) return;
      e.preventDefault();
      const i = lista.findIndex((f) => f.id === sel);
      const otra = lista[Math.max(0, Math.min(lista.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
      if (otra) { setSel(otra.id); document.getElementById(`fac-${otra.id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [lista, sel]);

  const periodo = () => {
    const ini = mes === null ? `${anio}-01-01` : `${anio}-${dosDig(mes + 1)}-01`;
    const fin = mes === null ? `${anio}-12-31` : `${anio}-${dosDig(mes + 1)}-${dosDig(new Date(anio, mes + 1, 0).getDate())}`;
    return { qs: `emisor_id=${emisor?.id}&desde=${ini}T00:00:00&hasta=${fin}T23:59:59`, nombre: mes === null ? `${anio}` : `${anio}-${dosDig(mes + 1)}` };
  };

  const guardarPlantilla = async (f: Factura) => {
    const nombre = window.prompt("Nombre de la plantilla", `${f.receptor_nombre ?? ""} · ${f.serie ?? ""}${f.folio ?? ""}`);
    if (!nombre) return;
    try {
      await api(`/plantillas/desde-factura/${f.id}?nombre=${encodeURIComponent(nombre)}`, { method: "POST" });
      toast.success("Plantilla guardada");
    } catch (e) { mostrarError(e); }
  };
  const pdf = (f: Factura) => descargar(`/facturas/${f.id}/pdf`, `${f.uuid}.pdf`).catch(mostrarError);
  const xml = (f: Factura) => descargar(`/facturas/${f.id}/xml`, `${f.uuid}.xml`).catch(mostrarError);
  // Si el cliente no tiene correo guardado, se pregunta a quién mandarlo y queda guardado para la próxima
  const enviarCorreo = async (f: Factura) => {
    try {
      const r = await api<{ para: string[] }>(`/facturas/${f.id}/enviar`, { method: "POST", json: {} });
      toast.success(`Enviada a ${r.para.join(", ")}`);
    } catch (e) {
      if ((e as { status?: number }).status !== 422) return mostrarError(e);
      const correo = window.prompt(`${f.receptor_nombre ?? "El cliente"} no tiene correo guardado. ¿A qué correo mando la factura?`)?.trim();
      if (!correo) return;
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correo)) return void toast.error("Ese correo no parece válido.");
      try {
        await api(`/facturas/${f.id}/enviar`, { method: "POST", json: { para: [correo], guardar: true } });
        toast.success(`Enviada a ${correo} y guardado en el cliente`);
      } catch (e2) { mostrarError(e2); }
    }
  };
  const estatusSat = (f: Factura) =>
    api<Record<string, string>>(`/facturas/${f.id}/estatus`).then((r) => {
      const txt = [r.Estado, r.EsCancelable, r.EstatusCancelacion].filter(Boolean).join(" · ") || JSON.stringify(r);
      (r.error ? toast.error : toast.success)(r.error ? `PAC: ${r.error}` : `SAT: ${txt}`, { duration: 12000 });
      mutate();
    }).catch(mostrarError);
  const acciones = (f: Factura) => [
    { label: "Clonar", icon: <Copy className="size-4" />, onClick: () => router.push(`/facturar?clonar=${f.id}`), oculto: f.tipo === "P" },
    { label: "Guardar como plantilla", icon: <BookmarkPlus className="size-4" />, onClick: () => guardarPlantilla(f), oculto: f.tipo === "P" },
    { label: "Consultar estatus en el SAT", icon: <ShieldCheck className="size-4" />, oculto: !f.uuid, onClick: () => estatusSat(f) },
    { label: "Cancelar ante el SAT", icon: <XCircle className="size-4" />, onClick: () => setCancelar(f), peligro: true, oculto: f.estado !== "timbrada" },
  ];

  const total = lista.filter((f) => f.estado !== "cancelada" && f.tipo === "I").reduce((s, f) => s + Number(f.total), 0);

  return (
    <div>
      <PageHeader title="Facturas emitidas">
        <Link href="/facturar"><Button variant="primario"><Plus className="size-4" /> Nueva</Button></Link>
      </PageHeader>

      {/* Año y meses: un clic y cambia al instante (el año ya está cargado) */}
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-2xl bg-hoja p-2 ring-1 ring-linea">
        <div className="flex items-center gap-1 pl-1">
          <button className="rounded-lg p-1.5 text-grafito hover:bg-tinta/5" aria-label="Año anterior" onClick={() => setAnio(anio - 1)}><ChevronLeft className="size-4" /></button>
          <span className="w-12 text-center font-semibold tabular-nums">{anio}</span>
          <button className="rounded-lg p-1.5 text-grafito hover:bg-tinta/5 disabled:opacity-30" aria-label="Año siguiente" disabled={anio >= hoy.getFullYear()} onClick={() => setAnio(anio + 1)}><ChevronRight className="size-4" /></button>
        </div>
        <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
          {MESES.map((m, i) => (
            <button key={m} onClick={() => setMes(i)}
              className={cx("relative flex min-w-[52px] flex-1 flex-col items-center rounded-xl px-2 py-1.5 text-sm transition",
                mes === i ? "bg-cobalto text-white shadow-sm" : porMes[i] ? "text-tinta hover:bg-tinta/5" : "text-grafito/60 hover:bg-tinta/5")}>
              {m}
              <span className={cx("text-[10px] tabular-nums", mes === i ? "text-white/80" : "text-grafito")}>{porMes[i] || "·"}</span>
            </button>
          ))}
          <button onClick={() => setMes(null)} className={cx("rounded-xl px-3 text-sm", mes === null ? "bg-cobalto text-white" : "text-grafito hover:bg-tinta/5")}>Año</button>
        </div>
      </div>

      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_190px_190px_auto_auto]">
        <div className="relative min-w-0 sm:col-span-2 lg:col-span-1">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-grafito" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cliente, RFC, folio o UUID" className="pl-9" aria-label="Buscar" />
        </div>
        <Select value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo">
          <option value="">Todos los tipos</option>
          {Object.entries(TIPOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
          <option value="">Todos los estados</option>
          {Object.entries(ESTADOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Button onClick={() => { const p = periodo(); descargar(`/facturas/exportar/zip?${p.qs}`, `XML_${emisor?.rfc}_${p.nombre}.zip`).catch(mostrarError); }}><FileArchive className="size-4" /> XML</Button>
        <Button onClick={() => { const p = periodo(); descargar(`/facturas/exportar/csv?${p.qs}`, `Facturas_${emisor?.rfc}_${p.nombre}.csv`).catch(mostrarError); }}><FileSpreadsheet className="size-4" /> Excel</Button>
      </div>

      {isLoading && !delAnio.length ? (
        <div className="grid gap-3 lg:grid-cols-[minmax(300px,380px)_1fr]">
          <div className="flex flex-col gap-2">{[0, 1, 2, 3].map((i) => <div key={i} className="esqueleto h-24" />)}</div>
          <div className="esqueleto hidden h-[60vh] lg:block" />
        </div>
      ) : !lista.length ? (
        <Vacio titulo={delAnio.length ? "Nada con esos filtros" : `Sin facturas en ${anio}`}>Cambia el mes o los filtros, o timbra una factura nueva con F2.</Vacio>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(300px,380px)_1fr]">
          {/* Tarjetas */}
          <div>
            <p className="mb-2 px-1 text-xs text-grafito">
              {lista.length.toLocaleString("es-MX")} {lista.length === 1 ? "comprobante" : "comprobantes"}
              {total > 0 && <> · facturado <b className="text-tinta tabular-nums">{dinero(total)}</b></>}
              <span className="hidden lg:inline"> · ↑ ↓ para recorrer</span>
            </p>
            <ul className="escalonar flex flex-col gap-2 lg:max-h-[calc(100vh-250px)] lg:overflow-y-auto lg:pr-1">
              {lista.map((f) => (
                <li key={f.id} id={`fac-${f.id}`}>
                  <button onClick={() => { setSel(f.id); setAbierta(true); }}
                    className={cx("group w-full rounded-2xl p-4 text-left ring-1 transition duration-150",
                      f.id === sel ? "bg-acento-suave/60 ring-cobalto shadow-tarjeta" : "bg-hoja ring-linea hover:-translate-y-0.5 hover:shadow-tarjeta hover:ring-cobalto/40",
                      f.estado === "cancelada" && "opacity-70")}>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-lg font-semibold tabular-nums tracking-tight">{folioDe(f)}</span>
                      <span className="text-xs text-grafito tabular-nums">{fecha(f.fecha)}</span>
                    </div>
                    <p className="mt-0.5 truncate text-sm font-medium">{f.receptor_nombre ?? "—"}</p>
                    <p className="truncate text-xs text-grafito tabular-nums">{f.receptor_rfc}</p>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="flex flex-wrap items-center gap-1">
                        {f.estado !== "timbrada" && <Badge tono={tono(f.estado)}>{ESTADOS[f.estado]}</Badge>}
                        <span className="text-xs text-grafito">{TIPOS[f.tipo]}{f.metodo_pago ? ` · ${f.metodo_pago}` : ""}</span>
                        {f.demo && <Badge tono="alerta">Demo</Badge>}
                      </span>
                      <span className="text-right">
                        <b className={cx("tabular-nums", f.estado === "cancelada" && "line-through")}>{dinero(f.total, f.moneda)}</b>
                        {Number(f.saldo) > 0 && <span className="block text-[11px] text-alerta tabular-nums">saldo {dinero(f.saldo)}</span>}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {/* Detalle: a la derecha en pantalla ancha, encima en celular */}
          {actual && (
            <div className={cx("lg:sticky lg:top-4", abierta ? "fixed inset-0 z-40 overflow-y-auto bg-papel p-3 lg:static lg:z-auto lg:bg-transparent lg:p-0" : "hidden lg:block")}>
              <Detalle f={actual} cerrar={() => setAbierta(false)} pdf={pdf} xml={xml} enviar={enviarCorreo} acciones={acciones(actual)} />
            </div>
          )}
        </div>
      )}
      <ModalCancelar f={cancelar} onClose={() => setCancelar(null)} onOk={() => { setCancelar(null); mutate(); }} />
    </div>
  );
}

function Detalle({ f, cerrar, pdf, xml, enviar, acciones }: {
  f: Factura; cerrar: () => void; pdf: (f: Factura) => void; xml: (f: Factura) => void; enviar: (f: Factura) => void;
  acciones: { label: string; icon?: React.ReactNode; onClick: () => void; peligro?: boolean; oculto?: boolean }[];
}) {
  const copiar = (t: string) => navigator.clipboard.writeText(t).then(() => toast.success("UUID copiado"));
  const dato = (titulo: string, valor: React.ReactNode) => (
    <div className="min-w-0"><p className="text-[11px] uppercase tracking-[.06em] text-grafito">{titulo}</p><div className="truncate text-sm">{valor}</div></div>
  );
  return (
    <section key={f.id} className="animate-entrar overflow-hidden rounded-3xl bg-hoja ring-1 ring-linea">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-linea p-5">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[.1em] text-cobalto">{TIPOS[f.tipo]}</p>
          <p className="text-3xl font-semibold tabular-nums tracking-tight">{folioDe(f)}</p>
          <div className="mt-1 flex flex-wrap gap-1"><Badge tono={tono(f.estado)}>{ESTADOS[f.estado]}</Badge>{f.demo && <Badge tono="alerta">Demo · sin validez</Badge>}</div>
        </div>
        <div className="flex items-start gap-2">
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-[.06em] text-grafito">Total</p>
            <p className={cx("text-2xl font-semibold tabular-nums", f.estado === "cancelada" && "line-through opacity-60")}>{dinero(f.total, f.moneda)}</p>
          </div>
          <button onClick={cerrar} className="rounded-lg p-2 text-grafito hover:bg-tinta/5 lg:hidden" aria-label="Cerrar"><X className="size-5" /></button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-linea px-5 py-3">
        <Button size="sm" onClick={() => pdf(f)}><FileDown className="size-4" /> PDF</Button>
        <Button size="sm" onClick={() => xml(f)}><Download className="size-4" /> XML</Button>
        <Button size="sm" onClick={() => enviar(f)}><Mail className="size-4" /> Enviar</Button>
        <Menu items={acciones} />
      </div>
      <div className="grid grid-cols-2 gap-4 p-5 sm:grid-cols-4">
        <div className="col-span-2">{dato("Receptor", <><b className="font-medium">{f.receptor_nombre ?? "—"}</b><span className="block text-xs text-grafito tabular-nums">{f.receptor_rfc}</span></>)}</div>
        {dato("Fecha", <span className="tabular-nums">{fecha(f.fecha)}</span>)}
        {dato("Pago", <>{f.metodo_pago ?? "—"}{f.forma_pago ? ` · ${f.forma_pago}` : ""}</>)}
        {Number(f.saldo) > 0 && dato("Saldo por cobrar", <b className="text-alerta tabular-nums">{dinero(f.saldo)}</b>)}
        {f.uuid && <div className="col-span-2 sm:col-span-3">{dato("Folio fiscal (UUID)",
          <button onClick={() => copiar(f.uuid!)} className="font-mono text-xs hover:text-cobalto" title="Copiar">{f.uuid}</button>)}</div>}
      </div>
      <Vista f={f} />
    </section>
  );
}

/** Vista previa: la misma representación impresa del PDF, en HTML (sale al instante; el PDF se genera sólo al bajarlo). */
function Vista({ f }: { f: Factura }) {
  const { data: html, error } = useSWR<string>(`/facturas/${f.id}/html`, fetcher, { revalidateOnFocus: false, dedupingInterval: 600_000 });
  const caja = useRef<HTMLDivElement>(null);
  const [escala, setEscala] = useState(1);
  useEffect(() => {
    const el = caja.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setEscala(Math.min(1, el.clientWidth / 816)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div className="border-t border-linea bg-papel p-4">
      <div ref={caja} className="relative mx-auto w-full max-w-[816px] overflow-hidden rounded-xl bg-white shadow-tarjeta ring-1 ring-linea" style={{ height: 1056 * escala }}>
        {error ? <p className="p-6 text-sm text-rojo">No se pudo mostrar la vista previa. Baja el PDF.</p>
          : !html ? <div className="esqueleto absolute inset-4" />
          : <iframe title={`Vista previa ${folioDe(f)}`} srcDoc={html} sandbox="" className="absolute left-0 top-0 border-0 bg-white"
              style={{ width: 816, height: 1056, transform: `scale(${escala})`, transformOrigin: "top left" }} />}
      </div>
    </div>
  );
}

function ModalCancelar({ f, onClose, onOk }: { f: Factura | null; onClose: () => void; onOk: () => void }) {
  const [motivo, setMotivo] = useState("02");
  const [sust, setSust] = useState("");
  const [cargando, setCargando] = useState(false);
  const [falla, setFalla] = useState("");  // lo que contestó el servidor, dentro del diálogo (un aviso flotante se pierde de vista)
  // Motivo 01: se ofrecen las facturas vigentes del mismo cliente para elegir la que sustituye (menos riesgo que teclear el UUID)
  const { data: candidatas = [] } = useSWR<Factura[]>(
    f && motivo === "01" && f.cliente_id ? `/facturas?emisor_id=${f.emisor_id}&cliente_id=${f.cliente_id}&estado=timbrada&limit=50` : null, fetcher);
  if (!f) return null;
  const uuidOk = /^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$/i.test(sust);
  const sustituibles = candidatas.filter((c) => c.id !== f.id && c.uuid && c.tipo === "I");
  // El SAT no deja cancelar un ingreso con complementos de pago vivos: se avisa al abrir, no al confirmar
  const conRep = f.tipo === "I" && f.parcialidades > 0;
  const ir = async () => {
    setCargando(true);
    setFalla("");
    try {
      const r = await api<Factura>(`/facturas/${f.id}/cancelar`, { method: "POST", json: { motivo, uuid_sustitucion: sust || null } });
      toast.success(r.estado === "cancelada" ? "Cancelada" : "Solicitud enviada; el receptor debe aceptar");
      onOk();
    } catch (e) {
      setFalla((e as Error).message);
    } finally {
      setCargando(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title={`Cancelar ${f.serie ?? ""}${f.folio ?? ""}`}
      footer={<><Button onClick={onClose}>No cancelar</Button><Button variant="peligro" onClick={ir} loading={cargando} disabled={conRep || (motivo === "01" && !uuidOk)}>Cancelar ante el SAT</Button></>}
    >
      <div className="flex flex-col gap-4">
        <p className="text-sm text-grafito">{f.receptor_nombre} · {dinero(f.total)}</p>
        {conRep && <p className="rounded-lg bg-alerta-suave px-3 py-2 text-sm text-alerta">Esta factura tiene complementos de pago vivos. Cancela primero sus REP (Pagos) y luego vuelve a cancelarla.</p>}
        <Field label="Motivo">
          <Select value={motivo} onChange={(e) => setMotivo(e.target.value)}>
            {Object.entries(MOTIVOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
        {motivo === "01" && (
          <>
            {sustituibles.length > 0 && (
              <Field label="Factura que la sustituye (de este cliente)">
                <Select value={sustituibles.find((c) => c.uuid === sust.toUpperCase())?.uuid ?? ""} onChange={(e) => setSust(e.target.value)}>
                  <option value="">Elige una…</option>
                  {sustituibles.map((c) => <option key={c.id} value={c.uuid!}>{c.serie}{c.folio} · {fecha(c.fecha)} · {dinero(c.total, c.moneda)}</option>)}
                </Select>
              </Field>
            )}
            <Field label={sustituibles.length ? "O pega su UUID" : "UUID de la factura que la sustituye"}
              error={sust && !uuidOk ? "Formato: 8-4-4-4-12 letras y números (A-F, 0-9)" : undefined}>
              <Input value={sust} onChange={(e) => { setSust(e.target.value.trim()); setFalla(""); }} placeholder="5FB2822E-396D-4725-8521-CDC4BDD20CCF" className="font-mono text-xs" />
            </Field>
          </>
        )}
        {falla && <p role="alert" className="rounded-lg bg-rojo-suave px-3 py-2 text-sm text-rojo">{falla}</p>}
      </div>
    </Modal>
  );
}
