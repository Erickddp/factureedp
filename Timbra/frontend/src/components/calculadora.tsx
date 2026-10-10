"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { baseDesde, type Desglose, type Modo } from "@/lib/impuestos";
import { dinero } from "@/lib/format";
import type { Impuesto } from "@/lib/types";
import { Button, Input, Modal, cx } from "./ui";

export const MODOS: { id: Modo; label: string; corto: string }[] = [
  { id: "base", label: "Precio sin IVA", corto: "Sin IVA" },
  { id: "con_iva", label: "Precio con IVA", corto: "Con IVA" },
  { id: "neto", label: "Lo que me depositan", corto: "Depositado" },
];

export function SelectorModo({ modo, setModo }: { modo: Modo; setModo: (m: Modo) => void }) {
  return (
    <div className="@container">
    <div className="flex rounded-lg border border-linea p-0.5" role="radiogroup" aria-label="¿Qué monto tienes?">
      {MODOS.map((m) => (
        <button key={m.id} type="button" role="radio" aria-checked={modo === m.id} onClick={() => setModo(m.id)}
          className={cx("h-9 min-w-0 flex-1 truncate rounded-md px-2 text-sm font-medium", modo === m.id ? "bg-tinta text-white" : "text-grafito hover:text-tinta")}>
          <span className="@min-[440px]:hidden">{m.corto}</span><span className="hidden @min-[440px]:inline">{m.label}</span>
        </button>
      ))}
    </div>
    </div>
  );
}

export function TablaDesglose({ d, moneda = "MXN", className }: { d: Desglose; moneda?: string; className?: string }) {
  const fila = (label: string, v: number, fuerte = false, signo = "") =>
    v !== 0 || fuerte ? (
      <div className={cx("flex justify-between gap-4", fuerte && "border-t border-linea pt-2 font-semibold")}>
        <dt className={fuerte ? "" : "text-grafito"}>{label}</dt>
        <dd className="tabular-nums">{signo}{dinero(v, moneda)}</dd>
      </div>
    ) : null;
  return (
    <dl className={cx("flex flex-col gap-1.5 text-sm", className)}>
      {fila("Subtotal (sin IVA)", d.base)}
      {fila("IVA trasladado", d.iva, false, "+ ")}
      {fila("IEPS", d.ieps, false, "+ ")}
      {fila("Precio con IVA", d.conIva)}
      {fila("Retención ISR", d.isr, false, "− ")}
      {fila("Retención IVA", d.ivaRet, false, "− ")}
      {fila("Total de la factura (lo que te depositan)", d.total, true)}
    </dl>
  );
}

/** Modal por concepto: "tengo $X con IVA / depositado" → precio unitario exacto. */
export function CalcPrecio({ abierto, cerrar, impuestos, cantidad, onUsar }: {
  abierto: boolean; cerrar: () => void; impuestos: Impuesto[]; cantidad: number; onUsar: (unitario: string) => void;
}) {
  const [modo, setModo] = useState<Modo>("neto");
  const [monto, setMonto] = useState("");
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (abierto) { setMonto(""); setTimeout(() => ref.current?.focus(), 40); } }, [abierto]);
  const r = useMemo(() => {
    const n = Number(monto.replace(/[$,\s]/g, ""));
    return n > 0 ? baseDesde(n, modo, impuestos) : null;
  }, [monto, modo, impuestos]);
  const cant = cantidad > 0 ? cantidad : 1;
  const unitario = r ? (r.d.base / cant).toFixed(cant === 1 ? 2 : 6).replace(/(\.\d{2}\d*?)0+$/, "$1") : "";
  const usar = () => { if (r) { onUsar(unitario); cerrar(); } };

  return (
    <Modal open={abierto} onClose={cerrar} title="Calcular el precio"
      footer={<div className="flex w-full justify-end gap-2"><Button onClick={cerrar}>Cancelar</Button><Button variant="primario" onClick={usar} disabled={!r}>Usar {unitario ? dinero(unitario) : "precio"}</Button></div>}>
      <div className="@container grid gap-4">
        <SelectorModo modo={modo} setModo={setModo} />
        <Input ref={ref} value={monto} onChange={(e) => setMonto(e.target.value)} inputMode="decimal" placeholder="Monto, ej. 10000"
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), usar())} className="h-12 text-lg tabular-nums" aria-label="Monto" />
        {r ? (
          <>
            <TablaDesglose d={r.d} />
            {cant !== 1 && <p className="text-sm text-grafito">Precio unitario para {cant} unidades: {dinero(unitario)}</p>}
            {r.diferencia !== 0 && <p className="text-sm text-alerta">Por redondeo al centavo queda {dinero(Math.abs(r.diferencia))} {r.diferencia > 0 ? "arriba" : "abajo"}.</p>}
          </>
        ) : (
          <p className="text-sm text-grafito">Usa los impuestos de este concepto. Enter para usar el precio.</p>
        )}
      </div>
    </Modal>
  );
}
