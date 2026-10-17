"use client";
/** Consola de depuración: registro en vivo del servidor, estado de servicios y red del navegador. F9 abre/cierra. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Copy, Download, Maximize2, Minimize2, Pause, Play, RefreshCw, Trash2, X } from "lucide-react";
import { api, descargar, fetcher } from "@/lib/api";
import { consola, useConsola } from "@/lib/debug";
import { mostrarError } from "@/lib/errores";
import { Badge, Button, Input, Select, cx } from "./ui";

type Item = { id: number; ts: number; nivel: string; origen: string; mensaje: string; req: string; datos: unknown; traza: string | null };
type Servicio = { nombre: string; estado: "ok" | "aviso" | "error"; detalle: string; ms: number | null; grupo: string };

const TONO: Record<string, "rojo" | "alerta" | "neutro" | "cobalto"> = { ERROR: "rojo", CRITICAL: "rojo", WARNING: "alerta", INFO: "cobalto", DEBUG: "neutro" };
const hora = (ts: number) => new Date(ts).toLocaleTimeString("es-MX", { hour12: false }) + "." + String(Math.floor(ts % 1000)).padStart(3, "0");

export function Consola() {
  const st = useConsola();
  const [alta, setAlta] = useState(false);
  // El registro del servidor y el estado de los servicios son sólo del administrador: una cuenta normal sólo ve la red de su navegador
  // (sin preguntarle al servidor cada segundo algo que siempre contesta 403). Misma llave que el resto de la app: no pide nada extra.
  const { data: yo } = useSWR<{ admin: boolean }>("/auth/yo", fetcher);
  const admin = !!yo?.admin;
  const pestana = admin ? st.pestana : "red";
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "F9") { e.preventDefault(); consola.alternar(); }
      if (e.key === "Escape" && st.abierta && !document.querySelector("[role=dialog]")) consola.cerrar();
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [st.abierta]);
  if (!st.abierta) return null;
  return (
    <section
      aria-label="Consola de depuración"
      className={cx("fixed inset-x-0 bottom-0 z-40 flex flex-col border-t-2 border-tinta bg-hoja shadow-[0_-12px_40px_rgba(21,32,51,.18)]", alta ? "h-[85dvh]" : "h-[45dvh] min-h-72")}
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-linea px-3 py-2">
        <strong className="mr-2 text-sm">Consola</strong>
        {(admin ? ["registro", "servicios", "red"] as const : ["red"] as const).map((p) => (
          <button key={p} onClick={() => consola.pestana(p)} className={cx("rounded-md px-3 py-1 text-sm", pestana === p ? "bg-tinta text-white" : "text-grafito hover:bg-tinta/5")}>
            {{ registro: "Registro", servicios: "Servicios", red: "Red del navegador" }[p]}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => setAlta((a) => !a)} title={alta ? "Reducir" : "Agrandar"} className="rounded-md p-1.5 hover:bg-tinta/5">
            {alta ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </button>
          <button onClick={consola.cerrar} title="Cerrar (F9)" className="rounded-md p-1.5 hover:bg-tinta/5"><X className="size-4" /></button>
        </div>
      </header>
      <div className="min-h-0 flex-1">
        {pestana === "registro" && <Registro filtroReq={st.filtroReq} />}
        {pestana === "servicios" && <Servicios />}
        {pestana === "red" && <RedNavegador admin={admin} />}
      </div>
    </section>
  );
}

function Registro({ filtroReq }: { filtroReq: string | null }) {
  const [items, setItems] = useState<Item[]>([]);
  const [nivel, setNivel] = useState("DEBUG");
  const [q, setQ] = useState("");
  const [pausa, setPausa] = useState(false);
  const [abiertos, setAbiertos] = useState<Set<number>>(new Set());
  const ultimo = useRef(0);
  const caja = useRef<HTMLDivElement>(null);
  const pegado = useRef(true);

  const traer = useCallback(async () => {
    try {
      const r = await api<{ items: Item[]; ultimo: number }>(`/debug/logs?despues=${ultimo.current}&limite=800`);
      if (r.items.length) {
        ultimo.current = r.items[r.items.length - 1].id;
        setItems((prev) => [...prev, ...r.items.map((i) => ({ ...i, ts: i.ts * 1000 }))].slice(-3000));
      }
    } catch {}
  }, []);

  useEffect(() => {
    traer();
    if (pausa) return;
    const t = setInterval(traer, 1500);
    return () => clearInterval(t);
  }, [traer, pausa]);

  useEffect(() => {
    if (pegado.current && caja.current) caja.current.scrollTop = caja.current.scrollHeight;
  }, [items]);

  const orden = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];
  const visibles = useMemo(() => {
    const min = orden.indexOf(nivel);
    const qq = q.toLowerCase();
    return items.filter((i) =>
      orden.indexOf(i.nivel) >= min &&
      (!filtroReq || i.req === filtroReq) &&
      (!qq || (i.mensaje + " " + i.origen + " " + (i.traza ?? "")).toLowerCase().includes(qq)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, nivel, q, filtroReq]);

  const copiar = (lista: Item[]) => {
    const txt = lista.map((i) => `${hora(i.ts)} ${i.nivel} [${i.req}] ${i.origen}: ${i.mensaje}${i.datos ? "\n  datos: " + JSON.stringify(i.datos) : ""}${i.traza ? "\n" + i.traza : ""}`).join("\n");
    navigator.clipboard.writeText(txt).then(() => toast.success("Copiado. Pégaselo a Claude Code tal cual."));
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-linea px-3 py-2">
        <Select value={nivel} onChange={(e) => setNivel(e.target.value)} className="h-8 w-40 text-xs" aria-label="Nivel mínimo">
          <option value="DEBUG">Todo (detalle)</option>
          <option value="INFO">Procesos</option>
          <option value="WARNING">Avisos y errores</option>
          <option value="ERROR">Sólo errores</option>
        </Select>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrar texto…" className="h-8 w-44 text-xs sm:w-64" />
        {filtroReq && (
          <button onClick={() => consola.filtrarReq(null)} className="rounded-full bg-cobalto-suave px-2.5 py-1 text-xs text-cobalto">
            Folio {filtroReq} ✕
          </button>
        )}
        <div className="ml-auto flex flex-wrap gap-1">
          <Button size="sm" variant="fantasma" onClick={() => setPausa((p) => !p)}>{pausa ? <Play className="size-4" /> : <Pause className="size-4" />}<span className="hidden sm:inline">{pausa ? "Reanudar" : "Pausar"}</span></Button>
          <Button size="sm" variant="fantasma" onClick={() => copiar(visibles)}><Copy className="size-4" /><span className="hidden sm:inline">Copiar</span></Button>
          <Button size="sm" variant="fantasma" onClick={() => setItems([])}><Trash2 className="size-4" /><span className="hidden sm:inline">Limpiar vista</span></Button>
          <Button size="sm" variant="fantasma" onClick={() => descargar("/debug/descargar", "timbra.log").catch(mostrarError)}><Download className="size-4" /><span className="hidden sm:inline">Archivo .log</span></Button>
        </div>
      </div>
      <div
        ref={caja}
        onScroll={(e) => { const el = e.currentTarget; pegado.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40; }}
        className="min-h-0 flex-1 overflow-auto font-[ui-monospace,SFMono-Regular,Menlo,Consolas,monospace] text-[12px] leading-5"
      >
        {!visibles.length && <p className="p-4 text-grafito">Sin eventos con esos filtros. Todo lo que haga Timbra aparece aquí en vivo.</p>}
        {visibles.map((i) => {
          const abierto = abiertos.has(i.id);
          const extra = i.traza || i.datos;
          return (
            <div key={i.id} className={cx("border-b border-linea/60 px-3 py-1", (i.nivel === "ERROR" || i.nivel === "CRITICAL") && "bg-rojo-suave/60", i.nivel === "WARNING" && "bg-alerta-suave/50")}>
              <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                <span className="text-grafito tabular-nums">{hora(i.ts)}</span>
                <Badge tono={TONO[i.nivel] ?? "neutro"} className="!px-1.5 !py-0 text-[10px]">{i.nivel}</Badge>
                {i.req && i.req !== "-" && (
                  <button onClick={() => consola.filtrarReq(i.req)} className="text-cobalto hover:underline" title="Ver sólo este folio">{i.req}</button>
                )}
                <span className="text-grafito">{i.origen}</span>
                <span className="min-w-0 flex-1 break-words">{i.mensaje}</span>
                {Boolean(extra) && (
                  <button onClick={() => setAbiertos((s) => { const n = new Set(s); n.has(i.id) ? n.delete(i.id) : n.add(i.id); return n; })} className="text-cobalto hover:underline">
                    {abierto ? "ocultar" : i.traza ? "ver traza" : "ver datos"}
                  </button>
                )}
                <button onClick={() => copiar([i])} className="text-grafito hover:text-tinta" title="Copiar este evento"><Copy className="size-3.5" /></button>
              </div>
              {abierto && (
                <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-tinta p-2 text-[11px] text-white">
                  {i.datos ? JSON.stringify(i.datos, null, 2) + "\n" : ""}{i.traza ?? ""}
                </pre>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Servicios() {
  const [data, setData] = useState<Servicio[] | null>(null);
  const [cargando, setCargando] = useState(false);
  const [correo, setCorreo] = useState("");
  const revisar = useCallback(async () => {
    setCargando(true);
    try { setData(await api<Servicio[]>("/debug/servicios")); } catch (e) { mostrarError(e); } finally { setCargando(false); }
  }, []);
  useEffect(() => { revisar(); }, [revisar]);
  const probar = async () => {
    try { await api("/debug/probar-correo", { method: "POST", json: { para: correo } }); toast.success("Correo de prueba enviado"); } catch (e) { mostrarError(e); }
  };
  return (
    <div className="h-full overflow-auto p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={revisar} loading={cargando}><RefreshCw className="size-4" /> Revisar de nuevo</Button>
        <div className="flex gap-1">
          <Input value={correo} onChange={(e) => setCorreo(e.target.value)} placeholder="tu@correo.com" className="h-8 w-52 text-xs" />
          <Button size="sm" onClick={probar} disabled={!correo.includes("@")}>Probar correo</Button>
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {data?.map((s) => (
          <div key={s.nombre} className={cx("rounded-xl border p-3", s.estado === "ok" ? "border-sello/30 bg-sello-suave/40" : s.estado === "aviso" ? "border-alerta/30 bg-alerta-suave/50" : "border-rojo/30 bg-rojo-suave/60")}>
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium">{s.nombre}</p>
              <Badge tono={s.estado === "ok" ? "sello" : s.estado === "aviso" ? "alerta" : "rojo"}>
                {s.estado === "ok" ? "Conectado" : s.estado === "aviso" ? "Revisar" : "Falla"}{s.ms != null ? ` · ${s.ms} ms` : ""}
              </Badge>
            </div>
            <p className="mt-1 break-words text-xs text-grafito">{s.detalle}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function RedNavegador({ admin }: { admin: boolean }) {
  const { red } = useConsola();
  return (
    <div className="h-full overflow-auto text-[12px]">
      {!admin && <p className="border-b border-linea px-3 py-2 text-grafito">Estas son las peticiones de tu navegador a Timbra. Si algo falla, copia esta lista (y lo que dice el aviso rojo) y mándala a soporte.</p>}
      {!red.length && <p className="p-4 text-grafito">Aún no hay peticiones.</p>}
      <table className="w-full min-w-[640px]">
        <tbody>
          {red.map((r) => (
            <tr key={r.id} className={cx("border-b border-linea/60", r.estado >= 400 || r.estado === 0 ? "bg-rojo-suave/60" : "")}>
              <td className="px-3 py-1 text-grafito tabular-nums">{new Date(r.t).toLocaleTimeString("es-MX", { hour12: false })}</td>
              <td className="px-2 py-1 font-medium">{r.metodo}</td>
              <td className="max-w-[40vw] truncate px-2 py-1">{r.ruta}</td>
              <td className="px-2 py-1 tabular-nums">{r.estado || "sin red"}</td>
              <td className="px-2 py-1 tabular-nums text-grafito">{r.ms} ms</td>
              <td className="px-2 py-1">{r.req && (admin ? <button onClick={() => consola.filtrarReq(r.req!)} className="text-cobalto hover:underline">{r.req}</button> : <span className="text-grafito">{r.req}</span>)}</td>
              <td className="px-2 py-1 text-rojo">{r.error}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
