"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { BookmarkPlus, Copy, Download, FileArchive, FileDown, FileSpreadsheet, Mail, Plus, Search, XCircle, ShieldCheck } from "lucide-react";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, ESTADOS, fecha, TIPOS } from "@/lib/format";
import type { Factura } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Field, Input, Menu, Modal, PageHeader, Select, Vacio } from "@/components/ui";

const MOTIVOS = {
  "01": "01 · Con errores, con relación (ya timbraste la que sustituye)",
  "02": "02 · Con errores, sin relación",
  "03": "03 · No se llevó a cabo la operación",
  "04": "04 · Operación nominativa en factura global",
};
const tono = (e: Factura["estado"]) => (e === "timbrada" ? "sello" : e === "cancelada" ? "rojo" : "alerta");

export default function Page() {
  return (
    <Suspense>
      <Facturas />
    </Suspense>
  );
}

function Facturas() {
  const { emisor } = useEmisor();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("");
  const [tipo, setTipo] = useState("");
  const [cancelar, setCancelar] = useState<Factura | null>(null);
  const ahora = new Date();
  const [desde, setDesde] = useState(new Date(ahora.getFullYear(), ahora.getMonth(), 1).toISOString().slice(0, 10));
  const [hasta, setHasta] = useState(ahora.toISOString().slice(0, 10));
  const qs = new URLSearchParams({ ...(emisor && { emisor_id: String(emisor.id) }), ...(q && { q }), ...(estado && { estado }), ...(tipo && { tipo }) });
  const { data = [], mutate, isLoading } = useSWR<Factura[]>(emisor ? `/facturas?${qs}` : null, fetcher);
  const periodo = () => `emisor_id=${emisor?.id}&desde=${desde}T00:00:00&hasta=${hasta}T23:59:59`;

  const guardarPlantilla = async (f: Factura) => {
    const nombre = window.prompt("Nombre de la plantilla", `${f.receptor_nombre ?? ""} · ${f.serie ?? ""}${f.folio ?? ""}`);
    if (!nombre) return;
    try {
      await api(`/plantillas/desde-factura/${f.id}?nombre=${encodeURIComponent(nombre)}`, { method: "POST" });
      toast.success("Plantilla guardada");
    } catch (e) {
      mostrarError(e);
    }
  };
  const pdf = (f: Factura) => descargar(`/facturas/${f.id}/pdf`, `${f.uuid}.pdf`).catch(mostrarError);
  const xml = (f: Factura) => descargar(`/facturas/${f.id}/xml`, `${f.uuid}.xml`).catch(mostrarError);
  // Si el cliente no tiene correo guardado, se pregunta a quién mandarlo y queda guardado para la próxima
  const enviarCorreo = async (f: Factura) => {
    try {
      const r = await api<{ para: string[] }>(`/facturas/${f.id}/enviar`, { method: "POST", json: {} });
      toast.success(`Enviada a ${r.para.join(", ")}`);
    } catch (e) {
      if ((e as { status?: number }).status !== 422) return mostrarError(e);
      const correo = window.prompt(`${f.receptor_nombre ?? "El cliente"} no tiene correo guardado. ¿A qué correo mando la factura?`)?.trim();
      if (!correo) return;
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correo)) return void toast.error("Ese correo no parece válido.");
      try {
        await api(`/facturas/${f.id}/enviar`, { method: "POST", json: { para: [correo], guardar: true } });
        toast.success(`Enviada a ${correo} y guardado en el cliente`);
      } catch (e2) { mostrarError(e2); }
    }
  };
  const acciones = (f: Factura) => [
    { label: "Enviar por correo", icon: <Mail className="size-4" />, onClick: () => enviarCorreo(f) },
    { label: "Clonar", icon: <Copy className="size-4" />, onClick: () => router.push(`/facturar?clonar=${f.id}`), oculto: f.tipo === "P" },
    { label: "Guardar como plantilla", icon: <BookmarkPlus className="size-4" />, onClick: () => guardarPlantilla(f), oculto: f.tipo === "P" },
    { label: "Consultar estatus en el SAT", icon: <ShieldCheck className="size-4" />, oculto: !f.uuid || f.tipo === undefined, onClick: () =>
        api<Record<string, string>>(`/facturas/${f.id}/estatus`).then((r) => {
          const txt = [r.Estado, r.EsCancelable, r.EstatusCancelacion].filter(Boolean).join(" · ") || JSON.stringify(r);
          (r.error ? toast.error : toast.success)(r.error ? `PAC: ${r.error}` : `SAT: ${txt}`, { duration: 12000 });
          mutate();
        }).catch(mostrarError) },
    { label: "Cancelar ante el SAT", icon: <XCircle className="size-4" />, onClick: () => setCancelar(f), peligro: true, oculto: f.estado !== "timbrada" },
  ];

  return (
    <div className="@container">
      <PageHeader title="Facturas">
        <Link href="/facturar"><Button variant="primario"><Plus className="size-4" /> Nueva</Button></Link>
      </PageHeader>

      <div className="mb-4 grid gap-2 rounded-2xl bg-hoja p-4 ring-1 ring-linea @min-[640px]:grid-cols-[auto_auto_1fr] @min-[640px]:items-end">
        <label className="flex flex-col gap-1 text-[13px] text-grafito">Desde<Input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></label>
        <label className="flex flex-col gap-1 text-[13px] text-grafito">Hasta<Input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></label>
        <div className="flex flex-wrap gap-2 @min-[640px]:justify-end">
          <Button className="flex-1 @min-[640px]:flex-none" onClick={() => descargar(`/facturas/exportar/zip?${periodo()}`, `XML_${emisor?.rfc}_${desde}_${hasta}.zip`).catch(mostrarError)}><FileArchive className="size-4" /> XML (ZIP)</Button>
          <Button className="flex-1 @min-[640px]:flex-none" onClick={() => descargar(`/facturas/exportar/csv?${periodo()}`, `Facturas_${emisor?.rfc}_${desde}_${hasta}.csv`).catch(mostrarError)}><FileSpreadsheet className="size-4" /> Excel</Button>
        </div>
      </div>

      <div className="mb-4 grid gap-2 @min-[640px]:grid-cols-[1fr_180px_200px]">
        <div className="relative min-w-0">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-grafito" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cliente, RFC, folio o UUID" className="pl-9" aria-label="Buscar" />
        </div>
        <Select value={tipo} onChange={(e) => setTipo(e.target.value)} aria-label="Tipo">
          <option value="">Todos los tipos</option>
          {Object.entries(TIPOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select value={estado} onChange={(e) => setEstado(e.target.value)} aria-label="Estado">
          <option value="">Todos los estados</option>
          {Object.entries(ESTADOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </div>

      {!isLoading && !data.length ? (
        <Vacio titulo="Nada por aquí">Cambia los filtros o timbra una factura nueva con F2.</Vacio>
      ) : (
        <>
          {/* Tarjetas (angosto) */}
          <ul className="flex flex-col gap-2 @min-[860px]:hidden">
            {data.map((f) => (
              <li key={f.id} className="rounded-2xl bg-hoja p-4 ring-1 ring-linea">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-semibold tabular-nums">{f.serie}{f.folio} <span className="font-normal text-grafito">· {TIPOS[f.tipo]}</span></p>
                    <p className="break-words text-sm">{f.receptor_nombre}</p>
                    <p className="text-xs text-grafito tabular-nums">{f.receptor_rfc} · {fecha(f.fecha)}</p>
                  </div>
                  <Menu items={acciones(f)} />
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <Badge tono={tono(f.estado)}>{ESTADOS[f.estado]}</Badge>{f.demo && <Badge tono="alerta" className="ml-1">Demo</Badge>}
                  <div className="text-right">
                    <p className="font-semibold tabular-nums">{dinero(f.total, f.moneda)}</p>
                    {Number(f.saldo) > 0 && <p className="text-xs text-alerta tabular-nums">Saldo {dinero(f.saldo)}</p>}
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Button size="sm" onClick={() => pdf(f)}><FileDown className="size-4" /> PDF</Button>
                  <Button size="sm" onClick={() => xml(f)}><Download className="size-4" /> XML</Button>
                </div>
              </li>
            ))}
          </ul>

          {/* Tabla (ancho) */}
          <div className="hidden overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea @min-[860px]:block">
            <table className="w-full table-fixed text-sm">
              <colgroup>
                <col className="w-20" /><col /><col className="w-32" /><col className="w-28" /><col className="w-40" /><col className="w-28" /><col className="w-28" /><col className="w-28" />
              </colgroup>
              <thead className="border-b border-linea text-left text-grafito">
                <tr>
                  <th className="px-4 py-3 font-medium">Folio</th>
                  <th className="px-4 py-3 font-medium">Receptor</th>
                  <th className="px-4 py-3 font-medium">Tipo</th>
                  <th className="px-4 py-3 font-medium">Fecha</th>
                  <th className="px-4 py-3 font-medium">Estado</th>
                  <th className="px-4 py-3 text-right font-medium">Total</th>
                  <th className="px-4 py-3 text-right font-medium">Saldo</th>
                  <th className="px-2 py-3"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {data.map((f) => (
                  <tr key={f.id} className="border-b border-linea last:border-0 hover:bg-papel">
                    <td className="px-4 py-3 font-medium tabular-nums">{f.serie}{f.folio}</td>
                    <td className="px-4 py-3">
                      <p className="line-clamp-2 leading-snug" title={f.receptor_nombre ?? ""}>{f.receptor_nombre}</p>
                      <p className="truncate text-xs text-grafito tabular-nums">{f.receptor_rfc}</p>
                    </td>
                    <td className="px-4 py-3"><span className="block truncate">{TIPOS[f.tipo]}{f.metodo_pago && <span className="text-grafito"> · {f.metodo_pago}</span>}</span></td>
                    <td className="px-4 py-3 tabular-nums">{fecha(f.fecha)}</td>
                    <td className="px-4 py-3"><Badge tono={tono(f.estado)}>{ESTADOS[f.estado]}</Badge>{f.demo && <Badge tono="alerta" className="ml-1">Demo</Badge>}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{dinero(f.total, f.moneda)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{Number(f.saldo) > 0 ? dinero(f.saldo) : "—"}</td>
                    <td className="px-2 py-3">
                      <div className="flex justify-end">
                        <button title="PDF" aria-label="PDF" onClick={() => pdf(f)} className="rounded-md p-2 text-grafito hover:bg-tinta/5 hover:text-tinta"><FileDown className="size-4" /></button>
                        <button title="XML" aria-label="XML" onClick={() => xml(f)} className="rounded-md p-2 text-grafito hover:bg-tinta/5 hover:text-tinta"><Download className="size-4" /></button>
                        <Menu items={acciones(f)} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <ModalCancelar f={cancelar} onClose={() => setCancelar(null)} onOk={() => { setCancelar(null); mutate(); }} />
    </div>
  );
}

function ModalCancelar({ f, onClose, onOk }: { f: Factura | null; onClose: () => void; onOk: () => void }) {
  const [motivo, setMotivo] = useState("02");
  const [sust, setSust] = useState("");
  const [cargando, setCargando] = useState(false);
  if (!f) return null;
  const ir = async () => {
    setCargando(true);
    try {
      const r = await api<Factura>(`/facturas/${f.id}/cancelar`, { method: "POST", json: { motivo, uuid_sustitucion: sust || null } });
      toast.success(r.estado === "cancelada" ? "Cancelada" : "Solicitud enviada; el receptor debe aceptar");
      onOk();
    } catch (e) {
      mostrarError(e);
    } finally {
      setCargando(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title={`Cancelar ${f.serie ?? ""}${f.folio ?? ""}`}
      footer={<><Button onClick={onClose}>No cancelar</Button><Button variant="peligro" onClick={ir} loading={cargando}>Cancelar ante el SAT</Button></>}
    >
      <div className="flex flex-col gap-4">
        <p className="text-sm text-grafito">{f.receptor_nombre} · {dinero(f.total)}</p>
        <Field label="Motivo">
          <Select value={motivo} onChange={(e) => setMotivo(e.target.value)}>
            {Object.entries(MOTIVOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
        {motivo === "01" && (
          <Field label="UUID de la factura que la sustituye">
            <Input value={sust} onChange={(e) => setSust(e.target.value.trim())} />
          </Field>
        )}
      </div>
    </Modal>
  );
}
