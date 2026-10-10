"use client";
import { consola } from "./debug";

export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId?: string, public traza?: string) {
    super(message);
  }
}

export function getToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("timbra_token");
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem("timbra_token", t);
  else localStorage.removeItem("timbra_token");
}

const SILENCIO = ["/debug/logs", "/facturas/preview"];

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const metodo = (init.method || "GET").toUpperCase();
  const t0 = performance.now();
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, headers, body });
  } catch (e) {
    const msg = "Sin conexión con Timbra. Revisa que esté abierto (ícono junto al reloj o la ventana de INICIAR.bat).";
    consola.red({ metodo, ruta: path, estado: 0, ms: Math.round(performance.now() - t0), error: String(e) });
    throw new ApiError(0, msg);
  }
  const ms = Math.round(performance.now() - t0);
  const req = res.headers.get("x-request-id") ?? undefined;

  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth")) {
    setToken(null);
    window.location.href = "/login/";
  }
  if (!res.ok) {
    let msg = res.statusText || `Error ${res.status}`;
    let traza: string | undefined;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      traza = j.traza;
    } catch {}
    consola.red({ metodo, ruta: path, estado: res.status, ms, req, error: msg });
    throw new ApiError(res.status, msg, req, traza);
  }
  if (!SILENCIO.some((s) => path.startsWith(s))) consola.red({ metodo, ruta: path, estado: res.status, ms, req });
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const fetcher = (path: string): Promise<any> => api(path);

/** Descarga un archivo autenticado (XML/PDF/ZIP). Si llega HTML (sin PDF en el servidor) lo abre para imprimir. */
export async function descargar(path: string, nombre: string) {
  const t0 = performance.now();
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  const req = res.headers.get("x-request-id") ?? undefined;
  consola.red({ metodo: "GET", ruta: path, estado: res.status, ms: Math.round(performance.now() - t0), req });
  if (!res.ok) {
    let msg = "No se pudo descargar";
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {}
    throw new ApiError(res.status, msg, req);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  if (blob.type.includes("html")) {
    window.open(url, "_blank");
    return;
  }
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(url);
}

/** Manda errores del navegador al registro del servidor (se ven en la consola). */
let ultimoReporte = 0;
export function reportarNavegador(mensaje: string, datos?: Record<string, unknown>) {
  const ahora = Date.now();
  if (ahora - ultimoReporte < 1000) return;
  ultimoReporte = ahora;
  fetch("/api/debug/cliente", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ nivel: "error", mensaje, datos: { ...datos, url: location.pathname } }),
  }).catch(() => {});
}
