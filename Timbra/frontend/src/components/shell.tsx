"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR, { SWRConfig } from "swr";
import { toast } from "sonner";
import {
  AlertTriangle, BadgeDollarSign, Building2, Calculator, CalendarClock, Check, ChevronDown, CloudDownload, FilePlus2, Files, HandCoins, Handshake, Keyboard,
  LayoutDashboard, LayoutTemplate, ListChecks, LogOut, Menu as MenuIcon, Monitor, Moon, Package, Palette, ChevronLeft, ChevronRight, Plug, QrCode,
  ReceiptText, Repeat, ScanSearch, Settings, Stamp, Sun, Table2, Terminal, Users, X, Zap, FolderOpen, Send, Wallet,
} from "lucide-react";
import { api, fetcher, getSoporte, getToken, reportarNavegador, setSoporte, setToken, type Soporte } from "@/lib/api";
import { consola, useConsola } from "@/lib/debug";
import { mostrarError } from "@/lib/errores";
import { tema, useTema } from "@/lib/tema";
import type { TimbresPac } from "@/lib/types";
import { AtajosProvider, useAtajos } from "./atajos";
import { Consola } from "./consola";
import { EmisorProvider, EtiquetaAmbiente, ambienteDe, useEmisor } from "./emisor-context";
import { Badge, Button, Field, Input, Modal, cx } from "./ui";

type Item = { href: string; label: string; icon: typeof Zap; k?: string; cta?: boolean; gratis?: boolean };
// Pendientes ya no va en el menú: si hay algo por atender sale el aviso arriba de la pantalla (y Alt+J sigue abriéndola).
// Orden por uso: primero el tablero y lo de todos los días; luego por tarea. En el riel, un grupo plegado se ve como un solo icono.
const NAV: { id: string; grupo?: string; icon?: typeof Zap; plegado?: boolean; items: Item[] }[] = [
  { id: "diario", items: [
    { href: "/", label: "Resumen", icon: LayoutDashboard },
    { href: "/facturar", label: "Nueva factura", icon: FilePlus2, k: "F2", cta: true },
    { href: "/facturas", label: "Facturas emitidas", icon: Files, k: "Alt F" },
    { href: "/sat", label: "XML del SAT", icon: CloudDownload, gratis: true },
  ] },
  { id: "emitir", grupo: "Emitir", icon: Send, items: [
    { href: "/lotes", label: "Lotes desde tabla", icon: Table2, k: "Alt L" },
    { href: "/recurrentes", label: "Recurrentes", icon: Repeat, k: "Alt R" },
    { href: "/pagos", label: "Pagos (REP)", icon: ReceiptText },
    { href: "/nomina", label: "Nómina", icon: BadgeDollarSign, k: "Alt E" },
    { href: "/portal", label: "Autofactura", icon: QrCode },
  ] },
  { id: "control", grupo: "Cobrar y revisar", icon: Wallet, items: [
    { href: "/cobranza", label: "Cobranza", icon: HandCoins, k: "Alt B" },
    { href: "/calculadora", label: "Calculadora", icon: Calculator },
  ] },
  { id: "catalogos", grupo: "Catálogos", icon: FolderOpen, items: [
    { href: "/clientes", label: "Clientes", icon: Users },
    { href: "/productos", label: "Productos y servicios", icon: Package },
    { href: "/claves", label: "Claves SAT", icon: ScanSearch, k: "Alt K" },
    { href: "/plantillas", label: "Plantillas", icon: LayoutTemplate },
    { href: "/terceros", label: "Terceros", icon: Handshake },
  ] },
  { id: "config", grupo: "Configuración", icon: Settings, plegado: true, items: [
    { href: "/emisores", label: "Emisores y CSD", icon: Building2 },
    { href: "/ajustes", label: "PAC y usuarios", icon: Plug },
    { href: "/timbres", label: "Timbres", icon: Stamp, k: "Alt T" },
    { href: "/marca", label: "Marca y nómina", icon: Palette },
  ] },
];

const activo = (path: string, href: string) => (href === "/" ? path === "/" : path.startsWith(href));
const leer = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const guardar = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch {} };
const iniciales = (s: string) => s.trim().split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join("").toUpperCase() || "?";

type Yo = {
  email: string; usuario?: string | null; nombre: string | null; admin: boolean; creado?: string | null; google_email?: string | null; timbres?: number | null; correo_verificado?: boolean;
  terminos?: { vigente: string; aceptada: string | null; aceptados: string | null; pendiente: boolean };
};

function SelectorEmisor() {
  const { emisores, emisor, setEmisorId } = useEmisor();
  const [abierto, setAbierto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setAbierto(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAbierto(false);
    document.addEventListener("mousedown", fuera);
    window.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fuera); window.removeEventListener("keydown", esc); };
  }, [abierto]);
  if (!emisores.length || !emisor)
    return <Link href="/emisores" className="block truncate rounded-lg bg-cobalto-suave px-3 py-2 text-sm text-cobalto">Da de alta tu primer RFC</Link>;
  const amb = ambienteDe(emisor);
  // En pruebas o demo el selector se pinta de ámbar con su distintivo: el cambio de emisor es global y se olvida fácil
  const prueba = amb === "pruebas" || amb === "demo";
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setAbierto((a) => !a)} aria-label="Emisor activo" aria-haspopup="menu" aria-expanded={abierto} title={`${emisor.rfc} · ${emisor.nombre}${prueba ? " · timbra en pruebas, sin validez fiscal" : ""}`}
        className={cx("flex h-11 w-full min-w-0 items-center gap-2 rounded-lg border px-2.5 text-left transition-[border-color,box-shadow] duration-150 hover:border-acento/50", prueba ? "bg-alerta-suave" : "bg-hoja", abierto ? "border-acento/50 shadow-[0_0_0_3px_var(--color-acento-suave)]" : prueba ? "border-alerta/60" : "border-linea")}>
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[13px] font-medium">{emisor.nombre}</span>
          <span className="flex items-center gap-1.5 text-[11px] tabular-nums text-grafito">{emisor.rfc}<EtiquetaAmbiente ambiente={amb} /></span>
        </span>
        <ChevronDown className={cx("size-4 shrink-0 text-grafito transition-transform duration-150", abierto && "rotate-180")} />
      </button>
      {abierto && (
        <div role="menu" className="absolute left-0 top-full z-[60] mt-1.5 max-h-[60vh] w-72 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl border border-linea bg-hoja p-1.5 shadow-flotante animate-aparecer">
          <p className="px-3 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-[.08em] text-grafito/70">Emisor con el que trabajas</p>
          {emisores.map((e) => (
            <button key={e.id} role="menuitemradio" aria-checked={e.id === emisor.id} onClick={() => { setEmisorId(e.id); setAbierto(false); }}
              className={cx("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors", e.id === emisor.id ? "bg-primario text-sobre-primario" : "hover:bg-tinta/5")}>
              <span className="min-w-0 flex-1"><span className="block truncate font-medium">{e.nombre}</span><span className="block text-[11px] tabular-nums opacity-70">{e.rfc}</span></span>
              <EtiquetaAmbiente ambiente={ambienteDe(e)} />
              {e.id === emisor.id && <Check className="size-4 shrink-0" />}
            </button>
          ))}
          <Link href="/emisores" onClick={() => setAbierto(false)} className="mt-1 block rounded-lg px-3 py-2 text-sm text-grafito hover:bg-tinta/5 hover:text-tinta">Administrar emisores…</Link>
        </div>
      )}
    </div>
  );
}

/** Tema, consola y atajos: fila de iconos (barra abierta) o columna (riel). */
function Utilidades({ riel }: { riel?: boolean }) {
  const t = useTema();
  const { erroresNuevos } = useConsola();
  const { abrirAyuda } = useAtajos();
  const IconTema = t === "oscuro" ? Moon : t === "claro" ? Sun : Monitor;
  const txtTema = t === "oscuro" ? "Oscuro" : t === "claro" ? "Claro" : "Como el sistema";
  const b = "relative grid size-9 place-items-center rounded-lg text-grafito transition-colors hover:bg-tinta/5 hover:text-tinta";
  return (
    <div className={cx("flex items-center gap-1", riel && "justify-center gap-0")}>
      <button onClick={() => tema.siguiente()} title={`Tema: ${txtTema} (Ctrl+Shift+L)`} aria-label={`Tema: ${txtTema}`} className={b}><IconTema className="size-4" /></button>
      <button onClick={() => consola.alternar()} title="Consola de depuración (F9)" aria-label="Consola" className={cx(b, riel && "hidden")}>
        <Terminal className="size-4" />
        {erroresNuevos > 0 && <span className="absolute right-0.5 top-0.5 grid size-4 place-items-center rounded-full bg-rojo text-[10px] text-white">{erroresNuevos > 9 ? "9+" : erroresNuevos}</span>}
      </button>
      <button onClick={abrirAyuda} title="Atajos de teclado (F1)" aria-label="Atajos" className={b}><Keyboard className="size-4" /></button>
      {riel && erroresNuevos > 0 && <button onClick={() => consola.alternar()} title="Hay errores: abrir consola (F9)" aria-label="Consola" className={b}><Terminal className="size-4 text-rojo" /></button>}
    </div>
  );
}

/** Quién está usando Timbra: nombre, correo y rol. Abre "Mi perfil". */
function BotonPerfil({ yo, riel, abrir }: { yo?: Yo; riel?: boolean; abrir: () => void }) {
  const nombre = yo?.nombre || yo?.email || "Mi perfil";
  return (
    <button onClick={abrir} title={riel ? `${nombre} · Mi perfil` : "Mi perfil"} className={cx("flex min-w-0 items-center gap-2.5 rounded-xl p-1.5 text-left transition-colors hover:bg-tinta/5", riel && "justify-center")}>
      <span className={cx("grid shrink-0 place-items-center rounded-full bg-linear-to-br from-acento-suave to-tinta/10 font-semibold text-tinta ring-1 ring-linea", riel ? "size-10 text-xs" : "size-8 text-[11px]")}>{iniciales(nombre)}</span>
      {!riel && (
        <span className="min-w-0 leading-tight">
          <b className="block truncate text-sm font-medium">{nombre}</b>
          <span className="block truncate text-[11px] text-grafito">{yo?.admin ? "Administrador" : "Usuario"}{yo?.nombre ? ` · ${yo.email}` : ""}</span>
        </span>
      )}
    </button>
  );
}

function Perfil({ abierto, cerrar, yo, cambio }: { abierto: boolean; cerrar: () => void; yo?: Yo; cambio: (y: Yo) => void }) {
  const router = useRouter();
  const { emisor, emisores } = useEmisor();
  const t = useTema();
  const [nombre, setNombre] = useState("");
  const [pwd, setPwd] = useState({ actual: "", nueva: "" });
  const [trabajando, setTrabajando] = useState("");
  useEffect(() => { if (abierto) { setNombre(yo?.nombre ?? ""); setPwd({ actual: "", nueva: "" }); } }, [abierto, yo]);
  const guardarNombre = async () => {
    setTrabajando("nombre");
    try { cambio(await api<Yo>("/auth/yo", { method: "PUT", json: { nombre } })); toast.success("Nombre actualizado"); }
    catch (e) { mostrarError(e); } finally { setTrabajando(""); }
  };
  const cambiarPwd = async () => {
    setTrabajando("pwd");
    try { const r = await api<{ token?: string }>("/auth/password", { method: "POST", json: pwd }); if (r.token) setToken(r.token); setPwd({ actual: "", nueva: "" }); toast.success("Contraseña cambiada"); }
    catch (e) { mostrarError(e); } finally { setTrabajando(""); }
  };
  // Conectar Google: después podrás entrar con «Continuar con Google» (y será la base para Drive y Sheets)
  const { data: cfgAuth } = useSWR<{ google: boolean }>("/auth/config", fetcher);
  const googleListo = cfgAuth?.google;  // sin las variables de Google en el servidor no se ofrece conectar
  const conectarGoogle = async () => {
    try { window.location.href = (await api<{ url: string }>("/auth/google/vincular")).url; } catch (e) { mostrarError(e); }
  };
  const desconectarGoogle = async () => {
    try { cambio(await api<Yo>("/auth/google", { method: "DELETE" })); toast.success("Google desconectado"); } catch (e) { mostrarError(e); }
  };
  const { data: accesos = [] } = useSWR<{ cuando: string; quien: string; motivo: string | null }[]>(abierto ? "/auth/soporte/accesos" : null, fetcher);
  const dato = (k: string, v: React.ReactNode) => <div className="flex justify-between gap-3 py-1.5 text-sm"><dt className="text-grafito">{k}</dt><dd className="min-w-0 truncate text-right">{v}</dd></div>;
  return (
    <Modal open={abierto} onClose={cerrar} title="Mi perfil"
      footer={<Button variant="fantasma" onClick={() => { setToken(null); router.push("/login/"); }}><LogOut className="size-4" /> Cerrar sesión</Button>}>
      <div className="grid gap-5">
        <div className="flex items-center gap-3">
          <span className="grid size-12 shrink-0 place-items-center rounded-full bg-primario text-sm font-semibold text-sobre-primario">{iniciales(yo?.nombre || yo?.email || "")}</span>
          <div className="min-w-0"><b className="block truncate">{yo?.nombre || "Sin nombre"}</b><span className="block truncate text-sm text-grafito">{yo?.email}</span></div>
          <Badge tono={yo?.admin ? "cobalto" : "neutro"} className="ml-auto">{yo?.admin ? "Administrador" : "Usuario"}</Badge>
        </div>
        <Field label="Tu nombre (sale en el menú)">
          <div className="flex gap-2">
            <Input value={nombre} onChange={(e) => setNombre(e.target.value)} onKeyDown={(e) => e.key === "Enter" && guardarNombre()} />
            <Button onClick={guardarNombre} loading={trabajando === "nombre"} disabled={!nombre.trim() || nombre.trim() === (yo?.nombre ?? "")}>Guardar</Button>
          </div>
        </Field>
        <dl className="divide-y divide-linea rounded-xl px-4 ring-1 ring-linea">
          {yo?.usuario && dato("Usuario", yo.usuario)}
          {dato("Correo de acceso", yo?.email)}
          {dato("Google", yo?.google_email
            ? <span>{yo.google_email} · <button className="underline" onClick={desconectarGoogle}>Desconectar</button></span>
            : googleListo === false ? <span className="text-grafito">Se activa pronto</span>
            : <button className="underline" onClick={conectarGoogle}>Conectar mi cuenta de Google</button>)}
          {yo?.creado && dato("Usuario desde", new Date(yo.creado).toLocaleDateString("es-MX", { day: "numeric", month: "long", year: "numeric" }))}
          {dato("Emisor activo", emisor ? `${emisor.rfc} · ${emisor.nombre}` : "Ninguno")}
          {dato("Emisores dados de alta", emisores.length)}
          {typeof yo?.timbres === "number" && dato("Timbres disponibles", <b className={yo.timbres <= 0 ? "text-rojo" : undefined}>{yo.timbres}</b>)}
          {emisor && dato("Timbrado", { demo: <span className="text-alerta">Modo demo (sin PAC)</span>, pruebas: <span className="text-alerta">PAC en ambiente de pruebas</span>, produccion: "Producción", "": "Con PAC" }[ambienteDe(emisor) ?? ""])}
          {yo?.terminos?.aceptados && dato("Términos y privacidad", <span>Aceptados el {new Date(yo.terminos.aceptados).toLocaleDateString("es-MX", { day: "numeric", month: "long", year: "numeric" })} · <Link className="underline" href="/legal/terminos/" target="_blank">Ver</Link></span>)}
          {dato("Tema", <button className="underline" onClick={() => tema.siguiente()}>{t === "oscuro" ? "Oscuro" : t === "claro" ? "Claro" : "Como el sistema"}</button>)}
        </dl>
        {accesos.length > 0 && (
          <div className="rounded-xl px-4 py-3 text-sm ring-1 ring-linea">
            <p className="mb-1.5 font-medium">Soporte ha entrado a tu cuenta</p>
            <ul className="grid gap-1 text-grafito">
              {accesos.slice(0, 5).map((a, i) => (
                <li key={i}>{new Date(a.cuando).toLocaleString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · {a.quien}{a.motivo ? ` · ${a.motivo}` : ""}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="grid gap-2">
          <span className="text-[13px] font-medium text-grafito">Cambiar contraseña</span>
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
            <Input type="password" placeholder="Actual" autoComplete="current-password" value={pwd.actual} onChange={(e) => setPwd({ ...pwd, actual: e.target.value })} />
            <Input type="password" placeholder="Nueva (mínimo 8)" autoComplete="new-password" value={pwd.nueva} onChange={(e) => setPwd({ ...pwd, nueva: e.target.value })} />
            <Button onClick={cambiarPwd} loading={trabajando === "pwd"} disabled={!pwd.actual || pwd.nueva.length < 8}>Cambiar</Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/** Riel: el emisor con el que se trabaja, bien a la vista bajo el logo. Clic = cambiar de emisor. */
function EmisorRiel() {
  const { emisores, emisor, setEmisorId } = useEmisor();
  const [abierto, setAbierto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setAbierto(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAbierto(false);
    document.addEventListener("mousedown", fuera);
    window.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fuera); window.removeEventListener("keydown", esc); };
  }, [abierto]);
  if (!emisor) return <Link href="/emisores" title="Da de alta tu primer RFC" className="mx-auto grid size-12 place-items-center rounded-xl border border-dashed border-linea text-grafito hover:text-tinta"><Building2 className="size-5" /></Link>;
  const letras = (rfc: string) => rfc.slice(0, rfc.length === 12 ? 3 : 4);
  const amb = ambienteDe(emisor);
  const prueba = amb === "pruebas" || amb === "demo";
  return (
    <div ref={ref} className="relative mx-auto">
      <button onClick={() => setAbierto((a) => !a)} aria-haspopup="menu" aria-expanded={abierto} title={`Trabajas con ${emisor.rfc} · ${emisor.nombre}${prueba ? " · timbra en pruebas, sin validez fiscal" : ""}`}
        className={cx("relative flex h-[52px] w-[60px] flex-col items-center justify-center rounded-xl border leading-none shadow-[0_1px_2px_rgb(12_22_41/.06)] transition-[border-color,box-shadow] duration-150 hover:border-acento/50 hover:shadow-[0_0_0_3px_var(--color-acento-suave)]", prueba ? "bg-alerta-suave" : "bg-papel", abierto ? "border-acento/50 shadow-[0_0_0_3px_var(--color-acento-suave)]" : prueba ? "border-alerta/60" : "border-linea")}>
        <b className="text-[15px] tracking-tight">{letras(emisor.rfc)}</b>
        <span className="mt-1 text-[9px] tabular-nums tracking-wide text-grafito">{emisor.rfc.slice(letras(emisor.rfc).length, letras(emisor.rfc).length + 6)}</span>
        <EtiquetaAmbiente ambiente={amb} className="absolute -bottom-2 left-1/2 -translate-x-1/2 px-1 text-[8px] leading-3" />
      </button>
      {abierto && (
        <div role="menu" className="absolute left-full top-0 z-[60] ml-3 w-72 origin-top-left rounded-xl border border-linea bg-hoja p-1.5 shadow-flotante animate-aparecer">
          <p className="px-3 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-[.08em] text-grafito/70">Emisor con el que trabajas</p>
          {emisores.map((e) => (
            <button key={e.id} role="menuitemradio" aria-checked={e.id === emisor.id} onClick={() => { setEmisorId(e.id); setAbierto(false); }}
              className={cx("flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors", e.id === emisor.id ? "bg-primario text-sobre-primario" : "hover:bg-tinta/5")}>
              <b className="w-11 shrink-0 text-[13px]">{letras(e.rfc)}</b>
              <span className="min-w-0 flex-1"><span className="block truncate font-medium">{e.nombre}</span><span className="block text-[11px] tabular-nums opacity-70">{e.rfc}</span></span>
              <EtiquetaAmbiente ambiente={ambienteDe(e)} />
            </button>
          ))}
          <Link href="/emisores" onClick={() => setAbierto(false)} className="mt-1 block rounded-lg px-3 py-2 text-sm text-grafito hover:bg-tinta/5 hover:text-tinta">Administrar emisores…</Link>
        </div>
      )}
    </div>
  );
}

function Navegacion({ path, riel, onIr, pend }: { path: string; riel?: boolean; onIr?: () => void; pend?: { total: number; errores: number } }) {
  // Grupos plegados (barra abierta): lo que el usuario eligió, o el valor por defecto. La pantalla actual siempre se ve.
  const [plegados, setPlegados] = useState<Record<string, boolean>>({});
  useEffect(() => { try { setPlegados(JSON.parse(leer("timbra_grupos") || "{}")); } catch {} }, []);
  const alternar = (id: string, ahora: boolean) => setPlegados((p) => { const n = { ...p, [id]: !ahora }; guardar("timbra_grupos", JSON.stringify(n)); return n; });
  // Riel: cada grupo es UN icono; al pasar el mouse (o con clic) sale su menú con nombres completos. Lo diario lleva etiqueta flotante.
  const [flota, setFlota] = useState<{ id: string; y: number } | null>(null);
  const cierre = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abrir = (id: string, el: HTMLElement) => { if (cierre.current) clearTimeout(cierre.current); const r = el.getBoundingClientRect(); setFlota({ id, y: r.top }); };
  const cerrarLuego = () => { if (cierre.current) clearTimeout(cierre.current); cierre.current = setTimeout(() => setFlota(null), 180); };
  const quedarse = () => { if (cierre.current) clearTimeout(cierre.current); };
  useEffect(() => setFlota(null), [path, riel]);
  const globo = (total: number, errores: number, enRiel: boolean) => (
    <span className={cx("grid place-items-center rounded-full font-semibold tabular-nums text-white", errores ? "bg-rojo" : "bg-alerta",
      enRiel ? "absolute -right-0.5 -top-0.5 min-w-[18px] px-1 text-[10px] leading-[18px]" : "ml-auto min-w-5 px-1.5 text-[11px]")}>{total > 99 ? "99+" : total}</span>
  );
  const fila = (it: Item, cerrar?: () => void) => it.gratis ? (
    <Link key={it.href} href={it.href} onClick={() => { cerrar?.(); onIr?.(); }}
      className={cx("group/fila relative mt-2 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ring-1 transition-[background-color,box-shadow,transform] duration-150 hover:-translate-y-px",
        activo(path, it.href) ? "bg-sello text-white ring-sello" : "bg-sello-suave text-sello ring-sello/35 hover:ring-sello/70")}>
      <it.icon className="size-6 shrink-0 transition-transform duration-150 group-hover/fila:scale-110" strokeWidth={1.75} />
      <span className="min-w-0 flex-1 leading-tight"><span className="block truncate">{it.label}</span><span className="block text-[11px] font-normal opacity-80">Descarga y lectura</span></span>
      <span className={cx("rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", activo(path, it.href) ? "bg-white/20" : "bg-sello text-white")}>Gratis</span>
    </Link>
  ) : (
    <Link key={it.href} href={it.href} onClick={() => { cerrar?.(); onIr?.(); }}
      className={cx("group/fila relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-[color,background-color,filter,transform] duration-150",
        it.cta ? "bg-acento bg-linear-to-b from-white/12 to-transparent font-medium text-white shadow-boton hover:-translate-y-px hover:brightness-110" :
        activo(path, it.href) ? "bg-acento-suave font-medium text-acento before:absolute before:left-0 before:top-1/2 before:h-4 before:w-[3px] before:-translate-y-1/2 before:rounded-r-full before:bg-acento" : "text-grafito hover:bg-tinta/5 hover:text-tinta")}>
      <it.icon className="size-[18px] shrink-0 transition-transform duration-150 group-hover/fila:scale-110" />
      <span className="min-w-0 truncate">{it.label}</span>
      {it.href === "/pendientes" && !!pend?.total ? globo(pend.total, pend.errores, false) : it.k && <kbd className="ml-auto pl-3 font-sans text-[10px] opacity-50">{it.k}</kbd>}
    </Link>
  );

  if (riel) {
    const g = flota ? NAV.find((x) => x.id === flota.id) : undefined;
    const item = flota ? NAV[0].items.find((x) => x.href === flota.id) : undefined;
    const boton = "group/riel relative grid size-12 place-items-center rounded-xl transition-[color,background-color,filter,transform] duration-150 active:scale-95";
    const marca = "before:absolute before:-left-3.5 before:top-1/2 before:h-6 before:w-[3px] before:-translate-y-1/2 before:rounded-r-full before:bg-acento";
    return (
      <nav className="flex flex-1 flex-col items-center gap-1.5">
        {NAV[0].items.map((it) => (
          <Link key={it.href} href={it.href} aria-label={it.label}
            onMouseEnter={(e) => abrir(it.href, e.currentTarget)} onMouseLeave={cerrarLuego} onFocus={(e) => abrir(it.href, e.currentTarget)} onBlur={cerrarLuego}
            className={cx(boton, it.cta ? "bg-acento bg-linear-to-b from-white/12 to-transparent text-white shadow-boton hover:-translate-y-px hover:brightness-110" :
              it.gratis ? cx("mt-1 ring-1 hover:-translate-y-px", activo(path, it.href) ? "bg-sello text-white ring-sello" : "bg-sello-suave text-sello ring-sello/40 hover:ring-sello/80") :
              activo(path, it.href) ? cx("bg-acento-suave text-acento", marca) : "text-grafito hover:bg-tinta/5 hover:text-tinta")}>
            <it.icon className={cx("transition-transform duration-150 group-hover/riel:scale-110", it.gratis ? "size-[26px]" : "size-[22px]")} strokeWidth={1.75} />
            {it.href === "/pendientes" && !!pend?.total && globo(pend.total, pend.errores, true)}
          </Link>
        ))}
        <span className="my-1.5 h-px w-7 bg-linea" />
        {NAV.slice(1).map((gr) => {
          const GIcon = gr.icon!;
          const aqui = gr.items.some((i) => activo(path, i.href));
          return (
            <button key={gr.id} aria-label={gr.grupo} aria-haspopup="menu" aria-expanded={flota?.id === gr.id}
              onMouseEnter={(e) => abrir(gr.id, e.currentTarget)} onMouseLeave={cerrarLuego} onClick={(e) => abrir(gr.id, e.currentTarget)}
              className={cx(boton, aqui ? cx("bg-acento-suave text-acento", marca) : flota?.id === gr.id ? "bg-tinta/5 text-tinta" : "text-grafito hover:bg-tinta/5 hover:text-tinta")}>
              <GIcon className="size-[22px] transition-transform duration-150 group-hover/riel:scale-110" strokeWidth={1.75} />
            </button>
          );
        })}
        {item && flota && (
          <div role="tooltip" style={{ top: flota.y + 24 }} className="pointer-events-none fixed left-[84px] z-[60] flex -translate-y-1/2 items-center gap-2 whitespace-nowrap rounded-lg border border-linea bg-hoja px-3 py-2 text-sm font-medium shadow-flotante">
            {item.label}{item.k && <kbd className="rounded bg-tinta/10 px-1.5 py-0.5 font-sans text-[11px] font-normal text-grafito">{item.k}</kbd>}
          </div>
        )}
        {g && flota && (
          <div role="menu" onMouseEnter={quedarse} onMouseLeave={cerrarLuego}
            style={{ top: Math.max(8, Math.min(flota.y - 8, (typeof window === "undefined" ? 800 : window.innerHeight) - (g.items.length * 40 + 56))) }}
            className="fixed left-[76px] z-[60] w-60 pl-2">
            <div key={g.id} className="flex origin-left flex-col gap-0.5 rounded-xl border border-linea bg-hoja p-1.5 shadow-flotante animate-aparecer">
              <p className="px-3 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-[.08em] text-grafito/70">{g.grupo}</p>
              {g.items.map((it) => fila(it, () => setFlota(null)))}
            </div>
          </div>
        )}
      </nav>
    );
  }

  return (
    <nav className="flex flex-1 flex-col gap-2 overflow-y-auto [scrollbar-width:thin] [scrollbar-color:var(--color-linea)_transparent]">
      {NAV.map((g) => {
        const plegado = !!g.grupo && (plegados[g.id] ?? !!g.plegado);
        return (
          <div key={g.id} className="flex flex-col gap-0.5">
            {g.grupo && (
              <button onClick={() => alternar(g.id, plegado)} aria-expanded={!plegado}
                className="flex items-center justify-between rounded-md px-3 py-1 text-[11px] font-medium uppercase tracking-[.08em] text-grafito/70 hover:text-tinta">
                {g.grupo}<ChevronDown className={cx("size-3.5 transition-transform", plegado && "-rotate-90")} />
              </button>
            )}
            {g.items.map((it) => (plegado && !activo(path, it.href) ? null : fila(it)))}
          </div>
        );
      })}
    </nav>
  );
}

function Marca({ riel }: { riel?: boolean }) {
  return (
    <Link href="/" className={cx("flex min-w-0 items-center gap-2.5", riel && "justify-center")}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo.png" alt="Timbra" className={cx("shrink-0 rounded-xl bg-black shadow-[0_1px_2px_rgb(12_22_41/.2),0_8px_16px_-8px_rgb(12_22_41/.5)] ring-1 ring-black/10 transition-transform duration-200 hover:scale-105", riel ? "size-11" : "size-9")} />
      {!riel && (
        <span className="min-w-0 leading-tight">
          <b className="block text-[15px] tracking-tight">Timbra</b>
          <span className="block truncate text-[11px] text-grafito">EDDP Servicios</span>
        </span>
      )}
    </Link>
  );
}

/** Modo soporte: siempre a la vista de quién es la cuenta que se está viendo, y la salida a un clic. */
function BandaSoporte() {
  const [s, setS] = useState<Soporte | null>(null);
  useEffect(() => setS(getSoporte()), []);
  if (!s) return null;
  const salir = async () => {
    try { await api(`/auth/soporte/${s.id}`, { method: "DELETE" }); } catch {}
    setSoporte(null);
    window.location.href = "/ajustes/";
  };
  return (
    <div className="sticky top-2 z-30 mb-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-rojo px-4 py-2.5 text-sm text-white shadow-flotante">
      <AlertTriangle className="size-4 shrink-0" />
      <span className="min-w-0 flex-1"><b>Modo soporte.</b> Estás dentro de la cuenta de <b>{s.nombre}</b> ({s.email}). Lo que hagas queda en su cuenta.</span>
      <button onClick={salir} className="rounded-lg bg-white/15 px-3 py-1 font-medium hover:bg-white/25">Salir de su cuenta</button>
    </div>
  );
}

/** Lo que no puede esperar: timbres por acabarse y recurrentes del día. Discreto, arriba del contenido. */
function Avisos() {
  const { emisor } = useEmisor();
  const { data: timbres = [] } = useSWR<TimbresPac[]>("/pacs/timbres", fetcher, { refreshInterval: 300_000 });
  const { data: pend = [] } = useSWR<{ id: number }[]>(emisor ? `/plantillas/recurrentes/pendientes?emisor_id=${emisor.id}` : null, fetcher, { refreshInterval: 300_000 });
  const malos = timbres.filter((t) => t.nivel !== "ok" && t.texto);
  const { data: pg } = useSWR<{ total: number; errores: number }>(emisor ? `/pendientes/resumen?emisor_id=${emisor.id}` : null, fetcher, { refreshInterval: 300_000 });
  const enPendientes = usePathname().startsWith("/pendientes");  // ahí el aviso sobra
  const { data: salud } = useSWR<{ almacen?: { permanente: boolean | null } }>("/health", fetcher, { revalidateOnFocus: false });
  const sinDisco = salud?.almacen?.permanente === false;
  // Saldo de timbres de la cuenta (quien factura con el PAC de Timbra): se avisa cuando quedan pocos
  const { data: yo } = useSWR<Yo>("/auth/yo", fetcher, { refreshInterval: 120_000 });
  const pocos = typeof yo?.timbres === "number" && yo.timbres <= 5 && yo.correo_verificado !== false;
  const sinConfirmar = yo?.correo_verificado === false;  // se registró con correo y contraseña y no ha confirmado el correo
  const reenviar = () => api("/auth/reenviar-verificacion", { method: "POST" })
    .then(() => toast.success("Listo: revisa tu correo (y la carpeta de spam)."), mostrarError);
  if (!sinConfirmar && !sinDisco && !pocos && !malos.length && !pend.length && (!pg?.total || enPendientes)) return null;
  return (
    <div className="escalonar mb-6 flex flex-wrap gap-2">
      {sinConfirmar && (
        <button onClick={reenviar} className="inline-flex items-center gap-2 rounded-full bg-alerta-suave px-3 py-1.5 text-[13px] font-medium text-alerta ring-1 ring-current/15">
          <Stamp className="size-4" /> Confirma tu correo ({yo!.email}) para recibir tus 3 timbres de regalo · Reenviar el enlace
        </button>
      )}
      {pocos && (
        <Link href="/timbres" className={cx("inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-medium ring-1 ring-current/15", yo!.timbres! <= 0 ? "bg-rojo-suave text-rojo" : "bg-alerta-suave text-alerta")}>
          <Stamp className="size-4" /> {yo!.timbres! <= 0 ? "Se acabaron tus timbres: recarga para seguir facturando" : `Te quedan ${yo!.timbres} timbres`}
        </Link>
      )}
      {sinDisco && (
        <Link href="/ajustes" className="inline-flex items-center gap-2 rounded-full bg-rojo-suave px-3 py-1.5 text-[13px] font-medium text-rojo ring-1 ring-current/15">
          <AlertTriangle className="size-4" /> Este servidor no guarda de forma permanente: lo que captures se perdería al actualizar
        </Link>
      )}
      {!!pg?.total && !enPendientes && (
        <Link href="/pendientes" className={cx("inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-medium ring-1 ring-current/15 transition-transform duration-150 hover:-translate-y-px", pg.errores ? "bg-rojo-suave text-rojo" : "bg-alerta-suave text-alerta")}>
          <ListChecks className="size-4" /> {pg.total} {pg.total === 1 ? "pendiente" : "pendientes"}{pg.errores ? ` · ${pg.errores} urgentes` : ""} · Revisar
        </Link>
      )}
      {pend.length > 0 && (
        <Link href="/recurrentes" className="inline-flex items-center gap-2 rounded-full bg-cobalto-suave px-3 py-1.5 text-[13px] font-medium text-cobalto ring-1 ring-current/15 transition-transform duration-150 hover:-translate-y-px">
          <CalendarClock className="size-4" /> {pend.length} {pend.length === 1 ? "factura recurrente toca" : "facturas recurrentes tocan"} hoy · Timbrar
        </Link>
      )}
      {malos.map((t) => (
        <Link key={t.pac_id} href="/timbres" className={cx("inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-medium ring-1 ring-current/15 transition-transform duration-150 hover:-translate-y-px",
          t.nivel === "error" ? "bg-rojo-suave text-rojo" : "bg-alerta-suave text-alerta")}>
          <AlertTriangle className="size-4" /> {t.texto}
        </Link>
      ))}
    </div>
  );
}

/**
 * Términos de uso y aviso de privacidad: la cuenta los acepta antes de usar Timbra y otra vez cuando cambian (backend/app/legal.py).
 * No se cierra con Esc ni dando clic afuera: o aceptas, o sales de tu cuenta. En modo soporte no aparece (no acepta el administrador por otro).
 */
function AceptarTerminos({ version, nueva, listo }: { version: string; nueva: boolean; listo: (y: Yo) => void }) {
  const router = useRouter();
  const [ok, setOk] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const aceptar = async () => {
    setEnviando(true);
    try { listo(await api<Yo>("/auth/terminos", { method: "POST", json: { version } })); toast.success("Listo, gracias"); }
    catch (e) { mostrarError(e); } finally { setEnviando(false); }
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-tinta/50 backdrop-blur-[3px] animate-velo sm:items-center sm:p-4">
      <div role="dialog" aria-modal aria-labelledby="terminos-titulo" className="w-full rounded-t-2xl bg-hoja p-6 shadow-flotante animate-subir sm:max-w-md sm:rounded-2xl">
        <h2 id="terminos-titulo" className="text-lg font-semibold">{nueva ? "Actualizamos los términos" : "Antes de empezar"}</h2>
        <p className="mt-2 text-sm leading-relaxed text-grafito">
          {nueva
            ? "Cambiamos los términos de uso o el aviso de privacidad. Revísalos y acéptalos para seguir usando Timbra."
            : "Timbra guarda tus datos fiscales y tu CSD para timbrar a tu nombre. Lee cómo los cuidamos y las reglas del servicio."}
        </p>
        <div className="mt-4 flex flex-col gap-1.5 text-sm">
          <Link href="/legal/terminos/" target="_blank" className="font-medium text-acento underline-offset-4 hover:underline">Términos de uso ↗</Link>
          <Link href="/legal/privacidad/" target="_blank" className="font-medium text-acento underline-offset-4 hover:underline">Aviso de privacidad ↗</Link>
        </div>
        <label className="mt-5 flex cursor-pointer items-start gap-2.5 text-sm">
          <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} className="mt-0.5 size-4 accent-[var(--color-acento)]" autoFocus />
          <span>Leí y acepto los términos de uso y el aviso de privacidad.</span>
        </label>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="fantasma" onClick={() => { setToken(null); router.push("/login/"); }}><LogOut className="size-4" /> Salir</Button>
          <Button variant="primario" onClick={aceptar} loading={enviando} disabled={!ok}>Aceptar y continuar</Button>
        </div>
      </div>
    </div>
  );
}

function Marco({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { emisor: emisorActivo, cargando } = useEmisor();
  const { data: pend } = useSWR<{ total: number; errores: number }>(emisorActivo ? `/pendientes/resumen?emisor_id=${emisorActivo.id}` : null, fetcher, { refreshInterval: 300_000 });
  const { data: yo, mutate: mutYo } = useSWR<Yo>("/auth/yo", fetcher);
  const [cajon, setCajon] = useState(false);
  const [perfil, setPerfil] = useState(false);
  const { erroresNuevos } = useConsola();
  useEffect(() => setCajon(false), [path]);

  // Barra lateral: abierta o plegada a riel de iconos. Se recuerda por equipo; en pantallas angostas arranca plegada.
  const [riel, setRiel] = useState(false);
  useEffect(() => {
    const g = leer("timbra_barra");
    setRiel(g ? g === "riel" : window.innerWidth < 1100);
  }, []);
  const alternarBarra = useCallback(() => setRiel((r) => { guardar("timbra_barra", r ? "abierta" : "riel"); return !r; }), []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "b") { e.preventDefault(); alternarBarra(); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [alternarBarra]);

  return (
    <div className="flex min-h-dvh">
      {/* Barra lateral: abierta o riel de iconos (Ctrl+B) */}
      <aside className={cx("sticky top-0 z-40 hidden h-dvh shrink-0 flex-col gap-3 border-r border-linea bg-hoja py-3 shadow-[8px_0_24px_-16px_rgb(12_22_41/.16)] transition-[width,padding] duration-200 md:flex", riel ? "w-[76px] px-2" : "w-64 px-3")}>
        <div className={cx("flex", riel ? "justify-center" : "pl-1")}><Marca riel={riel} /></div>
        {riel ? <EmisorRiel /> : <SelectorEmisor />}
        {/* Pestaña en el borde, a media altura: pliega o abre el menú (Ctrl+B) */}
        <button onClick={alternarBarra} title={riel ? "Abrir menú (Ctrl+B)" : "Plegar menú (Ctrl+B)"} aria-label={riel ? "Abrir menú" : "Plegar menú"} aria-expanded={!riel}
          className="absolute left-full top-1/2 grid h-16 w-4 -translate-y-1/2 place-items-center rounded-r-full border border-l-0 border-linea bg-hoja text-grafito shadow-[4px_0_10px_-4px_rgb(12_22_41/.14)] transition-[width,color] duration-150 hover:w-5 hover:text-acento">
          {riel ? <ChevronRight className="size-3.5" /> : <ChevronLeft className="size-3.5" />}
        </button>
        <Navegacion path={path} riel={riel} pend={pend} />
        <div className={cx("flex flex-col gap-1 border-t border-linea pt-2", riel && "items-center")}>
          <BotonPerfil yo={yo} riel={riel} abrir={() => setPerfil(true)} />
          <Utilidades riel={riel} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Barra superior (móvil) */}
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-linea bg-hoja/80 px-3 py-2 shadow-[0_8px_24px_-18px_rgb(12_22_41/.3)] backdrop-blur-md md:hidden">
          <button onClick={() => setCajon(true)} aria-label="Abrir menú" className="rounded-md p-2 hover:bg-tinta/5">
            <MenuIcon className="size-5" />
          </button>
          <div className="min-w-0 flex-1"><SelectorEmisor /></div>
          <button onClick={() => consola.alternar()} aria-label="Consola" className="relative rounded-md p-2 hover:bg-tinta/5">
            <Terminal className="size-5" />
            {erroresNuevos > 0 && <span className="absolute right-1 top-1 size-2 rounded-full bg-rojo" />}
          </button>
        </header>
        <main key={path} className="mx-auto w-full min-w-0 max-w-[1280px] flex-1 px-4 py-6 animate-entrar sm:px-6 lg:px-10 lg:py-8">
          <BandaSoporte />
          <Avisos />
          {/* Mientras llegan los emisores no se pinta la pantalla: así no sale «da de alta un emisor» por un instante */}
          {cargando ? <div aria-busy className="esqueleto h-9 w-72" /> : children}
        </main>
      </div>

      {/* Cajón móvil */}
      {cajon && (
        <div className="fixed inset-0 z-50 bg-tinta/40 backdrop-blur-[3px] animate-velo md:hidden" onClick={() => setCajon(false)}>
          <aside className="flex h-full w-[82vw] max-w-72 flex-col gap-3 bg-hoja px-3 py-4 shadow-flotante animate-deslizar" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pl-2">
              <Marca />
              <button onClick={() => setCajon(false)} aria-label="Cerrar menú" className="rounded-md p-1 hover:bg-tinta/5"><X className="size-5" /></button>
            </div>
            <SelectorEmisor />
            <Navegacion path={path} onIr={() => setCajon(false)} pend={pend} />
            <div className="flex flex-col gap-1 border-t border-linea pt-2">
              <BotonPerfil yo={yo} abrir={() => { setCajon(false); setPerfil(true); }} />
              <Utilidades />
            </div>
          </aside>
        </div>
      )}
      <Perfil abierto={perfil} cerrar={() => setPerfil(false)} yo={yo} cambio={(y) => mutYo(y, false)} />
      {yo?.terminos?.pendiente && !getSoporte() && <AceptarTerminos version={yo.terminos.vigente} nueva={!!yo.terminos.aceptada} listo={(y) => mutYo(y, false)} />}
      <Consola />
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [listo, setListo] = useState(false);

  useEffect(() => {
    // Sin sesión: en tu PC vas directo a entrar; en web, a la página de inicio pública
    if (!getToken()) router.replace(/^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname) ? "/login/" : "/inicio/");
    else setListo(true);
  }, [router]);

  // Errores de JavaScript del navegador → registro del servidor (se ven en la consola)
  useEffect(() => {
    const err = (e: ErrorEvent) => reportarNavegador(`${e.message} @ ${e.filename}:${e.lineno}`, { stack: e.error?.stack });
    const rej = (e: PromiseRejectionEvent) => {
      const r = e.reason as { status?: number; message?: string; stack?: string };
      if (r?.status !== undefined) return; // errores de API ya quedan registrados en el servidor
      reportarNavegador(`Promesa rechazada: ${r?.message ?? String(e.reason)}`, { stack: r?.stack });
    };
    window.addEventListener("error", err);
    window.addEventListener("unhandledrejection", rej);
    return () => { window.removeEventListener("error", err); window.removeEventListener("unhandledrejection", rej); };
  }, []);

  if (!listo) return null;
  return (
    <SWRConfig value={{ revalidateOnFocus: false }}>
      <EmisorProvider>
        <AtajosProvider>
          <Marco>{children}</Marco>
        </AtajosProvider>
      </EmisorProvider>
    </SWRConfig>
  );
}
