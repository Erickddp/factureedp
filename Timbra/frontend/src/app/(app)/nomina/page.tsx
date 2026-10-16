"use client";
import { useSearchParams } from "next/navigation";
import { Fragment, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, Download, Plus, UserPlus, Wand2 } from "lucide-react";
import { EtiquetaAmbiente, ambienteDe, useEmisor } from "@/components/emisor-context";
import { Badge, Button, Field, Input, Kbd, Modal, PageHeader, Select, Tabs, Vacio, cx, tabla } from "@/components/ui";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, fecha, isoLocal } from "@/lib/format";
import type { Empleado, Factura, LineaNomina, Recibo } from "@/lib/types";

const ESTADOS: [string, string][] = [["AGU", "Aguascalientes"], ["BCN", "Baja California"], ["BCS", "Baja California Sur"], ["CAM", "Campeche"],
  ["CHP", "Chiapas"], ["CHH", "Chihuahua"], ["CMX", "Ciudad de México"], ["COA", "Coahuila"], ["COL", "Colima"], ["DUR", "Durango"],
  ["GUA", "Guanajuato"], ["GRO", "Guerrero"], ["HID", "Hidalgo"], ["JAL", "Jalisco"], ["MEX", "Estado de México"], ["MIC", "Michoacán"],
  ["MOR", "Morelos"], ["NAY", "Nayarit"], ["NLE", "Nuevo León"], ["OAX", "Oaxaca"], ["PUE", "Puebla"], ["QUE", "Querétaro"],
  ["ROO", "Quintana Roo"], ["SLP", "San Luis Potosí"], ["SIN", "Sinaloa"], ["SON", "Sonora"], ["TAB", "Tabasco"], ["TAM", "Tamaulipas"],
  ["TLA", "Tlaxcala"], ["VER", "Veracruz"], ["YUC", "Yucatán"], ["ZAC", "Zacatecas"]];
const PERIODICIDAD: [string, string][] = [["01", "Diario"], ["02", "Semanal"], ["03", "Catorcenal"], ["04", "Quincenal"], ["05", "Mensual"], ["99", "Otra"]];
const REGIMEN: [string, string][] = [["02", "Sueldos y salarios"], ["13", "Asimilados (otros)"], ["11", "Asimilados honorarios"],
  ["09", "Asimilados consejeros"], ["08", "Asimilados asociaciones civiles"], ["10", "Asimilados comisionistas"], ["12", "Asimilados acciones"]];
const CONTRATO: [string, string][] = [["01", "Tiempo indeterminado"], ["02", "Obra determinada"], ["03", "Tiempo determinado"], ["04", "Por temporada"],
  ["05", "A prueba"], ["06", "Capacitación inicial"], ["09", "Sin relación de trabajo"], ["99", "Otro (asimilados)"]];
const RECETAS_UI: [string, string][] = [["sueldo", "Sueldos y salarios (sueldo, ISR, IMSS)"], ["asimilados", "Asimilados a salarios (ISR)"],
  ["asimilados_honorarios", "Honorarios asimilados (ISR)"]];

const n = (v?: string | null) => Number(v || 0);
const neto = (r: Recibo) => r.percepciones.reduce((s, p) => s + n(p.gravado) + n(p.exento), 0)
  + r.otros_pagos.reduce((s, o) => s + n(o.importe), 0) - r.deducciones.reduce((s, d) => s + n(d.importe), 0);
const iso = (d: Date) => isoLocal(d);

function periodos() {
  const h = new Date();
  const y = h.getFullYear(), m = h.getMonth();
  const fin = new Date(y, m + 1, 0).getDate();
  const lunes = new Date(h); lunes.setDate(h.getDate() - ((h.getDay() + 6) % 7));
  const dom = new Date(lunes); dom.setDate(lunes.getDate() + 6);
  return [
    { id: "q1", t: "1ª quincena", d: iso(new Date(y, m, 1)), h: iso(new Date(y, m, 15)) },
    { id: "q2", t: "2ª quincena", d: iso(new Date(y, m, 16)), h: iso(new Date(y, m, fin)) },
    { id: "sem", t: "Esta semana", d: iso(lunes), h: iso(dom) },
    { id: "mes", t: "Mes", d: iso(new Date(y, m, 1)), h: iso(new Date(y, m, fin)) },
  ];
}

export default function Pagina() {
  return <Suspense><Nomina /></Suspense>;
}

function Nomina() {
  const params = useSearchParams();
  const [vista, setVista] = useState<"recibos" | "empleados" | "historial">(params.get("vista") === "empleados" ? "empleados" : "recibos");
  const { emisor } = useEmisor();
  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;
  return (
    <>
      <PageHeader title="Nómina" />
      <Tabs value={vista} onChange={setVista} items={[{ id: "recibos", label: "Timbrar periodo" }, { id: "empleados", label: "Empleados" }, { id: "historial", label: "Recibos timbrados" }]} />
      {vista === "recibos" && <Periodo emisorId={emisor.id} irEmpleados={() => setVista("empleados")} />}
      {vista === "empleados" && <Empleados emisorId={emisor.id} />}
      {vista === "historial" && <Historial emisorId={emisor.id} />}
    </>
  );
}

function Periodo({ emisorId, irEmpleados }: { emisorId: number; irEmpleados: () => void }) {
  const ps = useMemo(periodos, []);
  const [p, setP] = useState(new Date().getDate() <= 15 ? ps[0] : ps[1]);
  const [recibos, setRecibos] = useState<(Recibo & { sel: boolean; abierto?: boolean; res?: { ok: boolean; error?: string; folio?: string } })[]>([]);
  const [cargando, setCargando] = useState(false);
  const [timbrando, setTimbrando] = useState(false);
  const { emisor, confirmarTimbre } = useEmisor();
  const { data: emps = [] } = useSWR<Empleado[]>(`/nomina/empleados?emisor_id=${emisorId}`, fetcher);
  const nombre = (id: number) => emps.find((e) => e.id === id);

  const armar = useCallback(async () => {
    setCargando(true);
    try {
      const r = await api<Recibo[]>(`/nomina/borrador?emisor_id=${emisorId}&desde=${p.d}&hasta=${p.h}`);
      setRecibos(r.map((x) => ({ ...x, sel: true })));
      if (!r.length) toast.message("No hay empleados activos. Dalos de alta primero.");
    } catch (e) { mostrarError(e); } finally { setCargando(false); }
  }, [emisorId, p]);

  const timbrar = useCallback(async () => {
    const sel = recibos.filter((r) => r.sel && !r.res?.ok);
    if (!sel.length) return toast.message("Marca al menos un recibo.");
    if (!(await confirmarTimbre())) return;
    setTimbrando(true);
    try {
      const limpio = sel.map(({ sel: _s, abierto: _a, res: _r, ...r }) => r);
      const out = await api<{ empleado_id: number; ok: boolean; error?: string; folio?: string }[]>("/nomina/timbrar", { method: "POST", json: { emisor_id: emisorId, recibos: limpio } });
      setRecibos((rs) => rs.map((r) => { const o = out.find((x) => x.empleado_id === r.empleado_id); return o ? { ...r, res: o, sel: !o.ok } : r; }));
      const ok = out.filter((o) => o.ok).length;
      (ok === out.length ? toast.success : toast.warning)(`Timbrados ${ok} de ${out.length} recibos`);
    } catch (e) { mostrarError(e); } finally { setTimbrando(false); }
  }, [recibos, emisorId, confirmarTimbre]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (document.querySelector("[role=dialog]")) return;
      if (e.altKey && e.code === "KeyQ") { e.preventDefault(); armar(); }
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && recibos.length) { e.preventDefault(); timbrar(); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [armar, timbrar, recibos.length]);

  const set = (i: number, cambio: Partial<Recibo & { sel: boolean; abierto: boolean }>) => setRecibos((rs) => rs.map((r, j) => (j === i ? { ...r, ...cambio } : r)));
  const setLinea = (i: number, grupo: "percepciones" | "deducciones" | "otros_pagos", j: number, campo: keyof LineaNomina, v: string) =>
    setRecibos((rs) => rs.map((r, k) => (k !== i ? r : { ...r, [grupo]: r[grupo].map((l, m) => (m === j ? { ...l, [campo]: v } : l)) })));
  const total = recibos.filter((r) => r.sel).reduce((s, r) => s + neto(r), 0);

  if (!emps.length) return <Vacio titulo="Aún no hay empleados"><Button className="mt-3" onClick={irEmpleados}><UserPlus className="size-4" /> Dar de alta empleados</Button></Vacio>;
  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-1.5">
          {ps.map((x) => (
            <button key={x.id} onClick={() => setP(x)} className={cx("rounded-full px-3 py-1.5 text-sm ring-1", p.id === x.id ? "bg-primario text-sobre-primario ring-primario" : "ring-linea hover:ring-tinta/40")}>{x.t}</button>
          ))}
        </div>
        <Field label="Del"><Input type="date" value={p.d} onChange={(e) => setP({ ...p, id: "otro", d: e.target.value })} /></Field>
        <Field label="Al"><Input type="date" value={p.h} onChange={(e) => setP({ ...p, id: "otro", h: e.target.value })} /></Field>
        <Button onClick={armar} loading={cargando}><Wand2 className="size-4" /> Armar recibos <Kbd>Alt Q</Kbd></Button>
      </div>

      {recibos.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
            <table className={tabla.base}>
              <thead><tr>
                <th className={cx(tabla.th, "w-8")}><input type="checkbox" aria-label="Todos" checked={recibos.every((r) => r.sel)} onChange={(e) => setRecibos((rs) => rs.map((r) => ({ ...r, sel: e.target.checked && !r.res?.ok })))} /></th>
                <th className={tabla.th}>Empleado</th><th className={tabla.th}>Días</th>
                <th className={cx(tabla.th, tabla.num)}>Percepción</th><th className={cx(tabla.th, tabla.num)}>ISR</th>
                <th className={cx(tabla.th, tabla.num)}>Otras deducciones</th><th className={cx(tabla.th, tabla.num)}>Neto</th><th className={tabla.th}></th>
              </tr></thead>
              <tbody>
                {recibos.map((r, i) => {
                  const emp = nombre(r.empleado_id);
                  const isr = r.deducciones.findIndex((d) => d.tipo === "002");
                  const otras = r.deducciones.filter((d) => d.tipo !== "002").reduce((s, d) => s + n(d.importe), 0);
                  return (
                    <Fragment key={r.empleado_id}>
                      <tr className={cx(r.res?.ok && "opacity-60")}>
                        <td className={tabla.td}><input type="checkbox" aria-label="Timbrar" checked={r.sel} disabled={r.res?.ok} onChange={(e) => set(i, { sel: e.target.checked })} /></td>
                        <td className={tabla.td}>
                          <p className="font-medium">{emp?.nombre ?? r.empleado_id}</p>
                          <p className="text-xs text-grafito">#{emp?.num_empleado} · {r.tipo_nomina === "E" ? "Extraordinaria" : "Ordinaria"}</p>
                          {r.res && (r.res.ok ? <Badge tono="sello">Timbrado {r.res.folio}</Badge> : <p className="text-xs text-rojo">{r.res.error}</p>)}
                        </td>
                        <td className={tabla.td}><Input className="h-8 w-16" value={r.dias} onChange={(e) => set(i, { dias: e.target.value })} /></td>
                        <td className={cx(tabla.td, tabla.num)}>
                          {r.percepciones[0] && <Input className="h-8 w-28 text-right" inputMode="decimal" value={r.percepciones[0].gravado ?? ""} onChange={(e) => setLinea(i, "percepciones", 0, "gravado", e.target.value)} />}
                        </td>
                        <td className={cx(tabla.td, tabla.num)}>
                          {isr >= 0 && <Input className="h-8 w-24 text-right" inputMode="decimal" value={r.deducciones[isr].importe ?? ""} onChange={(e) => setLinea(i, "deducciones", isr, "importe", e.target.value)} />}
                        </td>
                        <td className={cx(tabla.td, tabla.num, "text-grafito")}>{dinero(otras)}</td>
                        <td className={cx(tabla.td, tabla.num, "font-semibold", neto(r) < 0 && "text-rojo")}>{dinero(neto(r))}</td>
                        <td className={tabla.td}>
                          <button onClick={() => set(i, { abierto: !r.abierto })} aria-label="Detalle" className="rounded p-1 hover:bg-tinta/5">
                            {r.abierto ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                          </button>
                        </td>
                      </tr>
                      {r.abierto && (
                        <tr><td colSpan={8} className="bg-papel px-4 py-3">
                          <Detalle r={r} setLinea={(g, j, c, v) => setLinea(i, g, j, c, v)} agregar={(g) => set(i, { [g]: [...r[g], g === "percepciones"
                            ? { tipo: "", clave: "", concepto: "", gravado: "0", exento: "0" } : { tipo: "", clave: "", concepto: "", importe: "0" }] } as Partial<Recibo>)} />
                        </td></tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="sticky bottom-3 mt-4 flex flex-wrap items-center justify-end gap-4 rounded-2xl bg-hoja/95 p-3 ring-1 ring-linea backdrop-blur">
            <p className="text-sm text-grafito">{recibos.filter((r) => r.sel).length} recibos · neto <b className="text-tinta">{dinero(total)}</b></p>
            <Button variant="primario" size="lg" onClick={timbrar} loading={timbrando}>Timbrar recibos <EtiquetaAmbiente ambiente={ambienteDe(emisor)} enBoton /> <Kbd>Ctrl ↵</Kbd></Button>
          </div>
        </>
      )}
      {!recibos.length && <p className="text-sm text-grafito">Elige el periodo y presiona <Kbd>Alt Q</Kbd> para armar un recibo por empleado con su receta. Ajusta ISR y otras cifras y timbra con <Kbd>Ctrl ↵</Kbd>.</p>}
    </>
  );
}

function Detalle({ r, setLinea, agregar }: {
  r: Recibo; setLinea: (g: "percepciones" | "deducciones" | "otros_pagos", j: number, c: keyof LineaNomina, v: string) => void;
  agregar: (g: "percepciones" | "deducciones" | "otros_pagos") => void;
}) {
  const grupos: ["percepciones" | "deducciones" | "otros_pagos", string][] = [["percepciones", "Percepciones"], ["deducciones", "Deducciones"], ["otros_pagos", "Otros pagos (subsidio, viáticos)"]];
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {grupos.map(([g, t]) => (
        <div key={g}>
          <p className="mb-2 text-xs font-medium uppercase tracking-[.06em] text-grafito">{t}</p>
          {r[g].map((l, j) => (
            <div key={j} className="mb-1.5 grid grid-cols-[56px_1fr_88px] gap-1.5">
              <Input className="h-8" placeholder="Tipo" value={l.tipo} onChange={(e) => { setLinea(g, j, "tipo", e.target.value); setLinea(g, j, "clave", e.target.value); }} />
              <Input className="h-8" placeholder="Concepto" value={l.concepto} onChange={(e) => setLinea(g, j, "concepto", e.target.value)} />
              <Input className="h-8 text-right" inputMode="decimal" value={(g === "percepciones" ? l.gravado : l.importe) ?? ""}
                onChange={(e) => setLinea(g, j, g === "percepciones" ? "gravado" : "importe", e.target.value)} />
              {g === "percepciones" && <Input className="col-start-3 h-8 text-right" placeholder="Exento" inputMode="decimal" value={l.exento ?? ""} onChange={(e) => setLinea(g, j, "exento", e.target.value)} />}
              {g === "otros_pagos" && l.tipo === "002" && <Input className="col-span-3 h-8" placeholder="Subsidio causado" value={l.subsidio_causado ?? ""} onChange={(e) => setLinea(g, j, "subsidio_causado", e.target.value)} />}
            </div>
          ))}
          <button onClick={() => agregar(g)} className="flex items-center gap-1 text-xs text-cobalto hover:underline"><Plus className="size-3" /> Agregar</button>
        </div>
      ))}
    </div>
  );
}

const vacio = (emisor_id: number): Omit<Empleado, "id"> => ({
  emisor_id, num_empleado: "", rfc: "", curp: "", nombre: "", codigo_postal: "", nss: "", tipo_contrato: "01", tipo_regimen: "02",
  tipo_jornada: "01", periodicidad_pago: "04", clave_ent_fed: "CMX", fecha_inicio: null, departamento: "", puesto: "", riesgo_puesto: "1",
  banco: null, cuenta_bancaria: "", salario_diario: "0", sdi: "", emails: [], receta: {}, activo: true,
});

function Empleados({ emisorId }: { emisorId: number }) {
  const { data = [], mutate } = useSWR<Empleado[]>(`/nomina/empleados?emisor_id=${emisorId}&todos=true`, fetcher);
  const { data: recetas = {} } = useSWR<Record<string, Record<string, unknown>>>("/nomina/recetas", fetcher);
  const [edit, setEdit] = useState<(Omit<Empleado, "id"> & { id?: number; receta_id?: string }) | null>(null);
  const [cargando, setCargando] = useState(false);

  const guardar = async () => {
    if (!edit) return;
    setCargando(true);
    const { id, receta_id, ...body } = edit;
    const receta = receta_id ? recetas[receta_id] : body.receta;
    const json = { ...body, receta, nss: body.nss || null, sdi: body.sdi || null, cuenta_bancaria: body.cuenta_bancaria || null,
      fecha_inicio: body.fecha_inicio ? `${body.fecha_inicio.slice(0, 10)}T00:00:00` : null };
    try {
      await api(id ? `/nomina/empleados/${id}` : "/nomina/empleados", { method: id ? "PUT" : "POST", json });
      toast.success(id ? "Empleado actualizado" : "Empleado dado de alta");
      setEdit(null);
      mutate();
    } catch (e) { mostrarError(e); } finally { setCargando(false); }
  };
  const elegirReceta = (rid: string) => {
    if (!edit) return;
    const r = recetas[rid] as { tipo_regimen?: string; tipo_contrato?: string } | undefined;
    setEdit({ ...edit, receta_id: rid, tipo_regimen: r?.tipo_regimen ?? edit.tipo_regimen, tipo_contrato: r?.tipo_contrato ?? edit.tipo_contrato });
  };
  const F = edit;
  const s = (k: keyof Omit<Empleado, "id">) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setEdit((x) => (x ? { ...x, [k]: e.target.value } : x));

  return (
    <>
      <div className="mb-4 flex justify-end"><Button variant="primario" onClick={() => setEdit({ ...vacio(emisorId), receta_id: "sueldo" })}><UserPlus className="size-4" /> Nuevo empleado</Button></div>
      {!data.length ? <Vacio titulo="Sin empleados todavía">Elige una receta (sueldos o asimilados) y Timbra arma cada recibo solo.</Vacio> : (
        <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
          <table className={tabla.base}>
            <thead><tr><th className={tabla.th}>#</th><th className={tabla.th}>Nombre</th><th className={tabla.th}>RFC</th><th className={tabla.th}>Régimen</th>
              <th className={cx(tabla.th, tabla.num)}>Salario diario</th><th className={tabla.th}></th></tr></thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.id} className={cx(!e.activo && "opacity-50")}>
                  <td className={tabla.td}>{e.num_empleado}</td>
                  <td className={tabla.td}><p className="font-medium">{e.nombre}</p><p className="text-xs text-grafito">{(e.receta?.nombre as string) ?? "Receta propia"}</p></td>
                  <td className={cx(tabla.td, "font-mono text-xs")}>{e.rfc}</td>
                  <td className={tabla.td}>{REGIMEN.find((r) => r[0] === e.tipo_regimen)?.[1] ?? e.tipo_regimen}</td>
                  <td className={cx(tabla.td, tabla.num)}>{dinero(e.salario_diario)}</td>
                  <td className={cx(tabla.td, "text-right")}><Button size="sm" variant="fantasma" onClick={() => setEdit({ ...e, fecha_inicio: e.fecha_inicio?.slice(0, 10) ?? null })}>Editar</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={!!F} onClose={() => setEdit(null)} title={F?.id ? "Editar empleado" : "Nuevo empleado"} wide
        footer={<><Button onClick={() => setEdit(null)}>Cancelar</Button><Button variant="primario" onClick={guardar} loading={cargando}>Guardar</Button></>}>
        {F && (
          <form className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" onSubmit={(e) => { e.preventDefault(); guardar(); }}>
            <Field label="Receta del recibo" className="sm:col-span-2 lg:col-span-3" hint="Define percepciones y deducciones de cada periodo. Las cifras se ajustan al timbrar.">
              <Select value={F.receta_id ?? ""} onChange={(e) => elegirReceta(e.target.value)}>
                {F.id && <option value="">Conservar la actual</option>}
                {RECETAS_UI.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
              </Select>
            </Field>
            <Field label="No. empleado"><Input autoFocus value={F.num_empleado} onChange={s("num_empleado")} maxLength={15} /></Field>
            <Field label="Nombre (como en su constancia)" className="lg:col-span-2"><Input value={F.nombre} onChange={s("nombre")} /></Field>
            <Field label="RFC"><Input value={F.rfc} onChange={s("rfc")} maxLength={13} /></Field>
            <Field label="CURP"><Input value={F.curp} onChange={s("curp")} maxLength={18} /></Field>
            <Field label="CP fiscal"><Input value={F.codigo_postal} onChange={s("codigo_postal")} maxLength={5} inputMode="numeric" /></Field>
            <Field label="Régimen"><Select value={F.tipo_regimen} onChange={s("tipo_regimen")}>{REGIMEN.map(([k, t]) => <option key={k} value={k}>{k} · {t}</option>)}</Select></Field>
            <Field label="Contrato"><Select value={F.tipo_contrato} onChange={s("tipo_contrato")}>{CONTRATO.map(([k, t]) => <option key={k} value={k}>{k} · {t}</option>)}</Select></Field>
            <Field label="Periodicidad"><Select value={F.periodicidad_pago} onChange={s("periodicidad_pago")}>{PERIODICIDAD.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</Select></Field>
            <Field label="Entidad donde trabaja"><Select value={F.clave_ent_fed} onChange={s("clave_ent_fed")}>{ESTADOS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</Select></Field>
            <Field label="Salario diario"><Input inputMode="decimal" value={F.salario_diario} onChange={s("salario_diario")} /></Field>
            <Field label="Correo para su recibo"><Input type="email" value={F.emails[0] ?? ""} onChange={(e) => setEdit({ ...F, emails: e.target.value ? [e.target.value] : [] })} /></Field>
            {F.tipo_regimen === "02" && (
              <>
                <Field label="NSS"><Input value={F.nss ?? ""} onChange={s("nss")} maxLength={11} /></Field>
                <Field label="Fecha de ingreso"><Input type="date" value={F.fecha_inicio ?? ""} onChange={s("fecha_inicio")} /></Field>
                <Field label="SDI"><Input inputMode="decimal" value={F.sdi ?? ""} onChange={s("sdi")} /></Field>
                <Field label="Riesgo de puesto"><Select value={F.riesgo_puesto ?? "1"} onChange={s("riesgo_puesto")}>{["1", "2", "3", "4", "5", "99"].map((k) => <option key={k} value={k}>Clase {k}</option>)}</Select></Field>
                <Field label="Jornada"><Select value={F.tipo_jornada ?? "01"} onChange={s("tipo_jornada")}><option value="01">Diurna</option><option value="02">Nocturna</option><option value="03">Mixta</option></Select></Field>
                <Field label="Puesto"><Input value={F.puesto ?? ""} onChange={s("puesto")} /></Field>
              </>
            )}
            <Field label="Cuenta o CLABE (opcional)"><Input value={F.cuenta_bancaria ?? ""} onChange={s("cuenta_bancaria")} maxLength={18} /></Field>
            <label className="flex items-center gap-2 self-end pb-2 text-sm"><input type="checkbox" checked={F.activo} onChange={(e) => setEdit({ ...F, activo: e.target.checked })} /> Activo</label>
            <button type="submit" hidden />
          </form>
        )}
      </Modal>
    </>
  );
}

function Historial({ emisorId }: { emisorId: number }) {
  const { data = [] } = useSWR<Factura[]>(`/nomina/recibos?emisor_id=${emisorId}`, fetcher);
  if (!data.length) return <Vacio titulo="Aún no hay recibos timbrados" />;
  return (
    <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
      <table className={tabla.base}>
        <thead><tr><th className={tabla.th}>Folio</th><th className={tabla.th}>Fecha</th><th className={tabla.th}>Empleado</th><th className={tabla.th}>Estado</th>
          <th className={cx(tabla.th, tabla.num)}>Neto</th><th className={tabla.th}></th></tr></thead>
        <tbody>
          {data.map((f) => (
            <tr key={f.id}>
              <td className={tabla.td}>{f.serie}{f.folio}</td>
              <td className={tabla.td}>{fecha(f.fecha)}</td>
              <td className={tabla.td}>{f.receptor_nombre}</td>
              <td className={tabla.td}><Badge tono={f.estado === "timbrada" ? "sello" : f.estado === "cancelada" ? "rojo" : "alerta"}>{f.estado}</Badge></td>
              <td className={cx(tabla.td, tabla.num)}>{dinero(f.total)}</td>
              <td className={cx(tabla.td, "whitespace-nowrap text-right")}>
                <Button size="sm" variant="fantasma" onClick={() => descargar(`/facturas/${f.id}/pdf`, `${f.uuid}.pdf`).catch(mostrarError)}>PDF</Button>
                <Button size="sm" variant="fantasma" onClick={() => descargar(`/facturas/${f.id}/xml`, `${f.uuid}.xml`).catch(mostrarError)}><Download className="size-3.5" /> XML</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
