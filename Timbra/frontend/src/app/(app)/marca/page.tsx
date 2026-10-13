"use client";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ImageUp, Trash2 } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { Button, Field, Input, Interruptor, PageHeader, Vacio, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import type { Emisor } from "@/lib/types";

const COLORES = ["#111111", "#3149e0", "#0a7c66", "#8a1c1c", "#6b3fa0", "#b35c00", "#334155"];

export default function Marca() {
  const { emisor, recargar } = useEmisor();
  const [f, setF] = useState({ color: "#111111", logo_b64: "" as string | null, registro_patronal: "", curp: "", cobranza_auto: false });
  const [cargando, setCargando] = useState(false);
  const archivo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!emisor) return;
    setF({ color: emisor.color || "#111111", logo_b64: emisor.logo_b64 ?? null, registro_patronal: emisor.registro_patronal ?? "",
      curp: emisor.curp ?? "", cobranza_auto: !!emisor.cobranza_auto });
  }, [emisor]);

  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;

  const logo = (file?: File) => {
    if (!file) return;
    if (file.size > 300_000) return toast.error("El logo pesa más de 300 KB. Usa un PNG o JPG más ligero.");
    const r = new FileReader();
    r.onload = () => setF((x) => ({ ...x, logo_b64: String(r.result) }));
    r.readAsDataURL(file);
  };

  const guardar = async () => {
    setCargando(true);
    try {
      await api<Emisor>(`/emisores/${emisor.id}`, { method: "PUT", json: {
        rfc: emisor.rfc, nombre: emisor.nombre, regimen_fiscal: emisor.regimen_fiscal, lugar_expedicion: emisor.lugar_expedicion,
        email: emisor.email, pac_id: emisor.pac_id, region_fronteriza: !!emisor.region_fronteriza,
        color: f.color, logo_b64: f.logo_b64 || null, registro_patronal: f.registro_patronal.trim().toUpperCase() || null,
        curp: f.curp.trim().toUpperCase() || null, cobranza_auto: f.cobranza_auto,
      } });
      toast.success("Guardado");
      recargar();
    } catch (e) { mostrarError(e); } finally { setCargando(false); }
  };

  return (
    <>
      <PageHeader title="Marca y nómina">
        <Button variant="primario" onClick={guardar} loading={cargando}>Guardar cambios</Button>
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <section className="flex flex-col gap-5 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
          <h2 className="font-semibold">PDF de {emisor.rfc}</h2>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => archivo.current?.click()}><ImageUp className="size-4" /> {f.logo_b64 ? "Cambiar logo" : "Subir logo"}</Button>
            {f.logo_b64 && <Button variant="fantasma" onClick={() => setF({ ...f, logo_b64: null })}><Trash2 className="size-4" /> Quitar</Button>}
            <input ref={archivo} type="file" accept="image/png,image/jpeg,image/svg+xml" hidden onChange={(e) => logo(e.target.files?.[0])} />
          </div>
          <Field label="Color">
            <div className="flex flex-wrap items-center gap-2">
              {COLORES.map((c) => (
                <button key={c} type="button" aria-label={c} onClick={() => setF({ ...f, color: c })}
                  className={cx("size-8 rounded-full ring-offset-2 ring-offset-hoja transition", f.color === c ? "ring-2 ring-tinta" : "hover:scale-110")}
                  style={{ background: c }} />
              ))}
              <input type="color" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} className="size-8 cursor-pointer rounded-full border border-linea bg-transparent" aria-label="Otro color" />
            </div>
          </Field>
          <p className="text-xs text-grafito">El PDF conserva QR, sellos y cadena original del SAT; sólo cambia encabezado y colores.</p>
        </section>

        {/* Vista previa del encabezado del PDF */}
        <section className="overflow-hidden rounded-2xl bg-white p-6 text-[#111] shadow-sm ring-1 ring-linea">
          <div className="flex items-center gap-4 pb-3" style={{ borderBottom: `3px solid ${f.color}` }}>
            {f.logo_b64 && <img src={f.logo_b64} alt="logo" className="max-h-14 max-w-40 object-contain" />}
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-bold">{emisor.nombre}</p>
              <p className="text-[11px] text-[#555]">RFC {emisor.rfc} · Régimen {emisor.regimen_fiscal} · CP {emisor.lugar_expedicion}</p>
            </div>
            <div className="text-right">
              <p className="text-base font-bold" style={{ color: f.color }}>Factura A123</p>
              <p className="text-[10px] text-[#555]">5FB2822E-396D-4725-8521-CDC4BDD20CCF</p>
            </div>
          </div>
          <p className="mt-3 rounded py-1 text-center text-[11px] font-bold tracking-[3px] text-white" style={{ background: f.color }}>CONCEPTOS</p>
          <div className="mt-2 grid grid-cols-[1fr_auto] gap-y-1 text-[11px]">
            <span className="rounded px-2 py-1" style={{ background: `${f.color}14` }}>Servicios contables</span>
            <span className="rounded px-2 py-1 text-right" style={{ background: `${f.color}14` }}>$10,000.00</span>
          </div>
        </section>

        <section className="flex flex-col gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
          <h2 className="font-semibold">Nómina</h2>
          <Field label="Registro patronal (IMSS)" hint="Obligatorio para sueldos y salarios. Asimilados no lo llevan.">
            <Input value={f.registro_patronal} onChange={(e) => setF({ ...f, registro_patronal: e.target.value })} maxLength={20} />
          </Field>
          {emisor.rfc.length === 13 && (
            <Field label="CURP del emisor" hint="Persona física que timbra nómina: el SAT la pide en el recibo.">
              <Input value={f.curp} onChange={(e) => setF({ ...f, curp: e.target.value })} maxLength={18} />
            </Field>
          )}
          <h2 className="mt-2 font-semibold">Cobranza</h2>
          <Interruptor checked={f.cobranza_auto} onChange={(v) => setF({ ...f, cobranza_auto: v })} label="Recordatorios automáticos"
            hint="Cada lunes manda estado de cuenta a los clientes con facturas vencidas (máximo uno por semana)." />
        </section>

      </div>
    </>
  );
}

