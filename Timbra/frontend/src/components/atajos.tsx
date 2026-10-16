"use client";
/** Atajos globales, ayuda (F1 o ?) y paleta de comandos (Ctrl+K). */
import { useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { api, fetcher } from "@/lib/api";
import { consola } from "@/lib/debug";
import { mostrarError } from "@/lib/errores";
import { tema } from "@/lib/tema";
import type { Plantilla } from "@/lib/types";
import { useEmisor } from "./emisor-context";
import { Kbd, Modal, cx } from "./ui";

export const ATAJOS: { grupo: string; items: [string, string][] }[] = [
  { grupo: "En todas partes", items: [
    ["F2", "Nueva factura"], ["Ctrl + K", "Buscar pantalla o acción"], ["Ctrl + B", "Plegar o abrir el menú lateral"], ["F9", "Consola de depuración"], ["F1 o ?", "Esta ayuda"], ["Esc", "Cerrar ventana o menú"],
    ["Ctrl + Shift + L", "Tema: sistema → claro → oscuro"],
  ] },
  { grupo: "Ir rápido", items: [
    ["Alt + Shift + 1 … 9", "Abrir plantilla favorita en Facturar (luego Ctrl + Enter)"], ["Alt + R", "Recurrentes y favoritas"], ["Alt + L", "Lotes desde tabla"], ["Alt + J", "Pendientes"], ["Alt + K", "Investigar clave SAT"],
    ["Alt + E", "Nómina (empleados)"], ["Alt + B", "Cobranza"], ["Alt + F", "Facturas emitidas"], ["Alt + T", "Timbres"],
  ] },
  { grupo: "Nómina", items: [
    ["Alt + Q", "Armar la quincena de todos (recetas)"], ["Ctrl + Enter", "Timbrar los recibos marcados"], ["Tab / Enter", "Siguiente importe"],
  ] },
  { grupo: "Facturar", items: [
    ["Ctrl + Enter", "Timbrar"], ["Alt + C", "Ir a cliente"], ["Alt + G", "Lista de clientes guardados"], ["Alt + I", "Mis conceptos (catálogo y ya facturados)"], ["Alt + A", "Agregar concepto"], ["Alt + 1 … 4", "Factura · Público · Nota de crédito · Traslado"],
    ["Alt + M", "Cambiar PUE ⇄ PPD"], ["Alt + O", "Opciones avanzadas"], ["Alt + P", "Usar plantilla"], ["Ctrl + S", "Guardar como plantilla"],
    ["Alt + U", "Repetir la última factura del cliente elegido"],
  ] },
  { grupo: "Conceptos (como en Excel)", items: [
    ["Enter", "Siguiente campo; al final crea otra fila"], ["Shift + Enter", "Campo anterior"], ["↑ ↓", "Misma columna, fila de arriba/abajo"],
    ["Tab", "Recorre todos los campos"], ["Ctrl + D", "Duplicar concepto"], ["Ctrl + Supr", "Borrar concepto"], ["Alt + ↑ ↓", "Mover concepto"],
    ["=14500/1.16", "En precio: escribe operaciones (quitar IVA)"], ["F4 en precio", "Calcular desde precio con IVA o lo depositado"],
  ] },
];

const AyudaCtx = createContext<{ abrirAyuda: () => void; abrirPaleta: () => void }>({ abrirAyuda: () => {}, abrirPaleta: () => {} });
export const useAtajos = () => useContext(AyudaCtx);

const enCampo = (el: EventTarget | null) => {
  const t = el as HTMLElement | null;
  return !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
};

export function AtajosProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ayuda, setAyuda] = useState(false);
  const [paleta, setPaleta] = useState(false);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const ir = (ruta: string) => { e.preventDefault(); router.push(ruta); };
      if (e.altKey && e.shiftKey && /^Digit[1-9]$/.test(e.code)) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("timbra:favorita", { detail: Number(e.code.slice(5)) }));
      }
      else if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "l") { e.preventDefault(); tema.siguiente(); }
      else if (e.altKey && !e.shiftKey && !e.ctrlKey && e.code === "KeyR") ir("/recurrentes");
      else if (e.altKey && !e.shiftKey && !e.ctrlKey && e.code === "KeyE") ir("/nomina");
      else if (e.altKey && !e.shiftKey && !e.ctrlKey && e.code === "KeyB") ir("/cobranza");
      else if (e.altKey && !e.shiftKey && !e.ctrlKey && e.code === "KeyL") ir("/lotes");
      else if (e.altKey && !e.shiftKey && !e.ctrlKey && e.code === "KeyJ") ir("/pendientes");
      else if (e.altKey && !e.shiftKey && !e.ctrlKey && e.code === "KeyK") ir("/claves");
      else if (e.altKey && !e.shiftKey && !e.ctrlKey && e.code === "KeyF") ir("/facturas");
      else if (e.altKey && !e.shiftKey && !e.ctrlKey && e.code === "KeyT") ir("/timbres");
      else if (e.key === "F2") { e.preventDefault(); window.dispatchEvent(new Event("timbra:nueva")); router.push("/facturar"); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPaleta(true); }
      else if (e.key === "F1" || (e.key === "?" && !enCampo(e.target))) { e.preventDefault(); setAyuda(true); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [router]);

  return (
    <AyudaCtx.Provider value={{ abrirAyuda: () => setAyuda(true), abrirPaleta: () => setPaleta(true) }}>
      <Favoritas />
      {children}
      <Modal open={ayuda} onClose={() => setAyuda(false)} title="Atajos de teclado" wide>
        <div className="grid gap-6 md:grid-cols-2">
          {ATAJOS.map((g) => (
            <div key={g.grupo} className={g.grupo.startsWith("Conceptos") ? "md:col-span-2" : ""}>
              <h3 className="mb-2 font-semibold">{g.grupo}</h3>
              <dl className="grid gap-1.5 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-4">
                {g.items.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt><Kbd>{k}</Kbd></dt>
                    <dd className="mb-1 text-grafito sm:mb-0">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </Modal>
      <Paleta abierta={paleta} cerrar={() => setPaleta(false)} ayuda={() => { setPaleta(false); setAyuda(true); }} />
    </AyudaCtx.Provider>
  );
}

/** Alt+Shift+número → abre la plantilla favorita del emisor activo en Facturar. */
function Favoritas() {
  const router = useRouter();
  const { emisor } = useEmisor();
  const { data = [] } = useSWR<Plantilla[]>(emisor ? `/plantillas?emisor_id=${emisor.id}` : null, fetcher);
  useEffect(() => {
    const f = (e: Event) => {
      const n = (e as CustomEvent<number>).detail;
      const p = data.find((x) => x.favorita === n);
      if (p) router.push(`/facturar?plantilla=${p.id}`);
      else toast.message(`No hay favorita ${n}. Asígnala en Recurrentes y favoritas.`);
    };
    window.addEventListener("timbra:favorita", f);
    return () => window.removeEventListener("timbra:favorita", f);
  }, [data, router]);
  return null;
}

function Paleta({ abierta, cerrar, ayuda }: { abierta: boolean; cerrar: () => void; ayuda: () => void }) {
  const router = useRouter();
  const { emisores, emisor, setEmisorId, confirmarTimbre } = useEmisor();
  const { data: plantillas = [] } = useSWR<Plantilla[]>(abierta && emisor ? `/plantillas?emisor_id=${emisor.id}` : null, fetcher);
  const [q, setQ] = useState("");
  const [act, setAct] = useState(0);
  const lista = useRef<HTMLUListElement>(null);

  const comandos = useMemo(() => {
    const ir = (ruta: string) => () => router.push(ruta);
    const base = [
      { t: "Nueva factura", k: "F2", f: ir("/facturar") },
      { t: "Facturas emitidas", f: ir("/facturas") },
      { t: "Plantillas", f: ir("/plantillas") },
      { t: "Complementos de pago", f: ir("/pagos") },
      { t: "Calculadora de impuestos (IVA 16/8/0, exento, retenciones)", f: ir("/calculadora") },
      { t: "Clientes", f: ir("/clientes") },
      { t: "Importar clientes desde Excel", f: ir("/clientes?importar=1") },
      { t: "Productos y servicios", f: ir("/productos") },
      { t: "Emisores y CSD", f: ir("/emisores") },
      { t: "PAC, addendas y usuarios", f: ir("/ajustes") },
      { t: "Resumen del mes", f: ir("/") },
      { t: "Recurrentes y favoritas (igualas, rentas)", k: "Alt R", f: ir("/recurrentes") },
      { t: "Pendientes: todo lo que necesita una acción tuya", k: "Alt J", f: ir("/pendientes") },
      { t: "Revisar clientes: datos por corregir, duplicados, lista 69-B", f: ir("/clientes?revisar=1") },
      { t: "Claves SAT: investigar la clave de un producto o servicio", k: "Alt K", f: ir("/claves") },
      { t: "Catálogos sugeridos y importar productos", f: ir("/productos") },
      { t: "Lotes: facturar desde una tabla (pegar de Excel/Sheets o CSV)", k: "Alt L", f: ir("/lotes") },
      { t: "Nómina: armar y timbrar recibos", k: "Alt E", f: ir("/nomina") },
      { t: "Nómina: empleados", f: ir("/nomina?vista=empleados") },
      { t: "Cobranza: saldos vencidos y recordatorios", k: "Alt B", f: ir("/cobranza") },
      { t: "Descarga masiva SAT (recibidos para COI)", f: ir("/sat") },
      { t: "Autofactura: portal y tickets", f: ir("/portal") },
      { t: "Timbres: saldo y consumo", k: "Alt T", f: ir("/timbres") },
      { t: "Marca del PDF, nómina y e.firma", f: ir("/marca") },
      { t: "A cuenta de terceros (catálogo)", f: ir("/terceros") },
      { t: "Configurar la barra de Facturar (simple, estándar, completo, perfiles)", f: ir("/facturar?configurar=1") },
      { t: "Tema claro", f: () => tema.poner("claro") },
      { t: "Tema oscuro", f: () => tema.poner("oscuro") },
      { t: "Tema como el sistema", f: () => tema.poner("sistema") },
      { t: "Abrir consola de depuración", k: "F9", f: () => consola.abrir() },
      { t: "Estado de servicios (PAC, correo, CSD)", f: () => consola.abrir({ pestana: "servicios" }) },
      { t: "Atajos de teclado", k: "F1", f: ayuda },
    ];
    const cambios = emisores.map((e) => ({ t: `Cambiar a emisor ${e.rfc} · ${e.nombre}`, f: () => setEmisorId(e.id) }));
    const usar = plantillas.map((p) => ({
      t: `Facturar con plantilla: ${p.nombre}${p.cliente_nombre ? ` · ${p.cliente_nombre}` : ""}`,
      k: p.favorita ? `Alt ⇧ ${p.favorita}` : undefined, f: ir(`/facturar?plantilla=${p.id}`),
    }));
    const timbrar = plantillas.filter((p) => p.recurrente && p.proxima && new Date(p.proxima) <= new Date()).map((p) => ({
      t: `Timbrar ya la recurrente: ${p.nombre}`,
      f: async () => {
        if (!(await confirmarTimbre())) return;
        api<{ folio: string }>(`/plantillas/${p.id}/timbrar`, { method: "POST" }).then((r) => toast.success(`Timbrada ${r.folio}`)).catch(mostrarError);
      },
    }));
    return [...timbrar, ...base, ...usar, ...cambios] as { t: string; f: () => void; k?: string }[];
  }, [router, emisores, setEmisorId, ayuda, plantillas, confirmarTimbre]);

  const filtrados = comandos.filter((c) => q.split(" ").every((p) => c.t.toLowerCase().includes(p.toLowerCase())));
  useEffect(() => { setAct(0); }, [q]);
  useEffect(() => { if (abierta) setQ(""); }, [abierta]);
  useEffect(() => { lista.current?.children[act]?.scrollIntoView({ block: "nearest" }); }, [act]);

  const ejecutar = (i: number) => { const c = filtrados[i]; if (c) { cerrar(); c.f(); } };
  if (!abierta) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-tinta/40 p-3 pt-[12vh]" onMouseDown={cerrar}>
      <div className="w-full max-w-xl overflow-hidden rounded-2xl bg-hoja shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setAct((a) => Math.min(a + 1, filtrados.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setAct((a) => Math.max(a - 1, 0)); }
            if (e.key === "Enter") { e.preventDefault(); ejecutar(act); }
            if (e.key === "Escape") cerrar();
          }}
          placeholder="¿A dónde vas o qué hacemos?"
          className="h-14 w-full border-b border-linea px-5 text-base focus:outline-none"
        />
        <ul ref={lista} className="max-h-[50vh] overflow-auto p-1.5">
          {filtrados.map((c, i) => (
            <li key={c.t}>
              <button onMouseEnter={() => setAct(i)} onClick={() => ejecutar(i)} className={cx("flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left text-sm", i === act && "bg-cobalto-suave")}>
                <span className="min-w-0 truncate">{c.t}</span>
                {c.k && <Kbd>{c.k}</Kbd>}
              </button>
            </li>
          ))}
          {!filtrados.length && <li className="px-3 py-6 text-center text-sm text-grafito">Nada con “{q}”.</li>}
        </ul>
      </div>
    </div>
  );
}
