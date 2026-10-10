"use client";
/** Ayudas de la barra de Facturar: lista de clientes guardados, lista de conceptos (catálogo + ya facturados) y editor de impuestos. */
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { Plus, Trash2 } from "lucide-react";
import { fetcher } from "@/lib/api";
import { dinero } from "@/lib/format";
import type { Cliente, Concepto, Impuesto, Producto } from "@/lib/types";
import { Badge, Button, Input, Modal, Select, Tabs, cx } from "./ui";

export type ClienteReciente = Cliente & { facturas: number; ultima: string | null };
export type ConceptoFacturado = {
  descripcion: string; clave_prod_serv: string; clave_unidad: string; unidad: string | null; valor_unitario: string;
  impuestos: Impuesto[]; objeto_imp: string; usos: number;
};
export type ClaveSat = { clave: string; descripcion: string; alertas?: { nivel: string; mensaje: string }[] };
export type Sugerencias = { productos: Producto[]; facturados: ConceptoFacturado[]; sat: ClaveSat[] };

const sinAcentos = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const fechaCorta = (iso: string) => new Date(iso).toLocaleDateString("es-MX", { day: "2-digit", month: "short", year: "2-digit" });

export const deProducto = (p: Producto, precioActual = ""): Partial<Concepto> => ({
  producto_id: p.id, descripcion: p.descripcion, clave_prod_serv: p.clave_prod_serv, clave_unidad: p.clave_unidad, unidad: p.unidad,
  valor_unitario: Number(p.precio) ? String(Number(p.precio)) : precioActual, impuestos: p.impuestos, objeto_imp: p.objeto_imp,
});
export const deFacturado = (f: ConceptoFacturado, precioActual = ""): Partial<Concepto> => ({
  producto_id: null, descripcion: f.descripcion, clave_prod_serv: f.clave_prod_serv, clave_unidad: f.clave_unidad, unidad: f.unidad,
  valor_unitario: Number(f.valor_unitario) ? String(Number(f.valor_unitario)) : precioActual, impuestos: f.impuestos, objeto_imp: f.objeto_imp,
});

function Filtro({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="mb-3 h-11" autoComplete="off" />;
}

/** Todos los clientes guardados del emisor; primero a los que les facturaste más recientemente. */
export function ListaClientes({ emisorId, abierto, cerrar, onElegir }: { emisorId: number; abierto: boolean; cerrar: () => void; onElegir: (c: Cliente) => void }) {
  const { data = [], isLoading } = useSWR<ClienteReciente[]>(abierto ? `/clientes/recientes?emisor_id=${emisorId}` : null, fetcher);
  const [q, setQ] = useState("");
  useEffect(() => { if (abierto) setQ(""); }, [abierto]);
  const lista = useMemo(() => {
    const t = sinAcentos(q.trim());
    return t ? data.filter((c) => sinAcentos(`${c.nombre} ${c.rfc}`).includes(t)) : data;
  }, [data, q]);
  return (
    <Modal open={abierto} onClose={cerrar} title="Clientes guardados" wide>
      <Filtro value={q} onChange={setQ} placeholder="Filtra por nombre o RFC…" />
      {isLoading ? <p className="text-sm text-grafito">Cargando…</p> : !lista.length ? (
        <p className="py-8 text-center text-sm text-grafito">{data.length ? "Ninguno coincide." : "Aún no tienes clientes guardados. Se guardan solos al facturarles."}</p>
      ) : (
        <ul className="max-h-[58vh] divide-y divide-linea overflow-auto rounded-xl ring-1 ring-linea">
          {lista.map((c) => (
            <li key={c.id}>
              <button onClick={() => { onElegir(c); cerrar(); }} className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-left text-sm hover:bg-papel focus:bg-papel focus:outline-none">
                <span className="min-w-0 flex-1">
                  <b className="block truncate font-medium">{c.nombre}</b>
                  <span className="text-xs text-grafito tabular-nums">{c.rfc} · CP {c.codigo_postal} · Rég. {c.regimen_fiscal} · Uso {c.uso_cfdi}</span>
                </span>
                {c.ultima ? <Badge tono="sello">{c.facturas} {c.facturas === 1 ? "factura" : "facturas"} · {fechaCorta(c.ultima)}</Badge> : <Badge>Sin facturas</Badge>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

/** Tu catálogo de productos y los conceptos que ya facturaste (aunque no los hayas guardado). */
export function ListaConceptos({ emisorId, abierto, cerrar, onElegir }: { emisorId: number; abierto: boolean; cerrar: () => void; onElegir: (c: Partial<Concepto>) => void }) {
  const { data, isLoading } = useSWR<Sugerencias>(abierto ? `/productos/sugerencias?emisor_id=${emisorId}&sat=false` : null, fetcher);
  const [q, setQ] = useState("");
  const [vista, setVista] = useState<"catalogo" | "facturados">("catalogo");
  useEffect(() => { if (abierto) setQ(""); }, [abierto]);
  const t = sinAcentos(q.trim());
  const prods = (data?.productos ?? []).filter((p) => !t || sinAcentos(`${p.descripcion} ${p.clave_prod_serv}`).includes(t));
  const facts = (data?.facturados ?? []).filter((f) => !t || sinAcentos(`${f.descripcion} ${f.clave_prod_serv}`).includes(t));
  const fila = "flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-left text-sm hover:bg-papel focus:bg-papel focus:outline-none";
  return (
    <Modal open={abierto} onClose={cerrar} title="Conceptos guardados" wide>
      <Filtro value={q} onChange={setQ} placeholder="Filtra por descripción o clave…" />
      <Tabs value={vista} onChange={setVista} items={[{ id: "catalogo", label: "Mi catálogo", n: prods.length }, { id: "facturados", label: "Ya facturados", n: facts.length }]} />
      {isLoading ? <p className="text-sm text-grafito">Cargando…</p> : (
        <ul className="max-h-[52vh] divide-y divide-linea overflow-auto rounded-xl ring-1 ring-linea">
          {vista === "catalogo" && prods.map((p) => (
            <li key={p.id}><button onClick={() => { onElegir(deProducto(p)); cerrar(); }} className={fila}>
              <span className="min-w-0 flex-1 truncate font-medium">{p.descripcion}</span>
              <span className="font-mono text-xs text-grafito">{p.clave_prod_serv} · {p.clave_unidad}</span>
              {Number(p.precio) > 0 && <span className="tabular-nums">{dinero(p.precio)}</span>}
            </button></li>
          ))}
          {vista === "facturados" && facts.map((f) => (
            <li key={f.descripcion + f.clave_prod_serv}><button onClick={() => { onElegir(deFacturado(f)); cerrar(); }} className={fila}>
              <span className="min-w-0 flex-1 truncate font-medium">{f.descripcion}</span>
              <span className="font-mono text-xs text-grafito">{f.clave_prod_serv} · {f.clave_unidad}</span>
              {Number(f.valor_unitario) > 0 && <span className="tabular-nums">{dinero(f.valor_unitario)}</span>}
              <Badge>{f.usos} {f.usos === 1 ? "vez" : "veces"}</Badge>
            </button></li>
          ))}
          {((vista === "catalogo" && !prods.length) || (vista === "facturados" && !facts.length)) && (
            <li className="px-4 py-8 text-center text-sm text-grafito">{vista === "catalogo" ? "Nada en tu catálogo con ese texto." : "Aquí aparecen los conceptos de tus facturas que no están en el catálogo."}</li>
          )}
        </ul>
      )}
    </Modal>
  );
}

// ======================= Editor de impuestos =======================

type Linea = { clase: string; tasa: string };
const CLASES: { id: string; label: string; imp: Omit<Impuesto, "tasa">; sugeridas: string[]; cuota?: boolean; sinTasa?: boolean }[] = [
  { id: "iva", label: "IVA trasladado", imp: { tipo: "traslado", impuesto: "002", factor: "Tasa" }, sugeridas: ["16", "8", "0"] },
  { id: "iva_exento", label: "IVA exento", imp: { tipo: "traslado", impuesto: "002", factor: "Exento" }, sugeridas: [], sinTasa: true },
  { id: "ieps", label: "IEPS por tasa (%)", imp: { tipo: "traslado", impuesto: "003", factor: "Tasa" }, sugeridas: ["8", "25", "26.5", "30", "53"] },
  { id: "ieps_cuota", label: "IEPS por cuota ($ por unidad)", imp: { tipo: "traslado", impuesto: "003", factor: "Cuota" }, sugeridas: [], cuota: true },
  { id: "ret_isr", label: "Retención de ISR", imp: { tipo: "retencion", impuesto: "001", factor: "Tasa" }, sugeridas: ["10", "1.25"] },
  { id: "ret_iva", label: "Retención de IVA", imp: { tipo: "retencion", impuesto: "002", factor: "Tasa" }, sugeridas: ["10.6667", "5.3333", "6", "4", "16"] },
];
const claseDe = (i: Impuesto) => CLASES.find((c) => c.imp.tipo === i.tipo && c.imp.impuesto === i.impuesto && c.imp.factor === i.factor) ?? CLASES[0];
const aLinea = (i: Impuesto): Linea => {
  const c = claseDe(i);
  const n = Number(i.tasa ?? 0);
  return { clase: c.id, tasa: c.sinTasa ? "" : c.cuota ? String(n) : String(Number((n * 100).toFixed(4))) };
};
const aImpuesto = (l: Linea): Impuesto | null => {
  const c = CLASES.find((x) => x.id === l.clase)!;
  if (c.sinTasa) return { ...c.imp, tasa: null };
  const n = Number(l.tasa.replace(",", "."));
  if (!isFinite(n) || l.tasa.trim() === "" || n < 0) return null;
  return { ...c.imp, tasa: (c.cuota ? n : n / 100).toFixed(6) };
};

/** Arma a mano los impuestos de un concepto: cualquier tasa de IEPS, cuotas, retenciones poco comunes. */
export function EditorImpuestos({ abierto, cerrar, impuestos, onUsar }: { abierto: boolean; cerrar: () => void; impuestos: Impuesto[]; onUsar: (i: Impuesto[]) => void }) {
  const [lineas, setLineas] = useState<Linea[]>([]);
  useEffect(() => { if (abierto) setLineas(impuestos.length ? impuestos.map(aLinea) : [{ clase: "iva", tasa: "16" }]); }, [abierto]); // eslint-disable-line react-hooks/exhaustive-deps
  const upd = (i: number, p: Partial<Linea>) => setLineas(lineas.map((l, j) => (j === i ? { ...l, ...p } : l)));
  const res = lineas.map(aImpuesto);
  const malo = res.some((r) => r === null);
  const ivas = lineas.filter((l) => l.clase === "iva" || l.clase === "iva_exento").length;
  return (
    <Modal open={abierto} onClose={cerrar} title="Impuestos del concepto"
      footer={<><Button onClick={cerrar}>Cancelar</Button><Button variant="primario" disabled={malo || ivas > 1} onClick={() => { onUsar(res as Impuesto[]); cerrar(); }}>Usar estos impuestos</Button></>}>
      <div className="grid gap-2">
        {lineas.map((l, i) => {
          const c = CLASES.find((x) => x.id === l.clase)!;
          return (
            <div key={i} className="grid grid-cols-[1fr_96px_auto] items-center gap-2">
              <Select value={l.clase} aria-label="Impuesto" onChange={(e) => { const n = CLASES.find((x) => x.id === e.target.value)!; upd(i, { clase: n.id, tasa: n.sugeridas[0] ?? "" }); }}>
                {CLASES.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
              </Select>
              {c.sinTasa ? <span className="text-center text-sm text-grafito">—</span> : (
                <Input value={l.tasa} inputMode="decimal" list={`tasas-${i}`} aria-label={c.cuota ? "Cuota en pesos" : "Tasa en porcentaje"} placeholder={c.cuota ? "$ / unidad" : "%"}
                  onChange={(e) => upd(i, { tasa: e.target.value })} className={cx("text-right tabular-nums", res[i] === null && "border-rojo")} />
              )}
              <datalist id={`tasas-${i}`}>{c.sugeridas.map((s) => <option key={s} value={s} />)}</datalist>
              <button onClick={() => setLineas(lineas.filter((_, j) => j !== i))} aria-label="Quitar" className="rounded-md p-2 text-grafito hover:bg-rojo-suave hover:text-rojo"><Trash2 className="size-4" /></button>
            </div>
          );
        })}
        <Button size="sm" variant="fantasma" className="self-start justify-self-start" onClick={() => setLineas([...lineas, { clase: "ieps", tasa: "8" }])}><Plus className="size-4" /> Agregar impuesto</Button>
        {!lineas.length && <p className="text-sm text-grafito">Sin impuestos: el concepto sale como «no objeto de impuesto» (01).</p>}
        {ivas > 1 && <p className="text-sm text-rojo">Sólo puede ir un IVA trasladado por concepto.</p>}
        <p className="mt-2 text-xs text-grafito">
          Las tasas van en porcentaje (8 = 8%). Con IEPS, el IVA se calcula sobre el precio más el IEPS. La cuota de IEPS es en pesos por unidad
          (por litro, por pieza) y se multiplica por la cantidad; las cuotas de refrescos, tabaco y combustibles cambian cada año: usa la vigente.
        </p>
      </div>
    </Modal>
  );
}
