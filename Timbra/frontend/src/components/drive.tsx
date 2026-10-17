"use client";
/** Copia de los XML de la cuenta a su Google Drive (backend services/drive.py). Sólo XML: nada de PDF ni datos de la cuenta. */
import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CheckCircle2, HardDriveUpload, RefreshCw, TriangleAlert } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { Button, cx } from "./ui";

type EstadoDrive = {
  configurado: boolean; conectado: boolean; correo?: string | null; estado?: "activa" | "sincronizando" | "error" | "revocada";
  error?: string | null; subidos?: number; faltan?: number; ultimo?: string | null;
};

const hace = (iso?: string | null) => {
  if (!iso) return "todavía no";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return min < 1 ? "hace un momento" : min < 60 ? `hace ${min} min` : min < 1440 ? `hace ${Math.round(min / 60)} h` : new Date(iso).toLocaleDateString("es-MX");
};

export function DriveTarjeta() {
  const [copiando, setCopiando] = useState(false);
  const { data: d, mutate } = useSWR<EstadoDrive>("/drive", fetcher, {
    refreshInterval: (x) => (x?.estado === "sincronizando" ? 3000 : 60_000),
  });
  const [seguro, setSeguro] = useState(false);

  // Regreso de Google: el resultado viene en el fragmento (#drive=ok o #drive_error=…)
  useEffect(() => {
    const h = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    if (!h.has("drive") && !h.has("drive_error")) return;
    history.replaceState(null, "", window.location.pathname);
    if (h.get("drive") === "ok") toast.success("Google Drive conectado. Copiando tus XML…");
    else toast.error(h.get("drive_error") || "No se conectó Google Drive.");
    mutate();
  }, [mutate]);

  if (!d?.configurado) return null;

  const conectar = async () => {
    try { window.location.href = (await api<{ url: string }>("/drive/conectar", { method: "POST" })).url; } catch (e) { mostrarError(e); }
  };
  const copiar = async () => {
    setCopiando(true);
    try { await api("/drive/sincronizar", { method: "POST" }); await mutate(); } catch (e) { mostrarError(e); } finally { setCopiando(false); }
  };
  const desconectar = async () => {
    try { await api("/drive", { method: "DELETE" }); toast.success("Drive desconectado. Lo que ya copiaste sigue en tu Drive."); setSeguro(false); mutate(); }
    catch (e) { mostrarError(e); }
  };

  if (!d.conectado)
    return (
      <section className="flex flex-wrap items-center gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-acento-suave text-acento"><HardDriveUpload className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Guarda tus XML en tu Google Drive</p>
          <p className="text-sm text-grafito">Timbra copia tus XML (los del SAT y los que timbras) a una carpeta «Timbra» de tu Drive, ordenados por RFC y mes. Sólo XML; no ve nada más de tu Drive.</p>
        </div>
        <Button variant="acento" onClick={conectar}>Conectar Google Drive</Button>
      </section>
    );

  const sinc = d.estado === "sincronizando";
  const mal = d.estado === "error" || d.estado === "revocada";
  return (
    <section className={cx("flex flex-wrap items-center gap-4 rounded-2xl bg-hoja p-5 ring-1", mal ? "ring-alerta/50" : "ring-linea")}>
      <span className={cx("grid size-11 shrink-0 place-items-center rounded-xl", mal ? "bg-alerta-suave text-alerta" : "bg-sello-suave text-sello")}>
        {mal ? <TriangleAlert className="size-5" /> : sinc ? <RefreshCw className="size-5 animate-spin" /> : <CheckCircle2 className="size-5" />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold">Google Drive{d.correo ? <span className="font-normal text-grafito"> · {d.correo}</span> : null}</p>
        <p className="text-sm text-grafito">
          {sinc ? `Copiando… ${d.subidos ?? 0} XML ya están en tu Drive` :
            `${d.subidos ?? 0} XML en tu Drive · última copia ${hace(d.ultimo)}${d.faltan ? ` · faltan ${d.faltan}` : ""}`}
        </p>
        {mal && d.error && <p className="mt-1 text-sm text-alerta">{d.error}</p>}
      </div>
      <div className="flex flex-wrap gap-2">
        {d.estado === "revocada"
          ? <Button variant="acento" onClick={conectar}>Volver a conectar</Button>
          : <Button onClick={copiar} loading={copiando} disabled={sinc}><RefreshCw className="size-4" /> Copiar ahora</Button>}
        {seguro
          ? <Button variant="peligro" onClick={desconectar} onBlur={() => setSeguro(false)} autoFocus>Sí, desconectar</Button>
          : <Button variant="fantasma" onClick={() => setSeguro(true)}>Desconectar</Button>}
      </div>
    </section>
  );
}
