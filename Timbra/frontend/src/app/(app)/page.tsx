"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { AlertTriangle, ArrowRight, ArrowUpRight, CalendarClock, Coins, HandCoins, Info, Zap } from "lucide-react";
import { fetcher } from "@/lib/api";
import { dinero, ESTADOS, fecha, TIPOS } from "@/lib/format";
import type { Factura, TimbresPac } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, cx } from "@/components/ui";

type Resumen = {
  facturado_mes: string; cobrado_mes: string; por_cobrar: string; vencido: string; comprobantes_mes: number;
  alertas: { nivel: string; texto: string }[];
  por_timbrar: { id: number; nombre: string; proxima: string; auto: boolean; error: string | null }[];
  timbres: TimbresPac[];
};

/** La cifra sube desde la anterior hasta la nueva. Sólo es adorno: al terminar se muestra el dato tal cual llegó. */
function useConteo(meta: number, ms = 800) {
  const [v, setV] = useState(0);
  const actual = useRef(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { actual.current = meta; setV(meta); return; }
    const desde = actual.current, t0 = performance.now();
    let raf = 0;
    const paso = (t: number) => {
      const p = Math.min(1, (t - t0) / ms);
      const x = p === 1 ? meta : desde + (meta - desde) * (1 - Math.pow(1 - p, 3));
      actual.current = x; setV(x);
      if (p < 1) raf = requestAnimationFrame(paso);
    };
    raf = requestAnimationFrame(paso);
    return () => cancelAnimationFrame(raf);
  }, [meta, ms]);
  return v;
}

const tarjeta = "group relative flex flex-col rounded-2xl bg-hoja p-5 ring-1 ring-linea hover:ring-acento/40";
const ficha = "grid size-9 shrink-0 place-items-center rounded-xl bg-acento-suave text-acento transition-transform duration-200 group-hover:scale-105";
const flecha = "absolute right-4 top-4 size-4 -translate-x-1 translate-y-1 text-acento opacity-0 transition-[opacity,transform] duration-200 group-hover:translate-x-0 group-hover:translate-y-0 group-hover:opacity-100";

export default function Inicio() {
  const { emisor } = useEmisor();
  const q = emisor ? `?emisor_id=${emisor.id}` : "";
  const { data } = useSWR<Resumen>(`/dashboard${q}`, fetcher, { refreshInterval: 120_000 });
  const { data: ultimas } = useSWR<Factura[]>(emisor ? `/facturas?emisor_id=${emisor.id}&limit=8` : null, fetcher);
  const hoy = new Date();
  const mes = hoy.toLocaleDateString("es-MX", { month: "long" });
  const timbres = (data?.timbres ?? []).filter((t) => !t.pruebas);
  const enPruebas = (data?.timbres ?? []).filter((t) => t.pruebas);
  const { data: yo } = useSWR<{ timbres: number | null }>("/auth/yo", fetcher);  // cuentas de clientes: su saldo
  const vencido = Number(data?.vencido ?? 0);
  const facturado = Number(data?.facturado_mes ?? 0);
  const cobrado = Number(data?.cobrado_mes ?? 0);
  const avance = facturado > 0 ? Math.min(100, Math.round((cobrado / facturado) * 100)) : 0;
  const cifra = useConteo(facturado);

  return (
    <>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[13px] text-grafito first-letter:uppercase">{hoy.toLocaleDateString("es-MX", { weekday: "long", day: "numeric", month: "long" })}</p>
          <h1 className="mt-1 truncate text-2xl font-semibold tracking-tight sm:text-[28px]">{emisor?.nombre ?? "Resumen"}</h1>
          {emisor && <p className="mt-1 font-mono text-xs tracking-wide text-grafito">{emisor.rfc}</p>}
        </div>
        <Link href="/facturar"><Button variant="acento" size="lg"><Zap className="size-4" /> Nueva factura <kbd className="rounded-md bg-white/20 px-1.5 py-0.5 font-sans text-[11px] font-medium">F2</kbd></Button></Link>
      </div>

      {!!data?.alertas.length && (
        <div className="escalonar mb-5 flex flex-col gap-2">
          {data.alertas.filter((a) => a.nivel !== "info").map((a, i) => (
            <p key={i} className={cx("flex items-center gap-2.5 rounded-xl px-4 py-3 text-sm ring-1 ring-current/15", a.nivel === "error" ? "bg-rojo-suave text-rojo" : "bg-alerta-suave text-alerta")}>
              <AlertTriangle className="size-4 shrink-0" /> {a.texto}
            </p>
          ))}
          {data.alertas.filter((a) => a.nivel === "info").map((a, i) => (
            <p key={`i${i}`} className="flex items-center gap-2.5 rounded-xl bg-tinta/[.04] px-4 py-3 text-sm text-grafito ring-1 ring-linea"><Info className="size-4 shrink-0" /> {a.texto}</p>
          ))}
        </div>
      )}

      <div className="escalonar grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <section className="panel-heroe flex min-h-56 flex-col rounded-2xl p-6 sm:col-span-2 sm:p-7 lg:row-span-2">
          <p className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[.14em] text-white/60">
            <span className="size-1.5 rounded-full bg-[#7ea0ff] shadow-[0_0_0_4px_rgb(126_160_255/.2)]" /> Facturado en {mes}
          </p>
          <p className={cx("mt-4 text-[44px] font-semibold leading-none tracking-[-.035em] tabular-nums sm:text-[56px]", !data && "esqueleto w-64 bg-white/10")}>
            {dinero(cifra === facturado ? data?.facturado_mes : cifra)}
          </p>
          <div className="mt-auto pt-8">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-white/60">Cobrado</span>
              <span className="tabular-nums text-white/60"><b className="font-medium text-white">{dinero(data?.cobrado_mes)}</b> · {avance}%</span>
            </div>
            <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-white/10">
              <div key={avance} className="animate-crecer h-full rounded-full bg-linear-to-r from-[#5b86ff] to-[#9db8ff]" style={{ width: `${avance}%` }} />
            </div>
            <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-white/10 pt-5">
              <div><dt className="text-xs text-white/55">Comprobantes timbrados</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{data?.comprobantes_mes ?? 0}</dd></div>
              <div><dt className="text-xs text-white/55">Promedio por comprobante</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{dinero(data?.comprobantes_mes ? facturado / data.comprobantes_mes : 0)}</dd></div>
            </dl>
          </div>
        </section>

        <Link href="/cobranza" className={tarjeta}>
          <ArrowUpRight className={flecha} />
          <span className={ficha}><HandCoins className="size-[18px]" /></span>
          <p className="mt-4 text-[13px] text-grafito">Por cobrar (PPD)</p>
          <p className="mt-1 text-[28px] font-semibold leading-tight tracking-tight tabular-nums">{dinero(data?.por_cobrar)}</p>
          <p className={cx("mt-1.5 flex items-center gap-1.5 text-[13px]", vencido > 0 ? "text-rojo" : "text-grafito")}>
            <span className={cx("size-1.5 rounded-full", vencido > 0 ? "bg-rojo" : "bg-sello")} />{vencido > 0 ? `${dinero(vencido)} vencido` : "Nada vencido"}
          </p>
        </Link>

        <Link href="/timbres" className={tarjeta}>
          <ArrowUpRight className={flecha} />
          <span className={ficha}><Coins className="size-[18px]" /></span>
          <p className="mt-4 text-[13px] text-grafito">Timbres</p>
          {typeof yo?.timbres === "number" ? (
            <>
              <p className={cx("mt-1 text-[28px] font-semibold leading-tight tracking-tight tabular-nums", yo.timbres <= 0 ? "text-rojo" : yo.timbres <= 5 ? "text-alerta" : "")}>{yo.timbres}</p>
              <p className="mt-1.5 text-[13px] text-grafito">disponibles en tu cuenta</p>
            </>
          ) : timbres.length ? timbres.slice(0, 2).map((t, i) => (
            <p key={t.pac_id} className={cx("truncate text-[13px] text-grafito", i ? "mt-1" : "mt-1", t.nivel === "error" ? "text-rojo" : t.nivel === "aviso" ? "text-alerta" : "")}>
              <b className={cx("font-semibold tracking-tight tabular-nums", i ? "text-lg" : "text-[28px] leading-tight", t.nivel === "ok" && "text-tinta")}>{t.restantes ?? t.usados_mes}</b> {t.restantes !== null ? "restantes" : "usados este mes"} · {t.nombre}
            </p>
          )) : enPruebas.length ? (
            <>
              <p className="mt-1 text-[28px] font-semibold leading-tight tracking-tight tabular-nums">{enPruebas[0].usados_mes}</p>
              <p className="mt-1.5 flex items-center gap-1.5 text-[13px] text-grafito"><span className="size-1.5 rounded-full bg-cobalto" />en pruebas este mes · no se cobran</p>
            </>
          ) : (
            <>
              <p className="mt-1 text-[28px] font-semibold leading-tight tracking-tight text-grafito/50">—</p>
              <p className="mt-1.5 flex items-center gap-1.5 text-[13px] text-grafito"><span className="size-1.5 rounded-full bg-alerta" />Sin PAC de producción</p>
            </>
          )}
        </Link>

        <Link href="/recurrentes" className={cx(tarjeta, "sm:col-span-2")}>
          <ArrowUpRight className={flecha} />
          <div className="flex items-center gap-3">
            <span className={ficha}><CalendarClock className="size-[18px]" /></span>
            <div className="min-w-0">
              <p className="text-sm font-medium">Recurrentes por timbrar hoy</p>
              <p className="text-[13px] text-grafito">{data?.por_timbrar.length ? `${data.por_timbrar.length} en espera` : "Nada pendiente hoy."}</p>
            </div>
          </div>
          {!!data?.por_timbrar.length && (
            <ul className="mt-4 flex flex-col divide-y divide-linea border-t border-linea text-sm">
              {data.por_timbrar.slice(0, 4).map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-2 py-2"><span className="truncate">{p.nombre}</span>
                  <span className={cx("shrink-0 text-xs", p.error ? "text-rojo" : "text-grafito")}>{p.error ? "con error" : p.auto ? "automática" : fecha(p.proxima)}</span></li>
              ))}
              {data.por_timbrar.length > 4 && <li className="pt-2 text-xs text-grafito">y {data.por_timbrar.length - 4} más</li>}
            </ul>
          )}
        </Link>
      </div>

      <div className="mb-3 mt-10 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Lo último</h2>
        <Link href="/facturas" className="group flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-grafito transition-colors hover:bg-tinta/5 hover:text-tinta">Todas <ArrowRight className="size-3.5 transition-transform duration-150 group-hover:translate-x-0.5" /></Link>
      </div>
      <div className="escalonar overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea">
        {ultimas?.map((f) => (
          <Link key={f.id} href={`/facturas?id=${f.id}`} className="group flex items-center gap-4 border-b border-linea px-5 py-3.5 transition-colors last:border-0 hover:bg-papel/70">
            <span className="w-16 shrink-0 rounded-md bg-tinta/[.045] px-2 py-1 text-center font-mono text-xs font-medium tabular-nums">{f.serie}{f.folio}</span>
            <span className="min-w-0 flex-1 truncate font-medium">{f.receptor_nombre}</span>
            <span className="hidden text-[13px] text-grafito sm:inline">{TIPOS[f.tipo]}</span>
            <span className="hidden text-[13px] tabular-nums text-grafito md:inline">{fecha(f.fecha)}</span>
            <Badge punto tono={f.estado === "timbrada" ? "sello" : f.estado === "cancelada" ? "rojo" : "alerta"}>{ESTADOS[f.estado]}</Badge>
            <span className={cx("w-28 text-right font-semibold tabular-nums", f.estado === "cancelada" && "font-normal text-grafito line-through")}>{dinero(f.total)}</span>
            <ArrowRight className="hidden size-4 shrink-0 -translate-x-1 text-grafito opacity-0 transition-[opacity,transform] duration-150 group-hover:translate-x-0 group-hover:opacity-100 sm:block" />
          </Link>
        ))}
        {!ultimas && emisor && [0, 1, 2].map((i) => (
          <div key={i} className="flex items-center gap-4 border-b border-linea px-5 py-4 last:border-0">
            <span className="esqueleto h-6 w-16" /><span className="esqueleto h-4 flex-1" /><span className="esqueleto h-4 w-24" />
          </div>
        ))}
        {(ultimas ? !ultimas.length : !emisor) && <p className="px-5 py-12 text-center text-grafito">Aún no hay facturas. Presiona F2 y timbra la primera.</p>}
      </div>
    </>
  );
}
