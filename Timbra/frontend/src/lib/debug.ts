"use client";
/** Estado compartido de la consola de depuración (sin librerías). */
import { useSyncExternalStore } from "react";

export type Red = {
  id: number;
  t: number;
  metodo: string;
  ruta: string;
  estado: number;
  ms: number;
  req?: string;
  error?: string;
};

type Estado = {
  abierta: boolean;
  pestana: "registro" | "servicios" | "red";
  filtroReq: string | null;
  red: Red[];
  erroresNuevos: number;
};

let estado: Estado = { abierta: false, pestana: "registro", filtroReq: null, red: [], erroresNuevos: 0 };
const oyentes = new Set<() => void>();
let seq = 1;

function set(p: Partial<Estado>) {
  estado = { ...estado, ...p };
  oyentes.forEach((f) => f());
}

export const consola = {
  abrir(opts: { req?: string | null; pestana?: Estado["pestana"] } = {}) {
    set({ abierta: true, filtroReq: opts.req ?? null, pestana: opts.pestana ?? "registro", erroresNuevos: 0 });
  },
  cerrar() {
    set({ abierta: false });
  },
  alternar() {
    estado.abierta ? consola.cerrar() : consola.abrir();
  },
  pestana(p: Estado["pestana"]) {
    set({ pestana: p });
  },
  filtrarReq(req: string | null) {
    set({ filtroReq: req, pestana: "registro" });
  },
  red(r: Omit<Red, "id" | "t">) {
    const nuevo = { ...r, id: seq++, t: Date.now() };
    set({
      red: [nuevo, ...estado.red].slice(0, 300),
      erroresNuevos: estado.abierta || r.estado < 400 ? estado.erroresNuevos : estado.erroresNuevos + 1,
    });
  },
};

export function useConsola() {
  return useSyncExternalStore(
    (f) => {
      oyentes.add(f);
      return () => oyentes.delete(f);
    },
    () => estado,
    () => estado,
  );
}
