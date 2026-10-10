"use client";
import { Suspense, forwardRef, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, ArrowDown, ArrowUp, BookmarkPlus, CheckCircle2, ChevronDown, ChevronUp, Copy, Download, FileDown, Mail, Percent, Plus, RotateCcw, Trash2, XCircle, Calculator, Settings2, Repeat, Users, Zap, BookUser, List, FlaskConical } from "lucide-react";
import { api, descargar, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { dinero, IVA16, IVA8, PRESETS_IMPUESTOS, RFC_RE } from "@/lib/format";
import { OpcionesImpuestos } from "@/components/impuestos";
import { CalcPrecio } from "@/components/calculadora";
import { evaluarMonto, regimenPermitido, usoPermitido, usoSugerido } from "@/lib/sat";
import type { Addenda, CampoFacturar, Cliente, Concepto, ConfigFacturar, Factura, Impuesto, PerfilFacturar, Plantilla, Producto, Tercero } from "@/lib/types";
import { ConfigFacturarModal, visiblesDe } from "@/components/config-facturar";
import { EditorImpuestos, ListaClientes, ListaConceptos, deFacturado, deProducto, type Sugerencias } from "@/components/facturar-listas";
import { useEmisor } from "@/components/emisor-context";
import { CatSelect, ClaveSearch } from "@/components/catalogo";
import { Badge, Button, Field, Input, Kbd, Menu, Select, cx } from "@/components/ui";

type Modo = "I" | "G" | "E" | "T";
const MODOS: { id: Modo; label: string }[] = [
  { id: "I", label: "Factura" },
  { id: "G", label: "Público en general" },
  { id: "E", label: "Nota de crédito" },
  { id: "T", label: "Traslado" },
];
type Val = { campo: string; mensaje: string; sugerencia: string | null };
type Preview = { subtotal: string; descuento: string; traslados: string; retenciones: string; total: string; errores: Val[]; avisos: Val[] };
type NuevoReceptor = { rfc: string; nombre: string; regimen_fiscal: string; codigo_postal: string; uso_cfdi: string };

const receptorVacio: NuevoReceptor = { rfc: "", nombre: "", regimen_fiscal: "", codigo_postal: "", uso_cfdi: "G03" };
// IVA por defecto de conceptos nuevos: 8% si el emisor está en región fronteriza (se ajusta al cambiar de emisor)
// Clave y unidad por defecto vienen de la configuración de la barra (nivel simple: no se capturan)
const defecto = { imps: [IVA16] as Impuesto[], clave: "", unidad: "E48" };
const nuevoConcepto = (): Concepto => ({
  key: crypto.randomUUID(), clave_prod_serv: defecto.clave, clave_unidad: defecto.unidad, descripcion: "", cantidad: "1",
  valor_unitario: "", objeto_imp: defecto.imps.length ? "02" : "01", impuestos: [...defecto.imps],
});
const vacio = (c: Concepto) => !c.descripcion.trim() && !c.valor_unitario.trim();
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const conMes = (s: string) => s.replace(/\{MES\}/g, MESES[new Date().getMonth()].toUpperCase()).replace(/\{mes\}/g, MESES[new Date().getMonth()])
  .replace(/\{año\}/g, String(new Date().getFullYear()));
type Ultima = { factura_id: number; folio: string; fecha: string; total: string; payload: Record<string, any> } | null;
// "0.08" y "0.080000" son la misma tasa: se comparan normalizadas
const firma = (imps: readonly { tipo: string; impuesto: string; factor: string; tasa: string | null }[]) =>
  imps.map((i) => `${i.tipo}|${i.impuesto}|${i.factor}|${i.tasa === null ? "" : Number(i.tasa).toFixed(6)}`).join(";");
const presetDe = (imps: Impuesto[]) =>
  Object.entries(PRESETS_IMPUESTOS).find(([, v]) => firma(v) === firma(imps))?.[0] ?? "Personalizado";
const hoy = new Date();
// Impuestos locales más comunes. Las tasas son punto de partida: cada estado fija la suya.
const LOCALES: { nombre: string; label: string; tipo: "traslado" | "retencion"; tasa: string }[] = [
  { nombre: "ISH", label: "ISH · Impuesto sobre hospedaje", tipo: "traslado", tasa: "3" },
  { nombre: "Cedular", label: "Cedular (honorarios, arrendamiento)", tipo: "retencion", tasa: "" },
  { nombre: "5 al millar", label: "5 al millar · inspección de obra pública", tipo: "retencion", tasa: "0.5" },
  { nombre: "2 al millar", label: "2 al millar · capacitación (CMIC)", tipo: "retencion", tasa: "0.2" },
];
const ishDe = (cp: string) => (/^3[1-3]/.test(cp) ? "4" : "3"); // Chihuahua cobra 4%

export default function FacturarPage() {
  return (
    <Suspense>
      <Facturar />
    </Suspense>
  );
}

function Facturar() {
  const { emisor } = useEmisor();
  const frontera = !!emisor?.region_fronteriza;
  const { data: cfg, mutate: mutCfg } = useSWR<ConfigFacturar>(emisor ? `/emisores/${emisor.id}/config-facturar` : null, fetcher);
  const vis = visiblesDe(cfg);
  const presetCfg = cfg?.defaults.impuesto ? PRESETS_IMPUESTOS[cfg.defaults.impuesto as keyof typeof PRESETS_IMPUESTOS] : undefined;
  defecto.imps = presetCfg ? ([...presetCfg] as Impuesto[]) : [(frontera ? IVA8 : IVA16) as Impuesto];
  defecto.clave = vis.clave_sat ? "" : cfg?.defaults.clave_prod_serv ?? "";
  defecto.unidad = cfg?.defaults.clave_unidad ?? "E48";
  const [configurar, setConfigurar] = useState(false);
  const llave = useRef(crypto.randomUUID()); // Idempotency-Key: un reintento nunca timbra dos veces
  const { data: terceros = [] } = useSWR<Tercero[]>(emisor && (vis.terceros || cfg?.perfiles.some((p) => p.tercero_id)) ? `/terceros?emisor_id=${emisor.id}` : null, fetcher);
  const params = useSearchParams();
  const [modo, setModo] = useState<Modo>("I");
  const [cliente, setCliente] = useState<Cliente | null>(null);
  const [nuevo, setNuevo] = useState<NuevoReceptor | null>(null);
  const [metodo, setMetodo] = useState("PUE");
  const [forma, setForma] = useState("03");
  const [moneda, setMoneda] = useState("MXN");
  const [tc, setTc] = useState("");
  const [conceptos, setConceptos] = useState<Concepto[]>([nuevoConcepto()]);
  // Al cargar o cambiar de emisor: si no has capturado nada, los conceptos toman su IVA (8% frontera o 16%)
  const defectoDe = useRef("");
  useEffect(() => {
    const llave = `${emisor?.id}|${frontera}|${!!cfg}|${cfg?.defaults.impuesto ?? ""}|${cfg?.defaults.clave_prod_serv ?? ""}|${cfg?.defaults.clave_unidad ?? ""}`;
    if (defectoDe.current === llave) return; // sólo al entrar, cambiar de emisor o cambiar los valores por defecto: nunca pisa lo que elegiste
    defectoDe.current = llave;
    setConceptos((cs) => (cs.every(vacio) ? cs.map((c) => ({ ...c, impuestos: [...defecto.imps], objeto_imp: defecto.imps.length ? "02" : "01",
      clave_prod_serv: c.clave_prod_serv || defecto.clave, clave_unidad: c.clave_unidad || defecto.unidad })) : cs));
  }, [frontera, cfg, emisor?.id]);
  const [avanzado, setAvanzado] = useState(false);
  const [condiciones, setCondiciones] = useState("");
  const [relTipo, setRelTipo] = useState("01");
  const [relUuids, setRelUuids] = useState("");
  const [global, setGlobal] = useState({ periodicidad: "04", meses: String(hoy.getMonth() + 1).padStart(2, "0"), ano: String(hoy.getFullYear()) });
  const [addendaId, setAddendaId] = useState<number | null>(null);
  const [addendaDatos, setAddendaDatos] = useState<Record<string, string>>({});
  const [locales, setLocales] = useState<{ tipo: "traslado" | "retencion"; nombre: string; tasa: string; importe: string }[]>([]);
  const [enviar, setEnviar] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [timbrando, setTimbrando] = useState(false);
  const [resultado, setResultado] = useState<Factura | null>(null);
  const [foco, setFoco] = useState<[number, number] | null>(null);
  const clienteRef = useRef<HTMLInputElement>(null);
  const plantillaRef = useRef<HTMLSelectElement>(null);
  const [ultima, setUltima] = useState<Ultima>(null);
  const [verClientes, setVerClientes] = useState(false);
  const [verConceptos, setVerConceptos] = useState(false);

  // Valores por defecto de la configuración (una vez por emisor, sin pisar lo que ya capturaste)
  const aplicado = useRef<number | null>(null);
  useEffect(() => {
    if (!cfg || !emisor || aplicado.current === emisor.id) return;
    aplicado.current = emisor.id;
    if (params.get("clonar") || params.get("plantilla") || params.get("calc")) return;
    setModo(cfg.modos.includes(cfg.defaults.modo) ? cfg.defaults.modo : cfg.modos[0]);
    setMetodo(cfg.defaults.metodo);
    setForma(cfg.defaults.forma);
    setEnviar(cfg.defaults.enviar_email);
    setAvanzado(cfg.avanzado_abierto);
  }, [cfg, emisor]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data: addendas = [] } = useSWR<Addenda[]>("/addendas", fetcher);
  const addenda = addendas.find((a) => a.id === addendaId);
  const { data: plantillas = [], mutate: mutPlantillas } = useSWR<Plantilla[]>(
    emisor ? `/plantillas?emisor_id=${emisor.id}${cliente ? `&cliente_id=${cliente.id}` : ""}` : null,
    fetcher,
  );

  // Foco pedido por teclado (fila, columna) → se aplica tras el render
  useEffect(() => {
    if (!foco) return;
    const el = document.querySelector<HTMLElement>(`[data-cell="${foco[0]}-${foco[1]}"]`);
    if (el) {
      el.focus();
      if (el instanceof HTMLInputElement) el.select();
    }
    setFoco(null);
  }, [foco, conceptos]);

  // ---------- Plantillas / clonar ----------
  const cargarPayload = useCallback(async (p: Record<string, any>) => {
    setResultado(null);
    setModo(p.publico_general ? "G" : (p.tipo ?? "I"));
    setMetodo(p.metodo_pago ?? "PUE");
    setForma(p.forma_pago && p.forma_pago !== "99" ? p.forma_pago : "03");
    setMoneda(p.moneda ?? "MXN");
    setTc(p.tipo_cambio ?? "");
    setCondiciones(p.condiciones_pago ?? "");
    setLocales((p.impuestos_locales ?? []).map((l: any) => ({ ...l, tasa: String(l.tasa), importe: String(l.importe) })));
    setAddendaId(p.addenda?.addenda_id ?? null);
    setAddendaDatos(p.addenda?.datos ?? {});
    setConceptos(p.conceptos.map((c: any) => ({
      ...c, key: crypto.randomUUID(), cantidad: String(c.cantidad), valor_unitario: String(c.valor_unitario),
      descuento: c.descuento ? String(c.descuento) : "", ver_descuento: !!c.descuento,
      ver_extra: !!(c.a_cuenta_terceros || c.cuenta_predial || c.informacion_aduanera?.length),
    })));
    if (p.cliente_id) {
      const lista = await api<Cliente[]>(`/clientes?emisor_id=${p.emisor_id}&limit=500`);
      setCliente(lista.find((c) => c.id === p.cliente_id) ?? null);
      setNuevo(null);
    } else if (p.receptor) {
      setCliente(null);
      setNuevo(p.receptor);
    }
  }, []);

  useEffect(() => {
    if (params.get("calc")) {
      try {
        const cs = JSON.parse(localStorage.getItem("timbra:calc") || "[]") as Omit<Concepto, "key">[];
        if (cs.length) {
          setConceptos(cs.map((c) => ({ ...c, key: crypto.randomUUID() })));
          toast.message("Conceptos de la calculadora cargados. Elige cliente y timbra.");
        }
        localStorage.removeItem("timbra:calc");
      } catch { /* nada que cargar */ }
    }
    if (params.get("configurar")) setConfigurar(true);
    const clonar = params.get("clonar");
    const plantilla = params.get("plantilla");
    if (clonar) api<Record<string, any>>(`/facturas/${clonar}/payload`).then(cargarPayload).then(() => toast.message("Factura clonada. Revisa y timbra.")).catch(mostrarError);
    if (plantilla) api<Record<string, any>>(`/plantillas/${plantilla}/usar`, { method: "POST" }).then(cargarPayload).then(() => toast.message("Plantilla cargada")).catch(mostrarError);
  }, [params, cargarPayload]);

  const usarPlantilla = async (id: number) => {
    try {
      await cargarPayload(await api<Record<string, any>>(`/plantillas/${id}/usar`, { method: "POST" }));
      toast.message("Plantilla cargada. Ajusta lo que cambie y timbra.");
    } catch (e) {
      mostrarError(e);
    }
  };

  // ---------- Última factura del cliente: repetir en un clic ----------
  useEffect(() => {
    setUltima(null);
    if (!cliente || !vis.repetir_ultima) return;
    api<Ultima>(`/facturas/ultima?cliente_id=${cliente.id}`).then(setUltima).catch(() => setUltima(null));
  }, [cliente, vis.repetir_ultima]);
  const repetirUltima = useCallback(() => {
    if (!ultima || !cliente || !emisor) return;
    cargarPayload({ ...ultima.payload, cliente_id: cliente.id, emisor_id: emisor.id, conceptos: ultima.payload.conceptos.map((c: any) => ({ ...c, descripcion: c.descripcion })) })
      .then(() => toast.message(`Cargada la última (${ultima.folio}). Ajusta lo que cambie y timbra.`));
    setUltima(null);
  }, [ultima, cliente, emisor, cargarPayload]);

  // ---------- Perfiles rápidos ----------
  const aplicarPerfil = (p: PerfilFacturar) => {
    if (p.modo) setModo(p.modo);
    if (p.metodo) setMetodo(p.metodo);
    if (p.forma) setForma(p.forma);
    const preset = p.impuesto ? PRESETS_IMPUESTOS[p.impuesto as keyof typeof PRESETS_IMPUESTOS] : undefined;
    const imps = preset ? ([...preset] as Impuesto[]) : [...defecto.imps];
    const t = p.tercero_id ? terceros.find((x) => x.id === p.tercero_id) : undefined;
    if (t) api(`/terceros/${t.id}/usado`, { method: "POST" }).catch(() => {});
    else if (p.tercero_id) toast.warning(`El tercero del perfil «${p.nombre}» ya no existe. Edítalo en Configurar → Perfiles.`);
    const c: Concepto = {
      ...nuevoConcepto(), impuestos: imps, objeto_imp: imps.length ? "02" : "01",
      descripcion: p.concepto?.descripcion ? conMes(p.concepto.descripcion) : "",
      clave_prod_serv: p.concepto?.clave_prod_serv || defecto.clave, clave_unidad: p.concepto?.clave_unidad || defecto.unidad,
      valor_unitario: p.concepto?.valor_unitario ?? "",
      a_cuenta_terceros: t ? { rfc: t.rfc, nombre: t.nombre, regimen_fiscal: t.regimen_fiscal, codigo_postal: t.codigo_postal } : null,
      ver_extra: !!t,
    };
    setConceptos((cs) => (cs.every(vacio) ? [c] : [...cs, c]));
    toast.message(`Perfil «${p.nombre}» aplicado`);
  };

  // ---------- Defaults del cliente ----------
  useEffect(() => {
    if (!cliente) return;
    if (cliente.metodo_pago) setMetodo(cliente.metodo_pago);
    if (cliente.forma_pago) setForma(cliente.forma_pago);
    setAddendaId(cliente.addenda_id);
    setAddendaDatos(cliente.addenda_defaults ?? {});
  }, [cliente]);

  // ---------- Payload ----------
  const payload = useMemo(() => {
    if (!emisor) return null;
    const p: Record<string, unknown> = {
      emisor_id: emisor.id,
      tipo: modo === "G" ? "I" : modo,
      publico_general: modo === "G",
      metodo_pago: metodo,
      forma_pago: metodo === "PPD" ? "99" : forma,
      moneda,
      tipo_cambio: moneda !== "MXN" && tc ? evaluarMonto(tc) || null : null,
      condiciones_pago: condiciones || null,
      enviar_email: enviar,
      conceptos: conceptos.filter((c) => !vacio(c)).map(({ key, ver_descuento, ver_extra, ...c }) => ({
        ...c,
        a_cuenta_terceros: c.a_cuenta_terceros?.rfc ? c.a_cuenta_terceros : null,
        cuenta_predial: c.cuenta_predial?.trim() || null,
        informacion_aduanera: (c.informacion_aduanera ?? []).filter(Boolean),
        cantidad: evaluarMonto(c.cantidad) || "0",
        valor_unitario: evaluarMonto(c.valor_unitario) || "0",
        descuento: evaluarMonto(c.descuento ?? "") || null,
        objeto_imp: c.impuestos.length ? "02" : "01",
      })),
      relacionados: relUuids.trim() ? [{ tipo_relacion: relTipo, uuids: relUuids.split(/[\s,]+/).filter(Boolean) }] : [],
      impuestos_locales: locales.filter((l) => l.nombre && l.importe).map((l) => ({ ...l, tasa: evaluarMonto(l.tasa) || "0", importe: evaluarMonto(l.importe) || "0" })),
      addenda: addendaId ? { addenda_id: addendaId, datos: addendaDatos } : null,
      informacion_global: modo === "G" ? { periodicidad: global.periodicidad, meses: global.meses, ano: Number(global.ano) } : null,
    };
    if (modo !== "G") {
      if (cliente) p.cliente_id = cliente.id;
      else if (nuevo && RFC_RE.test(nuevo.rfc)) p.receptor = { ...nuevo, guardar: true };
    }
    return p;
  }, [emisor, modo, metodo, forma, moneda, tc, condiciones, enviar, conceptos, relTipo, relUuids, locales, addendaId, addendaDatos, cliente, nuevo, global]);

  const nConceptos = (payload?.conceptos as unknown[] | undefined)?.length ?? 0;

  // Totales y validaciones SAT en vivo (mismo cálculo que el CFDI final)
  useEffect(() => {
    if (!payload || !nConceptos) return setPreview(null);
    const t = setTimeout(async () => {
      try {
        setPreview(await api<Preview>("/facturas/preview", { method: "POST", json: payload }));
      } catch (e) {
        setPreview({ subtotal: "0", descuento: "0", traslados: "0", retenciones: "0", total: "0", avisos: [], errores: [{ campo: "cfdi", mensaje: (e as Error).message, sugerencia: null }] });
      }
    }, 280);
    return () => clearTimeout(t);
  }, [payload, nConceptos]);

  const errores = preview?.errores ?? [];
  const listo = nConceptos > 0 && !!preview && errores.length === 0;

  const timbrar = useCallback(async () => {
    if (!payload || timbrando || resultado) return;
    if (!nConceptos) return toast.error("Agrega al menos un concepto.");
    if (errores.length) return toast.error(`Corrige ${errores.length} ${errores.length === 1 ? "detalle" : "detalles"} antes de timbrar: ${errores[0].mensaje}`);
    setTimbrando(true);
    try {
      const f = await api<Factura>("/facturas", { method: "POST", json: payload, headers: { "Idempotency-Key": llave.current } });
      llave.current = crypto.randomUUID();
      if (f.error) toast.warning(f.error);
      if (cfg?.tras_timbrar === "nueva") {
        toast.success(`Timbrada ${f.serie ?? ""}${f.folio ?? ""} · ${dinero(f.total, f.moneda)}`, {
          duration: 10000, action: { label: "PDF", onClick: () => descargar(`/facturas/${f.id}/pdf`, `${f.uuid}.pdf`).catch(mostrarError) },
        });
        reiniciarRef.current();
      } else {
        setResultado(f);
        toast.success(`Timbrada ${f.serie ?? ""}${f.folio ?? ""}`);
      }
    } catch (e) {
      mostrarError(e);
    } finally {
      setTimbrando(false);
    }
  }, [payload, timbrando, resultado, nConceptos, errores, cfg]);
  const reiniciarRef = useRef(() => {});

  const guardarPlantilla = useCallback(async () => {
    if (!payload || !emisor || !nConceptos) return toast.error("Arma primero la factura que quieres guardar.");
    const sugerido = `${cliente?.nombre ?? nuevo?.nombre ?? "Público en general"} · ${conceptos[0]?.descripcion ?? ""}`.slice(0, 80);
    const nombre = window.prompt("Nombre de la plantilla", sugerido);
    if (!nombre) return;
    try {
      await api("/plantillas", { method: "POST", json: { emisor_id: emisor.id, cliente_id: cliente?.id ?? null, nombre, payload } });
      toast.success("Plantilla guardada");
      mutPlantillas();
    } catch (e) {
      mostrarError(e);
    }
  }, [payload, emisor, nConceptos, cliente, nuevo, conceptos, mutPlantillas]);

  const reiniciar = useCallback(() => {
    llave.current = crypto.randomUUID();
    setResultado(null);
    setUltima(null);
    setCliente(null);
    setNuevo(null);
    setConceptos([nuevoConcepto()]);
    setRelUuids("");
    setLocales([]);
    setAddendaId(null);
    setAddendaDatos({});
    setPreview(null);
    setTimeout(() => clienteRef.current?.focus(), 50);
  }, []);
  reiniciarRef.current = reiniciar;

  // ---------- Conceptos ----------
  const upd = (i: number, patch: Partial<Concepto>) => setConceptos((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const agregar = useCallback((foc = true) => {
    setConceptos((cs) => {
      if (foc) setFoco([cs.length, 0]);
      return [...cs, nuevoConcepto()];
    });
  }, []);
  const duplicar = (i: number) => setConceptos((cs) => [...cs.slice(0, i + 1), { ...cs[i], key: crypto.randomUUID() }, ...cs.slice(i + 1)]);
  const borrar = (i: number) => setConceptos((cs) => (cs.length > 1 ? cs.filter((_, j) => j !== i) : [nuevoConcepto()]));
  const mover = (i: number, d: number) =>
    setConceptos((cs) => {
      const j = i + d;
      if (j < 0 || j >= cs.length) return cs;
      const n = [...cs];
      [n[i], n[j]] = [n[j], n[i]];
      return n;
    });

  // ---------- Atajos de esta pantalla ----------
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (document.querySelector("[role=dialog]")) return;
      const ctrl = e.ctrlKey || e.metaKey;
      if (ctrl && e.key === "Enter") { e.preventDefault(); timbrar(); return; }
      if (ctrl && e.key.toLowerCase() === "s") { e.preventDefault(); guardarPlantilla(); return; }
      if (!e.altKey || ctrl) return;
      const code = e.code;
      if (code === "KeyC") { e.preventDefault(); clienteRef.current ? clienteRef.current.focus() : document.querySelector<HTMLElement>("[data-campo=receptor]")?.focus(); }
      else if (code === "KeyA") { e.preventDefault(); agregar(); }
      else if (/^Digit[1-4]$/.test(code) && !e.shiftKey) { e.preventDefault(); setModo(MODOS[Number(code.slice(-1)) - 1].id); }
      else if (code === "KeyM") { e.preventDefault(); setMetodo((m) => (m === "PUE" ? "PPD" : "PUE")); }
      else if (code === "KeyO") { e.preventDefault(); setAvanzado((a) => !a); }
      else if (code === "KeyP") { e.preventDefault(); plantillaRef.current?.focus(); }
      else if (code === "KeyU") { e.preventDefault(); repetirUltima(); }
      else if (code === "KeyG") { e.preventDefault(); setVerClientes(true); }
      else if (code === "KeyI") { e.preventDefault(); setVerConceptos(true); }
    };
    const nueva = () => { if (resultado) reiniciar(); else clienteRef.current?.focus(); };
    window.addEventListener("keydown", k);
    window.addEventListener("timbra:nueva", nueva);
    return () => { window.removeEventListener("keydown", k); window.removeEventListener("timbra:nueva", nueva); };
  }, [timbrar, guardarPlantilla, agregar, resultado, reiniciar, repetirUltima]);

  // Llevar al campo con problema al tocar un error
  const irA = (campo: string) => {
    if (campo.startsWith("relacionados") || campo.startsWith("global")) setAvanzado(true);
    const m = campo.match(/^conceptos\.(\d+)/);
    const sel = m ? `[data-cell="${Number(m[1]) - 1}-0"]` : `[data-campo="${campo.split(".")[0]}"]`;
    setTimeout(() => {
      const el = document.querySelector<HTMLElement>(sel) ?? document.querySelector<HTMLElement>(`[data-campo^="${campo.split(".")[0]}"]`);
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
      el?.focus();
    }, 60);
  };

  // Arreglos de un clic que sugiere la validación
  const aplicarSugerencia = async (v: Val) => {
    if (!v.sugerencia) return;
    const primero = v.sugerencia.split(",")[0].trim();
    const patch = v.campo.endsWith("uso_cfdi") ? { uso_cfdi: primero } : v.campo.endsWith("nombre") ? { nombre: v.sugerencia } : null;
    if (!patch) return;
    if (nuevo) return setNuevo({ ...nuevo, ...patch });
    if (cliente) {
      try {
        const c = await api<Cliente>(`/clientes/${cliente.id}`, { method: "PUT", json: { ...cliente, ...patch } });
        setCliente(c);
        toast.success("Cliente actualizado");
      } catch (e) {
        mostrarError(e);
      }
    }
  };

  if (!emisor) return <p className="text-grafito">Da de alta un emisor con su CSD para empezar a facturar.</p>;

  // Importe de un impuesto local = (subtotal − descuento) × tasa
  const importeLocal = (tasa: string) => {
    const base = Number(preview?.subtotal ?? 0) - Number(preview?.descuento ?? 0);
    const t = Number(evaluarMonto(tasa) || 0);
    return base > 0 && t > 0 ? (Math.round(base * t) / 100).toFixed(2) : "";
  };
  const receptorNombre = modo === "G" ? "PÚBLICO EN GENERAL" : cliente?.nombre ?? nuevo?.nombre ?? "";
  const ticketProps = { emisor, preview, moneda, receptorNombre, resultado, listo, timbrando, enviar, setEnviar, timbrar, guardarPlantilla, reiniciar, irA, aplicarSugerencia, nConceptos };

  return (
    <div className="@container">
      <div className="grid gap-6 @min-[940px]:grid-cols-[minmax(0,1fr)_300px] @min-[1100px]:grid-cols-[minmax(0,1fr)_330px]">
        <div className="flex min-w-0 flex-col gap-5">
          {emisor.modo_demo && (
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-alerta-suave px-4 py-2.5 text-sm text-alerta">
              <FlaskConical className="size-4 shrink-0" /> <b>Modo demo:</b> {emisor.rfc} no tiene PAC asignado. Lo que timbres aquí es de práctica, no llega al SAT ni tiene validez fiscal.
              <a href="/ajustes/" className="font-medium underline">Dar de alta mi PAC</a>
            </p>
          )}
          {resultado && <div className="@min-[940px]:hidden"><Resultado f={resultado} reiniciar={reiniciar} /></div>}

          {/* Tipo de comprobante + plantillas */}
          <div className="flex flex-wrap items-center gap-2">
            <div role="tablist" aria-label="Tipo de comprobante" className="-mx-1 flex max-w-full gap-1.5 overflow-x-auto px-1 pb-1">
              {MODOS.map((m, i) => (!cfg || cfg.modos.includes(m.id)) && (
                <button
                  key={m.id}
                  role="tab"
                  aria-selected={modo === m.id}
                  title={`Alt + ${i + 1}`}
                  onClick={() => setModo(m.id)}
                  className={cx("shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition-colors", modo === m.id ? "bg-tinta text-white" : "border border-linea bg-hoja text-grafito hover:text-tinta")}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <Button size="sm" variant="fantasma" onClick={() => setConfigurar(true)} title="Configurar la barra: nivel, campos, valores por defecto y perfiles" className="@min-[640px]:order-last">
              <Settings2 className="size-4" /> <span className="hidden @min-[480px]:inline">{cfg ? { simple: "Simple", estandar: "Estándar", completo: "Completo" }[cfg.nivel] : "Configurar"}</span>
            </Button>
            {plantillas.length > 0 && vis.plantillas && (
              <Select ref={plantillaRef} value="" onChange={(e) => e.target.value && usarPlantilla(Number(e.target.value))} className="w-full @min-[640px]:ml-auto @min-[640px]:w-60" aria-label="Usar plantilla (Alt+P)">
                <option value="">Usar plantilla… (Alt+P)</option>
                {plantillas.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
              </Select>
            )}
          </div>

          {/* Perfiles rápidos */}
          {!!cfg?.perfiles.length && (
            <div className="-mt-2 flex flex-wrap gap-1.5" aria-label="Perfiles rápidos">
              {cfg.perfiles.map((p) => (
                <button key={p.id} onClick={() => aplicarPerfil(p)} className="inline-flex items-center gap-1.5 rounded-full bg-hoja px-3 py-1.5 text-sm ring-1 ring-linea transition hover:ring-tinta/40">
                  <Zap className="size-3.5 text-grafito" /> {p.nombre}
                </button>
              ))}
            </div>
          )}

          {/* Receptor */}
          {modo !== "G" ? (
            <section className="rounded-2xl bg-hoja p-4 shadow-sm ring-1 ring-linea sm:p-5">
              <h2 className="mb-3 flex items-center gap-2 font-semibold">¿A quién le facturas?
                <Button size="sm" variant="fantasma" className="ml-auto font-normal" onClick={() => setVerClientes(true)} title="Ver la lista de clientes guardados (Alt+G)"><BookUser className="size-4" /> Clientes</Button>
                <span className="hidden text-xs font-normal text-grafito @min-[480px]:inline"><Kbd>Alt + C</Kbd></span></h2>
              <BuscarCliente
                ref={clienteRef}
                emisorId={emisor.id}
                cliente={cliente}
                onCliente={(c) => { setCliente(c); setNuevo(null); if (c) setFoco([0, 0]); }}
                onNuevo={(rfc, nombre) => { setCliente(null); setNuevo({ ...receptorVacio, rfc, nombre }); }}
              />
              {nuevo && !cliente && <FormNuevoReceptor nuevo={nuevo} setNuevo={setNuevo} />}
              {ultima && conceptos.every(vacio) && (
                <button onClick={repetirUltima} className="mt-3 flex w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-cobalto-suave px-4 py-2.5 text-left text-sm text-cobalto hover:underline">
                  <Repeat className="size-4" /> Repetir la última: {ultima.folio} · {dinero(ultima.total)} · {ultima.payload.conceptos?.[0]?.descripcion ?? ""}
                  <span className="ml-auto"><Kbd>Alt + U</Kbd></span>
                </button>
              )}
            </section>
          ) : (
            <p className="rounded-xl bg-cobalto-suave px-4 py-3 text-sm text-cobalto">
              Factura global a XAXX010101000 · régimen 616 · uso S01 · periodo {global.periodicidad === "04" ? "mensual" : "según opciones avanzadas"} {global.meses}/{global.ano}.
            </p>
          )}

          {/* Pago */}
          {modo !== "T" && vis.pago && (
            <section className="grid gap-4 rounded-2xl bg-hoja p-4 shadow-sm ring-1 ring-linea sm:p-5 @min-[560px]:grid-cols-2 @min-[820px]:grid-cols-3">
              <Field label="Método de pago (Alt+M)">
                <div className="flex rounded-lg border border-linea p-0.5" data-campo="metodo_pago" role="radiogroup">
                  {["PUE", "PPD"].map((m) => (
                    <button key={m} role="radio" aria-checked={metodo === m} onClick={() => setMetodo(m)} className={cx("h-9 flex-1 whitespace-nowrap rounded-md px-2 text-sm font-medium", metodo === m ? "bg-tinta text-white" : "text-grafito")}>
                      {m === "PUE" ? "Una exhibición" : "Parcialidades"}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="Forma de pago" hint={metodo === "PPD" ? "En PPD va 99 (Por definir), se pone solo" : undefined}>
                <CatSelect catalogo="forma_pago" data-campo="forma_pago" value={metodo === "PPD" ? "99" : forma} onChange={setForma} disabled={metodo === "PPD"} filtro={(c) => metodo === "PPD" || c.clave !== "99"} />
              </Field>
              {vis.moneda && <Field label="Moneda">
                <div className="flex gap-2">
                  <Select value={moneda} onChange={(e) => setMoneda(e.target.value)} className="w-24 shrink-0" aria-label="Moneda">
                    {["MXN", "USD", "EUR"].map((m) => <option key={m}>{m}</option>)}
                  </Select>
                  {moneda !== "MXN" && <Input data-campo="tipo_cambio" placeholder="Tipo de cambio" value={tc} onChange={(e) => setTc(e.target.value)} inputMode="decimal" />}
                </div>
              </Field>}
            </section>
          )}

          {/* Conceptos */}
          <section className="@container rounded-2xl bg-hoja p-3 shadow-sm ring-1 ring-linea sm:p-5">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 px-1">
              <h2 className="flex items-center gap-2 font-semibold">Conceptos <span className="font-normal text-grafito">({nConceptos})</span>
                <Button size="sm" variant="fantasma" className="font-normal" onClick={() => setVerConceptos(true)} title="Elegir de tu catálogo o de lo que ya facturaste (Alt+I)"><List className="size-4" /> Mis conceptos</Button></h2>
              <p className="hidden text-xs text-grafito @min-[560px]:block">
                <Kbd>Enter</Kbd> avanza y crea fila · <Kbd>↑↓</Kbd> filas · <Kbd>Ctrl+D</Kbd> duplica · <Kbd>Ctrl+Supr</Kbd> borra
              </p>
            </div>
            <div
              className="flex flex-col gap-3"
              onKeyDown={(e) => {
                if (e.defaultPrevented) return;
                const el = e.target as HTMLElement;
                const cell = el.dataset.cell;
                if (!cell) return;
                const [r, c] = cell.split("-").map(Number);
                const ctrl = e.ctrlKey || e.metaKey;
                if (ctrl && e.key.toLowerCase() === "d") { e.preventDefault(); duplicar(r); setFoco([r + 1, c]); return; }
                if (ctrl && e.key === "Delete") { e.preventDefault(); borrar(r); setFoco([Math.max(0, r - 1), c]); return; }
                if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
                  e.preventDefault();
                  const d = e.key === "ArrowUp" ? -1 : 1;
                  mover(r, d);
                  setFoco([Math.min(Math.max(r + d, 0), conceptos.length - 1), c]);
                  return;
                }
                if (e.key === "Enter" && !ctrl && !e.altKey) {
                  e.preventDefault();
                  if (e.shiftKey) {
                    if (c > 0) setFoco([r, c - 1]);
                    else if (r > 0) setFoco([r - 1, 5]);
                    return;
                  }
                  const fila = conceptos[r];
                  const orden = [0, 1, 2, ...(fila.clave_prod_serv ? [] : [3]), ...(fila.clave_unidad ? [] : [4])];
                  const sig = orden.find((x) => x > c);
                  if (sig !== undefined) return setFoco([r, sig]);
                  if (r < conceptos.length - 1) return setFoco([r + 1, 0]);
                  if (fila.descripcion.trim() && fila.valor_unitario.trim()) return agregar();
                  const falta = !fila.descripcion.trim() ? 0 : 2;
                  return setFoco([r, falta]);
                }
                if ((e.key === "ArrowDown" || e.key === "ArrowUp") && el.tagName !== "SELECT") {
                  e.preventDefault();
                  const nr = r + (e.key === "ArrowDown" ? 1 : -1);
                  if (nr >= 0 && nr < conceptos.length) setFoco([nr, c]);
                }
              }}
            >
              {conceptos.map((c, i) => (
                <FilaConcepto
                  key={c.key}
                  i={i}
                  total={conceptos.length}
                  c={c}
                  emisorId={emisor.id}
                  tipo={modo}
                  onChange={(p) => upd(i, p)}
                  onDuplicar={() => { duplicar(i); setFoco([i + 1, 0]); }}
                  onBorrar={() => borrar(i)}
                  onMover={(d) => mover(i, d)}
                  onElegido={() => setFoco([i, 1])}
                  frontera={frontera}
                  vis={vis}
                  terceros={terceros}
                />
              ))}
            </div>
            <button onClick={() => agregar()} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-linea py-3 text-sm font-medium text-grafito hover:border-cobalto hover:text-cobalto">
              <Plus className="size-4" /> Agregar concepto <span className="hidden sm:inline"><Kbd>Alt + A</Kbd></span>
            </button>
          </section>

          {/* Addenda del cliente */}
          {addenda && (
            <section className="rounded-2xl bg-hoja p-4 shadow-sm ring-1 ring-linea sm:p-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h2 className="font-semibold">Addenda</h2>
                <Badge tono="cobalto">{addenda.nombre}</Badge>
              </div>
              <div className="grid gap-3 @min-[560px]:grid-cols-2">
                {addenda.campos.map((f) => (
                  <Field key={f.name} label={f.label + (f.required ? "" : " (opcional)")}>
                    <Input data-campo="addenda" value={addendaDatos[f.name] ?? ""} onChange={(e) => setAddendaDatos({ ...addendaDatos, [f.name]: e.target.value })} />
                  </Field>
                ))}
              </div>
            </section>
          )}

          {/* Avanzado */}
          {(modo === "G" || modo === "E" || vis.relacionados || vis.condiciones || vis.addenda || vis.locales) && (
          <section className="rounded-2xl bg-hoja shadow-sm ring-1 ring-linea">
            <button onClick={() => setAvanzado((a) => !a)} aria-expanded={avanzado} className="flex w-full items-center justify-between gap-2 px-4 py-4 text-left font-semibold sm:px-5">
              <span>Opciones avanzadas <span className="hidden text-xs font-normal text-grafito sm:inline">(Alt+O)</span></span>
              <ChevronDown className={cx("size-5 transition-transform", avanzado && "rotate-180")} />
            </button>
            {avanzado && (
              <div className="grid gap-4 border-t border-linea p-4 sm:p-5 @min-[640px]:grid-cols-2">
                {modo === "G" && (
                  <Field label="Periodo de la factura global" className="@min-[640px]:col-span-2">
                    <div className="grid gap-2 @min-[480px]:grid-cols-3" data-campo="global">
                      <CatSelect catalogo="periodicidad" value={global.periodicidad} onChange={(v) => setGlobal({ ...global, periodicidad: v })} aria-label="Periodicidad" />
                      <CatSelect catalogo="meses" value={global.meses} onChange={(v) => setGlobal({ ...global, meses: v })} aria-label="Meses" />
                      <Input value={global.ano} onChange={(e) => setGlobal({ ...global, ano: e.target.value })} inputMode="numeric" aria-label="Año" />
                    </div>
                  </Field>
                )}
                {(vis.relacionados || modo === "E" || !!relUuids) && <Field label="CFDI relacionados" hint="UUIDs separados por coma o espacio">
                  <div className="flex flex-col gap-2 @min-[480px]:flex-row">
                    <CatSelect catalogo="tipo_relacion" value={relTipo} onChange={setRelTipo} className="@min-[480px]:w-44" aria-label="Tipo de relación" />
                    <Input data-campo="relacionados" value={relUuids} onChange={(e) => setRelUuids(e.target.value)} placeholder="UUID…" />
                  </div>
                </Field>}
                {(vis.condiciones || !!condiciones) && <Field label="Condiciones de pago">
                  <Input value={condiciones} onChange={(e) => setCondiciones(e.target.value)} placeholder="Crédito 30 días" />
                </Field>}
                {(vis.addenda || !!addendaId) && <Field label="Addenda">
                  <Select value={addendaId ?? ""} onChange={(e) => setAddendaId(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Sin addenda</option>
                    {addendas.map((a) => <option key={a.id} value={a.id}>{a.nombre}</option>)}
                  </Select>
                </Field>}
                {(vis.locales || locales.length > 0) && <div className="flex min-w-0 flex-col gap-1.5 @min-[640px]:col-span-2">
                  <span className="text-[13px] font-medium text-grafito">Impuestos locales (estatales)</span>
                  <div className="flex flex-col gap-2">
                    {locales.map((l, i) => {
                      const conocido = LOCALES.find((x) => x.nombre === l.nombre);
                      const set = (p: Partial<typeof l>) => setLocales(locales.map((x, j) => (j === i ? { ...x, ...p } : x)));
                      return (
                        <div key={i} className="flex flex-wrap items-end gap-2">
                          <label className="flex min-w-44 flex-1 flex-col gap-1"><span className="text-[11px] font-medium text-grafito">Impuesto</span>
                            <Select value={conocido ? l.nombre : "otro"} onChange={(e) => {
                              const x = LOCALES.find((y) => y.nombre === e.target.value);
                              if (!x) return set({ nombre: "" });
                              const tasa = x.nombre === "ISH" ? ishDe(emisor.lugar_expedicion) : x.tasa;
                              set({ nombre: x.nombre, tipo: x.tipo, tasa, importe: importeLocal(tasa) });
                            }}>
                              {LOCALES.map((x) => <option key={x.nombre} value={x.nombre}>{x.label}</option>)}
                              <option value="otro">Otro (escribir nombre)…</option>
                            </Select>
                          </label>
                          {!conocido && <label className="flex min-w-36 flex-1 flex-col gap-1"><span className="text-[11px] font-medium text-grafito">Nombre</span>
                            <Input placeholder="Como lo pide tu estado" value={l.nombre} onChange={(e) => set({ nombre: e.target.value })} /></label>}
                          <label className="flex w-32 flex-col gap-1"><span className="text-[11px] font-medium text-grafito">Tipo</span>
                            <Select value={l.tipo} onChange={(e) => set({ tipo: e.target.value as "traslado" })} aria-label="Tipo">
                              <option value="traslado">Se cobra</option>
                              <option value="retencion">Se retiene</option>
                            </Select></label>
                          <label className="flex w-20 flex-col gap-1"><span className="text-[11px] font-medium text-grafito">Tasa %</span>
                            <Input value={l.tasa} inputMode="decimal" onChange={(e) => set({ tasa: e.target.value })} onBlur={() => { if (!l.importe) set({ importe: importeLocal(l.tasa) }); }} /></label>
                          <label className="flex w-28 flex-col gap-1"><span className="text-[11px] font-medium text-grafito">Importe $</span>
                            <Input value={l.importe} inputMode="decimal" placeholder="0.00" onChange={(e) => set({ importe: e.target.value })} /></label>
                          <button onClick={() => set({ importe: importeLocal(l.tasa) })} title="Recalcular importe = subtotal × tasa" aria-label="Recalcular importe" className="rounded-md p-2.5 text-grafito hover:bg-tinta/5 hover:text-tinta"><Calculator className="size-4" /></button>
                          <button onClick={() => setLocales(locales.filter((_, j) => j !== i))} aria-label="Quitar" className="rounded-md p-2.5 text-grafito hover:bg-rojo-suave hover:text-rojo"><Trash2 className="size-4" /></button>
                        </div>
                      );
                    })}
                    <Button size="sm" variant="fantasma" className="self-start" disabled={locales.length >= 2} onClick={() => {
                      const tasa = ishDe(emisor.lugar_expedicion);
                      setLocales([...locales, locales.some((x) => x.tipo === "traslado")
                        ? { tipo: "retencion", nombre: "5 al millar", tasa: "0.5", importe: importeLocal("0.5") }
                        : { tipo: "traslado", nombre: "ISH", tasa, importe: importeLocal(tasa) }]);
                    }}>
                      <Plus className="size-4" /> Impuesto local
                    </Button>
                    <span className="text-xs text-grafito/80">La tasa la fija cada estado: confirma la del tuyo. Máximo uno que se cobra y uno que se retiene por factura.</span>
                  </div>
                </div>}
              </div>
            )}
          </section>
          )}

          {/* Barra inferior (pantallas angostas) */}
          <div className="sticky bottom-3 z-20 @min-[940px]:hidden">
            <BarraMovil {...ticketProps} />
          </div>
        </div>

        <ListaClientes emisorId={emisor.id} abierto={verClientes} cerrar={() => setVerClientes(false)}
          onElegir={(c) => { if (modo === "G") setModo("I"); setCliente(c); setNuevo(null); setFoco([0, 0]); }} />
        <ListaConceptos emisorId={emisor.id} abierto={verConceptos} cerrar={() => setVerConceptos(false)}
          onElegir={(c) => setConceptos((cs) => {
            const i = cs.findIndex(vacio);
            setFoco([i >= 0 ? i : cs.length, 1]);
            return i >= 0 ? cs.map((x, j) => (j === i ? { ...x, ...c } : x)) : [...cs, { ...nuevoConcepto(), ...c }];
          })} />
        <ConfigFacturarModal emisorId={emisor.id} abierto={configurar} cerrar={() => setConfigurar(false)} actual={cfg} onGuardado={(c) => mutCfg(c, false)} />

        {/* Ticket lateral (pantallas anchas) */}
        <aside className="hidden @min-[940px]:block @min-[940px]:sticky @min-[940px]:top-8 @min-[940px]:self-start">
          <Ticket {...ticketProps} />
        </aside>
      </div>
    </div>
  );
}

// ======================= Receptor =======================


const BuscarCliente = forwardRef<HTMLInputElement, { emisorId: number; cliente: Cliente | null; onCliente: (c: Cliente | null) => void; onNuevo: (rfc: string, nombre: string) => void }>(
  function BuscarCliente({ emisorId, cliente, onCliente, onNuevo }, ref) {
    const [q, setQ] = useState("");
    const [open, setOpen] = useState(false);
    const [act, setAct] = useState(0);
    const { data = [] } = useSWR<Cliente[]>(q.length >= 2 ? `/clientes?emisor_id=${emisorId}&q=${encodeURIComponent(q)}&limit=8` : null, fetcher);
    const rfcTecleado = RFC_RE.test(q.toUpperCase().trim()) ? q.toUpperCase().trim() : "";
    const opciones = data.length + 1; // + "nuevo receptor"
    useEffect(() => setAct(0), [q]);

    const elegir = (i: number) => {
      if (i < data.length) onCliente(data[i]);
      else onNuevo(rfcTecleado, rfcTecleado ? "" : q.trim().toUpperCase()); // lo que ya escribiste pasa al formulario
      setOpen(false);
      setQ("");
    };

    if (cliente)
      return (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-papel px-4 py-3">
          <div className="min-w-0">
            <p className="break-words font-medium">{cliente.nombre}</p>
            <p className="text-sm text-grafito tabular-nums">
              {cliente.rfc} · CP {cliente.codigo_postal} · Régimen {cliente.regimen_fiscal} · Uso {cliente.uso_cfdi}
            </p>
          </div>
          <Button size="sm" variant="fantasma" onClick={() => onCliente(null)}>Cambiar</Button>
        </div>
      );

    return (
      <div className="relative">
        <Input
          ref={ref}
          data-campo="receptor"
          value={q}
          role="combobox"
          aria-expanded={open && q.length >= 2}
          autoComplete="off"
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (!open || q.length < 2) return;
            if (e.key === "ArrowDown") { e.preventDefault(); setAct((a) => Math.min(a + 1, opciones - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setAct((a) => Math.max(a - 1, 0)); }
            if (e.key === "Enter") { e.preventDefault(); elegir(act); }
            if (e.key === "Escape") { e.stopPropagation(); setOpen(false); }
          }}
          placeholder="RFC o nombre del cliente"
          className="h-12 text-base"
        />
        {open && q.length >= 2 && (
          <ul role="listbox" className="absolute z-30 mt-1 w-full rounded-xl border border-linea bg-hoja p-1 shadow-xl">
            {data.map((c, i) => (
              <li key={c.id} role="option" aria-selected={i === act}>
                <button tabIndex={-1} onMouseDown={() => elegir(i)} onMouseEnter={() => setAct(i)} className={cx("flex w-full flex-wrap justify-between gap-x-3 rounded-lg px-3 py-2 text-left text-sm", i === act && "bg-cobalto-suave")}>
                  <span className="min-w-0 font-medium">{c.nombre}</span>
                  <span className="text-grafito tabular-nums">{c.rfc}</span>
                </button>
              </li>
            ))}
            <li role="option" aria-selected={act === data.length}>
              <button tabIndex={-1} onMouseDown={() => elegir(data.length)} onMouseEnter={() => setAct(data.length)} className={cx("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-cobalto", act === data.length && "bg-cobalto-suave")}>
                <Plus className="size-4 shrink-0" /> Nuevo receptor{rfcTecleado ? ` con RFC ${rfcTecleado}` : q.trim().length >= 2 ? ` «${q.trim().toUpperCase()}»` : ""}
              </button>
            </li>
          </ul>
        )}
      </div>
    );
  },
);

function FormNuevoReceptor({ nuevo, setNuevo }: { nuevo: NuevoReceptor; setNuevo: (n: NuevoReceptor) => void }) {
  const regimenMal = nuevo.regimen_fiscal && !regimenPermitido(nuevo.regimen_fiscal, nuevo.rfc);
  return (
    <div className="mt-4 grid gap-3 @min-[480px]:grid-cols-2">
      <Field label="RFC" error={nuevo.rfc && !RFC_RE.test(nuevo.rfc) ? "Formato de RFC inválido" : undefined}>
        <Input data-campo="receptor" autoFocus value={nuevo.rfc} placeholder={nuevo.nombre ? "RFC de " + nuevo.nombre : undefined} onChange={(e) => setNuevo({ ...nuevo, rfc: e.target.value.toUpperCase().trim() })} />
      </Field>
      <Field label="Código postal fiscal">
        <Input value={nuevo.codigo_postal} maxLength={5} inputMode="numeric" onChange={(e) => setNuevo({ ...nuevo, codigo_postal: e.target.value.replace(/\D/g, "") })} />
      </Field>
      <Field label="Nombre o razón social (como en la constancia, sin SA de CV)" className="@min-[480px]:col-span-2">
        <Input value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value.toUpperCase() })} />
      </Field>
      <Field label="Régimen fiscal" error={regimenMal ? `No aplica a persona ${nuevo.rfc.length === 12 ? "moral" : "física"}` : undefined}>
        <CatSelect catalogo="regimen_fiscal" value={nuevo.regimen_fiscal} onChange={(v) => setNuevo({ ...nuevo, regimen_fiscal: v, uso_cfdi: usoSugerido(v, nuevo.uso_cfdi) })} />
      </Field>
      <Field label="Uso del CFDI" hint={nuevo.regimen_fiscal ? "Sólo se muestran los usos válidos para su régimen" : undefined}>
        <CatSelect catalogo="uso_cfdi" value={nuevo.uso_cfdi} onChange={(v) => setNuevo({ ...nuevo, uso_cfdi: v })} filtro={(c) => usoPermitido(c.clave, nuevo.regimen_fiscal) && c.clave !== "CN01" && c.clave !== "CP01"} />
      </Field>
    </div>
  );
}

// ======================= Conceptos =======================

const COLS: Record<string, string> = {
  "11": "@min-[560px]:grid-cols-[72px_minmax(96px,130px)_minmax(96px,120px)_76px_minmax(130px,1fr)]",
  "10": "@min-[560px]:grid-cols-[72px_minmax(96px,130px)_minmax(96px,120px)_minmax(130px,1fr)]",
  "01": "@min-[560px]:grid-cols-[72px_minmax(96px,130px)_76px_minmax(130px,1fr)]",
  "00": "@min-[560px]:grid-cols-[72px_minmax(110px,160px)_minmax(160px,1fr)]",
};

function FilaConcepto({ i, total, c, emisorId, tipo, onChange, onDuplicar, onBorrar, onMover, onElegido, frontera, vis, terceros }: {
  i: number; total: number; c: Concepto; emisorId: number; tipo: Modo; frontera?: boolean;
  vis: Record<CampoFacturar, boolean>; terceros: Tercero[];
  onChange: (p: Partial<Concepto>) => void; onDuplicar: () => void; onBorrar: () => void; onMover: (d: number) => void; onElegido: () => void;
}) {
  const [sug, setSug] = useState(false);
  const [act, setAct] = useState(-1);
  const [calc, setCalc] = useState(false);
  const [editarImp, setEditarImp] = useState(false);
  const { data: sugs } = useSWR<Sugerencias>(sug && c.descripcion.trim().length >= 2 && !c.producto_id ? `/productos/sugerencias?emisor_id=${emisorId}&q=${encodeURIComponent(c.descripcion.trim())}${vis.clave_sat ? "" : "&sat=false"}` : null, fetcher, { keepPreviousData: true });
  // Primero tu catálogo, luego lo que ya facturaste y al final el catálogo completo del SAT (sólo pone la clave)
  const opciones = useMemo(() => [
    ...(sugs?.productos ?? []).map((p) => ({ k: `p${p.id}`, grupo: "Mi catálogo", texto: p.descripcion, dato: Number(p.precio) ? dinero(p.precio) : p.clave_prod_serv, patch: deProducto(p, c.valor_unitario) })),
    ...(sugs?.facturados ?? []).map((f) => ({ k: `f${f.descripcion}${f.clave_prod_serv}`, grupo: "Ya facturado", texto: f.descripcion, dato: Number(f.valor_unitario) ? dinero(f.valor_unitario) : f.clave_prod_serv, patch: deFacturado(f, c.valor_unitario) })),
    ...(sugs?.sat ?? []).map((x) => ({ k: `s${x.clave}`, grupo: "Catálogo del SAT · pone descripción y clave", texto: x.descripcion, dato: x.clave, patch: { descripcion: x.descripcion, clave_prod_serv: x.clave, producto_id: null } as Partial<Concepto> })),
  ], [sugs, c.valor_unitario]);
  const abierto = sug && opciones.length > 0 && c.descripcion.trim().length >= 2 && !c.producto_id;
  useEffect(() => setAct(-1), [c.descripcion]);
  const cant = Number(evaluarMonto(c.cantidad) || 0);
  const pu = Number(evaluarMonto(c.valor_unitario) || 0);
  const importe = cant * pu - Number(evaluarMonto(c.descuento ?? "") || 0);

  const usarOpcion = (o: (typeof opciones)[number]) => {
    onChange(o.patch);
    setSug(false);
    onElegido();
  };
  const resolver = (campo: "cantidad" | "valor_unitario" | "descuento") => {
    const v = evaluarMonto((c[campo] as string) ?? "");
    if (v !== null && v !== c[campo]) onChange({ [campo]: v } as Partial<Concepto>);
  };
  const etiqueta = "text-[11px] font-medium text-grafito";
  // Se muestra si la configuración lo pide o si falta (nunca se esconde algo que hay que corregir)
  const verClave = vis.clave_sat || !c.clave_prod_serv;
  const verUnidad = vis.unidad || !c.clave_unidad;
  const extras = vis.terceros || vis.predial || vis.aduana || !!c.a_cuenta_terceros || !!c.cuenta_predial || !!c.informacion_aduanera?.length;

  return (
    <div className="rounded-xl border border-linea p-3 focus-within:border-cobalto/50 focus-within:shadow-[0_0_0_3px_rgba(36,70,216,.08)]">
      <div className="flex items-start gap-2">
        <span className="mt-6 grid size-6 shrink-0 place-items-center rounded-full bg-papel text-xs font-semibold text-grafito">{i + 1}</span>
        <label className="relative flex min-w-0 flex-1 flex-col gap-1">
          <span className={etiqueta}>Descripción</span>
          <Input
            data-cell={`${i}-0`}
            data-campo={`conceptos.${i + 1}`}
            value={c.descripcion}
            placeholder="Escribe: sale tu catálogo y el del SAT…"
            autoComplete="off"
            role="combobox"
            aria-expanded={abierto}
            onChange={(e) => { onChange({ descripcion: e.target.value, producto_id: null }); setSug(true); }}
            onFocus={() => setSug(true)}
            onBlur={() => setTimeout(() => setSug(false), 150)}
            onKeyDown={(e) => {
              if (!abierto) return;
              if (e.key === "ArrowDown") { e.preventDefault(); setAct((a) => Math.min(a + 1, opciones.length - 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setAct((a) => Math.max(a - 1, -1)); }
              else if (e.key === "Enter" && !e.ctrlKey && act >= 0 && opciones[act]) { e.preventDefault(); usarOpcion(opciones[act]); }
              else if (e.key === "Enter") setSug(false); // sin elegir: se queda lo que escribiste y Enter avanza de campo
              else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setSug(false); }
            }}
          />
          {abierto && (
            <ul role="listbox" className="absolute top-full z-30 mt-1 max-h-64 w-full overflow-auto rounded-xl border border-linea bg-hoja p-1 shadow-xl">
              {opciones.map((o, j) => (
                <li key={o.k} role="option" aria-selected={j === act}>
                  {(j === 0 || opciones[j - 1].grupo !== o.grupo) && <p className="px-3 pb-0.5 pt-2 text-[10px] font-medium uppercase tracking-[.08em] text-grafito/70">{o.grupo}</p>}
                  <button tabIndex={-1} onMouseDown={() => usarOpcion(o)} onMouseEnter={() => setAct(j)} className={cx("flex w-full justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm", j === act && "bg-cobalto-suave")}>
                    <span className="min-w-0">{o.texto}</span>
                    <span className="shrink-0 tabular-nums text-grafito">{o.dato}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </label>
        <div className="hidden w-28 shrink-0 flex-col items-end gap-1 @min-[560px]:flex">
          <span className={etiqueta}>Importe</span>
          <span className="flex h-10 items-center font-semibold tabular-nums">{dinero(importe)}</span>
        </div>
        <div className="mt-5 shrink-0">
          <Menu
            label={`Acciones del concepto ${i + 1}`}
            items={[
              { label: "Calcular precio desde con IVA o depositado (F4)", icon: <Calculator className="size-4" />, onClick: () => setCalc(true), oculto: tipo === "T" },
              { label: "Duplicar (Ctrl+D)", icon: <Copy className="size-4" />, onClick: onDuplicar },
              { label: c.ver_descuento ? "Quitar descuento" : "Agregar descuento", icon: <Percent className="size-4" />, onClick: () => onChange({ ver_descuento: !c.ver_descuento, descuento: "" }), oculto: !vis.descuento && !c.ver_descuento },
              { label: c.ver_extra ? "Ocultar terceros / predial / pedimento" : "A cuenta de terceros, predial o pedimento", icon: <Users className="size-4" />, onClick: () => onChange({ ver_extra: !c.ver_extra }), oculto: !extras && !(vis.terceros || vis.predial || vis.aduana) },
              { label: "Subir (Alt+↑)", icon: <ArrowUp className="size-4" />, onClick: () => onMover(-1), oculto: i === 0 },
              { label: "Bajar (Alt+↓)", icon: <ArrowDown className="size-4" />, onClick: () => onMover(1), oculto: i === total - 1 },
              { label: "Borrar (Ctrl+Supr)", icon: <Trash2 className="size-4" />, onClick: onBorrar, peligro: true },
            ]}
          />
          <CalcPrecio abierto={calc} cerrar={() => setCalc(false)} impuestos={c.impuestos} cantidad={cant || 1}
            onUsar={(u) => onChange({ valor_unitario: u })} />
          <EditorImpuestos abierto={editarImp} cerrar={() => setEditarImp(false)} impuestos={c.impuestos}
            onUsar={(imps) => onChange({ impuestos: imps, objeto_imp: imps.length ? "02" : "01" })} />
        </div>
      </div>
      <div className={cx("mt-2 grid grid-cols-2 gap-2 pl-0 @min-[560px]:pl-8", COLS[`${verClave ? 1 : 0}${verUnidad ? 1 : 0}`])}>
        <label className="flex min-w-0 flex-col gap-1">
          <span className={etiqueta}>Cantidad</span>
          <Input data-cell={`${i}-1`} value={c.cantidad} inputMode="decimal" onChange={(e) => onChange({ cantidad: e.target.value })} onBlur={() => resolver("cantidad")} />
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className={etiqueta}>Precio unitario</span>
          <Input data-cell={`${i}-2`} value={c.valor_unitario} inputMode="decimal" placeholder={tipo === "T" ? "0" : "0.00 ó =1160/1.16"} onChange={(e) => onChange({ valor_unitario: e.target.value })} onBlur={() => resolver("valor_unitario")}
            onKeyDown={(e) => { if (e.key === "F4") { e.preventDefault(); setCalc(true); } if (e.key === "Enter") resolver("valor_unitario"); }} />
        </label>
        {verClave && <label className="flex min-w-0 flex-col gap-1">
          <span className={etiqueta}>Clave SAT</span>
          <ClaveSearch tipo="prod_serv" value={c.clave_prod_serv} placeholder="84111500" inputProps={{ "data-cell": `${i}-3` }} onChange={(clave) => onChange({ clave_prod_serv: clave })} />
        </label>}
        {verUnidad && <label className="flex min-w-0 flex-col gap-1">
          <span className={etiqueta}>Unidad</span>
          <ClaveSearch tipo="unidad" value={c.clave_unidad} inputProps={{ "data-cell": `${i}-4` }} onChange={(clave) => onChange({ clave_unidad: clave })} />
        </label>}
        <label className="col-span-2 flex min-w-0 flex-col gap-1 @min-[560px]:col-span-1">
          <span className={etiqueta}>Impuestos</span>
          <Select
            data-cell={`${i}-5`}
            value={presetDe(c.impuestos)}
            disabled={tipo === "T"}
            onChange={(e) => {
              if (e.target.value === "__editar") return setEditarImp(true);
              const v = PRESETS_IMPUESTOS[e.target.value as keyof typeof PRESETS_IMPUESTOS];
              if (v) onChange({ impuestos: [...v] as Impuesto[], objeto_imp: v.length ? "02" : "01" });
            }}
          >
            <OpcionesImpuestos frontera={frontera} />
            <option value="__editar">Otro impuesto o tasa… (IEPS, cuotas)</option>
          </Select>
        </label>
        {c.ver_descuento && (
          <label className="flex min-w-0 flex-col gap-1">
            <span className={etiqueta}>Descuento $</span>
            <Input data-cell={`${i}-6`} value={c.descuento ?? ""} inputMode="decimal" placeholder="0.00" onChange={(e) => onChange({ descuento: e.target.value })} onBlur={() => resolver("descuento")} />
          </label>
        )}
      </div>
      {(c.ver_extra || (extras && (!!c.a_cuenta_terceros || !!c.cuenta_predial || !!c.informacion_aduanera?.length))) && (
        <ExtrasConcepto c={c} vis={vis} terceros={terceros} onChange={onChange} />
      )}
      <div className="mt-2 flex justify-end text-sm @min-[560px]:hidden">
        <span className="text-grafito">Importe&nbsp;</span>
        <span className="font-semibold tabular-nums">{dinero(importe)}</span>
      </div>
    </div>
  );
}

/** A cuenta de terceros (nodo ACuentaTerceros), cuenta predial y pedimentos de un concepto. */
function ExtrasConcepto({ c, vis, terceros, onChange }: { c: Concepto; vis: Record<CampoFacturar, boolean>; terceros: Tercero[]; onChange: (p: Partial<Concepto>) => void }) {
  const t = c.a_cuenta_terceros;
  const elegido = t ? terceros.find((x) => x.rfc === t.rfc) : undefined;
  const etiqueta = "text-[11px] font-medium text-grafito";
  const setT = (p: Partial<NonNullable<Concepto["a_cuenta_terceros"]>>) =>
    onChange({ a_cuenta_terceros: { rfc: "", nombre: "", regimen_fiscal: "", codigo_postal: "", ...t, ...p } });
  return (
    <div className="mt-3 grid gap-3 rounded-lg bg-papel p-3 @min-[560px]:ml-8">
      {(vis.terceros || t) && (
        <div className="grid gap-2">
          <label className="flex min-w-0 flex-col gap-1">
            <span className={etiqueta}>A cuenta de terceros</span>
            <Select value={t ? (elegido ? String(elegido.id) : "otro") : ""} onChange={(e) => {
              const v = e.target.value;
              if (!v) return onChange({ a_cuenta_terceros: null });
              if (v === "otro") return onChange({ a_cuenta_terceros: { rfc: "", nombre: "", regimen_fiscal: "", codigo_postal: "" } });
              const x = terceros.find((y) => y.id === Number(v));
              if (!x) return;
              api(`/terceros/${x.id}/usado`, { method: "POST" }).catch(() => {});
              const extra = x.concepto ?? {};
              onChange({ a_cuenta_terceros: { rfc: x.rfc, nombre: x.nombre, regimen_fiscal: x.regimen_fiscal, codigo_postal: x.codigo_postal },
                ...(extra.clave_prod_serv && !c.clave_prod_serv ? { clave_prod_serv: extra.clave_prod_serv } : {}),
                ...(extra.descripcion && !c.descripcion ? { descripcion: extra.descripcion } : {}) });
            }}>
              <option value="">No (factura propia)</option>
              {terceros.map((x) => <option key={x.id} value={x.id}>{x.alias || x.nombre}</option>)}
              <option value="otro">Otro… (capturar)</option>
            </Select>
          </label>
          {t && (
            <div className="grid grid-cols-2 gap-2 @min-[560px]:grid-cols-[140px_1fr_76px_90px]">
              <Input placeholder="RFC" value={t.rfc} onChange={(e) => setT({ rfc: e.target.value.toUpperCase().trim() })} aria-label="RFC del tercero" />
              <Input placeholder="Nombre como en su constancia" value={t.nombre} onChange={(e) => setT({ nombre: e.target.value.toUpperCase() })} aria-label="Nombre del tercero" className="col-span-2 @min-[640px]:col-span-1" />
              <Input placeholder="Rég." value={t.regimen_fiscal} maxLength={3} onChange={(e) => setT({ regimen_fiscal: e.target.value.replace(/\D/g, "") })} aria-label="Régimen del tercero" />
              <Input placeholder="CP" value={t.codigo_postal} maxLength={5} inputMode="numeric" onChange={(e) => setT({ codigo_postal: e.target.value.replace(/\D/g, "") })} aria-label="CP del tercero" />
            </div>
          )}
        </div>
      )}
      {(vis.predial || !!c.cuenta_predial) && (
        <label className="flex min-w-0 flex-col gap-1">
          <span className={etiqueta}>Cuenta predial (arrendamiento; varias separadas por coma)</span>
          <Input value={c.cuenta_predial ?? ""} onChange={(e) => onChange({ cuenta_predial: e.target.value.replace(/[^0-9a-zA-Z,]/g, "") })} placeholder="1234567890" />
        </label>
      )}
      {(vis.aduana || !!c.informacion_aduanera?.length) && (
        <label className="flex min-w-0 flex-col gap-1">
          <span className={etiqueta}>Pedimentos (15 dígitos; se acomodan solos al formato SAT)</span>
          <Input value={(c.informacion_aduanera ?? []).join(", ")} placeholder="23 16 3456 1234567"
            onChange={(e) => onChange({ informacion_aduanera: e.target.value.split(",").map((x) => x.trim()).filter((x, k, a) => x || k < a.length - 1) })} />
        </label>
      )}
    </div>
  );
}

// ======================= Ticket / barra / resultado =======================

type TicketProps = {
  emisor: { nombre: string; rfc: string; modo_demo?: boolean };
  preview: Preview | null;
  moneda: string;
  receptorNombre: string;
  resultado: Factura | null;
  listo: boolean;
  timbrando: boolean;
  enviar: boolean;
  setEnviar: (b: boolean) => void;
  timbrar: () => void;
  guardarPlantilla: () => void;
  reiniciar: () => void;
  irA: (campo: string) => void;
  aplicarSugerencia: (v: Val) => void;
  nConceptos: number;
};

function Totales({ preview, moneda }: { preview: Preview | null; moneda: string }) {
  const L = ({ label, v, menos }: { label: string; v?: string; menos?: boolean }) => (
    <div className="flex justify-between gap-3">
      <dt className="text-grafito">{label}</dt>
      <dd className="tabular-nums">{v !== undefined ? (menos ? "−" : "") + dinero(v, moneda) : "—"}</dd>
    </div>
  );
  return (
    <dl className="flex flex-col gap-1.5 text-sm">
      <L label="Subtotal" v={preview?.subtotal} />
      {Number(preview?.descuento) > 0 && <L label="Descuento" v={preview?.descuento} menos />}
      <L label="Impuestos trasladados" v={preview?.traslados} />
      {Number(preview?.retenciones) > 0 && <L label="Retenciones" v={preview?.retenciones} menos />}
    </dl>
  );
}

function Validaciones({ preview, irA, aplicarSugerencia, nConceptos }: { preview: Preview | null; irA: (c: string) => void; aplicarSugerencia: (v: Val) => void; nConceptos: number }) {
  const [verAvisos, setVerAvisos] = useState(false);
  if (!nConceptos) return <p className="text-sm text-grafito">Agrega un concepto para calcular.</p>;
  if (!preview) return <p className="text-sm text-grafito">Revisando reglas del SAT…</p>;
  const { errores, avisos } = preview;
  return (
    <div className="flex flex-col gap-2 text-sm">
      {errores.length === 0 ? (
        <p className="flex items-center gap-2 font-medium text-sello"><CheckCircle2 className="size-4" /> Cumple CFDI 4.0: listo para timbrar</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {errores.slice(0, 6).map((v, i) => (
            <li key={i} className="flex gap-2 text-rojo">
              <XCircle className="mt-0.5 size-4 shrink-0" />
              <span className="min-w-0">
                <button onClick={() => irA(v.campo)} className="text-left hover:underline">{v.mensaje}</button>
                {v.sugerencia && (v.campo.endsWith("uso_cfdi") || v.campo.endsWith("nombre")) && (
                  <button onClick={() => aplicarSugerencia(v)} className="ml-1 font-medium text-cobalto hover:underline">
                    Usar {v.sugerencia.split(",")[0]}
                  </button>
                )}
              </span>
            </li>
          ))}
          {errores.length > 6 && <li className="text-rojo">y {errores.length - 6} más…</li>}
        </ul>
      )}
      {avisos.length > 0 && (
        <div>
          <button onClick={() => setVerAvisos((v) => !v)} className="flex items-center gap-1.5 text-alerta">
            <AlertTriangle className="size-4" /> {avisos.length} {avisos.length === 1 ? "aviso" : "avisos"} {verAvisos ? "▴" : "▾"}
          </button>
          {verAvisos && (
            <ul className="mt-1 flex flex-col gap-1 pl-6 text-alerta">
              {avisos.map((v, i) => (
                <li key={i}>
                  {v.mensaje}
                  {v.sugerencia && v.campo.endsWith("nombre") && (
                    <button onClick={() => aplicarSugerencia(v)} className="ml-1 font-medium text-cobalto hover:underline">Usar «{v.sugerencia}»</button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Acciones({ f }: { f: Factura }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <Button onClick={() => descargar(`/facturas/${f.id}/pdf`, `${f.uuid}.pdf`).catch(mostrarError)}><FileDown className="size-4" /> PDF</Button>
      <Button onClick={() => descargar(`/facturas/${f.id}/xml`, `${f.uuid}.xml`).catch(mostrarError)}><Download className="size-4" /> XML</Button>
      <Button className="col-span-2" onClick={() => api(`/facturas/${f.id}/enviar`, { method: "POST", json: {} }).then(() => toast.success("Enviada")).catch(mostrarError)}>
        <Mail className="size-4" /> Reenviar por correo
      </Button>
    </div>
  );
}

function Sello({ f, className }: { f: Factura; className?: string }) {
  return (
    <div className={cx("pointer-events-none grid size-[5.5rem] animate-sellar place-items-center rounded-full border-[3px] border-sello text-center text-sello", className)}>
      <div>
        <p className="text-[11px] font-bold leading-tight">{f.demo ? "DEMO" : "TIMBRADA"}</p>
        <p className="text-[10px] font-medium">{f.serie}{f.folio}</p>
      </div>
    </div>
  );
}

function Resultado({ f, reiniciar }: { f: Factura; reiniciar: () => void }) {
  return (
    <section className="relative rounded-2xl bg-sello-suave p-4 ring-1 ring-sello/30">
      <Sello f={f} className="absolute right-3 top-3 hidden @min-[480px]:grid" />
      <p className="font-semibold text-sello">Timbrada {f.serie}{f.folio} · {dinero(f.total, f.moneda)}{f.demo ? " · DEMO, sin validez fiscal" : ""}</p>
      <p className="mb-3 break-all text-xs text-sello tabular-nums @min-[480px]:pr-24">UUID {f.uuid}</p>
      <Acciones f={f} />
      <Button variant="primario" className="mt-2 w-full" onClick={reiniciar}><RotateCcw className="size-4" /> Nueva factura (F2)</Button>
    </section>
  );
}

function Ticket(p: TicketProps) {
  const { emisor, preview, moneda, receptorNombre, resultado, listo, timbrando, enviar, setEnviar, timbrar, guardarPlantilla, reiniciar } = p;
  return (
    <div>
      <div className="relative rounded-t-2xl bg-hoja px-5 pb-6 pt-6 shadow-lg ring-1 ring-linea">
        <div className={cx(resultado && "pr-24")}>
          <p className="break-words text-sm text-grafito">{emisor.nombre}</p>
          <p className="text-xs text-grafito/80 tabular-nums">{emisor.rfc}</p>
        </div>
        {resultado && <Sello f={resultado} className="absolute right-3 top-2" />}
        <div className="mt-5"><Totales preview={preview} moneda={moneda} /></div>
        <div className="mt-4 border-t-2 border-dashed border-linea pt-4">
          <p className="text-sm text-grafito">Total</p>
          <p className="break-all text-[40px] font-semibold leading-none tracking-tight tabular-nums">{preview ? dinero(preview.total, moneda) : "—"}</p>
          <p className="mt-2 break-words text-xs text-grafito">{receptorNombre || "Sin receptor"}</p>
        </div>
        {!resultado && <div className="mt-4 border-t border-linea pt-4"><Validaciones {...p} /></div>}
        <div className="mt-5 flex flex-col gap-2">
          {!resultado ? (
            <>
              <Button variant="primario" size="lg" onClick={timbrar} loading={timbrando} disabled={!listo}>Timbrar</Button>
              <label className="flex items-center gap-2 text-sm text-grafito">
                <input type="checkbox" checked={enviar} onChange={(e) => setEnviar(e.target.checked)} className="accent-cobalto" /> Mandar por correo al cliente
              </label>
              <Button variant="fantasma" size="sm" onClick={guardarPlantilla}><BookmarkPlus className="size-4" /> Guardar como plantilla</Button>
              <p className="text-xs text-grafito/80"><Kbd>Ctrl + Enter</Kbd> timbra · <Kbd>F1</Kbd> atajos</p>
              {emisor.modo_demo && <p className="rounded-lg bg-alerta-suave px-3 py-2 text-xs text-alerta">Modo demo: no llega al SAT ni gasta timbres.</p>}
            </>
          ) : (
            <>
              <p className="break-all rounded-lg bg-sello-suave px-3 py-2 text-xs text-sello tabular-nums">UUID {resultado.uuid}</p>
              <Acciones f={resultado} />
              <Button variant="primario" onClick={reiniciar}><RotateCcw className="size-4" /> Nueva factura (F2)</Button>
            </>
          )}
        </div>
      </div>
      <div className="ticket-borde bg-hoja" />
    </div>
  );
}

function BarraMovil(p: TicketProps) {
  const [abierta, setAbierta] = useState(false);
  const { preview, moneda, resultado, listo, timbrando, timbrar, enviar, setEnviar, guardarPlantilla } = p;
  if (resultado) return null;
  const nErr = preview?.errores.length ?? 0;
  return (
    <div className="rounded-2xl bg-hoja shadow-[0_8px_30px_rgba(21,32,51,.22)] ring-1 ring-linea">
      {abierta && (
        <div className="flex max-h-[55dvh] flex-col gap-4 overflow-y-auto border-b border-linea p-4">
          <Totales preview={preview} moneda={moneda} />
          <Validaciones {...p} />
          <label className="flex items-center gap-2 text-sm text-grafito">
            <input type="checkbox" checked={enviar} onChange={(e) => setEnviar(e.target.checked)} className="accent-cobalto" /> Mandar por correo al cliente
          </label>
          <Button variant="fantasma" size="sm" className="self-start" onClick={guardarPlantilla}><BookmarkPlus className="size-4" /> Guardar como plantilla</Button>
        </div>
      )}
      <div className="flex items-center gap-3 p-3">
        <button onClick={() => setAbierta((a) => !a)} aria-expanded={abierta} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          {abierta ? <ChevronDown className="size-5 shrink-0" /> : <ChevronUp className="size-5 shrink-0" />}
          <span className="min-w-0">
            <span className="block truncate text-xl font-semibold leading-tight tabular-nums">{preview ? dinero(preview.total, moneda) : "—"}</span>
            <span className={cx("block truncate text-xs", nErr ? "text-rojo" : preview ? "text-sello" : "text-grafito")}>
              {!p.nConceptos ? "Sin conceptos" : nErr ? `${nErr} por corregir · toca para ver` : preview ? "Listo para timbrar" : "Calculando…"}
            </span>
          </span>
        </button>
        <Button variant="primario" size="lg" onClick={timbrar} loading={timbrando} disabled={!listo} className="px-5">Timbrar</Button>
      </div>
    </div>
  );
}
