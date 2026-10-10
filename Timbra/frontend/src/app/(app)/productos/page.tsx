"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, ChevronDown, FileUp, Layers, Plus, Search, Telescope } from "lucide-react";
import { mostrarError } from "@/lib/errores";
import { api, fetcher } from "@/lib/api";
import { dinero, PRESETS_IMPUESTOS, presetPorDefecto } from "@/lib/format";
import { OpcionesImpuestos } from "@/components/impuestos";
import type { FilaImportProducto, Impuesto, PackProductos, Producto } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { ClaveSearch } from "@/components/catalogo";
import { Badge, Button, Field, Input, Modal, PageHeader, Select, Vacio, cx, tabla } from "@/components/ui";

type Edit = Omit<Producto, "id" | "emisor_id"> & { id?: number; preset: string };
const vacio: Edit = { descripcion: "", clave_prod_serv: "", clave_unidad: "E48", unidad: "", no_identificacion: "", precio: "", objeto_imp: "02", impuestos: [...PRESETS_IMPUESTOS["IVA 16%"]] as Impuesto[], preset: "IVA 16%" };
const presetDe = (imps: Impuesto[]) => Object.entries(PRESETS_IMPUESTOS).find(([, v]) => JSON.stringify(v) === JSON.stringify(imps))?.[0] ?? "Personalizado";

export default function Productos() {
  const { emisor } = useEmisor();
  const [edit, setEdit] = useState<Edit | null>(null);
  const [q, setQ] = useState("");
  const [packs, setPacks] = useState(false);
  const [importar, setImportar] = useState(false);
  const { data = [], mutate } = useSWR<Producto[]>(emisor ? `/productos?emisor_id=${emisor.id}${q ? `&q=${encodeURIComponent(q)}` : ""}` : null, fetcher);

  const guardar = async () => {
    if (!edit || !emisor) return;
    const { preset, id, ...body } = edit;
    try {
      await api(id ? `/productos/${id}` : "/productos", { method: id ? "PUT" : "POST", json: { ...body, emisor_id: emisor.id, precio: body.precio || "0" } });
      toast.success("Producto guardado");
      setEdit(null);
      mutate();
    } catch (e) {
      mostrarError(e);
    }
  };

  return (
    <>
      <PageHeader title="Productos y servicios">
        <Link href="/claves"><Button><Telescope className="size-4" /> Investigar clave SAT</Button></Link>
        <Button onClick={() => setPacks(true)}><Layers className="size-4" /> Catálogos sugeridos</Button>
        <Button onClick={() => setImportar(true)}><FileUp className="size-4" /> Importar tabla</Button>
        <Button variant="primario" onClick={() => { const pr = presetPorDefecto(emisor?.region_fronteriza); setEdit({ ...vacio, preset: pr, impuestos: [...PRESETS_IMPUESTOS[pr]] as Impuesto[] }); }}><Plus className="size-4" /> Producto</Button>
      </PageHeader>
      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-3 size-4 text-grafito" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar en mi catálogo" className="pl-9" aria-label="Buscar producto" />
      </div>
      {!data.length ? (
        <Vacio titulo={q ? `Nada con “${q}”` : "Tu catálogo está vacío"}>
          {q ? "Prueba con otra palabra." : <>Agrega un <b>catálogo sugerido</b> para tu giro, importa tu tabla, o guarda lo que facturas seguido y se autocompleta al facturar.</>}
        </Vacio>
      ) : (
        <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
          <table className={tabla.base}>
            <thead><tr><th className={tabla.th}>Descripción</th><th className={tabla.th}>Clave · unidad</th><th className={tabla.th}>Impuestos</th><th className={cx(tabla.th, tabla.num)}>Precio</th></tr></thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id} onClick={() => setEdit({ ...p, precio: String(Number(p.precio)), preset: presetDe(p.impuestos) })} className="cursor-pointer hover:bg-tinta/[.02]">
                  <td className={tabla.td}><span className="line-clamp-2">{p.descripcion}</span></td>
                  <td className={cx(tabla.td, "whitespace-nowrap tabular-nums text-grafito")}>
                    {p.clave_prod_serv} · {p.clave_unidad} {p.clave_prod_serv.startsWith("51") && <span title="Familia de medicamentos y productos farmacéuticos"><AlertTriangle className="ml-1 inline size-3.5 text-alerta" /></span>}
                  </td>
                  <td className={cx(tabla.td, "max-w-56 truncate text-xs text-grafito")}>{presetDe(p.impuestos)}</td>
                  <td className={cx(tabla.td, tabla.num, "font-medium")}>{Number(p.precio) ? dinero(p.precio) : <span className="text-grafito/60">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? "Editar producto" : "Nuevo producto"} wide>
        {edit && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Descripción" className="sm:col-span-2"><Input value={edit.descripcion} onChange={(e) => setEdit({ ...edit, descripcion: e.target.value })} /></Field>
            <Field label="Clave producto/servicio SAT" hint="Busca por palabra: 'contable', 'consultoría'… (o investígala en Claves SAT)">
              <ClaveSearch tipo="prod_serv" value={edit.clave_prod_serv} onChange={(c) => setEdit({ ...edit, clave_prod_serv: c })} />
            </Field>
            <Field label="Clave de unidad" hint="E48 servicio, H87 pieza, ACT actividad">
              <ClaveSearch tipo="unidad" value={edit.clave_unidad} onChange={(c) => setEdit({ ...edit, clave_unidad: c })} />
            </Field>
            <Field label="Precio unitario (sin IVA)"><Input value={edit.precio} inputMode="decimal" onChange={(e) => setEdit({ ...edit, precio: e.target.value })} /></Field>
            <Field label="Impuestos">
              <Select value={edit.preset} onChange={(e) => { const v = PRESETS_IMPUESTOS[e.target.value as keyof typeof PRESETS_IMPUESTOS]; setEdit({ ...edit, preset: e.target.value, impuestos: [...v] as Impuesto[], objeto_imp: v.length ? "02" : "01" }); }}>
                <OpcionesImpuestos frontera={!!emisor?.region_fronteriza} />
              </Select>
            </Field>
            <Field label="SKU / No. identificación"><Input value={edit.no_identificacion ?? ""} onChange={(e) => setEdit({ ...edit, no_identificacion: e.target.value })} /></Field>
            <Field label="Unidad (texto libre)"><Input value={edit.unidad ?? ""} onChange={(e) => setEdit({ ...edit, unidad: e.target.value })} placeholder="Servicio" /></Field>
            <div className="flex justify-between gap-2 sm:col-span-2">
              {edit.id ? <Button variant="fantasma" className="text-rojo" onClick={async () => { await api(`/productos/${edit.id}`, { method: "DELETE" }); setEdit(null); mutate(); }}>Borrar</Button> : <span />}
              <div className="flex gap-2"><Button onClick={() => setEdit(null)}>Cancelar</Button><Button variant="primario" onClick={guardar}>Guardar producto</Button></div>
            </div>
          </div>
        )}
      </Modal>
      <PacksModal abierto={packs} cerrar={() => setPacks(false)} listo={() => mutate()} />
      <ImportarModal abierto={importar} cerrar={() => setImportar(false)} listo={() => mutate()} />
    </>
  );
}

function PacksModal({ abierto, cerrar, listo }: { abierto: boolean; cerrar: () => void; listo: () => void }) {
  const { emisor } = useEmisor();
  const { data: packs = [], mutate } = useSWR<PackProductos[]>(abierto && emisor ? `/productos/packs?emisor_id=${emisor.id}` : null, fetcher);
  const [abierta, setAbierta] = useState<string | null>(null);
  const [agregando, setAgregando] = useState("");
  const agregar = async (p: PackProductos) => {
    if (!emisor) return;
    setAgregando(p.id);
    try {
      const r = await api<{ agregados: number; ya_estaban: number }>(`/productos/packs/${p.id}?emisor_id=${emisor.id}`, { method: "POST" });
      toast.success(r.agregados ? `${r.agregados} agregados${r.ya_estaban ? ` · ${r.ya_estaban} ya los tenías` : ""}. Ponles precio al facturar o aquí.` : "Ya tenías todo este catálogo");
      mutate(); listo();
    } catch (e) { mostrarError(e); } finally { setAgregando(""); }
  };
  return (
    <Modal open={abierto} onClose={cerrar} title="Catálogos sugeridos por giro" wide>
      <p className="mb-4 text-sm text-grafito">Claves, unidades e impuestos ya armados. Se agregan a tu catálogo sin precio (lo pones tú) y no duplican lo que ya tienes.</p>
      <div className="grid gap-3">
        {packs.map((p) => (
          <div key={p.id} className="rounded-xl ring-1 ring-linea">
            <div className="flex flex-wrap items-center gap-3 p-4">
              <button className="flex min-w-0 flex-1 items-start gap-2 text-left" onClick={() => setAbierta(abierta === p.id ? null : p.id)} aria-expanded={abierta === p.id}>
                <ChevronDown className={cx("mt-1 size-4 shrink-0 transition-transform", abierta === p.id && "rotate-180")} />
                <span className="min-w-0"><b className="block">{p.nombre}</b><span className="block text-sm text-grafito">{p.descripcion}</span></span>
              </button>
              <span className="text-xs text-grafito">{p.ya_tiene ?? 0}/{p.productos.length} en tu catálogo</span>
              <Button size="sm" variant={(p.ya_tiene ?? 0) >= p.productos.length ? "secundario" : "primario"} onClick={() => agregar(p)} loading={agregando === p.id}
                disabled={(p.ya_tiene ?? 0) >= p.productos.length}>{(p.ya_tiene ?? 0) >= p.productos.length ? "Completo" : "Agregar"}</Button>
            </div>
            {abierta === p.id && (
              <div className="border-t border-linea px-4 py-3 text-sm">
                {p.nota && <p className="mb-3 flex gap-2 rounded-lg bg-alerta-suave px-3 py-2 text-alerta"><AlertTriangle className="mt-0.5 size-4 shrink-0" /> {p.nota}</p>}
                <ul className="grid gap-1">
                  {p.productos.map((x, i) => (
                    <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5"><span className="min-w-0 flex-1">{x.descripcion}</span>
                      <span className="font-mono text-xs text-grafito">{x.clave} · {x.unidad}</span><Badge>{x.impuestos}</Badge></li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </Modal>
  );
}

function ImportarModal({ abierto, cerrar, listo }: { abierto: boolean; cerrar: () => void; listo: () => void }) {
  const { emisor } = useEmisor();
  const [texto, setTexto] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [prev, setPrev] = useState<{ filas: FilaImportProducto[]; resumen: Record<string, number>; error: string | null } | null>(null);
  const [aceptar, setAceptar] = useState(false);
  const [cargando, setCargando] = useState(false);
  const inp = useRef<HTMLInputElement>(null);

  const enviar = async (confirmar: boolean) => {
    if (!emisor) return;
    if (!texto.trim() && !archivo) return toast.error("Pega tu tabla o sube un archivo.");
    setCargando(true);
    try {
      const fd = new FormData();
      fd.append("emisor_id", String(emisor.id));
      fd.append("confirmar", String(confirmar));
      fd.append("aceptar_sugeridas", String(aceptar));
      if (archivo) fd.append("archivo", archivo); else fd.append("texto", texto);
      const r = await api<any>("/productos/importar", { method: "POST", body: fd });
      if (confirmar) {
        toast.success(`${r.nuevos} nuevos · ${r.actualizados} actualizados${r.omitidos ? ` · ${r.omitidos} sin importar` : ""}`);
        listo(); setPrev(null); setTexto(""); setArchivo(null); cerrar();
      } else setPrev(r);
    } catch (e) { mostrarError(e); } finally { setCargando(false); }
  };
  const sugeridas = prev?.filas.filter((f) => f.clave_sugerida && f.estado !== "error").length ?? 0;
  const buenas = prev?.filas.filter((f) => f.estado !== "error" && (aceptar || !f.clave_sugerida)).length ?? 0;

  return (
    <Modal open={abierto} onClose={cerrar} title="Importar productos y servicios" wide="xl"
      footer={<><Button onClick={cerrar}>Cancelar</Button>
        <Button onClick={() => enviar(false)} loading={cargando && !prev}>Revisar</Button>
        {prev && !prev.error && <Button variant="primario" disabled={!buenas} onClick={() => enviar(true)} loading={cargando}>Importar {buenas}</Button>}</>}>
      <p className="mb-3 text-sm text-grafito">
        Primera fila = encabezados: <code className="rounded bg-tinta/5 px-1">DESCRIPCION</code> <code className="rounded bg-tinta/5 px-1">CLAVE</code> <code className="rounded bg-tinta/5 px-1">UNIDAD</code> <code className="rounded bg-tinta/5 px-1">PRECIO</code> <code className="rounded bg-tinta/5 px-1">IMPUESTO</code> (16, 8, 0, exento, honorarios, resico, ninguno).
        Si no traes la clave, Timbra te sugiere una y tú la confirmas.
      </p>
      <textarea value={texto} onChange={(e) => { setTexto(e.target.value); setPrev(null); }} rows={6} placeholder={"DESCRIPCION\tCLAVE\tUNIDAD\tPRECIO\tIMPUESTO\nConsulta de nutrición\t\t\t800\t16"}
        className="mb-3 w-full rounded-xl border border-linea bg-hoja p-3 font-mono text-xs focus:border-tinta focus:outline-none" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={() => inp.current?.click()}><FileUp className="size-4" /> {archivo ? archivo.name : "Subir CSV o Excel"}</Button>
        <input ref={inp} type="file" accept=".csv,.tsv,.txt,.xlsx" hidden onChange={(e) => { setArchivo(e.target.files?.[0] ?? null); setPrev(null); }} />
        {prev && !prev.error && sugeridas > 0 && (
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={aceptar} onChange={(e) => setAceptar(e.target.checked)} /> Aceptar las {sugeridas} claves sugeridas</label>
        )}
      </div>
      {prev?.error && <p className="rounded-lg bg-rojo-suave px-3 py-2 text-sm text-rojo">{prev.error}</p>}
      {prev && !prev.error && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-linea">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-[.06em] text-grafito"><th className="px-3 py-2">Fila</th><th className="px-3 py-2">Descripción</th><th className="px-3 py-2">Clave</th><th className="px-3 py-2">Unidad</th><th className="px-3 py-2 text-right">Precio</th><th className="px-3 py-2">Estado</th></tr></thead>
            <tbody>
              {prev.filas.map((f) => (
                <tr key={f.n} className="border-t border-linea align-top">
                  <td className="px-3 py-2 text-grafito">{f.n}</td>
                  <td className="max-w-64 px-3 py-2">{f.descripcion}{f.errores.map((e, i) => <p key={i} className="text-xs text-rojo">{e}</p>)}{f.avisos.map((a, i) => <p key={i} className="text-xs text-alerta">{a}</p>)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{f.clave}{f.clave_sugerida && <Badge tono="alerta" className="ml-1">sugerida</Badge>}</td>
                  <td className="px-3 py-2">{f.unidad}</td><td className="px-3 py-2 text-right tabular-nums">{dinero(f.precio)}</td>
                  <td className="px-3 py-2"><Badge tono={f.estado === "error" ? "rojo" : f.estado === "actualiza" ? "cobalto" : "sello"}>{f.estado === "nuevo" ? "Nuevo" : f.estado === "actualiza" ? "Actualiza" : "Error"}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
