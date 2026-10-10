"use client";
import Link from "next/link";
import useSWR from "swr";
import { AlertTriangle, ArrowRight, CalendarClock, Coins, HandCoins, Info, Zap } from "lucide-react";
import { fetcher } from "@/lib/api";
import { dinero, ESTADOS, fecha, TIPOS } from "@/lib/format";
import type { Factura, TimbresPac } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Kbd, PageHeader, cx } from "@/components/ui";

type Resumen = {
  facturado_mes: string; cobrado_mes: string; por_cobrar: string; vencido: string; comprobantes_mes: number;
  alertas: { nivel: string; texto: string }[];
  por_timbrar: { id: number; nombre: string; proxima: string; auto: boolean; error: string | null }[];
  timbres: TimbresPac[];
};

export default function Inicio() {
  const { emisor } = useEmisor();
  const q = emisor ? `?emisor_id=${emisor.id}` : "";
  const { data } = useSWR<Resumen>(`/dashboard${q}`, fetcher, { refreshInterval: 120_000 });
  const { data: ultimas = [] } = useSWR<Factura[]>(emisor ? `/facturas?emisor_id=${emisor.id}&limit=8` : null, fetcher);
  const mes = new Date().toLocaleDateString("es-MX", { month: "long" });
  const timbres = (data?.timbres ?? []).filter((t) => !t.pruebas);
  const vencido = Number(data?.vencido ?? 0);

  return (
    <>
      <PageHeader title={emisor?.nombre ?? "Resumen"}>
        <Link href="/facturar"><Button variant="primario"><Zap className="size-4" /> Facturar <Kbd>F2</Kbd></Button></Link>
      </PageHeader>

      {data?.alertas.filter((a) => a.nivel !== "info").map((a, i) => (
        <p key={i} className={cx("mb-2 flex items-center gap-2 rounded-xl px-4 py-3 text-sm", a.nivel === "error" ? "bg-rojo-suave text-rojo" : "bg-alerta-suave text-alerta")}>
          <AlertTriangle className="size-4 shrink-0" /> {a.texto}
        </p>
      ))}
      {data?.alertas.filter((a) => a.nivel === "info").map((a, i) => (
        <p key={`i${i}`} className="mb-2 flex items-center gap-2 rounded-xl bg-tinta/5 px-4 py-3 text-sm text-grafito"><Info className="size-4 shrink-0" /> {a.texto}</p>
      ))}

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl bg-tinta p-6 text-white sm:col-span-2 lg:row-span-2">
          <p className="text-sm text-white/70">Facturado en {mes}</p>
          <p className="mt-2 text-5xl font-semibold tracking-tight tabular-nums">{dinero(data?.facturado_mes)}</p>
          <p className="mt-3 text-sm text-white/70">{data?.comprobantes_mes ?? 0} comprobantes timbrados · cobrado {dinero(data?.cobrado_mes)}</p>
        </div>
        <Link href="/cobranza" className="group rounded-2xl bg-hoja p-6 ring-1 ring-linea transition hover:ring-tinta/40">
          <p className="flex items-center gap-2 text-sm text-grafito"><HandCoins className="size-4" /> Por cobrar (PPD)</p>
          <p className="mt-1 text-3xl font-semibold tabular-nums">{dinero(data?.por_cobrar)}</p>
          <p className={cx("mt-1 text-sm", vencido > 0 ? "text-rojo" : "text-grafito")}>{vencido > 0 ? `${dinero(vencido)} vencido` : "Nada vencido"}</p>
        </Link>
        <Link href="/timbres" className="group rounded-2xl bg-hoja p-6 ring-1 ring-linea transition hover:ring-tinta/40">
          <p className="flex items-center gap-2 text-sm text-grafito"><Coins className="size-4" /> Timbres</p>
          {timbres.length ? timbres.slice(0, 2).map((t) => (
            <p key={t.pac_id} className={cx("mt-1 text-sm", t.nivel === "error" ? "text-rojo" : t.nivel === "aviso" ? "text-alerta" : "")}>
              <b className="text-2xl font-semibold tabular-nums">{t.restantes ?? t.usados_mes}</b> {t.restantes !== null ? "restantes" : "usados este mes"} · {t.nombre}
            </p>
          )) : <p className="mt-1 text-sm text-grafito">Sin PAC de producción</p>}
        </Link>
        <Link href="/recurrentes" className="group rounded-2xl bg-hoja p-6 ring-1 ring-linea transition hover:ring-tinta/40 sm:col-span-2">
          <p className="flex items-center gap-2 text-sm text-grafito"><CalendarClock className="size-4" /> Recurrentes por timbrar hoy</p>
          {data?.por_timbrar.length ? (
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {data.por_timbrar.slice(0, 4).map((p) => (
                <li key={p.id} className="flex justify-between gap-2"><span className="truncate">{p.nombre}</span>
                  <span className={cx("shrink-0 text-xs", p.error ? "text-rojo" : "text-grafito")}>{p.error ? "con error" : p.auto ? "automática" : fecha(p.proxima)}</span></li>
              ))}
              {data.por_timbrar.length > 4 && <li className="text-xs text-grafito">y {data.por_timbrar.length - 4} más</li>}
            </ul>
          ) : <p className="mt-1 text-sm text-grafito">Nada pendiente hoy.</p>}
        </Link>
      </div>

      <div className="mb-3 mt-10 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Lo último</h2>
        <Link href="/facturas" className="flex items-center gap-1 text-sm text-grafito hover:text-tinta">Todas <ArrowRight className="size-3.5" /></Link>
      </div>
      <div className="overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea">
        {ultimas.map((f) => (
          <Link key={f.id} href={`/facturas?id=${f.id}`} className="flex items-center gap-4 border-b border-linea px-5 py-3 last:border-0 hover:bg-papel">
            <span className="w-20 font-medium tabular-nums">{f.serie}{f.folio}</span>
            <span className="min-w-0 flex-1 truncate">{f.receptor_nombre}</span>
            <span className="hidden text-sm text-grafito sm:inline">{TIPOS[f.tipo]}</span>
            <span className="hidden text-sm text-grafito md:inline">{fecha(f.fecha)}</span>
            <Badge tono={f.estado === "timbrada" ? "sello" : f.estado === "cancelada" ? "rojo" : "alerta"}>{ESTADOS[f.estado]}</Badge>
            <span className="w-32 text-right font-medium tabular-nums">{dinero(f.total)}</span>
          </Link>
        ))}
        {!ultimas.length && <p className="px-5 py-10 text-center text-grafito">Aún no hay facturas. Presiona F2 y timbra la primera.</p>}
      </div>
    </>
  );
}
