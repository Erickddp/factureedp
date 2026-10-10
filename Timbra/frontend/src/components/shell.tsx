"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import useSWR, { SWRConfig } from "swr";
import { toast } from "sonner";
import {
  BookMarked, Building2, Calculator, ChevronDown, CloudDownload, Coins, FileText, Gauge, HandCoins, Keyboard, LogOut, Menu as MenuIcon,
  Monitor, Moon, Package, PanelLeftClose, PanelLeftOpen, Palette, Plug, Store, Sun, Terminal, Users, Wallet, X, Zap, BadgeDollarSign, AlertTriangle,
  CalendarClock, UserSquare, Layers, Telescope, ListChecks,
} from "lucide-react";
import { api, fetcher, getToken, reportarNavegador, setToken } from "@/lib/api";
import { consola, useConsola } from "@/lib/debug";
import { mostrarError } from "@/lib/errores";
import { tema, useTema } from "@/lib/tema";
import type { TimbresPac } from "@/lib/types";
import { AtajosProvider, useAtajos } from "./atajos";
import { Consola } from "./consola";
import { EmisorProvider, useEmisor } from "./emisor-context";
import { Badge, Button, Field, Input, Modal, cx } from "./ui";

type Item = { href: string; label: string; icon: typeof Zap; k?: string };
// Orden por uso: arriba lo de todos los días; los grupos de abajo se pliegan (Control y Configuración vienen plegados).
const NAV: { id: string; grupo?: string; plegado?: boolean; items: Item[] }[] = [
  { id: "diario", items: [
    { href: "/facturar", label: "Facturar", icon: Zap, k: "F2" },
    { href: "/facturas", label: "Facturas", icon: FileText, k: "Alt F" },
    { href: "/pendientes", label: "Pendientes", icon: ListChecks, k: "Alt J" },
    { href: "/", label: "Resumen", icon: Gauge },
  ] },
  { id: "emitir", grupo: "Emitir", items: [
    { href: "/lotes", label: "Lotes desde tabla", icon: Layers, k: "Alt L" },
    { href: "/recurrentes", label: "Recurrentes", icon: CalendarClock, k: "Alt R" },
    { href: "/pagos", label: "Pagos (REP)", icon: Wallet },
    { href: "/nomina", label: "Nómina", icon: BadgeDollarSign, k: "Alt E" },
    { href: "/portal", label: "Autofactura", icon: Store },
  ] },
  { id: "catalogos", grupo: "Catálogos", items: [
    { href: "/clientes", label: "Clientes", icon: Users },
    { href: "/productos", label: "Productos", icon: Package },
    { href: "/claves", label: "Claves SAT", icon: Telescope, k: "Alt K" },
    { href: "/plantillas", label: "Plantillas", icon: BookMarked },
    { href: "/terceros", label: "Terceros", icon: UserSquare },
  ] },
  { id: "control", grupo: "Control", plegado: true, items: [
    { href: "/cobranza", label: "Cobranza", icon: HandCoins, k: "Alt B" },
    { href: "/calculadora", label: "Calculadora", icon: Calculator },
    { href: "/sat", label: "Descarga SAT", icon: CloudDownload },
  ] },
  { id: "config", grupo: "Configuración", plegado: true, items: [
    { href: "/emisores", label: "Emisores y CSD", icon: Building2 },
    { href: "/ajustes", label: "PAC y usuarios", icon: Plug },
    { href: "/timbres", label: "Timbres", icon: Coins, k: "Alt T" },
    { href: "/marca", label: "Marca y e.firma", icon: Palette },
  ] },
];

const activo = (path: string, href: string) => (href === "/" ? path === "/" : path.startsWith(href));
const leer = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const guardar = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch {} };
const iniciales = (s: string) => s.trim().split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join("").toUpperCase() || "?";

type Yo = { email: string; nombre: string | null; admin: boolean; creado?: string | null };

function SelectorEmisor() {
  const { emisores, emisor, setEmisorId } = useEmisor();
  if (!emisores.length)
    return <Link href="/emisores" className="block truncate rounded-lg bg-cobalto-suave px-3 py-2 text-sm text-cobalto">Da de alta tu primer RFC</Link>;
  return (
    <select
      aria-label="Emisor activo"
      value={emisor?.id ?? ""}
      onChange={(e) => setEmisorId(Number(e.target.value))}
      className="h-9 w-full min-w-0 truncate rounded-lg border border-linea bg-hoja px-2.5 text-sm focus:border-tinta focus:outline-none"
    >
      {emisores.map((e) => (
        <option key={e.id} value={e.id}>{e.rfc} · {e.nombre}</option>
      ))}
    </select>
  );
}

/** Tema, consola y atajos: fila de iconos (barra abierta) o columna (riel). */
function Utilidades({ riel }: { riel?: boolean }) {
  const t = useTema();
  const { erroresNuevos } = useConsola();
  const { abrirAyuda } = useAtajos();
  const IconTema = t === "oscuro" ? Moon : t === "claro" ? Sun : Monitor;
  const txtTema = t === "oscuro" ? "Oscuro" : t === "claro" ? "Claro" : "Como el sistema";
  const b = "relative grid size-9 place-items-center rounded-lg text-grafito hover:bg-tinta/5 hover:text-tinta";
  return (
    <div className={cx("flex gap-1", riel ? "flex-col items-center" : "items-center")}>
      <button onClick={() => tema.siguiente()} title={`Tema: ${txtTema} (Ctrl+Shift+L)`} aria-label={`Tema: ${txtTema}`} className={b}><IconTema className="size-4" /></button>
      <button onClick={() => consola.alternar()} title="Consola de depuración (F9)" aria-label="Consola" className={b}>
        <Terminal className="size-4" />
        {erroresNuevos > 0 && <span className="absolute right-0.5 top-0.5 grid size-4 place-items-center rounded-full bg-rojo text-[10px] text-white">{erroresNuevos > 9 ? "9+" : erroresNuevos}</span>}
      </button>
      <button onClick={abrirAyuda} title="Atajos de teclado (F1)" aria-label="Atajos" className={b}><Keyboard className="size-4" /></button>
    </div>
  );
}

/** Quién está usando Timbra: nombre, correo y rol. Abre "Mi perfil". */
function BotonPerfil({ yo, riel, abrir }: { yo?: Yo; riel?: boolean; abrir: () => void }) {
  const nombre = yo?.nombre || yo?.email || "Mi perfil";
  return (
    <button onClick={abrir} title={riel ? `${nombre} · Mi perfil` : "Mi perfil"} className={cx("flex min-w-0 items-center gap-2.5 rounded-lg p-1.5 text-left hover:bg-tinta/5", riel && "justify-center")}>
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-tinta/10 text-[11px] font-semibold">{iniciales(nombre)}</span>
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
    try { await api("/auth/password", { method: "POST", json: pwd }); setPwd({ actual: "", nueva: "" }); toast.success("Contraseña cambiada"); }
    catch (e) { mostrarError(e); } finally { setTrabajando(""); }
  };
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
          {dato("Correo de acceso", yo?.email)}
          {yo?.creado && dato("Usuario desde", new Date(yo.creado).toLocaleDateString("es-MX", { day: "numeric", month: "long", year: "numeric" }))}
          {dato("Emisor activo", emisor ? `${emisor.rfc} · ${emisor.nombre}` : "Ninguno")}
          {dato("Emisores dados de alta", emisores.length)}
          {emisor && dato("Timbrado", emisor.modo_demo ? <span className="text-alerta">Modo demo (sin PAC)</span> : "Con PAC")}
          {dato("Tema", <button className="underline" onClick={() => tema.siguiente()}>{t === "oscuro" ? "Oscuro" : t === "claro" ? "Claro" : "Como el sistema"}</button>)}
        </dl>
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

function Navegacion({ path, riel, onIr, pend }: { path: string; riel?: boolean; onIr?: () => void; pend?: { total: number; errores: number } }) {
  // Grupos plegados: lo que el usuario eligió, o el valor por defecto. El grupo de la pantalla actual siempre se ve.
  const [plegados, setPlegados] = useState<Record<string, boolean>>({});
  useEffect(() => { try { setPlegados(JSON.parse(leer("timbra_grupos") || "{}")); } catch {} }, []);
  const alternar = (id: string, ahora: boolean) => setPlegados((p) => { const n = { ...p, [id]: !ahora }; guardar("timbra_grupos", JSON.stringify(n)); return n; });
  return (
    <nav className={cx("flex flex-1 flex-col overflow-y-auto", riel ? "gap-1" : "gap-2")}>
      {NAV.map((g) => {
        const aqui = g.items.some((i) => activo(path, i.href));
        const plegado = !riel && !!g.grupo && (plegados[g.id] ?? !!g.plegado);
        return (
          <div key={g.id} className={cx("flex flex-col gap-0.5", riel && g.grupo && "border-t border-linea pt-1")}>
            {g.grupo && !riel && (
              <button onClick={() => alternar(g.id, plegado)} aria-expanded={!plegado}
                className="flex items-center justify-between rounded-md px-3 py-1 text-[11px] font-medium uppercase tracking-[.08em] text-grafito/70 hover:text-tinta">
                {g.grupo}<ChevronDown className={cx("size-3.5 transition-transform", plegado && "-rotate-90")} />
              </button>
            )}
            {g.items.map(({ href, label, icon: Icon, k }) => (plegado && !activo(path, href) && !(href === "/pendientes")) ? null : (
              <Link
                key={href}
                href={href}
                onClick={onIr}
                title={riel ? `${label}${k ? ` (${k})` : ""}` : undefined}
                className={cx(
                  "relative flex items-center gap-3 rounded-lg px-3 py-[7px] text-sm transition-colors",
                  riel && "justify-center px-0",
                  activo(path, href) ? "bg-primario font-medium text-sobre-primario" : "text-grafito hover:bg-tinta/5 hover:text-tinta",
                )}
              >
                <Icon className="size-4 shrink-0" />
                {!riel && <span className="min-w-0 truncate">{label}</span>}
                {href === "/pendientes" && !!pend?.total ? (
                  <span className={cx("grid place-items-center rounded-full font-semibold tabular-nums text-white", pend.errores ? "bg-rojo" : "bg-alerta",
                    riel ? "absolute right-0.5 top-0 min-w-4 px-1 text-[10px]" : "ml-auto min-w-5 px-1.5 text-[11px]")}>{pend.total > 99 ? "99+" : pend.total}</span>
                ) : !riel && k && <kbd className="ml-auto font-sans text-[10px] opacity-50">{k}</kbd>}
              </Link>
            ))}
            {plegado && aqui && <span className="sr-only">Grupo plegado</span>}
          </div>
        );
      })}
    </nav>
  );
}

function Marca({ riel }: { riel?: boolean }) {
  return (
    <Link href="/" className={cx("flex min-w-0 items-center gap-2.5", riel && "justify-center")}>
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primario text-[11px] font-bold tracking-tight text-sobre-primario">ED</span>
      {!riel && (
        <span className="min-w-0 leading-tight">
          <b className="block text-[15px] tracking-tight">Timbra</b>
          <span className="block truncate text-[11px] text-grafito">EDDP Servicios</span>
        </span>
      )}
    </Link>
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
  if (!malos.length && !pend.length && (!pg?.total || enPendientes)) return null;
  return (
    <div className="mb-5 flex flex-wrap gap-2 animate-entrar">
      {!!pg?.total && !enPendientes && (
        <Link href="/pendientes" className={cx("inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm hover:underline", pg.errores ? "bg-rojo-suave text-rojo" : "bg-alerta-suave text-alerta")}>
          <ListChecks className="size-4" /> {pg.total} {pg.total === 1 ? "pendiente" : "pendientes"}{pg.errores ? ` · ${pg.errores} urgentes` : ""} · Revisar
        </Link>
      )}
      {pend.length > 0 && (
        <Link href="/recurrentes" className="inline-flex items-center gap-2 rounded-full bg-cobalto-suave px-3 py-1.5 text-sm text-cobalto hover:underline">
          <CalendarClock className="size-4" /> {pend.length} {pend.length === 1 ? "factura recurrente toca" : "facturas recurrentes tocan"} hoy · Timbrar
        </Link>
      )}
      {malos.map((t) => (
        <Link key={t.pac_id} href="/timbres" className={cx("inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm hover:underline",
          t.nivel === "error" ? "bg-rojo-suave text-rojo" : "bg-alerta-suave text-alerta")}>
          <AlertTriangle className="size-4" /> {t.texto}
        </Link>
      ))}
    </div>
  );
}

function Marco({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { emisor: emisorActivo } = useEmisor();
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
      <aside className={cx("sticky top-0 hidden h-dvh shrink-0 flex-col gap-3 border-r border-linea bg-hoja py-3 transition-[width] duration-150 md:flex", riel ? "w-[60px] px-2" : "w-64 px-3")}>
        <div className={cx("flex items-center gap-1", riel ? "flex-col" : "justify-between pl-2")}>
          <Marca riel={riel} />
          <button onClick={alternarBarra} title={riel ? "Abrir menú (Ctrl+B)" : "Plegar menú (Ctrl+B)"} aria-label={riel ? "Abrir menú" : "Plegar menú"} aria-expanded={!riel}
            className="grid size-9 shrink-0 place-items-center rounded-lg text-grafito hover:bg-tinta/5 hover:text-tinta">
            {riel ? <PanelLeftOpen className="size-[18px]" /> : <PanelLeftClose className="size-[18px]" />}
          </button>
        </div>
        {riel ? (
          emisorActivo && <button onClick={alternarBarra} title={`${emisorActivo.rfc} · ${emisorActivo.nombre} · clic para cambiar de emisor`}
            className="mx-auto grid h-8 w-10 place-items-center rounded-lg border border-linea text-[10px] font-semibold tracking-tight text-grafito hover:text-tinta">{emisorActivo.rfc.slice(0, 4)}</button>
        ) : <SelectorEmisor />}
        <Navegacion path={path} riel={riel} pend={pend} />
        <div className={cx("flex flex-col gap-1 border-t border-linea pt-2", riel && "items-center")}>
          <BotonPerfil yo={yo} riel={riel} abrir={() => setPerfil(true)} />
          <Utilidades riel={riel} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Barra superior (móvil) */}
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-linea bg-hoja/90 px-3 py-2 backdrop-blur md:hidden">
          <button onClick={() => setCajon(true)} aria-label="Abrir menú" className="rounded-md p-2 hover:bg-tinta/5">
            <MenuIcon className="size-5" />
          </button>
          <div className="min-w-0 flex-1"><SelectorEmisor /></div>
          <button onClick={() => consola.alternar()} aria-label="Consola" className="relative rounded-md p-2 hover:bg-tinta/5">
            <Terminal className="size-5" />
            {erroresNuevos > 0 && <span className="absolute right-1 top-1 size-2 rounded-full bg-rojo" />}
          </button>
        </header>
        <main key={path} className="mx-auto w-full min-w-0 max-w-[1320px] flex-1 px-4 py-6 animate-entrar sm:px-6 lg:px-10 lg:py-8">
          <Avisos />
          {children}
        </main>
      </div>

      {/* Cajón móvil */}
      {cajon && (
        <div className="fixed inset-0 z-50 bg-tinta/40 md:hidden" onClick={() => setCajon(false)}>
          <aside className="flex h-full w-[82vw] max-w-72 flex-col gap-3 bg-hoja px-3 py-4" onClick={(e) => e.stopPropagation()}>
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
      <Consola />
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [listo, setListo] = useState(false);

  useEffect(() => {
    if (!getToken()) router.replace("/login/");
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
