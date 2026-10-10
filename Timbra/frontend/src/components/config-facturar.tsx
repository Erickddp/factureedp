"use client";
/** Configuración de la barra de Facturar por emisor: nivel, campos, valores por defecto y perfiles de un clic. */
import { useEffect, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { PRESETS_IMPUESTOS } from "@/lib/format";
import type { CampoFacturar, ConfigFacturar, PerfilFacturar, Tercero } from "@/lib/types";
import { CatSelect } from "./catalogo";
import { Button, Field, Input, Interruptor, Modal, Select, Tabs, cx } from "./ui";

export const NIVELES: { id: ConfigFacturar["nivel"]; titulo: string; texto: string }[] = [
  { id: "simple", titulo: "Simple", texto: "Cliente, descripción y precio. Clave SAT, unidad e impuestos salen de tus valores por defecto." },
  { id: "estandar", titulo: "Estándar", texto: "Lo de diario: claves, descuento, moneda, relacionados, addenda e impuestos locales." },
  { id: "completo", titulo: "Completo", texto: "Todo: a cuenta de terceros, cuenta predial, pedimentos y opciones avanzadas abiertas." },
];
const BASE: Record<ConfigFacturar["nivel"], Record<CampoFacturar, boolean>> = {
  simple: { clave_sat: false, unidad: false, descuento: false, pago: true, moneda: false, relacionados: false, condiciones: false, addenda: false,
    locales: false, terceros: false, predial: false, aduana: false, plantillas: true, repetir_ultima: true },
  estandar: { clave_sat: true, unidad: true, descuento: true, pago: true, moneda: true, relacionados: true, condiciones: true, addenda: true,
    locales: true, terceros: false, predial: false, aduana: false, plantillas: true, repetir_ultima: true },
  completo: { clave_sat: true, unidad: true, descuento: true, pago: true, moneda: true, relacionados: true, condiciones: true, addenda: true,
    locales: true, terceros: true, predial: true, aduana: true, plantillas: true, repetir_ultima: true },
};
const CAMPOS: [CampoFacturar, string, string][] = [
  ["clave_sat", "Clave SAT del concepto", "Apagada: usa la del producto o la de por defecto"],
  ["unidad", "Unidad del concepto", ""],
  ["descuento", "Descuento por concepto", ""],
  ["pago", "Método y forma de pago", "Apagado: usa los de por defecto o los del cliente"],
  ["moneda", "Moneda y tipo de cambio", ""],
  ["relacionados", "CFDI relacionados", "Notas de crédito, sustituciones, anticipos"],
  ["condiciones", "Condiciones de pago", ""],
  ["addenda", "Addenda", "Si el cliente tiene addenda, aparece siempre"],
  ["locales", "Impuestos locales (ISH, cedular)", ""],
  ["terceros", "A cuenta de terceros", "Cobras a nombre de otro contribuyente (renta del dueño, comisión, honorarios de otro)"],
  ["predial", "Cuenta predial", "Arrendamiento de inmuebles"],
  ["aduana", "Pedimento (información aduanera)", "Venta de primera mano de mercancía importada"],
  ["plantillas", "Selector de plantillas", ""],
  ["repetir_ultima", "Ofrecer repetir la última factura del cliente", "Al elegir cliente, un clic carga lo de la vez pasada"],
];
const MODOS: [ConfigFacturar["modos"][number], string][] = [["I", "Factura"], ["G", "Público en general"], ["E", "Nota de crédito"], ["T", "Traslado"]];

export const visiblesDe = (c: ConfigFacturar | undefined): Record<CampoFacturar, boolean> =>
  c?.visibles ?? BASE.estandar;

export function ConfigFacturarModal({ emisorId, abierto, cerrar, actual, onGuardado }: {
  emisorId: number; abierto: boolean; cerrar: () => void; actual?: ConfigFacturar; onGuardado: (c: ConfigFacturar) => void;
  /** Perfil armado con lo que está en pantalla (para "Guardar lo actual como perfil") */
}) {
  const [c, setC] = useState<ConfigFacturar | null>(null);
  const [vista, setVista] = useState<"nivel" | "defaults" | "perfiles">("nivel");
  const [guardando, setGuardando] = useState(false);
  const { data: terceros = [] } = useSWR<Tercero[]>(abierto ? `/terceros?emisor_id=${emisorId}` : null, fetcher);
  // Al abrir se lee la versión guardada (no la de caché): así nunca se pisa un cambio hecho en otra pestaña o equipo
  useEffect(() => {
    if (!abierto) return setC(null);
    if (actual) setC(structuredClone(actual));
    api<ConfigFacturar>(`/emisores/${emisorId}/config-facturar`).then((x) => setC(structuredClone(x))).catch(() => {});
  }, [abierto]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!c) return null;

  const vis = { ...BASE[c.nivel], ...c.campos };
  const toggle = (k: CampoFacturar, v: boolean) => {
    const campos = { ...c.campos, [k]: v };
    if (BASE[c.nivel][k] === v) delete campos[k]; // igual que el nivel: no hace falta guardarlo
    setC({ ...c, campos });
  };
  const setD = (k: keyof ConfigFacturar["defaults"], v: unknown) => setC({ ...c, defaults: { ...c.defaults, [k]: v } });
  const setP = (i: number, p: Partial<PerfilFacturar>) => setC({ ...c, perfiles: c.perfiles.map((x, j) => (j === i ? { ...x, ...p } : x)) });

  const guardar = async () => {
    setGuardando(true);
    try {
      const r = await api<ConfigFacturar>(`/emisores/${emisorId}/config-facturar`, { method: "PUT", json: {
        nivel: c.nivel, campos: c.campos, modos: c.modos, defaults: c.defaults, perfiles: c.perfiles,
        tras_timbrar: c.tras_timbrar, avanzado_abierto: c.avanzado_abierto, claves_bloqueadas: c.claves_bloqueadas ?? [],
      } });
      toast.success("Barra de Facturar configurada");
      onGuardado(r);
      cerrar();
    } catch (e) { mostrarError(e); } finally { setGuardando(false); }
  };

  return (
    <Modal open={abierto} onClose={cerrar} title="Configurar la barra de Facturar" wide
      footer={<><Button onClick={cerrar}>Cancelar</Button><Button variant="primario" onClick={guardar} loading={guardando}>Guardar</Button></>}>
      <Tabs value={vista} onChange={setVista} items={[{ id: "nivel", label: "Nivel y campos" }, { id: "defaults", label: "Valores por defecto" }, { id: "perfiles", label: "Perfiles rápidos", n: c.perfiles.length }]} />

      {vista === "nivel" && (
        <div className="grid gap-5">
          <div className="grid gap-2 sm:grid-cols-3">
            {NIVELES.map((n) => (
              <button key={n.id} onClick={() => setC({ ...c, nivel: n.id, campos: {} })}
                className={cx("rounded-xl p-3 text-left ring-1 transition", c.nivel === n.id ? "bg-primario text-sobre-primario ring-primario" : "ring-linea hover:ring-tinta/40")}>
                <p className="font-semibold">{n.titulo}</p>
                <p className={cx("mt-1 text-xs", c.nivel === n.id ? "opacity-80" : "text-grafito")}>{n.texto}</p>
              </button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {CAMPOS.map(([k, t, h]) => <Interruptor key={k} checked={vis[k]} onChange={(v) => toggle(k, v)} label={t} hint={h || undefined} />)}
          </div>
          <Field label="Tipos de comprobante en la barra">
            <div className="flex flex-wrap gap-2">
              {MODOS.map(([m, t]) => (
                <label key={m} className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ring-1 ring-linea">
                  <input type="checkbox" checked={c.modos.includes(m)} onChange={(e) => setC({ ...c, modos: e.target.checked ? [...c.modos, m] : c.modos.filter((x) => x !== m) })} /> {t}
                </label>
              ))}
            </div>
          </Field>
          <Interruptor checked={c.avanzado_abierto} onChange={(v) => setC({ ...c, avanzado_abierto: v })} label="Opciones avanzadas abiertas al entrar" />
          <Interruptor checked={c.tras_timbrar === "nueva"} onChange={(v) => setC({ ...c, tras_timbrar: v ? "nueva" : "quedarse" })}
            label="Después de timbrar, dejar lista la siguiente" hint="Limpia la pantalla al instante; el PDF/XML quedan en el aviso y en Facturas." />
        </div>
      )}

      {vista === "defaults" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tipo al abrir">
            <Select value={c.defaults.modo} onChange={(e) => setD("modo", e.target.value)}>{MODOS.map(([m, t]) => <option key={m} value={m}>{t}</option>)}</Select>
          </Field>
          <Field label="Método de pago">
            <Select value={c.defaults.metodo} onChange={(e) => setD("metodo", e.target.value)}><option value="PUE">PUE · una exhibición</option><option value="PPD">PPD · parcialidades</option></Select>
          </Field>
          <Field label="Forma de pago (PUE)"><CatSelect catalogo="forma_pago" value={c.defaults.forma} onChange={(v) => setD("forma", v)} filtro={(x) => x.clave !== "99"} /></Field>
          <Field label="Impuestos de cada concepto nuevo" hint="Vacío = IVA 16% (u 8% si el emisor es fronterizo)">
            <Select value={c.defaults.impuesto ?? ""} onChange={(e) => setD("impuesto", e.target.value || null)}>
              <option value="">Automático</option>
              {Object.keys(PRESETS_IMPUESTOS).map((k) => <option key={k} value={k}>{k}</option>)}
            </Select>
          </Field>
          <Field label="Clave SAT por defecto" hint="Se usa si el concepto no viene de tu catálogo (nivel simple)">
            <Input value={c.defaults.clave_prod_serv} onChange={(e) => setD("clave_prod_serv", e.target.value)} maxLength={8} />
          </Field>
          <Field label="Unidad por defecto"><Input value={c.defaults.clave_unidad} onChange={(e) => setD("clave_unidad", e.target.value.toUpperCase())} maxLength={3} /></Field>
          <Field label="Claves SAT bloqueadas en este emisor" className="sm:col-span-2" hint="8 dígitos, separadas por coma. Cualquier factura con una de ellas se rechaza antes de timbrar (medicamentos, por ejemplo). También las bloqueas desde Claves SAT.">
            <Input value={(c.claves_bloqueadas ?? []).join(", ")} placeholder="51191903, 51191908, 51191910" onChange={(e) => setC({ ...c, claves_bloqueadas: e.target.value.split(/[,\s]+/).filter(Boolean) })} />
          </Field>
          <div className="sm:col-span-2"><Interruptor checked={c.defaults.enviar_email} onChange={(v) => setD("enviar_email", v)} label="Mandar por correo al cliente (marcado al abrir)" /></div>
        </div>
      )}

      {vista === "perfiles" && (
        <div className="grid gap-3">
          <p className="text-sm text-grafito">Un perfil llena en un clic tipo, pago, impuestos, el concepto típico y el tercero. Aparecen como botones arriba de Facturar.</p>
          {c.perfiles.map((p, i) => (
            <div key={p.id} className="grid gap-2 rounded-xl p-3 ring-1 ring-linea sm:grid-cols-6">
              <Input className="sm:col-span-2" placeholder="Nombre (ej. Renta a cuenta del dueño)" value={p.nombre} onChange={(e) => setP(i, { nombre: e.target.value })} />
              <Select value={p.modo ?? "I"} onChange={(e) => setP(i, { modo: e.target.value as PerfilFacturar["modo"] })}>{MODOS.map(([m, t]) => <option key={m} value={m}>{t}</option>)}</Select>
              <Select value={p.metodo ?? ""} onChange={(e) => setP(i, { metodo: e.target.value || undefined })}><option value="">Pago: igual</option><option value="PUE">PUE</option><option value="PPD">PPD</option></Select>
              <Select className="sm:col-span-2" value={p.impuesto ?? ""} onChange={(e) => setP(i, { impuesto: e.target.value || null })}>
                <option value="">Impuestos: los de por defecto</option>
                {Object.keys(PRESETS_IMPUESTOS).map((k) => <option key={k} value={k}>{k}</option>)}
              </Select>
              <Input className="sm:col-span-3" placeholder="Descripción del concepto (acepta {MES} {año})" value={p.concepto?.descripcion ?? ""} onChange={(e) => setP(i, { concepto: { ...p.concepto, descripcion: e.target.value } })} />
              <Input placeholder="Clave SAT" value={p.concepto?.clave_prod_serv ?? ""} onChange={(e) => setP(i, { concepto: { ...p.concepto, clave_prod_serv: e.target.value } })} maxLength={8} />
              <Input placeholder="Precio" inputMode="decimal" value={p.concepto?.valor_unitario ?? ""} onChange={(e) => setP(i, { concepto: { ...p.concepto, valor_unitario: e.target.value } })} />
              <div className="flex gap-2">
                <Select value={p.tercero_id ?? ""} onChange={(e) => setP(i, { tercero_id: e.target.value ? Number(e.target.value) : null })} aria-label="A cuenta de">
                  <option value="">Sin tercero</option>
                  {terceros.map((t) => <option key={t.id} value={t.id}>{t.alias || t.nombre}</option>)}
                </Select>
                <Button size="sm" variant="fantasma" aria-label="Quitar perfil" onClick={() => setC({ ...c, perfiles: c.perfiles.filter((_, j) => j !== i) })}><Trash2 className="size-4" /></Button>
              </div>
            </div>
          ))}
          <Button className="self-start" onClick={() => setC({ ...c, perfiles: [...c.perfiles, { id: crypto.randomUUID().slice(0, 8), nombre: "", modo: "I" }] })}><Plus className="size-4" /> Perfil</Button>
        </div>
      )}
    </Modal>
  );
}
