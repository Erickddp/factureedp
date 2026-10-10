"use client";
import Link from "next/link";
import useSWR from "swr";
import { AlertTriangle, ArrowRight, CheckCircle2, Info, RefreshCw, XCircle } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { Button, PageHeader, Vacio, cx } from "@/components/ui";
import { fetcher } from "@/lib/api";
import type { ItemPendiente, Pendientes } from "@/lib/types";

const ICONO = { error: XCircle, aviso: AlertTriangle, info: Info } as const;
const COLOR = { error: "text-rojo", aviso: "text-alerta", info: "text-grafito" } as const;

export default function PaginaPendientes() {
  const { emisor } = useEmisor();
  const { data, mutate, isLoading, isValidating } = useSWR<Pendientes>(emisor ? `/pendientes?emisor_id=${emisor.id}` : null, fetcher, { refreshInterval: 120_000 });
  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;
  return (
    <>
      <PageHeader title="Pendientes">
        <Button variant="fantasma" onClick={() => mutate()} loading={isValidating && !isLoading}><RefreshCw className="size-4" /> Actualizar</Button>
      </PageHeader>
      <p className="-mt-3 mb-6 max-w-2xl text-sm text-grafito">Todo lo que necesita una acción tuya en {emisor.rfc}, junto con el botón para resolverlo.</p>
      {isLoading ? <p className="text-sm text-grafito">Revisando…</p> : !data?.grupos.length ? (
        <div className="flex flex-col items-center gap-2 rounded-2xl bg-sello-suave px-6 py-14 text-center text-sello animate-entrar">
          <CheckCircle2 className="size-10" /><p className="text-lg font-semibold">Todo al día</p><p className="text-sm">No hay nada pendiente en este emisor.</p>
        </div>
      ) : (
        <div className="grid gap-6">
          <p className="text-sm text-grafito">
            {data.errores > 0 && <><b className="text-rojo">{data.errores} urgentes</b> · </>}<b className="text-tinta">{data.total}</b> en total
          </p>
          {data.grupos.map((g) => (
            <section key={g.clave}>
              <h2 className="mb-2 text-sm font-medium uppercase tracking-[.06em] text-grafito">{g.titulo} <span className="ml-1 tabular-nums">{g.items.length}</span></h2>
              <ul className="overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea">
                {g.items.map((i: ItemPendiente) => {
                  const Ic = ICONO[i.nivel];
                  return (
                    <li key={i.id} className="flex flex-wrap items-center gap-3 border-b border-linea px-4 py-3.5 last:border-0">
                      <Ic className={cx("size-5 shrink-0", COLOR[i.nivel])} />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{i.titulo}</p>
                        <p className="text-sm text-grafito">{i.detalle}</p>
                      </div>
                      <Link href={i.accion.ruta}><Button size="sm" variant={i.nivel === "error" ? "primario" : "secundario"}>{i.accion.texto} <ArrowRight className="size-3.5" /></Button></Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
