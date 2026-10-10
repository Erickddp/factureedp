"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ClipboardPaste, Copy, ExternalLink, Plus, Trash2 } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Field, Input, Interruptor, Modal, PageHeader, Select, Vacio, cx, tabla } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, fecha } from "@/lib/format";
import type { Ticket } from "@/lib/types";

const FORMAS: [string, string][] = [["01", "Efectivo"], ["04", "Tarjeta de crédito"], ["28", "Tarjeta de débito"], ["03", "Transferencia"], ["02", "Cheque"]];

export default function Portal() {
  const { emisor, recargar } = useEmisor();
  const { data: tickets = [], mutate } = useSWR<Ticket[]>(emisor ? `/tickets?emisor_id=${emisor.id}` : null, fetcher);
  const [cfg, setCfg] = useState({ activo: false, clave_prod_serv: "01010101", clave_unidad: "ACT", descripcion: "Venta", tasa: "0.16" });
  const [nuevo, setNuevo] = useState({ folio: "", total: "", fecha: new Date().toISOString().slice(0, 10), forma_pago: "01" });
  const [pegar, setPegar] = useState<string | null>(null);

  useEffect(() => {
    if (!emisor) return;
    const c = emisor.portal_config ?? {};
    setCfg({ activo: !!emisor.portal_activo, clave_prod_serv: c.clave_prod_serv ?? "01010101", clave_unidad: c.clave_unidad ?? "ACT",
      descripcion: c.descripcion ?? "Venta", tasa: c.tasa ?? (emisor.region_fronteriza ? "0.08" : "0.16") });
  }, [emisor]);

  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;
  const liga = emisor.portal_clave ? `${typeof window !== "undefined" ? window.location.origin : ""}/autofactura/?c=${emisor.portal_clave}` : null;

  const guardarCfg = async (activo = cfg.activo) => {
    try {
      const { activo: _a, ...config } = cfg;
      await api(`/tickets/portal/${emisor.id}`, { method: "PUT", json: { activo, config } });
      setCfg({ ...cfg, activo });
      toast.success(activo ? "Portal encendido" : "Portal guardado");
      recargar();
    } catch (e) { mostrarError(e); }
  };
  const alta = async (lista: { folio: string; total: string; fecha: string; forma_pago: string }[]) => {
    try {
      const r = await api<{ nuevos: number; repetidos: number }>("/tickets", { method: "POST", json: lista.map((t) => ({ ...t, emisor_id: emisor.id, fecha: `${t.fecha}T12:00:00` })) });
      toast.success(`${r.nuevos} tickets nuevos${r.repetidos ? ` · ${r.repetidos} ya existían` : ""}`);
      mutate();
    } catch (e) { mostrarError(e); }
  };
  const importar = () => {
    // Folio, total y (opcional) fecha dd/mm/aaaa y forma de pago, separados por tabulador (pegado de Excel), coma o punto y coma
    const filas = (pegar ?? "").split(/\r?\n/).map((l) => l.split(/\t|;|,(?=\s*\d)/).map((x) => x.trim())).filter((c) => c[0] && c[1] && !isNaN(Number(c[1].replace(/[$,]/g, ""))));
    const hoy = new Date().toISOString().slice(0, 10);
    const lista = filas.map(([folio, total, f, forma]) => {
      const m = f?.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
      return { folio, total: total.replace(/[$,]/g, ""), fecha: m ? `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}` : hoy, forma_pago: forma || "01" };
    });
    if (!lista.length) return toast.error("No reconocí filas. Pega columnas: folio, total, fecha (opcional), forma de pago (opcional).");
    alta(lista);
    setPegar(null);
  };

  return (
    <>
      <PageHeader title="Autofactura" />
      <div className="mb-8 grid gap-5 lg:grid-cols-2">
        <section className="flex flex-col gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
          <Interruptor checked={cfg.activo} onChange={(v) => guardarCfg(v)} label="Portal encendido"
            hint="Tus clientes escriben folio y total del ticket, ponen sus datos y se llevan su factura. Cada ticket sólo se factura una vez y sólo dentro del mes." />
          {liga && cfg.activo && (
            <div className="flex items-center gap-2 rounded-xl bg-papel p-2 pl-3">
              <code className="min-w-0 flex-1 truncate text-xs">{liga}</code>
              <Button size="sm" variant="fantasma" onClick={() => { navigator.clipboard.writeText(liga); toast.success("Liga copiada"); }}><Copy className="size-3.5" /></Button>
              <a href={liga} target="_blank" rel="noreferrer"><Button size="sm" variant="fantasma"><ExternalLink className="size-3.5" /></Button></a>
            </div>
          )}
          <p className="text-xs text-grafito">Con Timbra instalado en tu PC la liga funciona en tu red. Para que la vean desde internet publícala con un túnel seguro (Cloudflare Tunnel) o en el servidor.</p>
        </section>
        <section className="grid gap-3 rounded-2xl bg-hoja p-5 ring-1 ring-linea sm:grid-cols-2">
          <p className="font-semibold sm:col-span-2">Concepto de los tickets</p>
          <Field label="Clave producto/servicio"><Input value={cfg.clave_prod_serv} onChange={(e) => setCfg({ ...cfg, clave_prod_serv: e.target.value })} maxLength={8} /></Field>
          <Field label="Clave unidad"><Input value={cfg.clave_unidad} onChange={(e) => setCfg({ ...cfg, clave_unidad: e.target.value })} maxLength={3} /></Field>
          <Field label="Descripción" className="sm:col-span-2"><Input value={cfg.descripcion} onChange={(e) => setCfg({ ...cfg, descripcion: e.target.value })} /></Field>
          <Field label="IVA incluido en el total">
            <Select value={cfg.tasa} onChange={(e) => setCfg({ ...cfg, tasa: e.target.value })}><option value="0.16">16%</option><option value="0.08">8% frontera</option><option value="0">0%</option></Select>
          </Field>
          <Button className="self-end" onClick={() => guardarCfg()}>Guardar concepto</Button>
        </section>
      </div>

      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (nuevo.folio && nuevo.total) { alta([nuevo]); setNuevo({ ...nuevo, folio: "", total: "" }); } }}>
          <Field label="Folio"><Input className="w-32" value={nuevo.folio} onChange={(e) => setNuevo({ ...nuevo, folio: e.target.value })} /></Field>
          <Field label="Total"><Input className="w-28" inputMode="decimal" value={nuevo.total} onChange={(e) => setNuevo({ ...nuevo, total: e.target.value })} /></Field>
          <Field label="Fecha"><Input type="date" value={nuevo.fecha} onChange={(e) => setNuevo({ ...nuevo, fecha: e.target.value })} /></Field>
          <Field label="Pago"><Select value={nuevo.forma_pago} onChange={(e) => setNuevo({ ...nuevo, forma_pago: e.target.value })}>{FORMAS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</Select></Field>
          <Button type="submit"><Plus className="size-4" /> Agregar</Button>
        </form>
        <Button variant="fantasma" onClick={() => setPegar("")}><ClipboardPaste className="size-4" /> Pegar de Excel</Button>
      </div>
      {!tickets.length ? <Vacio titulo="Sin tickets">Da de alta las ventas del día (o pégalas de tu punto de venta) para que se puedan facturar.</Vacio> : (
        <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
          <table className={tabla.base}>
            <thead><tr><th className={tabla.th}>Folio</th><th className={tabla.th}>Fecha</th><th className={tabla.th}>Pago</th><th className={cx(tabla.th, tabla.num)}>Total</th><th className={tabla.th}>Estado</th><th className={tabla.th}></th></tr></thead>
            <tbody>
              {tickets.map((t) => (
                <tr key={t.id}>
                  <td className={cx(tabla.td, "font-medium")}>{t.folio}</td><td className={tabla.td}>{fecha(t.fecha)}</td>
                  <td className={tabla.td}>{FORMAS.find((f) => f[0] === t.forma_pago)?.[1] ?? t.forma_pago}</td>
                  <td className={cx(tabla.td, tabla.num)}>{dinero(t.total)}</td>
                  <td className={tabla.td}>{t.factura_id ? <Badge tono="sello">Facturado</Badge> : <Badge>Disponible</Badge>}</td>
                  <td className={cx(tabla.td, "text-right")}>{!t.factura_id && (
                    <Button size="sm" variant="fantasma" aria-label="Borrar" onClick={() => api(`/tickets/${t.id}`, { method: "DELETE" }).then(() => mutate()).catch(mostrarError)}><Trash2 className="size-3.5" /></Button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={pegar !== null} onClose={() => setPegar(null)} title="Pegar tickets de Excel"
        footer={<><Button onClick={() => setPegar(null)}>Cancelar</Button><Button variant="primario" onClick={importar}>Agregar tickets</Button></>}>
        <p className="mb-2 text-sm text-grafito">Columnas: folio, total, fecha (dd/mm/aaaa, opcional), forma de pago (01, 04, 28…, opcional).</p>
        <textarea autoFocus value={pegar ?? ""} onChange={(e) => setPegar(e.target.value)} rows={10}
          className="w-full rounded-lg border border-linea bg-hoja p-3 font-mono text-xs focus:border-tinta focus:outline-none" placeholder={"T-1001\t580.00\t06/10/2026\t01\nT-1002\t1,240.50"} />
      </Modal>
    </>
  );
}
