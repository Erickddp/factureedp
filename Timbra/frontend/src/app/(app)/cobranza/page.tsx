"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Mail, Printer, Wallet } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Cifra, Modal, PageHeader, Vacio, cx, tabla } from "@/components/ui";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, fecha } from "@/lib/format";
import type { ClienteCobranza } from "@/lib/types";

type Antiguedad = { clientes: ClienteCobranza[]; totales: Record<string, string>; total: string };
type Estado = {
  cliente: { id: number; nombre: string; rfc: string; dias_credito: number };
  movimientos: { fecha: string; folio: string; tipo: string; cargo: string; abono: string; saldo: string }[];
  pendientes: { factura_id: number; folio: string; fecha: string; vence: string; dias_vencido: number; total: string; saldo: string }[];
  saldo: string;
};
const RANGOS = ["corriente", "1-30", "31-60", "61-90", "+90"] as const;

export default function Cobranza() {
  const { emisor } = useEmisor();
  const { data, mutate } = useSWR<Antiguedad>(emisor ? `/cobranza?emisor_id=${emisor.id}` : null, fetcher);
  const [sel, setSel] = useState<number[]>([]);
  const [ver, setVer] = useState<number | null>(null);
  const [enviando, setEnviando] = useState(false);

  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;
  const clientes = data?.clientes ?? [];
  const vencido = clientes.reduce((s, c) => s + Number(c.vencido), 0);

  const recordar = async (ids: number[]) => {
    setEnviando(true);
    try {
      const r = await api<{ cliente_id: number; ok: boolean; error?: string }[]>("/cobranza/recordar", { method: "POST", json: { cliente_ids: ids } });
      const ok = r.filter((x) => x.ok).length;
      if (ok) toast.success(`Recordatorio enviado a ${ok} cliente(s)`);
      r.filter((x) => !x.ok).forEach((x) => toast.error(`${clientes.find((c) => c.cliente_id === x.cliente_id)?.cliente ?? x.cliente_id}: ${x.error}`));
      setSel([]);
      mutate();
    } catch (e) { mostrarError(e); } finally { setEnviando(false); }
  };

  return (
    <>
      <PageHeader title="Cobranza">
        {sel.length > 0 && <Button variant="primario" onClick={() => recordar(sel)} loading={enviando}><Mail className="size-4" /> Mandar recordatorio a {sel.length}</Button>}
      </PageHeader>
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Cifra titulo="Por cobrar" valor={dinero(data?.total)} />
        <Cifra titulo="Vencido" valor={dinero(vencido)} tono={vencido > 0 ? "rojo" : undefined} />
        {RANGOS.slice(1).map((r) => <Cifra key={r} titulo={`${r} días`} valor={dinero(data?.totales?.[r])} tono={r === "+90" && Number(data?.totales?.[r]) > 0 ? "rojo" : undefined} />)}
      </div>
      {!clientes.length ? (
        <Vacio titulo="Nadie te debe">Aquí aparecen las facturas PPD con saldo. Los días de crédito de cada cliente se configuran en Clientes.</Vacio>
      ) : (
        <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
          <table className={tabla.base}>
            <thead><tr>
              <th className={cx(tabla.th, "w-8")}><input type="checkbox" aria-label="Todos" checked={sel.length === clientes.length} onChange={(e) => setSel(e.target.checked ? clientes.map((c) => c.cliente_id) : [])} /></th>
              <th className={tabla.th}>Cliente</th>
              {RANGOS.map((r) => <th key={r} className={cx(tabla.th, tabla.num)}>{r === "corriente" ? "Al corriente" : r}</th>)}
              <th className={cx(tabla.th, tabla.num)}>Saldo</th><th className={tabla.th}>Último aviso</th>
            </tr></thead>
            <tbody>
              {clientes.map((c) => (
                <tr key={c.cliente_id} className="cursor-pointer hover:bg-tinta/[.02]" onClick={() => setVer(c.cliente_id)}>
                  <td className={tabla.td} onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" aria-label={`Elegir ${c.cliente}`} checked={sel.includes(c.cliente_id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, c.cliente_id] : s.filter((x) => x !== c.cliente_id)))} />
                  </td>
                  <td className={tabla.td}>
                    <p className="font-medium">{c.cliente}</p>
                    <p className="text-xs text-grafito">{c.rfc} · {c.facturas} factura(s){c.max_dias > 0 && <> · <span className="text-rojo">{c.max_dias} días vencida</span></>}</p>
                  </td>
                  {RANGOS.map((r) => <td key={r} className={cx(tabla.td, tabla.num, Number(c[r]) === 0 && "text-grafito/40", r !== "corriente" && Number(c[r]) > 0 && "text-rojo")}>{Number(c[r]) ? dinero(c[r]) : "—"}</td>)}
                  <td className={cx(tabla.td, tabla.num, "font-semibold")}>{dinero(c.saldo)}</td>
                  <td className={cx(tabla.td, "text-grafito")}>{c.ultimo_recordatorio ? fecha(c.ultimo_recordatorio) : c.emails.length ? "—" : <Badge tono="alerta">Sin correo</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <EstadoCuenta clienteId={ver} cerrar={() => setVer(null)} recordar={(id) => recordar([id])} />
    </>
  );
}

function EstadoCuenta({ clienteId, cerrar, recordar }: { clienteId: number | null; cerrar: () => void; recordar: (id: number) => void }) {
  const { data } = useSWR<Estado>(clienteId ? `/cobranza/estado-cuenta/${clienteId}` : null, fetcher);
  return (
    <Modal open={!!clienteId} onClose={cerrar} title={data ? `Estado de cuenta · ${data.cliente.nombre}` : "Estado de cuenta"} wide
      footer={data && <>
        <Button onClick={() => descargar(`/cobranza/estado-cuenta/${data.cliente.id}/html`, "estado.html").catch(mostrarError)}><Printer className="size-4" /> Imprimir</Button>
        <Link href="/pagos"><Button><Wallet className="size-4" /> Registrar pago</Button></Link>
        <Button variant="primario" onClick={() => recordar(data.cliente.id)}><Mail className="size-4" /> Mandar por correo</Button>
      </>}>
      {!data ? <p className="text-sm text-grafito">Cargando…</p> : (
        <div className="grid gap-5">
          <p className="text-sm text-grafito">{data.cliente.rfc} · crédito {data.cliente.dias_credito || 0} días · saldo <b className="text-tinta">{dinero(data.saldo)}</b></p>
          <table className={tabla.base}>
            <thead><tr><th className={tabla.th}>Folio</th><th className={tabla.th}>Fecha</th><th className={tabla.th}>Vence</th>
              <th className={cx(tabla.th, tabla.num)}>Días</th><th className={cx(tabla.th, tabla.num)}>Total</th><th className={cx(tabla.th, tabla.num)}>Saldo</th></tr></thead>
            <tbody>
              {data.pendientes.map((p) => (
                <tr key={p.factura_id}>
                  <td className={tabla.td}>{p.folio}</td><td className={tabla.td}>{fecha(p.fecha)}</td><td className={tabla.td}>{fecha(p.vence)}</td>
                  <td className={cx(tabla.td, tabla.num, p.dias_vencido > 0 && "text-rojo")}>{p.dias_vencido || "—"}</td>
                  <td className={cx(tabla.td, tabla.num)}>{dinero(p.total)}</td><td className={cx(tabla.td, tabla.num, "font-semibold")}>{dinero(p.saldo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.movimientos.length > 0 && (
            <details>
              <summary className="cursor-pointer text-sm text-grafito">Movimientos ({data.movimientos.length})</summary>
              <table className={cx(tabla.base, "mt-2")}>
                <tbody>
                  {data.movimientos.map((m, i) => (
                    <tr key={i}>
                      <td className={tabla.td}>{fecha(m.fecha)}</td><td className={tabla.td}>{m.folio} · {m.tipo === "P" ? "Pago" : m.tipo === "E" ? "Nota de crédito" : "Factura"}</td>
                      <td className={cx(tabla.td, tabla.num)}>{Number(m.cargo) ? dinero(m.cargo) : ""}</td>
                      <td className={cx(tabla.td, tabla.num, "text-sello")}>{Number(m.abono) ? `−${dinero(m.abono)}` : ""}</td>
                      <td className={cx(tabla.td, tabla.num)}>{dinero(m.saldo)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </div>
      )}
    </Modal>
  );
}
