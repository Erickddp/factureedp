"use client";
import { createContext, useContext, useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Emisor } from "@/lib/types";

// cargando: la lista de emisores aún no llega. Sin esto, «no hay emisor» se confundía con «todavía no sé».
type Ctx = { emisores: Emisor[]; emisor: Emisor | null; cargando: boolean; setEmisorId: (id: number) => void; recargar: () => void };
const EmisorCtx = createContext<Ctx>({ emisores: [], emisor: null, cargando: true, setEmisorId: () => {}, recargar: () => {} });

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
    setId(n);
  };
  return <EmisorCtx.Provider value={{ emisores: data, emisor, cargando: isLoading, setEmisorId, recargar: () => mutate() }}>{children}</EmisorCtx.Provider>;
}

export const useEmisor = () => useContext(EmisorCtx);
