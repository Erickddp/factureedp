"use client";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Coins, RefreshCw } from "lucide-react";
import { Badge, Button, Field, Input, Modal, PageHeader, Vacio, cx } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { fecha, isoLocal } from "@/lib/format";
import type { Pac, TimbresPac } from "@/lib/types";

export default function Timbres() {
  const [vivo, setVivo] = useState(false);
  const { data = [], mutate, isLoading } = useSWR<TimbresPac[]>(`/pacs/timbres?en_vivo=${vivo}`, fetcher);
  const { data: pacs = [], mutate: mPacs } = useSWR<Pac[]>("/pacs", fetcher);
  const [compra, setCompra] = useState<Pac | null>(null);

  return (
    <>
      <PageHeader title="Timbres">
        <Button onClick={() => { setVivo(true); mutate(); }} loading={isLoading && vivo}><RefreshCw className="size-4" /> Consultar saldo en el PAC</Button>
      </PageHeader>
      <p className="-mt-3 mb-6 max-w-2xl text-sm text-grafito">
        Cada CFDI timbrado gasta un timbre, aunque después lo canceles. Registra cada paquete que compres y Timbra te avisa
        antes de quedarte sin timbres. Finkok cobra por mes lo que timbraste, así que ahí ves el consumo.
      </p>
      {!data.length ? (
        <Vacio titulo="No hay PAC de producción ni de pruebas registrado">Da de alta tu PAC en PAC y usuarios. El PAC demo no gasta timbres.</Vacio>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map((t) => {
            const pct = t.contratados ? Math.min(100, Math.round(((t.usados_paquete ?? 0) / t.contratados) * 100)) : null;
            const pac = pacs.find((p) => p.id === t.pac_id);
            return (
              <div key={t.pac_id} className="flex flex-col gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold">{t.nombre}</p>
                    <p className="text-sm capitalize text-grafito">{t.proveedor}</p>
                  </div>
                  {t.pruebas ? <Badge tono="cobalto">Pruebas</Badge> : <Badge tono="sello">Producción</Badge>}
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <Dato titulo="Este mes" valor={t.usados_mes} />
                  <Dato titulo="Restantes" valor={t.restantes ?? "—"} tono={t.nivel} />
                  <Dato titulo="Paquete" valor={t.contratados ?? "Pospago"} />
                </div>
                {pct !== null && (
                  <div>
                    <div className="h-2 overflow-hidden rounded-full bg-tinta/5">
                      <div className={cx("h-full rounded-full transition-all", t.nivel === "error" ? "bg-rojo" : t.nivel === "aviso" ? "bg-alerta" : "bg-primario")} style={{ width: `${pct}%` }} />
                    </div>
                    <p className="mt-1.5 text-xs text-grafito">{t.usados_paquete} de {t.contratados} usados desde {fecha(t.desde)} · aviso al quedar {t.alerta}</p>
                  </div>
                )}
                {t.pac && <p className="text-xs text-grafito">Saldo en {t.proveedor}: <b className="text-tinta">{t.pac.ilimitado ? "ilimitado" : t.pac.saldo}</b>{t.pac.vence && ` · vence ${fecha(t.pac.vence)}`}</p>}
                {t.pac_error && <p className="text-xs text-rojo">No se pudo consultar el saldo: {t.pac_error}</p>}
                {t.texto && <p className={cx("text-sm", t.nivel === "error" ? "text-rojo" : t.nivel === "aviso" ? "text-alerta" : "text-grafito")}>{t.texto}</p>}
                {pac && <Button className="self-start" onClick={() => setCompra(pac)}><Coins className="size-4" /> Registrar compra de timbres</Button>}
              </div>
            );
          })}
        </div>
      )}
      <Compra pac={compra} cerrar={() => setCompra(null)} ok={() => { setCompra(null); mutate(); mPacs(); }} />
    </>
  );
}

function Dato({ titulo, valor, tono }: { titulo: string; valor: React.ReactNode; tono?: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-[.06em] text-grafito">{titulo}</p>
      <p className={cx("text-xl font-semibold tabular-nums", tono === "error" && "text-rojo", tono === "aviso" && "text-alerta")}>{valor}</p>
    </div>
  );
}

function Compra({ pac, cerrar, ok }: { pac: Pac | null; cerrar: () => void; ok: () => void }) {
  const hoy = isoLocal();
  const [f, setF] = useState({ cantidad: "", desde: hoy, alerta: "50" });
  const [cargando, setCargando] = useState(false);
  const guardar = async () => {
    if (!pac) return;
    const n = Number(f.cantidad);
    if (!n && f.cantidad !== "0") return toast.error("¿Cuántos timbres compraste?");
    setCargando(true);
    try {
      await api(`/pacs/${pac.id}`, { method: "PUT", json: {
        nombre: pac.nombre, proveedor: pac.proveedor, usuario: pac.usuario, extra: pac.extra, pruebas: pac.pruebas,
        timbres_contratados: n === 0 ? null : n, timbres_desde: `${f.desde}T00:00:00`, timbres_alerta: Number(f.alerta) || 50,
      } });
      toast.success(n === 0 ? "Quedó como pospago" : `Paquete de ${n} timbres registrado`);
      ok();
    } catch (e) { mostrarError(e); } finally { setCargando(false); }
  };
  return (
    <Modal open={!!pac} onClose={cerrar} title={`Paquete de timbres · ${pac?.nombre ?? ""}`}
      footer={<><Button onClick={cerrar}>Cancelar</Button><Button variant="primario" onClick={guardar} loading={cargando}>Guardar</Button></>}>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); guardar(); }}>
        <Field label="Timbres del paquete" hint="Si te quedaban timbres, súmalos aquí. 0 = pospago (sin límite).">
          <Input autoFocus inputMode="numeric" value={f.cantidad} onChange={(e) => setF({ ...f, cantidad: e.target.value.replace(/\D/g, "") })} />
        </Field>
        <Field label="Cuentan desde"><Input type="date" value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} /></Field>
        <Field label="Avisarme al quedar" className="sm:col-span-2"><Input inputMode="numeric" value={f.alerta} onChange={(e) => setF({ ...f, alerta: e.target.value.replace(/\D/g, "") })} /></Field>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
