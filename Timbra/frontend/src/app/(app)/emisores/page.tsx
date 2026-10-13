"use client";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import Link from "next/link";
import { AlertTriangle, KeyRound, Palette, Plus, Trash2 } from "lucide-react";
import { mostrarError } from "@/lib/errores";
import { api, fetcher } from "@/lib/api";
import { fecha } from "@/lib/format";
import type { Emisor, Pac } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { CatSelect } from "@/components/catalogo";
import { Badge, Button, Field, Input, Modal, PageHeader, Select, Vacio } from "@/components/ui";

const vacio = { rfc: "", nombre: "", regimen_fiscal: "", lugar_expedicion: "", email: "", pac_id: "" as string | number, region_fronteriza: false };

export default function Emisores() {
  const { emisores, recargar, setEmisorId } = useEmisor();
  const { data: pacs = [] } = useSWR<Pac[]>("/pacs", fetcher);
  const [edit, setEdit] = useState<(typeof vacio & { id?: number }) | null>(null);
  const [csd, setCsd] = useState<Emisor | null>(null);
  const [borrar, setBorrar] = useState<Emisor | null>(null);
  const [rfcEscrito, setRfcEscrito] = useState("");
  const [borrando, setBorrando] = useState(false);

  const guardar = async () => {
    if (!edit) return;
    try {
      const e = await api<Emisor>(edit.id ? `/emisores/${edit.id}` : "/emisores", {
        method: edit.id ? "PUT" : "POST",
        json: { ...edit, pac_id: edit.pac_id ? Number(edit.pac_id) : null, email: edit.email || null },
      });
      toast.success("Emisor guardado");
      setEdit(null);
      recargar();
      if (!edit.id) { setEmisorId(e.id); setCsd(e); }
    } catch (err) {
      mostrarError(err);
    }
  };

  // Sólo se puede con emisores sin facturas timbradas en producción: el servidor se niega si hay CFDI con validez fiscal.
  const eliminar = async () => {
    if (!borrar) return;
    setBorrando(true);
    try {
      await api(`/emisores/${borrar.id}?confirmar=${encodeURIComponent(rfcEscrito.trim())}`, { method: "DELETE" });
      toast.success(`${borrar.rfc} eliminado`);
      setBorrar(null);
      recargar();
    } catch (err) { mostrarError(err); } finally { setBorrando(false); }
  };

  return (
    <>
      <PageHeader title="Emisores y CSD">
        <Button variant="primario" onClick={() => setEdit({ ...vacio })}><Plus className="size-4" /> RFC emisor</Button>
      </PageHeader>
      {!emisores.length ? (
        <Vacio titulo="Da de alta el primer RFC que va a facturar">Luego sube su CSD (.cer, .key y contraseña) y listo.</Vacio>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {emisores.map((e) => {
            const vencido = e.csd_vence && new Date(e.csd_vence) < new Date();
            const pac = pacs.find((p) => p.id === e.pac_id);
            return (
              <div key={e.id} className="rounded-2xl bg-hoja p-5 ring-1 ring-linea">
                <p className="font-semibold">{e.nombre}</p>
                <p className="text-sm text-grafito tabular-nums">{e.rfc} · Régimen {e.regimen_fiscal} · CP {e.lugar_expedicion}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {!e.no_certificado ? <Badge tono="rojo">Sin CSD</Badge> : vencido ? <Badge tono="rojo">CSD vencido</Badge> : <Badge tono="sello">CSD vigente al {fecha(e.csd_vence)}</Badge>}
                  <Badge tono={!pac || pac.proveedor === "demo" ? "alerta" : pac.pruebas ? "cobalto" : "sello"}>
                    {!pac ? "Modo demo" : `${pac.nombre}${pac.pruebas ? " (pruebas)" : ""}`}
                  </Badge>
                </div>
                {e.region_fronteriza && (
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                    <Badge tono="cobalto">IVA 8% región fronteriza</Badge>
                    <button className="text-cobalto hover:underline" onClick={async () => {
                      try {
                        const r = await api<{ actualizados: number }>(`/emisores/${e.id}/productos-a-frontera`, { method: "POST" });
                        toast.success(`${r.actualizados} productos pasados a IVA 8% (retención 5.3333%)`);
                      } catch (err) { mostrarError(err); }
                    }}>Pasar mi catálogo a 8%</button>
                  </div>
                )}
                <p className="mt-3 text-sm text-grafito">Series: {e.series.map((s) => `${s.serie} (${s.tipo}) → ${s.siguiente_folio}`).join(" · ")}</p>
                <div className="mt-4 flex gap-2">
                  <Button size="sm" onClick={() => setCsd(e)}><KeyRound className="size-4" /> {e.no_certificado ? "Renovar CSD" : "Subir CSD"}</Button>
                  <Button size="sm" variant="fantasma" onClick={() => setEdit({ ...vacio, rfc: e.rfc, nombre: e.nombre, regimen_fiscal: e.regimen_fiscal,
                    lugar_expedicion: e.lugar_expedicion, email: e.email ?? "", pac_id: e.pac_id ?? "", region_fronteriza: !!e.region_fronteriza, id: e.id })}>Editar</Button>
                  <Link href="/marca" onClick={() => setEmisorId(e.id)}><Button size="sm" variant="fantasma"><Palette className="size-4" /> Marca y nómina</Button></Link>
                </div>
                <div className="mt-4 flex justify-end border-t border-linea pt-3">
                  <button onClick={() => { setRfcEscrito(""); setBorrar(e); }}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-rojo ring-1 ring-rojo/40 transition-colors hover:bg-rojo hover:text-white">
                    <Trash2 className="size-3.5" /> Eliminar emisor
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? "Editar emisor" : "Nuevo emisor"} wide>
        {edit && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="RFC"><Input value={edit.rfc} onChange={(e) => setEdit({ ...edit, rfc: e.target.value.toUpperCase().trim() })} /></Field>
            <Field label="CP del lugar de expedición"><Input value={edit.lugar_expedicion} maxLength={5} onChange={(e) => setEdit({ ...edit, lugar_expedicion: e.target.value })} /></Field>
            <Field label="Nombre o razón social (sin régimen societario)" className="sm:col-span-2"><Input value={edit.nombre} onChange={(e) => setEdit({ ...edit, nombre: e.target.value.toUpperCase() })} /></Field>
            <Field label="Régimen fiscal"><CatSelect catalogo="regimen_fiscal" value={edit.regimen_fiscal} onChange={(v) => setEdit({ ...edit, regimen_fiscal: v })} /></Field>
            <Field label="PAC con el que timbra">
              <Select value={edit.pac_id} onChange={(e) => setEdit({ ...edit, pac_id: e.target.value })}>
                <option value="">Demo (no timbra de verdad)</option>
                {pacs.map((p) => <option key={p.id} value={p.id}>{p.nombre}{p.pruebas ? " (pruebas)" : ""}</option>)}
              </Select>
            </Field>
            <label className="flex items-start gap-3 rounded-xl bg-papel p-3 text-sm sm:col-span-2">
              <input type="checkbox" checked={!!edit.region_fronteriza} onChange={(e) => setEdit({ ...edit, region_fronteriza: e.target.checked })} className="mt-0.5 size-4 accent-cobalto" />
              <span><b className="font-medium">Región fronteriza: IVA 8%</b><br /><span className="text-grafito">Sólo si está inscrito en el padrón del estímulo fiscal (prorrogado hasta el 31/12/2026). Los conceptos nuevos saldrán con 8% y la retención de IVA con 5.3333%.</span></span>
            </label>
            <Field label="Correo remitente" className="sm:col-span-2"><Input value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
            <div className="flex justify-end gap-2 sm:col-span-2"><Button onClick={() => setEdit(null)}>Cancelar</Button><Button variant="primario" onClick={guardar}>Guardar emisor</Button></div>
          </div>
        )}
      </Modal>
      <ModalCsd e={csd} onClose={() => setCsd(null)} onOk={() => { setCsd(null); recargar(); }} />
      <Modal open={!!borrar} onClose={() => setBorrar(null)} title="Eliminar emisor"
        footer={<><Button data-autofocus onClick={() => setBorrar(null)}>Cancelar</Button>
          <Button variant="peligro" disabled={borrando || rfcEscrito.trim().toUpperCase() !== borrar?.rfc} onClick={eliminar}><Trash2 className="size-4" /> {borrando ? "Eliminando…" : "Eliminar para siempre"}</Button></>}>
        {borrar && (
          <div className="grid gap-4 text-sm">
            <p className="flex gap-2.5 rounded-xl bg-rojo-suave px-4 py-3 text-rojo ring-1 ring-rojo/25">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>Vas a eliminar <b>{borrar.nombre}</b> ({borrar.rfc}) con todo lo suyo: sellos, clientes, productos, plantillas, lotes y facturas. <b>No se puede deshacer.</b></span>
            </p>
            <p className="text-grafito">Si este emisor ya timbró facturas con validez fiscal, Timbra no lo elimina: esas hay que conservarlas.</p>
            <Field label={`Para confirmar, escribe su RFC: ${borrar.rfc}`}>
              <Input value={rfcEscrito} autoComplete="off" spellCheck={false} placeholder={borrar.rfc}
                onChange={(ev) => setRfcEscrito(ev.target.value.toUpperCase())}
                onKeyDown={(ev) => { if (ev.key === "Enter" && rfcEscrito.trim() === borrar.rfc && !borrando) eliminar(); }} />
            </Field>
          </div>
        )}
      </Modal>
    </>
  );
}

function ModalCsd({ e, onClose, onOk }: { e: Emisor | null; onClose: () => void; onOk: () => void }) {
  const [cer, setCer] = useState<File | null>(null);
  const [key, setKey] = useState<File | null>(null);
  const [pwd, setPwd] = useState("");
  const [cargando, setCargando] = useState(false);
  if (!e) return null;
  const subir = async () => {
    if (!cer || !key) return;
    const fd = new FormData();
    fd.append("cer", cer);
    fd.append("key", key);
    fd.append("password", pwd);
    setCargando(true);
    try {
      await api(`/emisores/${e.id}/csd`, { method: "POST", body: fd });
      toast.success("CSD cargado y validado");
      onOk();
    } catch (err) {
      mostrarError(err);
    } finally {
      setCargando(false);
    }
  };
  return (
    <Modal open onClose={onClose} title={`CSD de ${e.rfc}`}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-grafito">Es el Certificado de Sello Digital, no la e.firma. Se guarda cifrado.</p>
        <Field label="Certificado (.cer)"><Input type="file" accept=".cer" onChange={(ev) => setCer(ev.target.files?.[0] ?? null)} className="pt-2" /></Field>
        <Field label="Llave privada (.key)"><Input type="file" accept=".key" onChange={(ev) => setKey(ev.target.files?.[0] ?? null)} className="pt-2" /></Field>
        <Field label="Contraseña de la llave"><Input type="password" value={pwd} onChange={(ev) => setPwd(ev.target.value)} /></Field>
        <div className="flex justify-end gap-2"><Button onClick={onClose}>Cancelar</Button><Button variant="primario" onClick={subir} loading={cargando} disabled={!cer || !key || !pwd}>Validar y guardar</Button></div>
      </div>
    </Modal>
  );
}
