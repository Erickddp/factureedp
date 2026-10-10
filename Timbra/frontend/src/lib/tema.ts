"use client";
/** Tema: "sistema" (sigue a Windows), "claro" u "oscuro". Se guarda por equipo. */
import { useSyncExternalStore } from "react";

export type Tema = "sistema" | "claro" | "oscuro";
const ORDEN: Tema[] = ["sistema", "claro", "oscuro"];
const subs = new Set<() => void>();

function leer(): Tema {
  try {
    const t = localStorage.getItem("timbra_tema");
    return t === "claro" || t === "oscuro" ? t : "sistema";
  } catch {
    return "sistema";
  }
}

function aplicar(t: Tema) {
  const el = document.documentElement;
  if (t === "sistema") delete el.dataset.theme;
  else el.dataset.theme = t === "oscuro" ? "dark" : "light";
}

export const tema = {
  poner(t: Tema) {
    try {
      if (t === "sistema") localStorage.removeItem("timbra_tema");
      else localStorage.setItem("timbra_tema", t);
    } catch {}
    aplicar(t);
    subs.forEach((f) => f());
  },
  siguiente() {
    tema.poner(ORDEN[(ORDEN.indexOf(leer()) + 1) % ORDEN.length]);
  },
};

export function useTema(): Tema {
  return useSyncExternalStore(
    (f) => { subs.add(f); return () => subs.delete(f); },
    leer,
    () => "sistema",
  );
}
