"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CloudDownload, FileSpreadsheet, FileArchive, RefreshCw, ShieldAlert, Upload } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Cifra, Input, PageHeader, Tabs, Vacio, cx, tabla } from "@/components/ui";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, fecha, isoLocal } from "@/lib/format";
import type { CfdiSat, SolicitudSat } from "@/lib/types";

type Vista = "recibido" | "emitido" | "solicitudes" | "conciliacion";
type Conc = { solo_sat: { uuid: string; total: string; fecha: string; nombre: string }[]; solo_timbra: { uuid: string; total: string; folio: string }[];
  estatus_distinto: { uuid: string; sat: string; timbra: string }[]; coinciden: number };

const mesActual = () => isoLocal().slice(0, 7);
const rango = (mes: string) => {
  const [y, m] = mes.split("-").map(Number);
  const fin = new Date(y, m, 0).getDate();
  return { desde: `${mes}-01T00:00:00`, hasta: `${mes}-${String(fin).padStart(2, "0")}T23:59:59` };
};
const ESTADO_SOL: Record<string, ["sello" | "alerta" | "rojo" | "neutro", string]> = {
  terminada: ["sello", "Descargada"], en_proceso: ["alerta", "El SAT la está preparando"], sin_datos: ["neutro", "Sin CFDI en el periodo"],
  error: ["rojo", "Rechazada"], pendiente: ["alerta", "Pendiente"],
};

export default function Sat() {
  const { emisor } = useEmisor();
  const [vista, setVista] = useState<Vista>("recibido");
  const [mes, setMes] = useState(mesActual());
  const [lista69, setLista69] = useState(false);
  const r = rango(mes);
  const dir = vista === "emitido" ? "emitido" : "recibido";
  const { data: cfdis = [], mutate } = useSWR<CfdiSat[]>(emisor && (vista === "recibido" || vista === "emitido")
    ? `/sat/cfdi?emisor_id=${emisor.id}&direccion=${dir}&desde=${r.desde}&hasta=${r.hasta}${lista69 && dir === "recibido" ? "&lista_69b=true" : ""}` : null, fetcher);
  const { data: sols = [], mutate: mSols } = useSWR<SolicitudSat[]>(emisor ? `/sat/solicitudes?emisor_id=${emisor.id}` : null, fetcher, { refreshInterval: 60_000 });
  const { data: conc } = useSWR<Conc>(emisor && vista === "conciliacion" ? `/sat/conciliacion?emisor_id=${emisor.id}&desde=${r.desde}&hasta=${r.hasta}` : null, fetcher);
  const [pidiendo, setPidiendo] = useState("");
  const archivos = useRef<HTMLInputElement>(null);

  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;

  const pedir = async (direccion: string, tipo: string) => {
    setPidiendo(direccion + tipo);
    try {
      const s = await api<SolicitudSat>("/sat/solicitudes", { method: "POST", json: { emisor_id: emisor.id, direccion, tipo, ...r } });
      (s.estado === "error" ? toast.error : toast.success)(s.estado === "error" ? `SAT: ${s.mensaje}` : "Solicitud enviada. Timbra la revisa sola cada 10 minutos.");
      mSols();
      setVista("solicitudes");
    } catch (e) { mostrarError(e); } finally { setPidiendo(""); }
  };
  const subir = async (files: FileList | null) => {
    if (!files?.length) return;
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("archivos", f));
    try {
      const x = await api<{ nuevos: number; errores: number }>(`/sat/importar-xml/${emisor.id}`, { method: "POST", body: fd });
      toast.success(`${x.nuevos} CFDI nuevos${x.errores ? ` · ${x.errores} archivos no eran CFDI` : ""}`);
      mutate();
    } catch (e) { mostrarError(e); }
  };
  const verificar = async (id: number) => {
    try { await api(`/sat/solicitudes/${id}/verificar`, { method: "POST" }); mSols(); mutate(); } catch (e) { mostrarError(e); }
  };
  const suma = (k: keyof CfdiSat) => cfdis.filter((c) => c.estado !== "Cancelado").reduce((s, c) => s + Number(c[k] || 0), 0);
  const q = `emisor_id=${emisor.id}&direccion=${dir}&desde=${r.desde}&hasta=${r.hasta}`;

  return (
    <>
      <PageHeader title="Descarga SAT">
        <Input type="month" value={mes} onChange={(e) => setMes(e.target.value)} className="w-40" aria-label="Mes" />
        <Button onClick={() => archivos.current?.click()}><Upload className="size-4" /> Subir XML o ZIP</Button>
        <input ref={archivos} type="file" multiple accept=".xml,.zip" hidden onChange={(e) => subir(e.target.files)} />
      </PageHeader>
      {!emisor.fiel_vence && (
        <p className="mb-5 rounded-xl bg-alerta-suave px-4 py-3 text-sm text-alerta">
          Para descargar directo del SAT carga la e.firma de {emisor.rfc} en <Link href="/marca" className="underline">Marca, nómina y e.firma</Link>. Mientras, puedes subir los XML que ya tengas.
        </p>
      )}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Tabs value={vista} onChange={setVista} items={[
          { id: "recibido", label: "Recibidos" }, { id: "emitido", label: "Emitidos" },
          { id: "solicitudes", label: "Solicitudes", n: sols.filter((s) => s.estado === "en_proceso").length || undefined }, { id: "conciliacion", label: "Conciliación" },
        ]} />
        {(vista === "recibido" || vista === "emitido") && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => pedir(dir, "CFDI")} loading={pidiendo === dir + "CFDI"} disabled={!emisor.fiel_vence}><CloudDownload className="size-4" /> Pedir XML del mes al SAT</Button>
            <Button variant="fantasma" onClick={() => pedir(dir, "Metadata")} loading={pidiendo === dir + "Metadata"} disabled={!emisor.fiel_vence} title="Incluye cancelados">Metadata</Button>
          </div>
        )}
      </div>

      {(vista === "recibido" || vista === "emitido") && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Cifra titulo="CFDI" valor={cfdis.length} nota={`${cfdis.filter((c) => c.estado === "Cancelado").length} cancelados`} />
            <Cifra titulo="Subtotal" valor={dinero(suma("subtotal"))} />
            <Cifra titulo="IVA" valor={dinero(suma("iva"))} />
            <Cifra titulo="Retenciones" valor={dinero(suma("iva_retenido") + suma("isr_retenido"))} />
            <Cifra titulo="Total" valor={dinero(suma("total"))} />
          </div>
          <div className="mb-3 flex justify-end gap-2">
            {dir === "recibido" && <Button size="sm" variant={lista69 ? "primario" : "secundario"} onClick={() => setLista69((v) => !v)} title="Cruza a tus proveedores con la lista 69-B del SAT (necesita internet la primera vez)"><ShieldAlert className="size-4" /> {lista69 ? "Lista 69-B activa" : "Verificar proveedores 69-B"}</Button>}
            <Button size="sm" onClick={() => descargar(`/sat/exportar/csv?${q}`, `sat_${dir}s_${mes}.csv`).catch(mostrarError)}><FileSpreadsheet className="size-4" /> Excel para COI</Button>
            <Button size="sm" onClick={() => descargar(`/sat/exportar/zip?${q}`, `sat_${dir}s_${mes}.zip`).catch(mostrarError)}><FileArchive className="size-4" /> ZIP de XML</Button>
          </div>
          {!cfdis.length ? <Vacio titulo={`Sin CFDI ${dir}s en ${mes}`}>Pídelos al SAT o sube los XML.</Vacio> : (
            <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
              <table className={tabla.base}>
                <thead><tr><th className={tabla.th}>Fecha</th><th className={tabla.th}>{dir === "recibido" ? "Proveedor" : "Cliente"}</th><th className={tabla.th}>Tipo</th>
                  <th className={cx(tabla.th, tabla.num)}>Subtotal</th><th className={cx(tabla.th, tabla.num)}>IVA</th><th className={cx(tabla.th, tabla.num)}>Ret.</th>
                  <th className={cx(tabla.th, tabla.num)}>Total</th><th className={tabla.th}>Estado</th></tr></thead>
                <tbody>
                  {cfdis.map((c) => (
                    <tr key={c.id} className={cx(c.estado === "Cancelado" && "opacity-50 line-through")}>
                      <td className={tabla.td}>{fecha(c.fecha)}</td>
                      <td className={tabla.td}><p className="max-w-72 truncate font-medium">{c.nombre ?? "—"}</p><p className="font-mono text-[11px] text-grafito">{c.rfc}</p></td>
                      <td className={tabla.td}>{c.tipo}{c.metodo_pago ? ` · ${c.metodo_pago}` : ""}</td>
                      <td className={cx(tabla.td, tabla.num)}>{dinero(c.subtotal)}</td>
                      <td className={cx(tabla.td, tabla.num)}>{dinero(c.iva)}</td>
                      <td className={cx(tabla.td, tabla.num)}>{Number(c.iva_retenido) + Number(c.isr_retenido) ? dinero(Number(c.iva_retenido) + Number(c.isr_retenido)) : "—"}</td>
                      <td className={cx(tabla.td, tabla.num, "font-medium")}>{dinero(c.total)}</td>
                      <td className={tabla.td}>
                        <span className="flex gap-1">{c.estado === "Cancelado" ? <Badge tono="rojo">Cancelado</Badge> : <Badge tono="sello">Vigente</Badge>}
                          {!c.tiene_xml && <Badge>Sin XML</Badge>}{c.lista_69b && <Badge tono={/definitivo/i.test(c.lista_69b) ? "rojo" : /presunto/i.test(c.lista_69b) ? "alerta" : "neutro"}>69-B: {c.lista_69b}</Badge>}{dir === "emitido" && !c.en_timbra && <Badge tono="alerta">No está en Timbra</Badge>}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {vista === "solicitudes" && (
        !sols.length ? <Vacio titulo="Sin solicitudes">El SAT tarda de minutos a horas en preparar la descarga. Timbra revisa sola cada 10 minutos mientras está abierta.</Vacio> : (
          <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
            <table className={tabla.base}>
              <thead><tr><th className={tabla.th}>Pedida</th><th className={tabla.th}>Qué</th><th className={tabla.th}>Periodo</th><th className={tabla.th}>Estado</th><th className={tabla.th}></th></tr></thead>
              <tbody>
                {sols.map((s) => {
                  const [tono, txt] = ESTADO_SOL[s.estado] ?? ["neutro", s.estado];
                  return (
                    <tr key={s.id}>
                      <td className={tabla.td}>{fecha(s.creado)}</td>
                      <td className={tabla.td}>{s.tipo} {s.direccion}s</td>
                      <td className={tabla.td}>{fecha(s.desde)} – {fecha(s.hasta)}</td>
                      <td className={tabla.td}><Badge tono={tono}>{txt}</Badge>{s.descargados > 0 && <span className="ml-2 text-xs text-grafito">{s.descargados} CFDI</span>}
                        {s.mensaje && <p className="mt-1 text-xs text-grafito">{s.mensaje}</p>}</td>
                      <td className={cx(tabla.td, "text-right")}>{s.estado === "en_proceso" && <Button size="sm" variant="fantasma" onClick={() => verificar(s.id)}><RefreshCw className="size-3.5" /> Revisar ya</Button>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      {vista === "conciliacion" && (
        !conc ? <p className="text-sm text-grafito">Cargando…</p> : (
          <div className="grid gap-5">
            <p className="text-sm text-grafito">Emitidos de {mes}: lo que tiene el SAT contra lo que tiene Timbra. Primero descarga o sube los emitidos del mes.</p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Cifra titulo="Coinciden" valor={conc.coinciden} tono="sello" />
              <Cifra titulo="Sólo en el SAT" valor={conc.solo_sat.length} tono={conc.solo_sat.length ? "alerta" : undefined} nota="Timbrados en otro sistema" />
              <Cifra titulo="Sólo en Timbra" valor={conc.solo_timbra.length} tono={conc.solo_timbra.length ? "alerta" : undefined} nota="Falta descargar del SAT" />
              <Cifra titulo="Estatus distinto" valor={conc.estatus_distinto.length} tono={conc.estatus_distinto.length ? "rojo" : undefined} nota="Cancelado en un lado" />
            </div>
            {[...conc.solo_sat.map((x) => ({ k: x.uuid, t: `Sólo SAT · ${x.nombre ?? ""}`, v: dinero(x.total) })),
              ...conc.solo_timbra.map((x) => ({ k: x.uuid, t: `Sólo Timbra · ${x.folio}`, v: dinero(x.total) })),
              ...conc.estatus_distinto.map((x) => ({ k: x.uuid, t: `SAT: ${x.sat} · Timbra: ${x.timbra}`, v: "" }))].map((x) => (
              <div key={x.k} className="flex flex-wrap justify-between gap-2 border-b border-linea py-2 text-sm"><span>{x.t} <span className="font-mono text-xs text-grafito">{x.k}</span></span><span>{x.v}</span></div>
            ))}
          </div>
        )
      )}
    </>
  );
}
