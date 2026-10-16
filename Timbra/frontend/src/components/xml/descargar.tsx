"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { CalendarRange, CheckCircle2, CloudDownload, FileKey2, FolderOpen, KeyRound, Loader2, ShieldCheck, Square, Upload, XCircle } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { isoLocal } from "@/lib/format";
import type { Emisor } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { type Efirma, type TrabajoXml, dia, periodos, subirXml } from "@/lib/xml";
import { Button, Input, cx } from "@/components/ui";

const TIPOS = [{ id: "ambos", t: "Emitidos y recibidos" }, { id: "emitidos", t: "Sólo emitidos" }, { id: "recibidos", t: "Sólo recibidos" }];

export function Descargar({ emisor, alCambiar }: { emisor: Emisor; alCambiar: () => void }) {
  const { data: firma, mutate: mFirma } = useSWR<Efirma>(`/xml/efirma?emisor_id=${emisor.id}`, fetcher, { refreshInterval: 30_000 });
  const { data: trabajos = [], mutate: mTrabajos } = useSWR<TrabajoXml[]>(`/xml/trabajos?emisor_id=${emisor.id}`, fetcher,
    { refreshInterval: (d) => (d?.some((t) => t.estado === "curso") ? 2500 : 0) });
  const enCurso = trabajos.find((t) => t.estado === "curso");
  const ultimo = trabajos[0];
  const { data: detalle } = useSWR<TrabajoXml>(enCurso ? `/xml/trabajos/${enCurso.id}` : null, fetcher, { refreshInterval: 2500 });

  // Al terminar una descarga se refresca la tabla de abajo
  const antes = useRef<number | null>(null);
  useEffect(() => {
    if (antes.current && !enCurso) { alCambiar(); mFirma(); }
    antes.current = enCurso?.id ?? null;
  }, [enCurso, alCambiar, mFirma]);

  return (
    <div className="grid gap-5">
      <div className="grid gap-5 lg:grid-cols-2">
        <PasoFirma emisor={emisor} firma={firma} recargar={() => mFirma()} ocupada={!!enCurso} />
        <PasoPeriodo emisor={emisor} lista={!!firma?.puesta} ocupada={!!enCurso} alIniciar={() => { mTrabajos(); mFirma(); }} />
      </div>
      {enCurso && <Avance t={detalle ?? enCurso} alDetener={() => mTrabajos()} />}
      {!enCurso && ultimo && <Resultado t={ultimo} />}
      <LeerCarpeta emisor={emisor} alTerminar={alCambiar} />
    </div>
  );
}

function Tarjeta({ n, titulo, hecho, children }: { n: number; titulo: string; hecho?: boolean; children: React.ReactNode }) {
  return (
    <section className="rounded-3xl bg-hoja p-6 ring-1 ring-linea sm:p-7">
      <h2 className="mb-5 flex items-center gap-3 text-xl font-semibold tracking-tight">
        <span className={cx("grid size-9 shrink-0 place-items-center rounded-full text-sm font-semibold", hecho ? "bg-sello text-white" : "bg-primario text-sobre-primario")}>
          {hecho ? <CheckCircle2 className="size-5" /> : n}
        </span>
        {titulo}
      </h2>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------- 1 · e.firma
function Archivo({ etiqueta, ext, valor, alElegir }: { etiqueta: string; ext: string; valor: File | null; alElegir: (f: File | null) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <button type="button" onClick={() => ref.current?.click()}
      onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = [...e.dataTransfer.files].find((x) => x.name.toLowerCase().endsWith(ext)); if (f) alElegir(f); }}
      className={cx("flex min-h-24 flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed px-3 py-4 text-center transition-colors",
        valor ? "border-sello/60 bg-sello-suave/50" : "border-linea hover:border-acento/60 hover:bg-acento-suave/40")}>
      <input ref={ref} type="file" accept={ext} hidden onChange={(e) => alElegir(e.target.files?.[0] ?? null)} />
      {valor ? <CheckCircle2 className="size-6 text-sello" /> : <FileKey2 className="size-6 text-grafito" />}
      <span className="text-sm font-medium">{valor ? valor.name : etiqueta}</span>
      {!valor && <span className="text-xs text-grafito">archivo {ext}</span>}
    </button>
  );
}

function PasoFirma({ emisor, firma, recargar, ocupada }: { emisor: Emisor; firma?: Efirma; recargar: () => void; ocupada: boolean }) {
  const [cer, setCer] = useState<File | null>(null);
  const [key, setKey] = useState<File | null>(null);
  const [clave, setClave] = useState("");
  const [trabajando, setTrabajando] = useState("");
  const [prueba, setPrueba] = useState<{ ok: boolean; mensaje: string } | null>(null);
  const { setEmisorId, recargar: recargarEmisores } = useEmisor();
  useEffect(() => { setCer(null); setKey(null); setClave(""); setPrueba(null); }, [emisor.id]);

  const probar = async () => {
    setTrabajando("probar");
    try {
      const r = await api<{ ok: boolean; mensaje: string }>(`/xml/efirma/${emisor.id}/probar`, { method: "POST" });
      setPrueba(r);
      if (r.ok) toast.success(r.mensaje); else toast.error(r.mensaje);
    } catch (e) { mostrarError(e); } finally { setTrabajando(""); }
  };
  const poner = async () => {
    if (!cer || !key || !clave) return;
    setTrabajando("poner");
    try {
      const fd = new FormData();
      fd.append("cer", cer); fd.append("key", key); fd.append("password", clave);
      const r = await api<Efirma & { emisor_id: number; creado: boolean }>("/xml/efirma", { method: "POST", body: fd });
      setClave(""); setCer(null); setKey(null);
      if (r.emisor_id !== emisor.id) {  // la e.firma es de otro contribuyente: Timbra se cambia a él (y lo da de alta si hace falta)
        toast.success(r.creado ? `${r.rfc} dado de alta en tu cuenta` : `Cambiaste a ${r.rfc}`, { description: r.nombre });
        recargarEmisores();
        setEmisorId(r.emisor_id);
        setTrabajando("");
        return;
      }
      recargar();
      await probar();
    } catch (e) { mostrarError(e); setTrabajando(""); }
  };
  const olvidar = async () => {
    try { await api(`/xml/efirma/${emisor.id}`, { method: "DELETE" }); setPrueba(null); recargar(); toast.message("e.firma olvidada"); } catch (e) { mostrarError(e); }
  };

  if (firma?.puesta)
    return (
      <Tarjeta n={1} titulo="Tu e.firma está lista" hecho>
        <div className="flex items-start gap-4 rounded-2xl bg-sello-suave/60 p-5">
          <ShieldCheck className="mt-0.5 size-9 shrink-0 text-sello" />
          <div className="min-w-0 text-sm">
            <p className="text-base font-semibold">{firma.nombre || firma.rfc}</p>
            <p className="tabular-nums text-grafito">{firma.rfc} · vigente hasta el {dia(firma.vence)}</p>
            <p className="mt-2 text-grafito">{ocupada ? "En uso por la descarga." : `Se olvida sola en ${firma.minutos} min.`} No se guardó en ningún lado.</p>
            {prueba && <p className={cx("mt-2 flex items-center gap-1.5 font-medium", prueba.ok ? "text-sello" : "text-rojo")}>
              {prueba.ok ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />} {prueba.mensaje}</p>}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={probar} loading={trabajando === "probar"}><KeyRound className="size-4" /> Probar con el SAT</Button>
          <Button variant="fantasma" onClick={olvidar} disabled={ocupada}>Olvidar ahora</Button>
        </div>
      </Tarjeta>
    );

  return (
    <Tarjeta n={1} titulo="Pon tu e.firma">
      <div className="grid grid-cols-2 gap-3">
        <Archivo etiqueta="Certificado" ext=".cer" valor={cer} alElegir={setCer} />
        <Archivo etiqueta="Llave privada" ext=".key" valor={key} alElegir={setKey} />
      </div>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); poner(); }}>
        <Input type="password" autoComplete="off" placeholder="Contraseña de la llave privada" value={clave} onChange={(e) => setClave(e.target.value)} className="h-12 text-base" />
        <Button type="submit" variant="primario" size="lg" loading={trabajando !== ""} disabled={!cer || !key || !clave}>Probar e.firma</Button>
      </form>
      <p className="mt-4 flex gap-2.5 rounded-xl bg-tinta/[.04] px-4 py-3 text-sm text-grafito">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-sello" />
        <span>Por seguridad <b className="text-tinta">Timbra no guarda tu e.firma</b>. Se usa sólo en memoria para hablar con el SAT y se olvida al terminar; por eso se pide cada vez que descargas. Puede ser la de cualquier contribuyente: Timbra lee el RFC del certificado y abre ese RFC.</span>
      </p>
    </Tarjeta>
  );
}

// ---------------------------------------------------------------- 2 · periodo
function PasoPeriodo({ emisor, lista, ocupada, alIniciar }: { emisor: Emisor; lista: boolean; ocupada: boolean; alIniciar: () => void }) {
  const opciones = useMemo(() => periodos(), []);
  const [periodo, setPeriodo] = useState("mes");
  const [desde, setDesde] = useState(opciones[0].desde);
  const [hasta, setHasta] = useState(opciones[0].hasta);
  const [tipo, setTipo] = useState("ambos");
  const [cancelados, setCancelados] = useState(true);
  const [iniciando, setIniciando] = useState(false);
  const elegido = opciones.find((o) => o.id === periodo);
  const rango = elegido ?? { desde, hasta };

  const iniciar = async () => {
    setIniciando(true);
    try {
      await api("/xml/descargas", { method: "POST", json: { emisor_id: emisor.id, desde: rango.desde, hasta: rango.hasta, tipo, cancelados } });
      toast.success("Descarga iniciada. Puedes seguir trabajando: avisa aquí cuando termine.");
      alIniciar();
    } catch (e) { mostrarError(e); } finally { setIniciando(false); }
  };

  return (
    <Tarjeta n={2} titulo="¿Qué periodo quieres bajar?">
      <div className="grid grid-cols-2 gap-2.5">
        {opciones.map((o) => (
          <button key={o.id} onClick={() => setPeriodo(o.id)}
            className={cx("rounded-2xl px-4 py-3.5 text-left ring-1 transition-[background,box-shadow] duration-150",
              periodo === o.id ? "bg-primario text-sobre-primario ring-primario" : "ring-linea hover:ring-acento/50")}>
            <span className="block text-base font-semibold">{o.nombre}</span>
            <span className={cx("block text-xs", periodo === o.id ? "opacity-75" : "text-grafito")}>{o.detalle}</span>
          </button>
        ))}
        <button onClick={() => setPeriodo("otro")}
          className={cx("col-span-2 flex items-center gap-2 rounded-2xl px-4 py-3 text-left text-sm font-medium ring-1", periodo === "otro" ? "bg-primario text-sobre-primario ring-primario" : "ring-linea hover:ring-acento/50")}>
          <CalendarRange className="size-4" /> Otras fechas
        </button>
      </div>
      {periodo === "otro" && (
        <div className="mt-3 grid grid-cols-2 gap-2.5">
          <label className="grid gap-1 text-xs text-grafito">Desde<Input type="date" value={desde} max={hasta} onChange={(e) => setDesde(e.target.value)} /></label>
          <label className="grid gap-1 text-xs text-grafito">Hasta<Input type="date" value={hasta} min={desde} max={isoLocal()} onChange={(e) => setHasta(e.target.value)} /></label>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {TIPOS.map((t) => (
          <button key={t.id} onClick={() => setTipo(t.id)} className={cx("rounded-full px-3.5 py-1.5 text-sm ring-1", tipo === t.id ? "bg-acento-suave font-medium text-acento ring-acento/40" : "text-grafito ring-linea hover:text-tinta")}>{t.t}</button>
        ))}
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-grafito">
        <input type="checkbox" checked={cancelados} onChange={(e) => setCancelados(e.target.checked)} /> Revisar también cuáles están cancelados
      </label>
      <Button variant="acento" size="lg" className="mt-5 h-14 w-full text-base" onClick={iniciar} loading={iniciando} disabled={!lista || ocupada}>
        <CloudDownload className="size-5" /> {ocupada ? "Hay una descarga en curso" : lista ? "Descargar del SAT" : "Primero pon tu e.firma"}
      </Button>
      <p className="mt-2 text-center text-xs text-grafito tabular-nums">{dia(rango.desde)} al {dia(rango.hasta)}</p>
    </Tarjeta>
  );
}

// ---------------------------------------------------------------- avance y resultado
function Avance({ t, alDetener }: { t: TrabajoXml; alDetener: () => void }) {
  const lineas = (t.registro || "").trim().split("\n").slice(-7);
  return (
    <section className="rounded-3xl bg-primario p-6 text-sobre-primario sm:p-7">
      <div className="flex flex-wrap items-center gap-3">
        <Loader2 className="size-6 animate-spin" />
        <div className="min-w-0 flex-1">
          <p className="text-lg font-semibold">Descargando del SAT…</p>
          <p className="text-sm opacity-75">{t.mensaje || "Esperando a que el SAT arme los paquetes. Suele tardar de 1 a 15 minutos; puedes cerrar esta pantalla."}</p>
        </div>
        <Button variant="peligro" size="sm" onClick={() => api(`/xml/trabajos/${t.id}/cancelar`, { method: "POST" }).then(() => { toast.message("Se detiene en cuanto el SAT conteste"); alDetener(); }).catch(mostrarError)}>
          <Square className="size-3.5" /> Detener
        </Button>
      </div>
      {t.avance > 0 && <p className="mt-4 text-4xl font-semibold tabular-nums">{t.avance.toLocaleString("es-MX")} <span className="text-base font-normal opacity-70">XML nuevos</span></p>}
      {lineas[0] && <pre className="mt-4 max-h-40 overflow-auto whitespace-pre-wrap rounded-xl bg-black/25 p-3 font-mono text-[11px] leading-relaxed opacity-80">{lineas.join("\n")}</pre>}
    </section>
  );
}

function Resultado({ t }: { t: TrabajoXml }) {
  const r = t.resumen;
  const bien = t.estado === "listo";
  const dato = (n: number | undefined, etiqueta: string, tono?: string) => (
    <div><p className={cx("text-3xl font-semibold tabular-nums", tono)}>{(n ?? 0).toLocaleString("es-MX")}</p><p className="text-xs text-grafito">{etiqueta}</p></div>
  );
  return (
    <section className={cx("rounded-3xl p-6 ring-1 sm:p-7", bien ? "bg-hoja ring-linea" : "bg-alerta-suave ring-alerta/30")}>
      <p className="flex flex-wrap items-center gap-2 font-semibold">
        {bien ? <CheckCircle2 className="size-5 text-sello" /> : <XCircle className="size-5 text-alerta" />}
        {bien && r.pendientes?.length ? `Bajó lo que el SAT ya tenía listo; faltan ${r.pendientes.length} pedido(s) que el SAT sigue preparando` : { listo: "Última descarga: terminó bien", error: "La última descarga no terminó", cancelado: "Detuviste la última descarga", interrumpido: "La última descarga se interrumpió", curso: "" }[t.estado]}
        <span className="text-sm font-normal text-grafito">· {dia(t.params.desde)} al {dia(t.params.hasta)}</span>
      </p>
      {bien && (
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {dato(r.nuevos, "XML nuevos", "text-sello")}
          {dato(r.repetidos, "ya los tenías")}
          {r.estatus && dato(r.estatus.cancelados, "cancelados", r.estatus.cancelados ? "text-rojo" : undefined)}
          {r.estatus && dato(r.estatus.sin_xml, "en el SAT que aún no tienes", r.estatus.sin_xml ? "text-alerta" : undefined)}
        </div>
      )}
      {!bien && t.mensaje && <p className="mt-2 text-sm">{t.mensaje}</p>}
      {[...(r.errores ?? []), ...(r.avisos ?? [])].slice(0, 4).map((e, i) => <p key={i} className="mt-2 text-sm text-grafito">· {e}</p>)}
      {!bien && <p className="mt-3 text-sm text-grafito">Lo que ya se bajó está guardado. Pon tu e.firma y pide el mismo periodo: continúa donde se quedó, sin volver a pedirle al SAT.</p>}
    </section>
  );
}

// ---------------------------------------------------------------- XML que ya se tienen
function LeerCarpeta({ emisor, alTerminar }: { emisor: Emisor; alTerminar: () => void }) {
  const { setEmisorId, recargar: recargarEmisores } = useEmisor();
  const carpeta = useRef<HTMLInputElement>(null);
  const sueltos = useRef<HTMLInputElement>(null);
  const [avance, setAvance] = useState<{ h: number; t: number } | null>(null);
  useEffect(() => { carpeta.current?.setAttribute("webkitdirectory", ""); }, []);
  // Teléfonos y tabletas: el navegador no deja elegir carpetas (sólo archivos)
  const [celular, setCelular] = useState(false);
  useEffect(() => { setCelular(window.matchMedia("(pointer: coarse)").matches && !window.matchMedia("(pointer: fine)").matches); }, []);

  const leer = async (lista: FileList | File[] | null) => {
    const archivos = [...(lista ?? [])];
    if (!archivos.length) return;
    setAvance({ h: 0, t: archivos.length });
    try {
      if (!archivos.some((a) => /\.(xml|zip)$/i.test(a.name))) return void toast.error("Ahí no hay archivos .xml ni .zip");
      const r = await subirXml(archivos, (h, t) => setAvance({ h, t }), emisor.rfc, async (cand) => {
        const texto = cand.map((c, i) => `${i + 1}. ${c.rfc}  ${c.nombre}`).join("\n");
        const n = Number(window.prompt(`En esos XML aparecen igual de veces estos RFC.\n¿De quién es la carpeta? Escribe el número:\n\n${texto}`, "1"));
        return cand[n - 1]?.rfc ?? null;
      });
      const varios = r.contribuyentes.length > 1;
      toast.success(varios ? `${r.nuevos.toLocaleString("es-MX")} XML nuevos, repartidos en ${r.contribuyentes.length} contribuyentes`
        : `${r.nuevos.toLocaleString("es-MX")} XML nuevos de ${r.rfc}`, { duration: 15000, description: [
        ...(varios ? r.contribuyentes.map((c) => `${c.rfc} ${c.nombre}: ${c.nuevos} nuevos${c.creado ? " (dado de alta)" : ""}`)
          : [r.nombre, r.creado && "contribuyente dado de alta en tu cuenta"]),
        r.repetidos && `${r.repetidos} ya estaban`, r.ajenos && `${r.ajenos} no se pudo saber de quién son o son de otra cuenta`,
        r.invalidos && `${r.invalidos} no son CFDI`].filter(Boolean).join(" · ") + (varios ? ". Cámbialos arriba a la izquierda." : "") });
      if (r.emisor_id && r.emisor_id !== emisor.id) { recargarEmisores(); setEmisorId(r.emisor_id); }  // se abre el que más trajo
      else if (r.contribuyentes.some((c) => c.creado)) recargarEmisores();
      alTerminar();
    } catch (e) { mostrarError(e); } finally { setAvance(null); }
  };

  return (
    <section onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); leer(e.dataTransfer.files); }}
      className="flex flex-wrap items-center gap-4 rounded-3xl border-2 border-dashed border-linea px-6 py-5">
      <FolderOpen className="size-8 shrink-0 text-grafito" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">¿Ya tienes los XML? Léelos sin pedirle nada al SAT</p>
        <p className="text-sm text-grafito">
          {celular
            ? "En el celular no se pueden elegir carpetas: toca «XML o ZIP» y selecciona varios XML a la vez, o un ZIP con la carpeta completa."
            : "Elige una carpeta (con todas sus subcarpetas), o arrastra aquí tus XML o un ZIP, de uno o varios contribuyentes: Timbra reconoce de quién es cada CFDI, da de alta al que falte y los acomoda en emitidos y recibidos."}
        </p>
      </div>
      <input ref={carpeta} type="file" multiple hidden onChange={(e) => { leer(e.target.files); e.target.value = ""; }} />
      <input ref={sueltos} type="file" multiple accept=".xml,.zip,text/xml,application/xml,application/zip,application/x-zip-compressed" hidden onChange={(e) => { leer(e.target.files); e.target.value = ""; }} />
      {avance ? (
        <span className="flex items-center gap-2 text-sm text-cobalto"><Loader2 className="size-4 animate-spin" /> Leyendo {avance.h.toLocaleString("es-MX")} de {avance.t.toLocaleString("es-MX")}…</span>
      ) : (
        <span className="flex gap-2">
          {!celular && <Button onClick={() => carpeta.current?.click()}><FolderOpen className="size-4" /> Elegir carpeta</Button>}
          <Button variant={celular ? "primario" : "fantasma"} onClick={() => sueltos.current?.click()}><Upload className="size-4" /> XML o ZIP</Button>
        </span>
      )}
    </section>
  );
}
