"use client";
import { toast } from "sonner";
import { ApiError } from "./api";
import { consola } from "./debug";

/** Toast de error con acceso directo a la traza exacta en la consola.
 *  Si el servidor reconoció el error (catálogo de errores comunes) viene "Título. Qué hacer: … [Detalle del PAC: …]":
 *  se muestra el título grande y la solución abajo; el detalle técnico queda en la consola. */
export function mostrarError(e: unknown) {
  const err = e as ApiError;
  const msg = err?.message || String(e);
  const m = msg.match(/^(.*?)\. Qué hacer: (.*?)(?: \[Detalle del PAC: .*\])?$/s);
  toast.error(m ? m[1] : msg, {
    description: m ? `Qué hacer: ${m[2]}` : undefined,
    duration: m ? 10000 : 8000,  // el detalle sigue en la consola; un aviso largo tapaba los botones del ticket
    action: { label: "Ver detalle", onClick: () => consola.abrir({ req: err?.requestId ?? null }) },
  });
}
