"use client";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, Download, FileUp, Plus, Search, ShieldCheck, Upload, XCircle } from "lucide-react";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { RFC_RE } from "@/lib/format";
import { regimenPermitido, usoPermitido } from "@/lib/sat";
import type { Addenda, Cliente } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { CatSelect } from "@/components/catalogo";
import { RevisionClientes } from "@/components/clientes-revision";
import { Badge, Button, Field, Input, Kbd, Modal, PageHeader, Select, Vacio, cx } from "@/components/ui";

type Edit = {
  id?: number; rfc: string; nombre: string; regimen_fiscal: string; codigo_postal: string; uso_cfdi: string;
  forma_pago: string; metodo_pago: string; emails: string; telefono: string; direccion: string;
  addenda_id: string; addenda_defaults: Record<string, string>; notas: string; dias_credito: string;
};
const vacio: Edit = {
  rfc: "", nombre: "", regimen_fiscal: "", codigo_postal: "", uso_cfdi: "G03", forma_pago: "", metodo_pago: "",
  emails: "", telefono: "", direccion: "", addenda_id: "", addenda_defaults: {}, notas: "", dias_credito: "0",
};

export default function Clientes() {
  const { emisor } = useEmisor();
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<Edit | null>(null);
  const [importar, setImportar] = useState(false);
  const [revisar, setRevisar] = useState<"problemas" | "duplicados" | "lista" | null>(null);
  const buscar = useRef<HTMLInputElement>(null);
  // Nuevo cliente con lo que ya escribiste en la búsqueda (RFC o nombre): no hay que volver a teclearlo
  const qRef = useRef(q);
  qRef.current = q;
  const nuevo = () => {
    const t = qRef.current.trim().toUpperCase();
    setEdit({ ...vacio, ...(RFC_RE.test(t) ? { rfc: t } : { nombre: t }) });
  };
  const { data = [], mutate, isLoading } = useSWR<(Cliente & { telefono?: string | null; direccion?: string | null })[]>(
    emisor ? `/clientes?emisor_id=${emisor.id}&limit=1000${q ? `&q=${encodeURIComponent(q)}` : ""}` : null,
    fetcher,
  );
  const { data: addendas = [] } = useSWR<Addenda[]>("/addendas", fetcher);
  const nuevoRef = useRef(nuevo);
  nuevoRef.current = nuevo;

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    if (sp.get("importar")) setImportar(true);
    const rv = sp.get("revisar");  // /clientes?revisar=1 (problemas) o ?revisar=duplicados: lo usa la bandeja de pendientes
    if (rv) setRevisar(rv === "duplicados" ? "duplicados" : "problemas");
  }, []);

  // "/" enfoca la búsqueda · Alt+N nuevo cliente · Alt+I importar
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const escribiendo = ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName);
      if (e.key === "/" && !escribiendo) { e.preventDefault(); buscar.current?.focus(); }
      if (e.altKey && e.key.toLowerCase() === "n") { e.preventDefault(); nuevoRef.current(); }
      if (e.altKey && e.key.toLowerCase() === "i") { e.preventDefault(); setImportar(true); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  const abrir = (c: (typeof data)[number]) =>
    setEdit({
      ...vacio, ...c, forma_pago: c.forma_pago ?? "", metodo_pago: c.metodo_pago ?? "", emails: c.emails.join(", "),
      telefono: c.telefono ?? "", direccion: c.direccion ?? "", addenda_id: c.addenda_id ? String(c.addenda_id) : "",
      addenda_defaults: c.addenda_defaults ?? {}, notas: c.notas ?? "", dias_credito: String(c.dias_credito ?? 0),
    });

  return (
    <>
      <PageHeader title="Clientes">
        <Button onClick={() => setRevisar("problemas")}><ShieldCheck className="size-4" /> Revisar clientes</Button>
        <Button onClick={() => setImportar(true)} title="Alt + I"><FileUp className="size-4" /> Importar de Excel</Button>
        <Button variant="primario" onClick={nuevo} title="Alt + N"><Plus className="size-4" /> Cliente</Button>
      </PageHeader>
      <div className="relative mb-4">
        <Search className="pointer-events-none absolute left-3 top-3 size-4 text-grafito" />
        <Input ref={buscar} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por RFC o nombre  ( / )" className="pl-9" />
      </div>

      {!isLoading && !data.length ? (
        <Vacio titulo={q ? `Nadie coincide con “${q}”` : "Sin clientes"}>
          {q ? "Prueba con parte del RFC o del nombre." : "Impórtalos de tu Excel o se dan de alta solos la primera vez que les facturas."}
        </Vacio>
      ) : (
        <div className="@container overflow-hidden rounded-2xl bg-hoja ring-1 ring-linea">
          <p className="border-b border-linea px-4 py-2 text-xs text-grafito">{data.length} clientes</p>
          <ul>
            {data.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => abrir(c)}
                  className="grid w-full gap-x-4 gap-y-0.5 border-b border-linea px-4 py-3 text-left last:border-0 hover:bg-papel focus-visible:bg-cobalto-suave @min-[640px]:grid-cols-[minmax(0,1fr)_140px_90px_minmax(0,220px)] @min-[640px]:items-center"
                >
                  <span className="min-w-0 truncate font-medium">{c.nombre}</span>
                  <span className="text-sm text-grafito tabular-nums">{c.rfc}</span>
                  <span className="hidden text-sm text-grafito @min-[640px]:inline">Uso {c.uso_cfdi}</span>
                  <span className="min-w-0 truncate text-sm text-grafito">{c.emails[0] ?? c.telefono ?? ""}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <EditarCliente edit={edit} setEdit={setEdit} addendas={addendas} emisorId={emisor?.id} onOk={() => { setEdit(null); mutate(); }} />
      <Importar abierto={importar} cerrar={() => setImportar(false)} emisorId={emisor?.id} onOk={() => mutate()} />
      {emisor && <RevisionClientes emisorId={emisor.id} abierto={!!revisar} cerrar={() => setRevisar(null)} inicial={revisar ?? "problemas"} cambio={() => mutate()}
        editar={(id) => { const c = data.find((x) => x.id === id); if (c) abrir(c); else toast.message("Búscalo por su RFC en la lista para editarlo."); }} />}
    </>
  );
}

function EditarCliente({ edit, setEdit, addendas, emisorId, onOk }: {
  edit: Edit | null; setEdit: (e: Edit | null) => void; addendas: Addenda[]; emisorId?: number; onOk: () => void;
}) {
  const [guardando, setGuardando] = useState(false);
  if (!edit) return null;
  const addenda = addendas.find((a) => String(a.id) === edit.addenda_id);
  const rfcMal = !!edit.rfc && !RFC_RE.test(edit.rfc);
  const regMal = !!edit.regimen_fiscal && !regimenPermitido(edit.regimen_fiscal, edit.rfc);
  const usoMal = !!edit.uso_cfdi && !!edit.regimen_fiscal && !usoPermitido(edit.uso_cfdi, edit.regimen_fiscal);

  const guardar = async () => {
    if (!emisorId) return;
    setGuardando(true);
    try {
      await api(edit.id ? `/clientes/${edit.id}` : "/clientes", {
        method: edit.id ? "PUT" : "POST",
        json: {
          ...edit, emisor_id: emisorId, emails: edit.emails.split(/[\s,;|]+/).filter(Boolean),
          addenda_id: edit.addenda_id ? Number(edit.addenda_id) : null, forma_pago: edit.forma_pago || null,
          metodo_pago: edit.metodo_pago || null, telefono: edit.telefono || null, direccion: edit.direccion || null,
          dias_credito: Number(edit.dias_credito) || 0,
        },
      });
      toast.success("Cliente guardado");
      onOk();
    } catch (e) {
      mostrarError(e);
    } finally {
      setGuardando(false);
    }
  };
  const borrar = async () => {
    if (!edit.id || !confirm(`¿Borrar a ${edit.nombre}?`)) return;
    try {
      await api(`/clientes/${edit.id}`, { method: "DELETE" });
      onOk();
    } catch (e) {
      mostrarError(e);
    }
  };

  return (
    <Modal
      open
      onClose={() => setEdit(null)}
      title={edit.id ? "Editar cliente" : "Nuevo cliente"}
      wide
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          {edit.id ? <Button variant="fantasma" className="text-rojo" onClick={borrar}>Borrar</Button> : <span />}
          <div className="flex gap-2">
            <Button onClick={() => setEdit(null)}>Cancelar</Button>
            <Button variant="primario" onClick={guardar} loading={guardando} disabled={rfcMal || regMal || usoMal || !edit.nombre}>Guardar cliente</Button>
          </div>
        </div>
      }
    >
      <form
        onSubmit={(e) => { e.preventDefault(); guardar(); }}
        onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); guardar(); } }}
        className="@container grid gap-4"
      >
        <div className="grid gap-4 @min-[520px]:grid-cols-2">
          <Field label="RFC" error={rfcMal ? "Formato inválido" : undefined}>
            <Input value={edit.rfc} onChange={(e) => setEdit({ ...edit, rfc: e.target.value.toUpperCase().trim() })} autoCapitalize="characters" />
          </Field>
          <Field label="Código postal fiscal">
            <Input value={edit.codigo_postal} maxLength={5} inputMode="numeric" onChange={(e) => setEdit({ ...edit, codigo_postal: e.target.value.replace(/\D/g, "") })} />
          </Field>
          <Field label="Nombre o razón social (tal cual la constancia, sin SA de CV)" className="@min-[520px]:col-span-2">
            <Input value={edit.nombre} onChange={(e) => setEdit({ ...edit, nombre: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="Régimen fiscal" error={regMal ? `No aplica a persona ${edit.rfc.length === 12 ? "moral" : "física"}` : undefined}>
            <CatSelect catalogo="regimen_fiscal" value={edit.regimen_fiscal} onChange={(v) => setEdit({ ...edit, regimen_fiscal: v })} />
          </Field>
          <Field label="Uso del CFDI" error={usoMal ? `No va con el régimen ${edit.regimen_fiscal}` : undefined}>
            <CatSelect catalogo="uso_cfdi" value={edit.uso_cfdi} onChange={(v) => setEdit({ ...edit, uso_cfdi: v })} />
          </Field>
          <Field label="Método de pago habitual">
            <Select value={edit.metodo_pago} onChange={(e) => setEdit({ ...edit, metodo_pago: e.target.value })}>
              <option value="">Sin preferencia</option><option value="PUE">PUE · una exhibición</option><option value="PPD">PPD · parcialidades</option>
            </Select>
          </Field>
          <Field label="Forma de pago habitual">
            <CatSelect catalogo="forma_pago" value={edit.forma_pago} onChange={(v) => setEdit({ ...edit, forma_pago: v })} />
          </Field>
          <Field label="Correos para mandar facturas" hint="Separados por coma">
            <Input value={edit.emails} onChange={(e) => setEdit({ ...edit, emails: e.target.value })} inputMode="email" />
          </Field>
          <Field label="Teléfono">
            <Input value={edit.telefono} onChange={(e) => setEdit({ ...edit, telefono: e.target.value })} inputMode="tel" />
          </Field>
          <Field label="Dirección" className="@min-[520px]:col-span-2">
            <Input value={edit.direccion} onChange={(e) => setEdit({ ...edit, direccion: e.target.value })} />
          </Field>
          <Field label="Addenda que exige este cliente">
            <Select value={edit.addenda_id} onChange={(e) => setEdit({ ...edit, addenda_id: e.target.value })}>
              <option value="">Ninguna</option>
              {addendas.map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}
            </Select>
          </Field>
          <Field label="Notas"><Input value={edit.notas} onChange={(e) => setEdit({ ...edit, notas: e.target.value })} /></Field>
          <Field label="Días de crédito" hint="Cobranza marca la factura PPD como vencida después de estos días.">
            <Input inputMode="numeric" value={edit.dias_credito} onChange={(e) => setEdit({ ...edit, dias_credito: e.target.value.replace(/\D/g, "") })} />
          </Field>
        </div>
        {addenda && (
          <div className="grid gap-3 rounded-xl bg-papel p-4 @min-[520px]:grid-cols-2">
            <p className="text-sm text-grafito @min-[520px]:col-span-2">Datos fijos de la addenda (se precargan en cada factura)</p>
            {addenda.campos.map((f) => (
              <Field key={f.name} label={f.label}>
                <Input value={edit.addenda_defaults?.[f.name] ?? ""} onChange={(e) => setEdit({ ...edit, addenda_defaults: { ...edit.addenda_defaults, [f.name]: e.target.value } })} />
              </Field>
            ))}
          </div>
        )}
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}

/* ------------------------------ Importador ------------------------------ */

type FilaImp = {
  fila: number;
  datos: { rfc: string; nombre: string; codigo_postal: string; regimen_fiscal: string; uso_cfdi: string; emails: string[]; telefono: string | null; direccion: string | null } & Record<string, unknown>;
  errores: { campo: string; mensaje: string }[];
  avisos: { campo: string; mensaje: string }[];
  accion: "nuevo" | "actualizar" | "error" | "duplicado" | "conflicto" | "igual";
  regimen_original: string;
  conflictos?: { campo: string; etiqueta: string; hoja: string; base: string }[];
};
type Vista = { filas: FilaImp[]; faltan: string[]; resumen: Record<string, number> };
type Decision = "hoja" | "base";

const ENCABEZADO = "NOMBRE\tRFC\tCP\tDIRECCION\tREGIMEN_FISCAL\tCORREO_O_CONTACTO\tUSO_CFDI\tFORMA_PAGO\tMETODO_PAGO\tNOTAS";

function Importar({ abierto, cerrar, emisorId, onOk }: { abierto: boolean; cerrar: () => void; emisorId?: number; onOk: () => void }) {
  const [modo, setModo] = useState<"pegar" | "archivo">("pegar");
  const [texto, setTexto] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [uso, setUso] = useState("auto");
  const [vista, setVista] = useState<Vista | null>(null);
  const [existentes, setExistentes] = useState<"actualizar" | "omitir">("actualizar");
  const [cargando, setCargando] = useState(false);
  const [hecho, setHecho] = useState<{ creados: number; actualizados: number; omitidos: number; sin_decidir?: number } | null>(null);
  const [decisiones, setDecisiones] = useState<Record<string, Decision>>({});

  useEffect(() => {
    if (!abierto) { setVista(null); setHecho(null); setTexto(""); setArchivo(null); setDecisiones({}); }
  }, [abierto]);

  const revisar = async () => {
    if (!emisorId || (!texto.trim() && !archivo)) return;
    const fd = new FormData();
    fd.append("emisor_id", String(emisorId));
    fd.append("uso_default", uso);
    if (modo === "archivo" && archivo) fd.append("archivo", archivo);
    else fd.append("texto", texto);
    setCargando(true);
    try {
      setDecisiones({});
      setVista(await api<Vista>("/clientes/importar/previsualizar", { method: "POST", body: fd }));
    } catch (e) {
      mostrarError(e);
    } finally {
      setCargando(false);
    }
  };

  // Los conflictos sólo entran si TÚ decidiste (hoja o lo guardado); sin decisión no se toca nada
  const validas = vista?.filas.filter((f) => f.accion === "nuevo" || f.accion === "actualizar" || (f.accion === "conflicto" && decisiones[f.datos.rfc])) ?? [];
  const aImportar = existentes === "omitir" ? validas.filter((f) => f.accion === "nuevo" || f.accion === "conflicto") : validas;
  const sinDecidir = vista?.filas.filter((f) => f.accion === "conflicto" && !decisiones[f.datos.rfc]).length ?? 0;

  const confirmar = async () => {
    if (!emisorId || !aImportar.length) return;
    setCargando(true);
    try {
      const r = await api<{ creados: number; actualizados: number; omitidos: number; sin_decidir: number }>("/clientes/importar/confirmar", {
        method: "POST", json: { emisor_id: emisorId, filas: aImportar.map((f) => ({ ...f.datos, _accion: f.accion, _resolucion: decisiones[f.datos.rfc] ?? null })), modo: existentes },
      });
      setHecho(r);
      onOk();
    } catch (e) {
      mostrarError(e);
    } finally {
      setCargando(false);
    }
  };

  let footer: React.ReactNode;
  if (hecho) footer = <Button variant="primario" onClick={cerrar}>Listo</Button>;
  else if (vista)
    footer = (
      <div className="flex w-full flex-wrap items-center justify-between gap-2">
        <Button onClick={() => setVista(null)}>Volver a capturar</Button>
        <Button variant="primario" onClick={confirmar} loading={cargando} disabled={!aImportar.length}>
          Importar {aImportar.length} {aImportar.length === 1 ? "cliente" : "clientes"}{sinDecidir > 0 && ` (${sinDecidir} sin decidir quedan fuera)`}
        </Button>
      </div>
    );
  else
    footer = (
      <div className="flex w-full flex-wrap items-center justify-between gap-2">
        <Button variant="fantasma" onClick={() => descargar("/clientes/importar/plantilla", "formato_clientes_timbra.xlsx").catch(mostrarError)}>
          <Download className="size-4" /> Formato Excel
        </Button>
        <Button variant="primario" onClick={revisar} loading={cargando} disabled={modo === "pegar" ? !texto.trim() : !archivo}>
          Revisar datos <span className="hidden sm:inline"><Kbd>Ctrl + Enter</Kbd></span>
        </Button>
      </div>
    );

  return (
    <Modal open={abierto} onClose={cerrar} title="Importar clientes" wide="xl" footer={footer}>
      {hecho ? (
        <div className="py-6 text-center">
          <CheckCircle2 className="mx-auto size-10 text-sello" />
          <p className="mt-3 text-lg font-semibold">Clientes importados</p>
          <p className="mt-1 text-grafito">{hecho.creados} nuevos · {hecho.actualizados} actualizados · {hecho.omitidos} omitidos{!!hecho.sin_decidir && ` · ${hecho.sin_decidir} sin decidir`}</p>
        </div>
      ) : vista ? (
        <Revision vista={vista} existentes={existentes} setExistentes={setExistentes} decisiones={decisiones} setDecisiones={setDecisiones} />
      ) : (
        <div className="grid gap-4">
          <div className="flex gap-1 rounded-lg bg-papel p-1" role="tablist">
            {(["pegar", "archivo"] as const).map((m) => (
              <button key={m} role="tab" aria-selected={modo === m} onClick={() => setModo(m)} className={cx("h-9 flex-1 rounded-md text-sm font-medium", modo === m ? "bg-hoja shadow-sm" : "text-grafito")}>
                {m === "pegar" ? "Pegar desde Excel" : "Subir archivo (.xlsx / .csv)"}
              </button>
            ))}
          </div>
          {modo === "pegar" ? (
            <Field label="Copia las celdas en Excel (con la fila de encabezados) y pégalas aquí" hint="Columnas: NOMBRE, RFC, CP, DIRECCION, REGIMEN_FISCAL, CORREO_O_CONTACTO y opcionales USO_CFDI, FORMA_PAGO, METODO_PAGO, NOTAS. Régimen con clave o con texto.">
              <textarea
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); revisar(); } }}
                rows={9}
                spellCheck={false}
                placeholder={ENCABEZADO}
                className="w-full rounded-lg border border-linea bg-papel p-3 font-[ui-monospace,monospace] text-xs leading-relaxed focus:border-cobalto focus:outline-none"
              />
            </Field>
          ) : (
            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-linea bg-papel px-4 py-10 text-center hover:border-cobalto">
              <Upload className="size-6 text-grafito" />
              <span className="font-medium">{archivo ? archivo.name : "Elige tu archivo de Excel o CSV"}</span>
              <span className="text-sm text-grafito">La primera hoja, con la fila de encabezados</span>
              <input type="file" accept=".xlsx,.xlsm,.csv,.txt" className="sr-only" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
            </label>
          )}
          <Field label="Uso del CFDI cuando la columna venga vacía" hint="Siempre se valida contra el régimen de cada cliente; si no aplica, se usa uno válido.">
            <Select value={uso} onChange={(e) => setUso(e.target.value)}>
              <option value="auto">Automático: G03 Gastos en general, o S01 si su régimen no lo permite</option>
              <option value="D01">D01 Honorarios médicos (pacientes de consultorio)</option>
              <option value="G03">G03 Gastos en general</option>
              <option value="S01">S01 Sin efectos fiscales</option>
              <option value="G01">G01 Adquisición de mercancías</option>
            </Select>
          </Field>
        </div>
      )}
    </Modal>
  );
}

function Revision({ vista, existentes, setExistentes, decisiones, setDecisiones }: {
  vista: Vista; existentes: "actualizar" | "omitir"; setExistentes: (v: "actualizar" | "omitir") => void;
  decisiones: Record<string, Decision>; setDecisiones: (d: Record<string, Decision>) => void;
}) {
  const r = vista.resumen;
  const conflictos = vista.filas.filter((f) => f.accion === "conflicto");
  const decidirTodos = (d: Decision) => setDecisiones(Object.fromEntries(conflictos.map((f) => [f.datos.rfc, d])));
  return (
    <div className="@container grid gap-4">
      {vista.faltan.length > 0 && (
        <p className="flex items-start gap-2 rounded-xl bg-rojo-suave px-4 py-3 text-sm text-rojo">
          <XCircle className="mt-0.5 size-4 shrink-0" /> No encontré las columnas: {vista.faltan.join(", ")}. Revisa que pegaste la fila de encabezados.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Badge tono="sello">{r.nuevo ?? 0} nuevos</Badge>
        <Badge tono="cobalto">{r.actualizar ?? 0} ya existen</Badge>
        {(r.error ?? 0) > 0 && <Badge tono="rojo">{r.error} con errores (no se importan)</Badge>}
        {(r.duplicado ?? 0) > 0 && <Badge tono="alerta">{r.duplicado} repetidos</Badge>}
        {(r.conflicto ?? 0) > 0 && <Badge tono="alerta">{r.conflicto} con datos distintos a los guardados</Badge>}
        {(r.igual ?? 0) > 0 && <Badge>{r.igual} sin cambios</Badge>}
      </div>
      {conflictos.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-alerta-suave px-4 py-3 text-sm text-alerta">
          <AlertTriangle className="size-4 shrink-0" />
          <span className="min-w-0 flex-1">Estos clientes ya existen con nombre, CP o régimen distintos. Decide cuál es el correcto; no se pisa nada sin tu decisión.</span>
          <Button size="sm" onClick={() => decidirTodos("hoja")}>Usar todo lo de la hoja</Button>
          <Button size="sm" onClick={() => decidirTodos("base")}>Conservar todo lo guardado</Button>
        </div>
      )}
      {(r.actualizar ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-grafito">Si el RFC ya existe:</span>
          {(["actualizar", "omitir"] as const).map((m) => (
            <label key={m} className="flex items-center gap-1.5">
              <input type="radio" checked={existentes === m} onChange={() => setExistentes(m)} className="accent-cobalto" />
              {m === "actualizar" ? "Actualizar sus datos" : "Dejarlo como está"}
            </label>
          ))}
        </div>
      )}
      <ul className="max-h-[52vh] divide-y divide-linea overflow-auto rounded-xl ring-1 ring-linea">
        {vista.filas.map((f) => (
          <li key={f.fila} className={cx("px-4 py-3", f.accion === "error" && "bg-rojo-suave/50")}>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-xs text-grafito tabular-nums">Fila {f.fila}</span>
              <span className="min-w-0 flex-1 truncate font-medium">{f.datos.nombre || "(sin nombre)"}</span>
              <Badge tono={f.accion === "nuevo" ? "sello" : f.accion === "actualizar" ? "cobalto" : f.accion === "error" ? "rojo" : f.accion === "igual" ? "neutro" : "alerta"}>
                {{ nuevo: "Nuevo", actualizar: "Agrega datos", error: "Error", duplicado: "Repetido", conflicto: "Conflicto", igual: "Sin cambios" }[f.accion]}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-grafito tabular-nums">
              {f.datos.rfc} · CP {f.datos.codigo_postal || "—"} · Régimen {f.datos.regimen_fiscal || "?"} · Uso {f.datos.uso_cfdi}
              {f.datos.emails.length > 0 && ` · ${f.datos.emails.join(", ")}`}
              {f.datos.telefono && ` · Tel ${f.datos.telefono}`}
            </p>
            {f.accion === "conflicto" && f.conflictos && (
              <div className="mt-2 grid gap-2 rounded-lg bg-papel p-3 text-sm">
                {f.conflictos.map((d) => (
                  <p key={d.campo} className="flex flex-wrap items-baseline gap-x-2"><b className="w-16 shrink-0 text-grafito">{d.etiqueta}</b>
                    <span>guardado: <b>{d.base}</b></span><span className="text-grafito">→</span><span>hoja: <b className="text-alerta">{d.hoja}</b></span></p>
                ))}
                <div className="flex flex-wrap gap-4 pt-1">
                  {([["hoja", "Usar lo de la hoja"], ["base", "Conservar lo guardado"]] as const).map(([v, txt]) => (
                    <label key={v} className="flex items-center gap-1.5"><input type="radio" name={`dec-${f.fila}`} checked={decisiones[f.datos.rfc] === v}
                      onChange={() => setDecisiones({ ...decisiones, [f.datos.rfc]: v })} className="accent-cobalto" /> {txt}</label>
                  ))}
                </div>
              </div>
            )}
            {[...f.errores.map((e) => ({ ...e, error: true })), ...f.avisos.map((a) => ({ ...a, error: false }))].map((m, i) => (
              <p key={i} className={cx("mt-1 flex items-start gap-1.5 text-sm", m.error ? "text-rojo" : "text-alerta")}>
                {m.error ? <XCircle className="mt-0.5 size-3.5 shrink-0" /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />}
                {m.mensaje}
              </p>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}
