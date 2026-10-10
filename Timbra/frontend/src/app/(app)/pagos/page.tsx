"use client";
import { useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, fecha } from "@/lib/format";
import { evaluarMonto } from "@/lib/sat";
import type { Cliente, Factura } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { CatSelect } from "@/components/catalogo";
import { Button, Field, Input, PageHeader, Select, Vacio } from "@/components/ui";

const ahoraLocal = () => {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};

export default function Pagos() {
  const { emisor } = useEmisor();
  const [clienteId, setClienteId] = useState<number | "">("");
  const [fechaPago, setFechaPago] = useState(ahoraLocal());
  const [forma, setForma] = useState("03");
  const [montos, setMontos] = useState<Record<number, string>>({});
  const [enviar, setEnviar] = useState(true);
  const [cargando, setCargando] = useState(false);
  const lista = useRef<HTMLDivElement>(null);

  const { data: clientes = [] } = useSWR<Cliente[]>(emisor ? `/clientes?emisor_id=${emisor.id}&limit=1000` : null, fetcher);
  const { data: pendientes = [], mutate } = useSWR<Factura[]>(
    emisor && clienteId ? `/facturas?emisor_id=${emisor.id}&cliente_id=${clienteId}&pendientes=true` : null,
    fetcher,
  );
  const monto = (id: number) => Number(evaluarMonto(montos[id] ?? "") || 0);
  const total = pendientes.reduce((s, f) => s + monto(f.id), 0);
  const excedidos = pendientes.filter((f) => monto(f.id) > Number(f.saldo) + 0.005);

  const timbrar = async () => {
    if (!emisor || !clienteId || total <= 0 || excedidos.length) return;
    setCargando(true);
    try {
      const documentos = pendientes.filter((f) => monto(f.id) > 0).map((f) => ({ factura_id: f.id, imp_pagado: monto(f.id).toFixed(2) }));
      const r = await api<Factura>("/facturas/pagos", {
        method: "POST",
        json: { emisor_id: emisor.id, cliente_id: clienteId, fecha_pago: fechaPago, forma_pago: forma, documentos, enviar_email: enviar },
      });
      toast.success(`Complemento ${r.serie}${r.folio} timbrado`);
      setMontos({});
      mutate();
    } catch (e) {
      mostrarError(e);
    } finally {
      setCargando(false);
    }
  };

  // Enter en un monto → siguiente monto; Ctrl+Enter → timbrar
  const teclas = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); timbrar(); return; }
    if (e.key === "Enter" || e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const campos = Array.from(lista.current?.querySelectorAll<HTMLInputElement>("input[data-monto]") ?? []);
      const i = campos.indexOf(e.currentTarget);
      campos[e.key === "ArrowUp" ? Math.max(i - 1, 0) : Math.min(i + 1, campos.length - 1)]?.focus();
    }
  };

  return (
    <>
      <PageHeader title="Complementos de pago" />
      <div className="@container rounded-2xl bg-hoja p-4 ring-1 ring-linea sm:p-5">
        <div className="grid gap-4 @min-[720px]:grid-cols-3">
          <Field label="Cliente">
            <Select value={clienteId} onChange={(e) => { setClienteId(e.target.value ? Number(e.target.value) : ""); setMontos({}); }} autoFocus>
              <option value="">Elige cliente…</option>
              {clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </Select>
          </Field>
          <Field label="Fecha en que te pagaron">
            <Input type="datetime-local" value={fechaPago} onChange={(e) => setFechaPago(e.target.value)} />
          </Field>
          <Field label="Forma de pago">
            <CatSelect catalogo="forma_pago" value={forma} onChange={setForma} filtro={(c) => c.clave !== "99"} />
          </Field>
        </div>
      </div>

      <div className="mt-6">
        {!clienteId ? (
          <Vacio titulo="Elige un cliente">Te muestro sus facturas PPD con saldo.</Vacio>
        ) : !pendientes.length ? (
          <Vacio titulo="Este cliente no te debe nada">Sin facturas PPD con saldo pendiente.</Vacio>
        ) : (
          <div ref={lista} className="@container overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea">
            <div className="hidden grid-cols-[90px_100px_1fr_1fr_80px_minmax(180px,220px)] gap-3 border-b border-linea px-4 py-3 text-sm text-grafito @min-[760px]:grid">
              <span>Factura</span><span>Fecha</span><span className="text-right">Total</span><span className="text-right">Saldo</span><span className="text-right">Parcialidad</span><span>Pago</span>
            </div>
            {pendientes.map((f) => {
              const pasado = monto(f.id) > Number(f.saldo) + 0.005;
              return (
                <div key={f.id} className="grid grid-cols-2 items-center gap-x-3 gap-y-1 border-b border-linea px-4 py-3 last:border-0 @min-[760px]:grid-cols-[90px_100px_1fr_1fr_80px_minmax(180px,220px)]">
                  <span className="font-medium tabular-nums">{f.serie}{f.folio}</span>
                  <span className="text-right text-sm text-grafito tabular-nums @min-[760px]:text-left">{fecha(f.fecha)}</span>
                  <span className="text-sm tabular-nums @min-[760px]:text-right"><span className="text-grafito @min-[760px]:hidden">Total </span>{dinero(f.total)}</span>
                  <span className="text-right text-sm font-medium tabular-nums"><span className="font-normal text-grafito @min-[760px]:hidden">Saldo </span>{dinero(f.saldo)}</span>
                  <span className="hidden text-right text-sm tabular-nums @min-[760px]:block">{f.parcialidades + 1}</span>
                  <div className="col-span-2 flex gap-1 @min-[760px]:col-span-1">
                    <Input data-monto value={montos[f.id] ?? ""} inputMode="decimal" placeholder="0.00" aria-label={`Pago a ${f.serie}${f.folio}`} aria-invalid={pasado}
                      onChange={(e) => setMontos({ ...montos, [f.id]: e.target.value })} onKeyDown={teclas} className={pasado ? "border-rojo" : ""} />
                    <Button size="sm" variant="fantasma" className="h-10 shrink-0" onClick={() => setMontos({ ...montos, [f.id]: String(Number(f.saldo)) })}>Todo</Button>
                  </div>
                  {pasado && <p className="col-span-2 text-sm text-rojo @min-[760px]:col-start-6">Es más que el saldo</p>}
                </div>
              );
            })}
            <div className="flex flex-wrap items-center justify-end gap-3 border-t border-linea bg-papel/60 px-4 py-4">
              <label className="mr-auto flex items-center gap-2 text-sm text-grafito">
                <input type="checkbox" checked={enviar} onChange={(e) => setEnviar(e.target.checked)} className="accent-cobalto" /> Mandar por correo
              </label>
              <span className="text-lg font-semibold tabular-nums">{dinero(total)}</span>
              <Button variant="primario" onClick={timbrar} loading={cargando} disabled={total <= 0 || excedidos.length > 0} title="Ctrl + Enter">Timbrar complemento</Button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
