"use client";
/** Editor del perfil de importación: cómo se lee tu tabla y qué conceptos se arman por fila. */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { PRESETS_IMPUESTOS } from "@/lib/format";
import type { ConceptoPerfil, Impuesto, PerfilLote, PerfilLoteCfg } from "@/lib/types";
import { CatSelect, ClaveSearch } from "./catalogo";
import { Button, Field, Input, Modal, Select, Tabs, cx } from "./ui";

const OBLIGATORIAS = ["folio", "nombre", "rfc", "cp", "fecha", "monto", "forma"];
const TASAS: [string, string][] = [["0.16", "IVA 16%"], ["0.08", "IVA 8% (frontera)"], ["0", "IVA 0%"], ["exento", "Exento"]];
const presetDe = (imps: Impuesto[]) =>
  Object.entries(PRESETS_IMPUESTOS).find(([, v]) => JSON.stringify(v) === JSON.stringify(imps))?.[0] ?? "Personalizado";

const conceptoVacio = (): ConceptoPerfil => ({
  descripcion: "", clave_prod_serv: "", clave_unidad: "E48", no_identificacion: "", cantidad: "1", valor: "monto / 1.16",
  impuestos: [...PRESETS_IMPUESTOS["IVA 16%"]] as Impuesto[],
});

/** Renombra una llave conservando el orden (si no, la fila saltaría al final y se perdería el cursor). */
function renombrar<T>(o: Record<string, T>, de: string, a: string): Record<string, T> {
  return Object.fromEntries(Object.entries(o).map(([k, v]) => [k === de ? a : k, v]));
}

export function PerfilModal({ emisorId, perfil, abierto, cerrar, ok }: {
  emisorId: number; perfil: PerfilLote | "nuevo" | null; abierto: boolean; cerrar: () => void; ok: (p: PerfilLote) => void;
}) {
  const [nombre, setNombre] = useState("");
  const [cfg, setCfg] = useState<PerfilLoteCfg | null>(null);
  const [vista, setVista] = useState<"general" | "columnas" | "conceptos" | "reglas">("general");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    if (!abierto || !perfil) return;
    setVista("general");
    if (perfil === "nuevo") {
      setNombre("");
      api<PerfilLoteCfg>("/lotes/perfiles/ejemplo").then(setCfg).catch(mostrarError);
    } else {
      setNombre(perfil.nombre);
      setCfg(structuredClone(perfil.config));
    }
  }, [abierto, perfil]);
  if (!abierto || !cfg) return null;

  const set = (p: Partial<PerfilLoteCfg>) => setCfg({ ...cfg, ...p });
  const setC = (i: number, p: Partial<ConceptoPerfil>) => set({ conceptos: cfg.conceptos.map((c, j) => (j === i ? { ...c, ...p } : c)) });
  const cols = Object.keys(cfg.columnas);

  const guardar = async () => {
    if (!nombre.trim()) return toast.error("Ponle un nombre al perfil.");
    setGuardando(true);
    try {
      const body = { emisor_id: emisorId, nombre, config: cfg };
      const p = await api<PerfilLote>(perfil !== "nuevo" && perfil ? `/lotes/perfiles/${perfil.id}` : "/lotes/perfiles", {
        method: perfil !== "nuevo" && perfil ? "PUT" : "POST", json: body,
      });
      toast.success("Perfil guardado");
      ok(p);
    } catch (e) { mostrarError(e); } finally { setGuardando(false); }
  };

  return (
    <Modal open={abierto} onClose={cerrar} title={perfil === "nuevo" ? "Nuevo perfil de importación" : "Editar perfil"} wide="xl"
      footer={<><Button onClick={cerrar}>Cancelar</Button><Button variant="primario" onClick={guardar} loading={guardando}>Guardar perfil</Button></>}>
      <Field label="Nombre del perfil" className="mb-4 max-w-md"><Input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Pacientes · servicio + vitaminas" /></Field>
      <Tabs value={vista} onChange={setVista} items={[{ id: "general", label: "Datos del CFDI" }, { id: "columnas", label: "Tus columnas" }, { id: "conceptos", label: "Conceptos", n: cfg.conceptos.length }, { id: "reglas", label: "Reglas y bloqueos" }]} />

      {vista === "general" && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Serie"><Input value={cfg.serie} onChange={(e) => set({ serie: e.target.value.toUpperCase() })} maxLength={10} /></Field>
          <Field label="Folio" className="sm:col-span-2" hint={cfg.folio_modo === "hoja" ? "Se usa el folio de tu tabla (C-30 = serie C, folio 30). Si ya existe, esa fila no se timbra." : "Timbra asigna el siguiente; el de tu tabla queda como referencia."}>
            <Select value={cfg.folio_modo} onChange={(e) => set({ folio_modo: e.target.value as "hoja" | "consecutivo" })}>
              <option value="hoja">El de mi tabla (el que yo quiero)</option><option value="consecutivo">Consecutivo de Timbra</option>
            </Select>
          </Field>
          <Field label="Uso del CFDI"><CatSelect catalogo="uso_cfdi" value={cfg.uso_cfdi} onChange={(v) => set({ uso_cfdi: v })} filtro={(c) => c.clave !== "CN01" && c.clave !== "CP01"} /></Field>
          <Field label="Método de pago">
            <Select value={cfg.metodo_pago} onChange={(e) => set({ metodo_pago: e.target.value })}><option value="PUE">PUE · una exhibición</option><option value="PPD">PPD · parcialidades</option></Select>
          </Field>
          <Field label="Régimen si la tabla no lo trae"><CatSelect catalogo="regimen_fiscal" value={cfg.regimen_default} onChange={(v) => set({ regimen_default: v })} /></Field>
          <Field label="Ajuste de centavos permitido" className="sm:col-span-3" hint="Si con los decimales el total del CFDI sale un centavo distinto a lo cobrado, Timbra mueve hasta este monto por concepto para cuadrarlo (siempre lo marca en la vista previa). 0 = nunca mover.">
            <Select value={cfg.ajuste_centavos} onChange={(e) => set({ ajuste_centavos: Number(e.target.value) })} className="max-w-48">
              <option value={0}>0 · no mover</option><option value={1}>1 centavo</option><option value={2}>2 centavos</option>
            </Select>
          </Field>
          <Field label="Formas de pago de tu tabla" className="sm:col-span-3" hint="Lo que escribes en la columna → clave del SAT">
            <div className="grid gap-2 sm:grid-cols-2">
              {Object.entries(cfg.forma_map).map(([k, v], i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input className="w-28 shrink-0" value={k} onChange={(e) => { const n = e.target.value.toUpperCase(); if (n !== k && n in cfg.forma_map) return; set({ forma_map: renombrar(cfg.forma_map, k, n) }); }} />
                  <CatSelect catalogo="forma_pago" value={v} onChange={(x) => set({ forma_map: { ...cfg.forma_map, [k]: x } })} filtro={(c) => c.clave !== "99"} />
                  <Button size="sm" variant="fantasma" aria-label="Quitar" onClick={() => { const { [k]: _x, ...r } = cfg.forma_map; set({ forma_map: r }); }}><Trash2 className="size-4" /></Button>
                </div>
              ))}
              <Button size="sm" variant="fantasma" className="self-start" disabled={"" in cfg.forma_map} onClick={() => set({ forma_map: { ...cfg.forma_map, "": "03" } })}><Plus className="size-4" /> Forma</Button>
            </div>
          </Field>
        </div>
      )}

      {vista === "columnas" && (
        <div className="grid gap-3">
          <p className="text-sm text-grafito">
            Posición de cada dato en tu tabla (<b>0 = primera columna</b>). Si pegas con encabezados, se buscan por el nombre de la derecha y el orden deja de importar.
            Las columnas numéricas (monto, servicio…) puedes usarlas en las fórmulas de los conceptos.
          </p>
          <div className="overflow-x-auto rounded-xl ring-1 ring-linea">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-[.06em] text-grafito"><th className="px-3 py-2">Dato</th><th className="px-3 py-2">Posición</th><th className="px-3 py-2">Encabezado en tu tabla</th><th /></tr></thead>
              <tbody>
                {cols.map((k, i) => (
                  <tr key={i} className="border-t border-linea">
                    <td className="px-3 py-1.5"><Input className="h-8 w-40 font-mono text-xs" value={k} disabled={OBLIGATORIAS.includes(k)}
                      onChange={(e) => { const n = e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""); if (!n || (n !== k && n in cfg.columnas)) return; set({ columnas: renombrar(cfg.columnas, k, n), nombres_columnas: renombrar(cfg.nombres_columnas, k, n) }); }} /></td>
                    <td className="px-3 py-1.5"><Input className="h-8 w-20" inputMode="numeric" value={cfg.columnas[k]} onChange={(e) => set({ columnas: { ...cfg.columnas, [k]: Number(e.target.value.replace(/\D/g, "")) } })} /></td>
                    <td className="px-3 py-1.5"><Input className="h-8" value={cfg.nombres_columnas[k] ?? ""} onChange={(e) => set({ nombres_columnas: { ...cfg.nombres_columnas, [k]: e.target.value } })} /></td>
                    <td className="px-3 py-1.5 text-right">{!OBLIGATORIAS.includes(k) && <Button size="sm" variant="fantasma" aria-label="Quitar" onClick={() => { const { [k]: _a, ...r } = cfg.columnas; const { [k]: _b, ...rn } = cfg.nombres_columnas; set({ columnas: r, nombres_columnas: rn }); }}><Trash2 className="size-4" /></Button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button size="sm" className="self-start" onClick={() => set({ columnas: { ...cfg.columnas, [`dato${cols.length}`]: cols.length } })}><Plus className="size-4" /> Columna</Button>
        </div>
      )}

      {vista === "conceptos" && (
        <div className="grid gap-4">
          <p className="text-sm text-grafito">
            Un CFDI por fila con estos conceptos. El <b>precio</b> es una fórmula con tus columnas ({cols.filter((c) => !["folio", "nombre", "rfc", "cp", "fecha", "forma", "regimen", "direccion", "correo"].includes(c)).join(", ") || "monto"}):
            por ejemplo <code className="rounded bg-tinta/5 px-1">servicio / 1.16</code>. En la descripción usa <code className="rounded bg-tinta/5 px-1">{"{DD}"}</code> <code className="rounded bg-tinta/5 px-1">{"{MES}"}</code> <code className="rounded bg-tinta/5 px-1">{"{AAAA}"}</code> de la fecha de pago o <code className="rounded bg-tinta/5 px-1">{"{nombre}"}</code> de cualquier columna.
          </p>
          {cfg.conceptos.map((c, i) => (
            <div key={i} className="grid gap-3 rounded-xl p-4 ring-1 ring-linea sm:grid-cols-6">
              <div className="flex items-center justify-between sm:col-span-6"><b className="text-sm">Concepto {i + 1}</b>
                {cfg.conceptos.length > 1 && <Button size="sm" variant="fantasma" onClick={() => set({ conceptos: cfg.conceptos.filter((_, j) => j !== i) })}><Trash2 className="size-4" /> Quitar</Button>}</div>
              <Field label="Descripción" className="sm:col-span-6">
                <textarea value={c.descripcion} onChange={(e) => setC(i, { descripcion: e.target.value })} rows={3}
                  className="w-full rounded-lg border border-linea bg-hoja p-2.5 text-sm focus:border-tinta focus:outline-none" />
              </Field>
              <Field label="Clave SAT" className="sm:col-span-2"><ClaveSearch tipo="prod_serv" value={c.clave_prod_serv} onChange={(v) => setC(i, { clave_prod_serv: v })} /></Field>
              <Field label="Unidad"><ClaveSearch tipo="unidad" value={c.clave_unidad} onChange={(v) => setC(i, { clave_unidad: v })} /></Field>
              <Field label="Cantidad"><Input value={c.cantidad} onChange={(e) => setC(i, { cantidad: e.target.value })} /></Field>
              <Field label="Precio unitario (fórmula)"><Input className="font-mono text-xs" value={c.valor} onChange={(e) => setC(i, { valor: e.target.value })} /></Field>
              <Field label="No. identificación (opcional)" className="sm:col-span-3"><Input value={c.no_identificacion ?? ""} onChange={(e) => setC(i, { no_identificacion: e.target.value })} /></Field>
              <Field label="Impuestos" className="sm:col-span-3">
                <Select value={presetDe(c.impuestos)} onChange={(e) => { const v = PRESETS_IMPUESTOS[e.target.value as keyof typeof PRESETS_IMPUESTOS]; if (v) setC(i, { impuestos: [...v] as Impuesto[] }); }}>
                  {Object.keys(PRESETS_IMPUESTOS).map((k) => <option key={k} value={k}>{k}</option>)}
                  {presetDe(c.impuestos) === "Personalizado" && <option value="Personalizado">Personalizado</option>}
                </Select>
              </Field>
            </div>
          ))}
          <Button className="self-start" onClick={() => set({ conceptos: [...cfg.conceptos, conceptoVacio()] })}><Plus className="size-4" /> Concepto</Button>
        </div>
      )}

      {vista === "reglas" && (
        <div className="grid gap-5">
          <Field label="IVA permitido en este perfil" hint="Cualquier otro (por ejemplo exento o 0%) bloquea la fila antes de timbrar.">
            <div className="flex flex-wrap gap-2">
              {TASAS.map(([k, t]) => (
                <label key={k} className={cx("flex cursor-pointer items-center gap-2 rounded-lg px-3 py-1.5 text-sm ring-1", cfg.iva_permitido.includes(k) ? "bg-primario text-sobre-primario ring-primario" : "ring-linea")}>
                  <input type="checkbox" className="hidden" checked={cfg.iva_permitido.includes(k)} onChange={(e) => set({ iva_permitido: e.target.checked ? [...cfg.iva_permitido, k] : cfg.iva_permitido.filter((x) => x !== k) })} /> {t}
                </label>
              ))}
            </div>
          </Field>
          <Field label="Claves SAT bloqueadas" hint="Separadas por coma. Si un concepto usa una de estas claves, la fila NO se timbra y te avisa (medicamentos que nunca deben ir como suplemento).">
            <Input value={cfg.claves_bloqueadas.join(", ")} onChange={(e) => set({ claves_bloqueadas: e.target.value.split(/[,\s]+/).filter(Boolean) })} />
          </Field>
        </div>
      )}
    </Modal>
  );
}
