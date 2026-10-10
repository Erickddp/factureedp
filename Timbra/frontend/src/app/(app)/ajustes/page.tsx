"use client";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ExternalLink, Plus } from "lucide-react";
import { mostrarError } from "@/lib/errores";
import { api, fetcher } from "@/lib/api";
import type { Addenda, Pac } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { consola } from "@/lib/debug";
import { Badge, Button, Field, Input, Modal, PageHeader, Select, cx } from "@/components/ui";

const PROVEEDORES: Record<string, { label: string; campos: ("usuario" | "password" | "token" | "rfc" | "contrato" | "requestor")[] }> = {
  finkok: { label: "Finkok", campos: ["usuario", "password"] },
  swsapien: { label: "SW Sapien", campos: ["usuario", "password", "token"] },
  prodigia: { label: "Prodigia", campos: ["usuario", "password", "contrato"] },
  diverza: { label: "Diverza", campos: ["usuario", "token", "rfc"] },
  comerciodigital: { label: "Comercio Digital", campos: ["usuario", "password"] },
  mysuite: { label: "MySuite", campos: ["usuario", "requestor"] },
  demo: { label: "Demo (sin timbres reales)", campos: [] },
};

export default function Ajustes() {
  const { data: pacs = [], mutate } = useSWR<Pac[]>("/pacs", fetcher);
  const { data: addendas = [], mutate: mutA } = useSWR<Addenda[]>("/addendas", fetcher);
  const [pac, setPac] = useState<Record<string, any> | null>(null);
  const [add, setAdd] = useState<(Partial<Addenda> & { camposTxt: string }) | null>(null);
  const [probar, setProbar] = useState("");

  const guardarPac = async () => {
    const { id, rfc, contrato, requestor, ...rest } = pac!;
    try {
      await api(id ? `/pacs/${id}` : "/pacs", { method: id ? "PUT" : "POST", json: { ...rest, extra: { rfc, contrato, requestor } } });
      toast.success("PAC guardado");
      setPac(null);
      mutate();
    } catch (e) {
      mostrarError(e);
    }
  };

  const guardarAddenda = async () => {
    try {
      const campos = JSON.parse(add!.camposTxt);
      const { id, camposTxt, ...rest } = add!;
      await api(id ? `/addendas/${id}` : "/addendas", { method: id ? "PUT" : "POST", json: { ...rest, campos } });
      toast.success("Addenda guardada");
      setAdd(null);
      mutA();
    } catch (e) {
      mostrarError(e);
    }
  };

  const prueba = async () => {
    try {
      const campos = JSON.parse(add!.camposTxt) as { name: string }[];
      const datos = Object.fromEntries(campos.map((c) => [c.name, `EJEMPLO_${c.name.toUpperCase()}`]));
      const r = await api<{ xml: string }>("/addendas/probar", { method: "POST", json: { plantilla: add!.plantilla, datos } });
      setProbar(r.xml);
    } catch (e) {
      setProbar((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader title="PAC, addendas y usuarios" />
      <GuiaCompra />
      <section className="mt-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">PACs</h2>
          <Button size="sm" onClick={() => setPac({ nombre: "", proveedor: "finkok", pruebas: true })}><Plus className="size-4" /> PAC</Button>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {pacs.map((p) => <TarjetaPac key={p.id} p={p} editar={() => setPac({ ...p, ...p.extra, password: "", token: "" })} />)}
          {!pacs.length && <p className="text-sm text-grafito">Compra timbres con cualquier PAC de la lista, da de alta tus credenciales aquí y asígnalo al emisor.</p>}
        </div>
      </section>

      <section className="mt-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Addendas</h2>
          <Button size="sm" onClick={() => { setProbar(""); setAdd({ nombre: "", plantilla: "<MiAddenda>\n  <OC>{{ datos.orden_compra }}</OC>\n</MiAddenda>", camposTxt: '[{"name":"orden_compra","label":"Orden de compra","required":true}]' }); }}><Plus className="size-4" /> Addenda</Button>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {addendas.map((a) => (
            <button key={a.id} onClick={() => { setProbar(""); setAdd({ ...a, camposTxt: JSON.stringify(a.campos, null, 2) }); }} className="rounded-2xl bg-hoja p-5 text-left ring-1 ring-linea hover:ring-grafito/40">
              <p className="font-semibold">{a.nombre}</p>
              <p className="text-sm text-grafito">{a.descripcion}</p>
            </button>
          ))}
        </div>
      </section>

      <CorreoEnvio />
      <Usuarios />

      <Modal open={!!pac} onClose={() => setPac(null)} title={pac?.id ? "Editar PAC" : "Nuevo PAC"}>
        {pac && (
          <div className="flex flex-col gap-4">
            <Field label="Proveedor">
              <Select value={pac.proveedor} onChange={(e) => setPac({ ...pac, proveedor: e.target.value })}>
                {Object.entries(PROVEEDORES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </Field>
            <Field label="Nombre para identificarlo"><Input value={pac.nombre} onChange={(e) => setPac({ ...pac, nombre: e.target.value })} placeholder="Finkok despacho" /></Field>
            {PROVEEDORES[pac.proveedor].campos.map((c) => (
              <Field key={c} label={{ usuario: "Usuario", password: "Contraseña", token: "Token", rfc: "RFC", contrato: "Contrato", requestor: "Requestor" }[c]} hint={pac.id && (c === "password" || c === "token") ? "Déjalo vacío para no cambiarlo" : undefined}>
                <Input type={c === "password" || c === "token" ? "password" : "text"} value={pac[c] ?? ""} onChange={(e) => setPac({ ...pac, [c]: e.target.value })} />
              </Field>
            ))}
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={pac.pruebas} onChange={(e) => setPac({ ...pac, pruebas: e.target.checked })} className="accent-cobalto" />
              Ambiente de pruebas (desmárcalo para timbrar en serio)
            </label>
            <div className="flex justify-end gap-2"><Button onClick={() => setPac(null)}>Cancelar</Button><Button variant="primario" onClick={guardarPac}>Guardar PAC</Button></div>
          </div>
        )}
      </Modal>

      <Modal open={!!add} onClose={() => setAdd(null)} title={add?.id ? "Editar addenda" : "Nueva addenda"} wide>
        {add && (
          <div className="flex flex-col gap-4">
            <Field label="Nombre"><Input value={add.nombre ?? ""} onChange={(e) => setAdd({ ...add, nombre: e.target.value })} /></Field>
            <Field label="Descripción"><Input value={add.descripcion ?? ""} onChange={(e) => setAdd({ ...add, descripcion: e.target.value })} /></Field>
            <Field label="Plantilla XML (Jinja2)" hint="Usa {{ datos.campo }} para lo que se captura y {{ cfdi.Total }}, {{ cfdi.Serie }}… para datos de la factura">
              <textarea value={add.plantilla ?? ""} onChange={(e) => setAdd({ ...add, plantilla: e.target.value })} rows={10} className="w-full rounded-lg border border-linea bg-papel p-3 font-[ui-monospace,monospace] text-xs focus:border-cobalto focus:outline-none" />
            </Field>
            <Field label="Campos a capturar (JSON)">
              <textarea value={add.camposTxt} onChange={(e) => setAdd({ ...add, camposTxt: e.target.value })} rows={5} className="w-full rounded-lg border border-linea bg-papel p-3 font-[ui-monospace,monospace] text-xs focus:border-cobalto focus:outline-none" />
            </Field>
            {probar && <pre className="max-h-60 overflow-auto rounded-lg bg-tinta p-3 text-xs text-white">{probar}</pre>}
            <div className="flex justify-end gap-2"><Button onClick={prueba}>Probar con datos de ejemplo</Button><Button variant="primario" onClick={guardarAddenda}>Guardar addenda</Button></div>
          </div>
        )}
      </Modal>
    </>
  );
}

const OPCIONES = [
  {
    nombre: "Finkok · el que te recomiendo",
    url: "https://www.finkok.com/",
    precio: "$150 + IVA al mes cubre de 0 a 500 timbres; del 501 en adelante $0.30 + IVA c/u. Pagas al mes vencido lo que timbraste: sin paquetes, anualidad ni plazo forzoso. Tel. (55) 4624 0181.",
    pasos: [
      "Crea tu cuenta de pruebas en demo-facturacion.finkok.com (es en línea, sin costo).",
      "En ese panel da de alta el RFC de pruebas del SAT (ej. EKU9003173C9) y baja sus CSD de prueba de su wiki.",
      "En Timbra: + PAC → Finkok, pega usuario y contraseña, deja 'pruebas' marcado y presiona 'Probar timbrado'.",
      "Pide el pase a producción a integracion@finkok.com indicando el correo de tu cuenta de pruebas.",
      "En facturacion.finkok.com da de alta cada RFC emisor (tipo OnDemand) y cambia tus credenciales en Timbra; desmarca 'pruebas'.",
    ],
  },
  {
    nombre: "SW Sapien · alternativa",
    url: "https://tienda.sw.com.mx/shop",
    precio: "Prepago en su tienda en línea: 1,200 timbres $2,266 · 5,000 $5,530 · 10,000 $8,230. Los paquetes publicados dicen “para Odoo”: antes de pagar confirma con ventas que sirvan por API.",
    pasos: [
      "Pide tu usuario de pruebas gratis en su portal de desarrolladores (developers.sw.com.mx).",
      "En Timbra: + PAC → SW Sapien, usuario y contraseña (o token), 'pruebas' marcado, 'Probar timbrado'.",
      "Compra el paquete y cambia a credenciales de producción.",
    ],
  },
];


function GuiaCompra() {
  return (
    <section className="rounded-2xl bg-tinta p-6 text-white">
      <h2 className="text-lg font-semibold">Dónde comprar timbres</h2>
      <p className="mt-1 text-sm text-white/70">Precios consultados en septiembre 2026. Confírmalos al contratar.</p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {OPCIONES.map((o) => (
          <a key={o.nombre} href={o.url} target="_blank" rel="noreferrer" className="rounded-xl bg-white/10 p-4 hover:bg-white/15">
            <p className="flex items-center gap-2 font-semibold">{o.nombre} <ExternalLink className="size-4" /></p>
            <p className="mt-2 text-sm text-white/85">{o.precio}</p>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-white/70">{o.pasos.map((p) => <li key={p}>{p}</li>)}</ol>
          </a>
        ))}
      </div>
      <p className="mt-4 text-sm text-white/70">
        Tu app no se “certifica” ante el SAT: sólo el PAC está autorizado. Lo único que piden es que pruebes en su ambiente de pruebas antes de darte producción.
        Además de timbres, cada RFC necesita su CSD (Certificado de Sello Digital) vigente. Se tramita gratis en el portal del SAT con la e.firma (Certisat / SAT ID).
      </p>
    </section>
  );
}

type CorreoCfg = { configurado: boolean; host: string; port: number; user: string; remitente: string; nombre: string; tiene_password: boolean; origen: string | null };
const SERVIDORES: Record<string, { label: string; host: string; port: number }> = {
  gmail: { label: "Gmail o Google Workspace", host: "smtp.gmail.com", port: 587 },
  outlook: { label: "Outlook / Microsoft 365", host: "smtp.office365.com", port: 587 },
  otro: { label: "Otro servidor", host: "", port: 587 },
};

/** La cuenta desde la que salen facturas, estados de cuenta y recordatorios. La contraseña se guarda cifrada. */
function CorreoEnvio() {
  const { data: cfg, mutate } = useSWR<CorreoCfg>("/correo", fetcher);
  const { data: yo } = useSWR<{ admin: boolean }>("/auth/yo", fetcher);
  const [f, setF] = useState<{ tipo: string; host: string; port: string; user: string; password: string; nombre: string } | null>(null);
  const [para, setPara] = useState("");
  const [trabajando, setTrabajando] = useState("");
  const abrir = () => setF({
    tipo: !cfg?.host || cfg.host.includes("gmail") ? "gmail" : cfg.host.includes("office365") ? "outlook" : "otro",
    host: cfg?.host || SERVIDORES.gmail.host, port: String(cfg?.port || 587), user: cfg?.user ?? "", password: "", nombre: cfg?.nombre ?? "",
  });
  const guardar = async () => {
    if (!f) return;
    setTrabajando("guardar");
    try {
      mutate(await api<CorreoCfg>("/correo", { method: "PUT", json: { host: f.host, port: Number(f.port) || 587, user: f.user.trim(), password: f.password || null, nombre: f.nombre } }), false);
      toast.success("Correo guardado. Manda una prueba para confirmar.");
      setPara((p) => p || f.user.trim());
      setF(null);
    } catch (e) { mostrarError(e); } finally { setTrabajando(""); }
  };
  const probar = async () => {
    setTrabajando("probar");
    try { await api("/correo/probar", { method: "POST", json: { para } }); toast.success(`Prueba enviada a ${para}. Revisa la bandeja (y spam).`); }
    catch (e) { mostrarError(e); } finally { setTrabajando(""); }
  };
  return (
    <section className="mt-10">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Correo de envío</h2>
        {yo?.admin && <Button onClick={abrir}>{cfg?.configurado ? "Cambiar cuenta" : "Configurar correo"}</Button>}
      </div>
      <div className="rounded-2xl bg-hoja p-5 ring-1 ring-linea">
        {cfg?.configurado ? (
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-0 flex-1">
              <p className="font-medium">{cfg.nombre ? `${cfg.nombre} · ` : ""}{cfg.user}</p>
              <p className="text-sm text-grafito">Sale por {cfg.host}:{cfg.port}{cfg.origen === "env" ? " (configurado en el archivo .env)" : ""}</p>
            </div>
            <Field label="Mandar prueba a" className="w-64"><Input value={para} onChange={(e) => setPara(e.target.value)} placeholder="tu@correo.com" inputMode="email" /></Field>
            {yo?.admin && <Button variant="primario" onClick={probar} loading={trabajando === "probar"} disabled={!para.includes("@")}>Enviar prueba</Button>}
          </div>
        ) : (
          <p className="text-sm text-grafito">Sin configurar: «Mandar por correo al cliente» y los recordatorios de cobranza todavía no envían nada. Conecta la cuenta desde la que quieres que salgan tus facturas.</p>
        )}
      </div>
      <Modal open={!!f} onClose={() => setF(null)} title="Correo de envío"
        footer={<><Button onClick={() => setF(null)}>Cancelar</Button><Button variant="primario" onClick={guardar} loading={trabajando === "guardar"} disabled={!f?.user.includes("@") || !f.host || (!f.password && !cfg?.tiene_password)}>Guardar</Button></>}>
        {f && (
          <div className="grid gap-4">
            <Field label="Servicio">
              <Select value={f.tipo} onChange={(e) => { const s = SERVIDORES[e.target.value]; setF({ ...f, tipo: e.target.value, host: s.host || f.host, port: String(s.port) }); }}>
                {Object.entries(SERVIDORES).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
              </Select>
            </Field>
            <Field label="Correo desde el que se envía"><Input value={f.user} onChange={(e) => setF({ ...f, user: e.target.value })} placeholder="facturacion@tudominio.com" inputMode="email" autoComplete="off" /></Field>
            <Field label="Contraseña de aplicación" hint={cfg?.tiene_password ? "Déjala vacía para conservar la guardada" : f.tipo === "gmail" ? "16 letras que genera Google; no es la contraseña de tu cuenta" : undefined}>
              <Input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" />
            </Field>
            <Field label="Nombre que verá tu cliente (opcional)"><Input value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} placeholder="Facturación EDDP" /></Field>
            {f.tipo === "otro" && (
              <div className="grid grid-cols-[1fr_96px] gap-2">
                <Field label="Servidor SMTP"><Input value={f.host} onChange={(e) => setF({ ...f, host: e.target.value })} placeholder="smtp.tudominio.com" /></Field>
                <Field label="Puerto"><Input value={f.port} onChange={(e) => setF({ ...f, port: e.target.value.replace(/\D/g, "") })} inputMode="numeric" /></Field>
              </div>
            )}
            {f.tipo === "gmail" && (
              <ol className="list-decimal space-y-1 rounded-xl bg-papel py-3 pl-8 pr-4 text-sm text-grafito">
                <li>En tu cuenta de Google activa la <b>verificación en 2 pasos</b> (Seguridad).</li>
                <li>Abre <a className="text-cobalto underline" href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer">myaccount.google.com/apppasswords</a>, crea una llamada «Timbra» y copia las 16 letras.</li>
                <li>Pégalas aquí. Se guardan cifradas en esta computadora y puedes revocarlas en Google cuando quieras.</li>
              </ol>
            )}
          </div>
        )}
      </Modal>
    </section>
  );
}

type UsuarioFila = { id: number; email: string; usuario: string | null; nombre: string | null; admin: boolean; activo: boolean; google: boolean; emisores: number };

/** Cuentas: cada usuario ve sólo sus emisores, clientes y facturas. Sólo el administrador las da de alta. */
function Usuarios() {
  const { data: yo } = useSWR<{ admin: boolean; email: string }>("/auth/yo", fetcher);
  const { data = [], mutate } = useSWR<UsuarioFila[]>(yo?.admin ? "/auth/usuarios" : null, fetcher);
  const [nuevo, setNuevo] = useState({ email: "", usuario: "", nombre: "", password: "" });
  const [pwd, setPwd] = useState({ actual: "", nueva: "" });
  const crear = async () => {
    try {
      await api("/auth/usuarios", { method: "POST", json: { ...nuevo, usuario: nuevo.usuario || null } });
      toast.success("Cuenta creada. Esa persona sólo verá los emisores que ella dé de alta.");
      setNuevo({ email: "", usuario: "", nombre: "", password: "" });
      mutate();
    } catch (e) {
      mostrarError(e);
    }
  };
  const activar = async (u: UsuarioFila) => {
    try { await api(`/auth/usuarios/${u.id}/activo`, { method: "PUT", json: { activo: !u.activo } }); mutate(); } catch (e) { mostrarError(e); }
  };
  const cambiar = async () => {
    try {
      await api("/auth/password", { method: "POST", json: pwd });
      toast.success("Contraseña cambiada");
      setPwd({ actual: "", nueva: "" });
    } catch (e) {
      mostrarError(e);
    }
  };
  return (
    <section className="mt-10 grid gap-4 md:grid-cols-2">
      {yo?.admin && (
        <div className="rounded-2xl bg-hoja p-5 ring-1 ring-linea">
          <h2 className="text-lg font-semibold">Cuentas</h2>
          <p className="mb-3 text-sm text-grafito">Cada cuenta ve sólo sus propios emisores, clientes y facturas. Tú, como administrador, ves todo.</p>
          <ul className="mb-4 text-sm">
            {data.map((u) => (
              <li key={u.id} className={cx("flex flex-wrap items-center gap-2 border-b border-linea py-2 last:border-0", !u.activo && "opacity-50")}>
                <span className="min-w-0 flex-1"><b className="font-medium">{u.usuario || u.email}</b>{u.usuario && <span className="text-grafito"> · {u.email}</span>}
                  <span className="block text-xs text-grafito">{u.emisores} {u.emisores === 1 ? "emisor" : "emisores"}{u.google ? " · Google conectado" : ""}</span></span>
                {u.admin && <Badge tono="cobalto">admin</Badge>}
                {u.email !== yo.email && <button className="text-xs text-grafito underline hover:text-tinta" onClick={() => activar(u)}>{u.activo ? "Desactivar" : "Activar"}</button>}
              </li>
            ))}
          </ul>
          <div className="grid gap-2">
            <Input placeholder="Nombre de usuario (para entrar)" autoCapitalize="none" value={nuevo.usuario} onChange={(e) => setNuevo({ ...nuevo, usuario: e.target.value.toLowerCase().replace(/[^a-z0-9._-]/g, "") })} />
            <Input placeholder="Correo" value={nuevo.email} onChange={(e) => setNuevo({ ...nuevo, email: e.target.value })} />
            <Input placeholder="Nombre" value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} />
            <Input placeholder="Contraseña (mín. 8)" type="password" autoComplete="new-password" value={nuevo.password} onChange={(e) => setNuevo({ ...nuevo, password: e.target.value })} />
            <Button onClick={crear} disabled={!nuevo.email.includes("@") || nuevo.password.length < 8}>Crear cuenta</Button>
          </div>
        </div>
      )}
      <div className="rounded-2xl bg-hoja p-5 ring-1 ring-linea">
        <h2 className="mb-3 text-lg font-semibold">Cambiar mi contraseña</h2>
        <div className="grid gap-2">
          <Input placeholder="Contraseña actual" type="password" value={pwd.actual} onChange={(e) => setPwd({ ...pwd, actual: e.target.value })} />
          <Input placeholder="Nueva (mín. 8)" type="password" value={pwd.nueva} onChange={(e) => setPwd({ ...pwd, nueva: e.target.value })} />
          <Button variant="primario" onClick={cambiar} disabled={pwd.nueva.length < 8}>Cambiar contraseña</Button>
        </div>
      </div>
    </section>
  );
}

function TarjetaPac({ p, editar }: { p: Pac; editar: () => void }) {
  const { emisores } = useEmisor();
  const [emisorId, setEmisorId] = useState<number | "">(emisores.find((e) => e.pac_id === p.id)?.id ?? emisores[0]?.id ?? "");
  const [probando, setProbando] = useState<"" | "timbre" | "ciclo">("");
  const [res, setRes] = useState<{ ok: boolean; texto: string } | null>(null);
  const probar = async (ciclo: boolean) => {
    if (!emisorId) return;
    setProbando(ciclo ? "ciclo" : "timbre");
    setRes(null);
    try {
      const r = await api<{ ok: boolean; uuid: string; ms: number; cancelacion?: { codigo: string; ms: number }; estatus?: Record<string, string> }>(
        `/pacs/${p.id}/probar?emisor_id=${emisorId}&ciclo=${ciclo}`, { method: "POST" });
      const partes = [`Timbró en ${r.ms} ms · UUID ${r.uuid}`];
      if (r.cancelacion) partes.push(`Canceló (código ${r.cancelacion.codigo}) en ${r.cancelacion.ms} ms`);
      if (r.estatus) partes.push(`Estatus SAT: ${[r.estatus.Estado, r.estatus.EstatusCancelacion, r.estatus.error].filter(Boolean).join(" · ") || "sin respuesta"}`);
      setRes({ ok: r.ok, texto: partes.join(" → ") });
    } catch (e) {
      setRes({ ok: false, texto: (e as Error).message });
    } finally {
      setProbando("");
    }
  };
  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
      <button onClick={editar} className="text-left">
        <p className="font-semibold">{p.nombre}</p>
        <p className="text-sm text-grafito">{PROVEEDORES[p.proveedor]?.label ?? p.proveedor}</p>
        <div className="mt-2">{p.pruebas ? <Badge tono="cobalto">Ambiente de pruebas</Badge> : <Badge tono="sello">Producción</Badge>}</div>
      </button>
      {p.pruebas && emisores.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <Select value={emisorId} onChange={(e) => setEmisorId(Number(e.target.value))} className="min-w-0 flex-1" aria-label="Emisor para la prueba">
            {emisores.map((e) => <option key={e.id} value={e.id}>{e.rfc}</option>)}
          </Select>
          <Button onClick={() => probar(false)} loading={probando === "timbre"} disabled={!!probando}>Probar timbrado</Button>
          <Button onClick={() => probar(true)} loading={probando === "ciclo"} disabled={!!probando}
            title="Timbra, cancela (motivo 02) y consulta estatus: las pruebas que pide el PAC para darte producción">Probar ciclo completo</Button>
        </div>
      )}
      {res && (
        <p className={res.ok ? "break-all text-sm text-sello" : "text-sm text-rojo"}>
          {res.texto} {!res.ok && <button className="underline" onClick={() => consola.abrir()}>Ver detalle</button>}
        </p>
      )}
    </div>
  );
}
