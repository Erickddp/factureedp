"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CalendarClock, Play, Star, Zap } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Field, Input, Interruptor, Kbd, Modal, PageHeader, Select, Vacio, cx, tabla } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { fecha } from "@/lib/format";
import type { Plantilla } from "@/lib/types";

const hoy = () => new Date();
const toca = (p: Plantilla) => !!p.recurrente && !!p.proxima && new Date(p.proxima) <= hoy();

export default function Recurrentes() {
  const { emisor } = useEmisor();
  const { data = [], mutate } = useSWR<Plantilla[]>(emisor ? `/plantillas?emisor_id=${emisor.id}` : null, fetcher);
  const [edit, setEdit] = useState<Plantilla | null>(null);
  const [timbrando, setTimbrando] = useState<number | "todas" | null>(null);

  const pendientes = data.filter(toca);
  const recurrentes = data.filter((p) => p.recurrente);
  const favoritas = data.filter((p) => p.favorita).sort((a, b) => (a.favorita ?? 0) - (b.favorita ?? 0));

  const timbrar = async (p: Plantilla) => {
    setTimbrando(p.id);
    try {
      const r = await api<{ folio: string }>(`/plantillas/${p.id}/timbrar`, { method: "POST" });
      toast.success(`Timbrada ${r.folio} · ${p.nombre}`);
    } catch (e) { mostrarError(e); } finally { setTimbrando(null); mutate(); }
  };
  const timbrarTodas = async () => {
    setTimbrando("todas");
    let ok = 0;
    for (const p of pendientes) {
      try { await api(`/plantillas/${p.id}/timbrar`, { method: "POST" }); ok++; } catch (e) { mostrarError(e); }
    }
    setTimbrando(null);
    mutate();
    if (ok) toast.success(`Timbradas ${ok} de ${pendientes.length}`);
  };

  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;
  return (
    <>
      <PageHeader title="Recurrentes y favoritas">
        <Link href="/facturar"><Button variant="primario"><Zap className="size-4" /> Nueva factura <Kbd>F2</Kbd></Button></Link>
      </PageHeader>
      <p className="-mt-3 mb-6 max-w-2xl text-sm text-grafito">
        Igualas, rentas y honorarios que se repiten. Marca el día del mes y Timbra te avisa (o la timbra sola). En la
        descripción usa <code className="rounded bg-tinta/5 px-1">{"{MES}"}</code>, <code className="rounded bg-tinta/5 px-1">{"{mes}"}</code> o{" "}
        <code className="rounded bg-tinta/5 px-1">{"{año}"}</code>: “Honorarios contables {"{MES} {año}"}”.
      </p>

      {pendientes.length > 0 && (
        <section className="mb-8 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 font-semibold"><CalendarClock className="size-4" /> Por timbrar hoy</h2>
            <Button variant="primario" onClick={timbrarTodas} loading={timbrando === "todas"}>Timbrar las {pendientes.length}</Button>
          </div>
          <ul className="divide-y divide-linea">
            {pendientes.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{p.nombre}</p>
                  <p className="truncate text-xs text-grafito">{p.cliente_nombre ?? "Público en general"} · tocaba {fecha(p.proxima)}</p>
                  {p.ultimo_error && <p className="text-xs text-rojo">{p.ultimo_error}</p>}
                </div>
                <Link href={`/facturar?plantilla=${p.id}`}><Button size="sm">Revisar</Button></Link>
                <Button size="sm" variant="primario" onClick={() => timbrar(p)} loading={timbrando === p.id}><Play className="size-3.5" /> Timbrar</Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {favoritas.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 flex items-center gap-2 font-semibold"><Star className="size-4" /> Favoritas</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {favoritas.map((p) => (
              <Link key={p.id} href={`/facturar?plantilla=${p.id}`} className="group rounded-2xl bg-hoja p-4 ring-1 ring-linea transition hover:ring-tinta/40">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate font-medium">{p.nombre}</p>
                  <Kbd>Alt ⇧ {p.favorita}</Kbd>
                </div>
                <p className="mt-1 truncate text-sm text-grafito">{p.cliente_nombre ?? "Público en general"}</p>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-3 font-semibold">Todas las plantillas <span className="text-sm font-normal text-grafito">· {recurrentes.length} recurrentes</span></h2>
        {!data.length ? (
          <Vacio titulo="Aún no tienes plantillas">En Facturar arma la factura y presiona Ctrl + S para guardarla como plantilla.</Vacio>
        ) : (
          <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
            <table className={tabla.base}>
              <thead><tr>
                <th className={tabla.th}>Plantilla</th><th className={tabla.th}>Cliente</th><th className={tabla.th}>Se repite</th>
                <th className={tabla.th}>Próxima</th><th className={tabla.th}>Favorita</th><th className={tabla.th}></th>
              </tr></thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} className="hover:bg-tinta/[.02]">
                    <td className={tabla.td}><p className="font-medium">{p.nombre}</p><p className="text-xs text-grafito">{p.usos} usos</p></td>
                    <td className={cx(tabla.td, "max-w-56 truncate text-grafito")}>{p.cliente_nombre ?? "Público en general"}</td>
                    <td className={tabla.td}>
                      {p.recurrente ? (
                        <span className="flex flex-wrap gap-1.5">
                          <Badge tono="cobalto">Día {p.dia}</Badge>
                          {p.auto_timbrar ? <Badge tono="sello">Automática</Badge> : <Badge>Con aviso</Badge>}
                          {p.enviar_email && <Badge>Correo</Badge>}
                        </span>
                      ) : <span className="text-grafito">—</span>}
                    </td>
                    <td className={cx(tabla.td, toca(p) && "font-medium text-cobalto")}>{p.recurrente ? fecha(p.proxima) : "—"}</td>
                    <td className={tabla.td}>{p.favorita ? <Kbd>Alt ⇧ {p.favorita}</Kbd> : <span className="text-grafito">—</span>}</td>
                    <td className={cx(tabla.td, "text-right")}><Button size="sm" variant="fantasma" onClick={() => setEdit(p)}>Configurar</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <Configurar p={edit} cerrar={() => setEdit(null)} ok={() => { setEdit(null); mutate(); }} />
    </>
  );
}

function Configurar({ p, cerrar, ok }: { p: Plantilla | null; cerrar: () => void; ok: () => void }) {
  const [f, setF] = useState({ nombre: "", favorita: "", recurrente: false, dia: "1", auto_timbrar: false, enviar_email: false });
  const [abierta, setAbierta] = useState<number | null>(null);
  const [cargando, setCargando] = useState(false);
  if (p && abierta !== p.id) {
    setAbierta(p.id);
    setF({ nombre: p.nombre, favorita: p.favorita ? String(p.favorita) : "", recurrente: !!p.recurrente, dia: String(p.dia ?? new Date().getDate()),
      auto_timbrar: !!p.auto_timbrar, enviar_email: !!p.enviar_email });
  }
  if (!p && abierta !== null) setAbierta(null);
  const guardar = async () => {
    if (!p) return;
    setCargando(true);
    try {
      await api(`/plantillas/${p.id}`, { method: "PUT", json: { ...f, favorita: f.favorita ? Number(f.favorita) : null, dia: Number(f.dia) } });
      toast.success("Plantilla guardada");
      ok();
    } catch (e) { mostrarError(e); } finally { setCargando(false); }
  };
  return (
    <Modal open={!!p} onClose={cerrar} title="Configurar plantilla"
      footer={<><Button onClick={cerrar}>Cancelar</Button><Button variant="primario" onClick={guardar} loading={cargando}>Guardar</Button></>}>
      <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); guardar(); }}>
        <Field label="Nombre"><Input autoFocus value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></Field>
        <Field label="Favorita" hint="Alt + Shift + número la abre en Facturar desde cualquier pantalla.">
          <Select value={f.favorita} onChange={(e) => setF({ ...f, favorita: e.target.value })}>
            <option value="">Sin atajo</option>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => <option key={n} value={n}>Alt + Shift + {n}</option>)}
          </Select>
        </Field>
        <Interruptor checked={f.recurrente} onChange={(v) => setF({ ...f, recurrente: v })} label="Se repite cada mes"
          hint="Aparece en “Por timbrar hoy” el día indicado." />
        {f.recurrente && (
          <div className="grid gap-4 rounded-xl bg-papel p-4">
            <Field label="Día del mes" hint="Si el mes es más corto (31 en febrero), se usa el último día.">
              <Input type="number" min={1} max={31} value={f.dia} onChange={(e) => setF({ ...f, dia: e.target.value })} />
            </Field>
            <Interruptor checked={f.auto_timbrar} onChange={(v) => setF({ ...f, auto_timbrar: v })} label="Timbrar sola"
              hint="Con Timbra abierta, se timbra ese día sin preguntar. Si algo falla, se apaga y te avisa." />
            <Interruptor checked={f.enviar_email} onChange={(v) => setF({ ...f, enviar_email: v })} label="Enviar por correo al cliente" />
          </div>
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
