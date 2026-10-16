"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Emisor } from "@/lib/types";
import { Button, Modal, cx } from "./ui";

// Dónde timbra el emisor. Sólo «produccion» vale ante el SAT y gasta timbres reales. null = el servidor aún no lo dice
// (pantallas nuevas con un servidor sin actualizar): sin distintivo ni confirmación, como antes; nunca adivinar «producción».
export type Ambiente = "produccion" | "pruebas" | "demo";
export const ambienteDe = (e?: Pick<Emisor, "ambiente" | "modo_demo"> | null): Ambiente | null => e?.ambiente ?? (e?.modo_demo ? "demo" : null);
const NOMBRE: Record<Ambiente, string> = { produccion: "Producción", pruebas: "Pruebas", demo: "Demo" };

/** Distintivo del ambiente. Fuera de un botón sólo se pinta en pruebas y demo (producción es lo normal);
 *  dentro de un botón de timbrar se pinta siempre, para que quien timbra (persona o asistente) lea dónde lo hace. */
export function EtiquetaAmbiente({ ambiente, enBoton, className }: { ambiente: Ambiente | null; enBoton?: boolean; className?: string }) {
  if (!ambiente || (!enBoton && ambiente === "produccion")) return null;
  return (
    <span className={cx("inline-flex shrink-0 items-center rounded px-1.5 py-px text-[10px] font-semibold uppercase leading-4 tracking-wide",
      enBoton ? "bg-current/15" : "bg-alerta text-hoja", className)}>{NOMBRE[ambiente]}</span>
  );
}

// El emisor de producción ya confirmado en esta pestaña. Cambiar de emisor lo borra: el primer timbre después pregunta.
const CONFIRMADO = "timbra_prod_ok";
const leerConfirmado = () => { try { return sessionStorage.getItem(CONFIRMADO); } catch { return null; } };
const guardarConfirmado = (v: string | null) => { try { if (v) sessionStorage.setItem(CONFIRMADO, v); else sessionStorage.removeItem(CONFIRMADO); } catch {} };

// cargando: la lista de emisores aún no llega. Sin esto, «no hay emisor» se confundía con «todavía no sé».
// confirmarTimbre: llámalo antes de timbrar; en producción, la primera vez tras cambiar de emisor pregunta (false = no timbres).
// { visto: true } si la pantalla ya mostró el emisor y su ambiente en su propia confirmación (lotes): no pregunta dos veces.
type Ctx = { emisores: Emisor[]; emisor: Emisor | null; cargando: boolean; setEmisorId: (id: number) => void; recargar: () => void; confirmarTimbre: (o?: { visto?: boolean }) => Promise<boolean> };
const EmisorCtx = createContext<Ctx>({ emisores: [], emisor: null, cargando: true, setEmisorId: () => {}, recargar: () => {}, confirmarTimbre: async () => true });

export function EmisorProvider({ children }: { children: React.ReactNode }) {
  const { data = [], mutate, isLoading } = useSWR<Emisor[]>("/emisores", fetcher);
  const [id, setId] = useState<number | null>(null);

  useEffect(() => {
    const guardado = Number(localStorage.getItem("timbra_emisor"));
    if (guardado) setId(guardado);
  }, []);

  const emisor = data.find((e) => e.id === id) ?? data[0] ?? null;
  const setEmisorId = (n: number) => {
    localStorage.setItem("timbra_emisor", String(n));
    if (n !== emisor?.id) guardarConfirmado(null);
    setId(n);
  };

  const [pregunta, setPregunta] = useState<Emisor | null>(null);
  const respuesta = useRef<((ok: boolean) => void) | null>(null);
  const confirmarTimbre = useCallback((o?: { visto?: boolean }): Promise<boolean> => {
    if (!emisor || ambienteDe(emisor) !== "produccion" || leerConfirmado() === String(emisor.id)) return Promise.resolve(true);
    if (o?.visto) { guardarConfirmado(String(emisor.id)); return Promise.resolve(true); }
    respuesta.current?.(false);
    setPregunta(emisor);
    return new Promise((r) => { respuesta.current = r; });
  }, [emisor]);
  const responder = (ok: boolean) => {
    if (ok && pregunta) guardarConfirmado(String(pregunta.id));
    respuesta.current?.(ok);
    respuesta.current = null;
    setPregunta(null);
  };

  return (
    <EmisorCtx.Provider value={{ emisores: data, emisor, cargando: isLoading, setEmisorId, recargar: () => mutate(), confirmarTimbre }}>
      {children}
      <Modal open={!!pregunta} onClose={() => responder(false)} title="Timbrar en producción"
        footer={<><Button onClick={() => responder(false)}>Cancelar</Button>
          <Button variant="acento" data-autofocus onClick={() => responder(true)}>Sí, timbrar con {pregunta?.rfc}</Button></>}>
        <div className="grid gap-3 text-sm">
          <div className="rounded-xl bg-papel px-4 py-3 ring-1 ring-linea">
            <p className="break-words font-semibold">{pregunta?.nombre}</p>
            <p className="tabular-nums text-grafito">{pregunta?.rfc}</p>
          </div>
          <p>Este emisor timbra en <b>producción</b>: lo que timbres tiene validez ante el SAT y gasta timbres reales. Si no es el emisor que querías, cancela y cámbialo en el menú.</p>
          <p className="text-xs text-grafito">Sólo se pregunta la primera vez que timbras después de cambiar de emisor.</p>
        </div>
      </Modal>
    </EmisorCtx.Provider>
  );
}

export const useEmisor = () => useContext(EmisorCtx);
