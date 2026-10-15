"use client";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Coins, RefreshCw } from "lucide-react";
import { Badge, Button, Field, Input, Modal, PageHeader, Vacio, cx } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { fecha, isoLocal } from "@/lib/format";
import type { Pac, TimbresPac } from "@/lib/types";

type Paquete = { clave: string; timbres: number; precio: string | number };
type InfoPaquetes = { activo: boolean; paquetes: Paquete[]; timbres: number | null; vence: { fecha: string; timbres: number } | null; vigencia_meses: number };
type Movimiento = { cuando: string; cantidad: number; saldo: number; motivo: string | null; vence: string | null; restantes: number | null };
type PagoFila = { id: number; timbres: number; monto: string; estado: string; creado: string; detalle: string | null };

export default function Timbres() {
  const { data: yo } = useSWR<{ admin: boolean }>("/auth/yo", fetcher);
  if (!yo) return null;
  return yo.admin ? <TimbresAdmin /> : <MisTimbres />;
}

/** Cuentas que facturan con el PAC de Timbra: su saldo, cuándo vence y comprar más. */
function MisTimbres() {
  const { data: info, mutate } = useSWR<InfoPaquetes>("/pagos/paquetes", fetcher);
  const { data: movs, mutate: mMovs } = useSWR<{ movimientos: Movimiento[] }>("/auth/timbres", fetcher);
  const { data: pagos = [], mutate: mPagos } = useSWR<PagoFila[]>("/pagos", fetcher);
  const [comprando, setComprando] = useState("");

  // De regreso de Mercado Pago: /timbres?pago=12&payment_id=345&status=approved
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const pago = Number(q.get("pago"));
    if (!pago) return;
    window.history.replaceState(null, "", "/timbres");
    api<{ estado: string; timbres: number; timbres_cuenta: number }>("/pagos/regreso", { method: "POST", json: { pago, payment_id: q.get("payment_id") } })
      .then((r) => {
        if (r.estado === "aprobado") toast.success(`¡Listo! Se abonaron ${r.timbres} timbres. Ahora tienes ${r.timbres_cuenta}.`);
        else if (r.estado === "pendiente") toast.info("Tu pago está en proceso. Los timbres se abonan solos en cuanto Mercado Pago lo confirme.");
        else toast.error("El pago no se completó. No se cobró nada; puedes intentarlo de nuevo.");
        mutate(); mMovs(); mPagos();
      })
      .catch(mostrarError);
  }, [mutate, mMovs, mPagos]);

  const comprar = async (p: Paquete) => {
    setComprando(p.clave);
    try {
      const r = await api<{ url: string }>("/pagos", { method: "POST", json: { paquete: p.clave } });
      window.location.href = r.url;
    } catch (e) { mostrarError(e); setComprando(""); }
  };
  const saldo = info?.timbres ?? 0;
  return (
    <>
      <PageHeader title="Mis timbres" />
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-2 rounded-2xl bg-hoja p-6 ring-1 ring-linea">
          <p className="text-[11px] uppercase tracking-[.06em] text-grafito">Timbres disponibles</p>
          <p className={cx("text-5xl font-semibold tabular-nums", saldo <= 0 ? "text-rojo" : saldo <= 5 ? "text-alerta" : "text-tinta")}>{saldo}</p>
          <p className="text-sm text-grafito">Cada factura, nota de crédito o complemento de pago usa uno, aunque después lo canceles.</p>
          {info?.vence && <p className="text-sm text-grafito">{info.vence.timbres} vencen el <b className="text-tinta">{fecha(info.vence.fecha)}</b>. Cada recarga dura {info.vigencia_meses} meses.</p>}
        </div>
        <div className="rounded-2xl bg-hoja p-6 ring-1 ring-linea">
          <p className="mb-4 font-semibold">Comprar timbres</p>
          {!info?.activo ? (
            <p className="text-sm text-grafito">El pago en línea se activa pronto. Mientras, pide tu recarga a quien te dio de alta en Timbra.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {info.paquetes.map((p) => (
                <button key={p.clave} onClick={() => comprar(p)} disabled={!!comprando}
                  className="flex flex-col items-start gap-1 rounded-xl bg-papel p-4 text-left ring-1 ring-linea transition hover:ring-cobalto disabled:opacity-60">
                  <span className="text-2xl font-semibold tabular-nums">{p.timbres}</span>
                  <span className="text-xs text-grafito">timbres</span>
                  <span className="mt-2 text-lg font-semibold">${Number(p.precio).toLocaleString("es-MX")}</span>
                  <span className="text-xs text-grafito">${(Number(p.precio) / p.timbres).toFixed(2)} c/u · IVA incluido</span>
                  <span className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-cobalto">
                    {comprando === p.clave ? "Abriendo Mercado Pago…" : <><Coins className="size-4" /> Comprar</>}
                  </span>
                </button>
              ))}
            </div>
          )}
          <p className="mt-3 text-xs text-grafito">Pagas en Mercado Pago (tarjeta, OXXO o transferencia). Los timbres se abonan solos al confirmarse el pago.</p>
        </div>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl bg-hoja p-5 ring-1 ring-linea">
          <p className="mb-3 font-semibold">Movimientos</p>
          {!movs?.movimientos.length ? <p className="text-sm text-grafito">Sin recargas todavía.</p> : (
            <ul className="divide-y divide-linea text-sm">
              {movs.movimientos.map((m, i) => (
                <li key={i} className="flex items-center justify-between gap-3 py-2">
                  <span className="min-w-0"><span className="block truncate">{m.motivo || (m.cantidad > 0 ? "Recarga" : "Ajuste")}</span>
                    <span className="text-xs text-grafito">{fecha(m.cuando)}{m.vence ? ` · vence ${fecha(m.vence)}` : ""}</span></span>
                  <b className={cx("tabular-nums", m.cantidad < 0 ? "text-rojo" : "text-sello")}>{m.cantidad > 0 ? "+" : ""}{m.cantidad}</b>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded-2xl bg-hoja p-5 ring-1 ring-linea">
          <p className="mb-3 font-semibold">Mis compras</p>
          {!pagos.length ? <p className="text-sm text-grafito">Aún no compras en línea.</p> : (
            <ul className="divide-y divide-linea text-sm">
              {pagos.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 py-2">
                  <span>{p.timbres} timbres · ${Number(p.monto).toLocaleString("es-MX")}<span className="block text-xs text-grafito">{fecha(p.creado)}</span></span>
                  <Badge tono={p.estado === "aprobado" ? "sello" : p.estado === "pendiente" ? "cobalto" : "rojo"}>
                    {{ aprobado: "Abonado", pendiente: "Pendiente", rechazado: "Rechazado", cancelado: "Cancelado" }[p.estado] ?? p.estado}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

function TimbresAdmin() {
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
