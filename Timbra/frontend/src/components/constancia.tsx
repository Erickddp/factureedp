"use client";
/** Constancia de Situación Fiscal (CSF): alta rápida del emisor y tarjeta «Tu constancia fiscal». Backend: services/constancia.py */
import { useRef, useState } from "react";
import { toast } from "sonner";
import { FileText, TriangleAlert, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { fecha } from "@/lib/format";
import { Badge, Button, cx } from "./ui";

export type Regimen = { clave: string | null; nombre: string; desde: string | null; hasta: string | null; emite?: boolean };
export type Actividad = { orden: number; nombre: string; porcentaje: number; desde: string | null; hasta: string | null };
export type Constancia = {
  id: number; rfc: string; persona: string; nombre: string; cp: string; id_cif: string | null; emitida_el: string | null;
  regimenes: Regimen[]; actividades: Actividad[]; obligaciones: string[]; subida?: string | null;
};
export type Diferencia = { campo: "regimen_fiscal" | "lugar_expedicion" | "nombre"; texto: string; sugerido: string };
export type EmisorSugerido = { rfc: string; nombre: string; regimen_fiscal: string; lugar_expedicion: string; regimenes: Regimen[]; avisos: string[] };

/** Botón que pide el PDF. `alLeer` recibe lo que el servidor leyó; no guarda nada. */
export function BotonConstancia({ alLeer, children, variant = "secundario" }: {
  alLeer: (r: { emisor: EmisorSugerido; constancia: Constancia }, archivo: File) => void; children: React.ReactNode; variant?: "secundario" | "primario" | "acento";
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [leyendo, setLeyendo] = useState(false);
  const elegir = async (f: File | undefined) => {
    if (!f) return;
    const fd = new FormData();
    fd.append("archivo", f);
    setLeyendo(true);
    try { alLeer(await api("/constancia/leer", { method: "POST", body: fd }), f); } catch (e) { mostrarError(e); } finally { setLeyendo(false); if (ref.current) ref.current.value = ""; }
  };
  return (
    <>
      <input ref={ref} type="file" accept="application/pdf,.pdf" className="hidden" onChange={(e) => elegir(e.target.files?.[0])} />
      <Button variant={variant} loading={leyendo} onClick={() => ref.current?.click()}><FileText className="size-4" /> {children}</Button>
    </>
  );
}

const NOMBRE_CAMPO: Record<string, string> = { regimen_fiscal: "el régimen", lugar_expedicion: "el código postal", nombre: "el nombre" };

/** Tarjeta de la pestaña Gastos: la constancia vigente de este emisor, sus diferencias con el emisor (sin aplicarlas solas) y subir otra. */
export function TarjetaConstancia({ emisorId, constancia, diferencias, avisos, alCambiar }: {
  emisorId: number; constancia: Constancia | null; diferencias: Diferencia[]; avisos: string[]; alCambiar: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const subir = async (f: File | undefined) => {
    if (!f) return;
    const fd = new FormData();
    fd.append("archivo", f);
    setSubiendo(true);
    try { await api(`/constancia/${emisorId}`, { method: "POST", body: fd }); toast.success("Constancia guardada"); alCambiar(); }
    catch (e) { mostrarError(e); } finally { setSubiendo(false); if (ref.current) ref.current.value = ""; }
  };
  const aplicar = async (d: Diferencia) => {
    try {
      await api(`/constancia/${emisorId}/aplicar`, { method: "POST", json: d.campo === "nombre" ? { nombre: true } : { [d.campo]: d.sugerido } });
      toast.success(`Emisor actualizado: ${NOMBRE_CAMPO[d.campo]}`);
      alCambiar();
    } catch (e) { mostrarError(e); }
  };
  const vigentes = (constancia?.regimenes ?? []).filter((r) => !r.hasta);
  const acts = (constancia?.actividades ?? []).filter((a) => !a.hasta);
  return (
    <section className="rounded-2xl bg-hoja p-5 ring-1 ring-linea">
      <input ref={ref} type="file" accept="application/pdf,.pdf" className="hidden" onChange={(e) => subir(e.target.files?.[0])} />
      <div className="flex flex-wrap items-center gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-acento-suave text-acento"><FileText className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Tu constancia fiscal</p>
          <p className="text-sm text-grafito">
            {constancia ? <>Emitida el {fecha(constancia.emitida_el)} · CP {constancia.cp}{constancia.id_cif ? ` · idCIF ${constancia.id_cif}` : ""}</>
              : "Súbela para que Timbra sepa tu régimen y tu actividad y clasifique mejor tus gastos."}
          </p>
        </div>
        <Button variant={constancia ? "secundario" : "acento"} loading={subiendo} onClick={() => ref.current?.click()}><Upload className="size-4" /> {constancia ? "Subir una nueva" : "Subir constancia (PDF)"}</Button>
      </div>
      {constancia && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[.08em] text-grafito">Regímenes vigentes</p>
            <div className="flex flex-wrap gap-1.5">{vigentes.map((r) => <Badge key={r.nombre} tono={r.emite === false ? "neutro" : "cobalto"}>{r.clave ?? "?"} · {r.nombre.replace(/^Régimen (de |General de Ley |Simplificado de )?/i, "").slice(0, 44)}</Badge>)}</div>
          </div>
          <div>
            <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[.08em] text-grafito">Actividades</p>
            <ul className="grid gap-0.5 text-sm">{acts.map((a) => <li key={a.orden} className="flex justify-between gap-3"><span className="truncate">{a.nombre}</span><span className="tabular-nums text-grafito">{a.porcentaje}%</span></li>)}</ul>
          </div>
        </div>
      )}
      {diferencias.length > 0 && (
        <ul className="mt-4 grid gap-2">
          {diferencias.map((d) => (
            <li key={d.campo} className="flex flex-wrap items-center gap-3 rounded-xl bg-alerta-suave px-4 py-3 text-sm text-alerta">
              <TriangleAlert className="size-4 shrink-0" />
              <span className="min-w-0 flex-1">{d.texto}</span>
              <Button size="sm" onClick={() => aplicar(d)}>Usar el de la constancia</Button>
            </li>
          ))}
        </ul>
      )}
      {avisos.filter((a) => !a.startsWith("Tiene más de un régimen")).map((a) => <p key={a} className={cx("mt-2 text-sm text-grafito")}>{a}</p>)}
    </section>
  );
}
