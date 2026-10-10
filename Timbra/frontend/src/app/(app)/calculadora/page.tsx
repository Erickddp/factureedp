"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Plus, Trash2, Zap } from "lucide-react";
import { fetcher } from "@/lib/api";
import { dinero, PRESETS_IMPUESTOS, presetPorDefecto } from "@/lib/format";
import { baseDesde, suma, type Modo } from "@/lib/impuestos";
import type { Impuesto, Producto } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { OpcionesImpuestos } from "@/components/impuestos";
import { SelectorModo, TablaDesglose } from "@/components/calculadora";
import { Button, Field, Input, PageHeader, Select } from "@/components/ui";

type Linea = { key: string; producto_id: number | null; descripcion: string; clave_prod_serv: string; clave_unidad: string; cantidad: string; modo: Modo; monto: string; preset: string };

const nueva = (p: Partial<Linea> = {}): Linea => ({
  key: crypto.randomUUID(), producto_id: null, descripcion: "", clave_prod_serv: "", clave_unidad: "E48", cantidad: "1",
  modo: "base", monto: "", preset: "IVA 16%", ...p,
});

export default function Calculadora() {
  const { emisor } = useEmisor();
  const router = useRouter();
  const frontera = !!emisor?.region_fronteriza;
  const { data: productos = [] } = useSWR<Producto[]>(emisor ? `/productos?emisor_id=${emisor.id}` : null, fetcher);
  const [lineas, setLineas] = useState<Linea[]>([]);

  // Caso típico: honorarios + suplemento (con IVA 8% si el emisor es de región fronteriza)
  useEffect(() => {
    setLineas([
      nueva({ descripcion: "Honorarios", clave_prod_serv: "80101500", modo: "neto",
        preset: frontera ? "Honorarios PF → PM · IVA 8% frontera (ret. ISR 10%, IVA 5.3333%)" : "Honorarios PF → PM · IVA 16% (ret. ISR 10%, IVA 10.6667%)" }),
      nueva({ descripcion: "Suplemento alimenticio", clave_prod_serv: "51191900", clave_unidad: "H87", preset: presetPorDefecto(frontera) }),
    ]);
  }, [frontera]);

  const upd = (k: string, p: Partial<Linea>) => setLineas((ls) => ls.map((l) => (l.key === k ? { ...l, ...p } : l)));
  const calc = useMemo(() => lineas.map((l) => {
    const n = Number(l.monto.replace(/[$,\s]/g, ""));
    return n > 0 ? baseDesde(n, l.modo, (PRESETS_IMPUESTOS[l.preset] ?? []) as Impuesto[]) : null;
  }), [lineas]);
  const total = suma(calc.filter((c): c is NonNullable<typeof c> => !!c).map((c) => c.d));

  const facturar = () => {
    const conceptos = lineas.map((l, i) => {
      const c = calc[i];
      if (!c) return null;
      const cant = Number(l.cantidad) > 0 ? Number(l.cantidad) : 1;
      const imps = [...(PRESETS_IMPUESTOS[l.preset] ?? [])] as Impuesto[];
      return {
        producto_id: l.producto_id, descripcion: l.descripcion || "Concepto", clave_prod_serv: l.clave_prod_serv, clave_unidad: l.clave_unidad,
        cantidad: String(cant), valor_unitario: (c.d.base / cant).toFixed(cant === 1 ? 2 : 6), impuestos: imps, objeto_imp: imps.length ? "02" : "01",
      };
    }).filter(Boolean);
    localStorage.setItem("timbra:calc", JSON.stringify(conceptos));
    router.push("/facturar?calc=1");
  };

  return (
    <>
      <PageHeader title="Calculadora de impuestos">
        <Button variant="primario" onClick={facturar} disabled={!calc.some(Boolean)}><Zap className="size-4" /> Facturar esto</Button>
      </PageHeader>
      <p className="mb-5 max-w-3xl text-sm text-grafito">
        Escribe el monto que tienes —sin IVA, con IVA o lo que te van a depositar— y te saco el precio exacto al centavo con IVA 16%, 8% frontera, 0% o exento
        y sus retenciones (la de IVA siempre es 2/3 del IVA: 10.6667% con 16%, 5.3333% con 8%).
      </p>
      <div className="grid gap-6 @container min-[1100px]:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col gap-4">
          {lineas.map((l, i) => (
            <section key={l.key} className="@container rounded-2xl bg-hoja p-4 ring-1 ring-linea sm:p-5">
              <div className="mb-3 flex items-center gap-2">
                <span className="grid size-6 place-items-center rounded-full bg-papel text-xs font-semibold">{i + 1}</span>
                <Select value={l.producto_id ?? ""} aria-label="Tomar de mi catálogo" className="min-w-0 flex-1"
                  onChange={(e) => {
                    const p = productos.find((x) => x.id === Number(e.target.value));
                    if (p) upd(l.key, { producto_id: p.id, descripcion: p.descripcion, clave_prod_serv: p.clave_prod_serv, clave_unidad: p.clave_unidad,
                      preset: Object.entries(PRESETS_IMPUESTOS).find(([, v]) => JSON.stringify(v) === JSON.stringify(p.impuestos))?.[0] ?? l.preset });
                  }}>
                  <option value="">Tomar de mi catálogo…</option>
                  {productos.map((p) => <option key={p.id} value={p.id}>{p.descripcion}</option>)}
                </Select>
                {lineas.length > 1 && (
                  <button onClick={() => setLineas((ls) => ls.filter((x) => x.key !== l.key))} aria-label="Quitar línea" className="rounded-md p-2 text-grafito hover:bg-rojo-suave hover:text-rojo">
                    <Trash2 className="size-4" />
                  </button>
                )}
              </div>
              <div className="grid gap-3 @min-[620px]:grid-cols-[minmax(0,1fr)_90px]">
                <Field label="Descripción"><Input value={l.descripcion} onChange={(e) => upd(l.key, { descripcion: e.target.value })} /></Field>
                <Field label="Cantidad"><Input value={l.cantidad} inputMode="decimal" onChange={(e) => upd(l.key, { cantidad: e.target.value })} /></Field>
              </div>
              <div className="mt-3 grid gap-3 @min-[620px]:grid-cols-2">
                <Field label="¿Qué monto tienes? (del total de la línea)"><SelectorModo modo={l.modo} setModo={(m) => upd(l.key, { modo: m })} /></Field>
                <Field label="Monto"><Input value={l.monto} inputMode="decimal" placeholder="0.00" className="tabular-nums" onChange={(e) => upd(l.key, { monto: e.target.value })} /></Field>
                <Field label="Impuestos" className="@min-[620px]:col-span-2">
                  <Select value={PRESETS_IMPUESTOS[l.preset] ? l.preset : "Personalizado"} onChange={(e) => upd(l.key, { preset: e.target.value })}>
                    <OpcionesImpuestos frontera={frontera} />
                  </Select>
                </Field>
              </div>
              {calc[i] && <TablaDesglose d={calc[i]!.d} className="mt-4 rounded-xl bg-papel p-3" />}
            </section>
          ))}
          <Button variant="fantasma" className="self-start" onClick={() => setLineas((ls) => [...ls, nueva({ preset: presetPorDefecto(frontera) })])}>
            <Plus className="size-4" /> Otra línea
          </Button>
        </div>
        <aside className="self-start rounded-2xl bg-hoja p-5 shadow-sm ring-1 ring-linea min-[1100px]:sticky min-[1100px]:top-8">
          <h2 className="mb-3 font-semibold">Toda la factura</h2>
          <TablaDesglose d={total} />
          <p className="mt-4 text-[44px] font-semibold leading-none tracking-tight tabular-nums">{dinero(total.total)}</p>
          <p className="mt-1 text-sm text-grafito">te depositan</p>
          <Button variant="primario" size="lg" className="mt-5 w-full" onClick={facturar} disabled={!calc.some(Boolean)}>Facturar esto</Button>
        </aside>
      </div>
    </>
  );
}
