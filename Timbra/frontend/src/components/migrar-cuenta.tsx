"use client";
import { useRef, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { ArrowRightLeft, CheckCircle2, Download, FileUp, Loader2, ShieldCheck, TriangleAlert, Upload } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { bajarConPost } from "@/lib/xml";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Input, cx } from "@/components/ui";

type Fila = { id: number; rfc: string; nombre: string; ambiente: "demo" | "pruebas" | "produccion"; tiene_csd: boolean; clientes: number; productos: number; facturas: number; sugerido: boolean };
type Resultado = {
  rfc: string; nombre: string; estado: "nuevo" | "ya_existe" | "otra_cuenta" | "error"; motivo: string; csd: "ok" | "sin_csd" | "no_valido"; avisos: string[];
  clientes?: number; productos?: number; terceros?: number; empleados?: number; perfiles_lote?: number; plantillas?: number; facturas?: number; series?: number;
};
type Informe = { simulacro: boolean; creado: string | null; con_facturas: boolean; emisores: Resultado[] };

const ESTADO = {
  nuevo: { t: "Entra", tono: "sello" as const },
  ya_existe: { t: "Ya está aquí", tono: "neutro" as const },
  otra_cuenta: { t: "Es de otra cuenta", tono: "rojo" as const },
  error: { t: "Error", tono: "rojo" as const },
};
const AMBIENTE = { demo: "Demo", pruebas: "Pruebas", produccion: "Producción" };

/** Pasar emisores de una Timbra a otra (de tu PC a la web). El archivo va cifrado con una contraseña que tú eliges. */
export function MigrarCuenta() {
  return (
    <section className="mt-10">
      <h2 className="mb-1 flex items-center gap-2 text-lg font-semibold"><ArrowRightLeft className="size-5 text-cobalto" /> Pasar mis emisores a otra Timbra</h2>
      <p className="mb-4 max-w-3xl text-sm text-grafito">
        Para llevar tus emisores de tu computadora a la web (o al revés) sin capturarlos otra vez: el emisor con su CSD, series y folios, clientes,
        productos, plantillas y, si quieres, las facturas con su XML. <b>Exporta</b> donde están hoy e <b>importa</b> donde los quieres.
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Exportar />
        <Importar />
      </div>
    </section>
  );
}

function Exportar() {
  const { data = [], error } = useSWR<Fila[]>("/migracion/emisores", fetcher, { revalidateOnFocus: false });
  const [elegidos, setElegidos] = useState<Set<number> | null>(null);
  const [conFacturas, setConFacturas] = useState(true);
  const [clave, setClave] = useState("");
  const [repetir, setRepetir] = useState("");
  const [trabajando, setTrabajando] = useState(false);
  const sel = elegidos ?? new Set(data.filter((f) => f.sugerido).map((f) => f.id));  // los RFC de prueba del SAT no vienen marcados
  const alternar = (id: number) => setElegidos(() => { const n = new Set(sel); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const claveOk = clave.length >= 10 && clave === repetir;

  const exportar = async () => {
    setTrabajando(true);
    try {
      await bajarConPost("/migracion/exportar", { emisor_ids: [...sel], con_facturas: conFacturas, clave }, "cuenta_timbra.timbracuenta");
      toast.success("Archivo guardado. Llévalo a la otra Timbra e impórtalo con la misma contraseña.", { duration: 9000 });
      setClave(""); setRepetir("");
    } catch (e) { mostrarError(e); } finally { setTrabajando(false); }
  };

  return (
    <div className="flex flex-col gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
      <p className="flex items-center gap-2 font-semibold"><Download className="size-4" /> 1 · Exportar (donde están ahora)</p>
      {error ? <p className="text-sm text-rojo">{(error as Error).message}</p> : !data.length ? <p className="text-sm text-grafito">No hay emisores en esta Timbra.</p> : (
        <ul className="divide-y divide-linea rounded-xl ring-1 ring-linea">
          {data.map((f) => (
            <li key={f.id}>
              <label className="flex cursor-pointer items-start gap-3 px-3 py-2.5 text-sm hover:bg-papel">
                <input type="checkbox" className="mt-1 accent-cobalto" checked={sel.has(f.id)} onChange={() => alternar(f.id)} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{f.nombre}</span>
                  <span className="block text-xs text-grafito">
                    <span className="font-mono">{f.rfc}</span> · {f.clientes} clientes · {f.facturas} facturas · {f.tiene_csd ? "con CSD" : "sin CSD"}
                    {!f.sugerido && " · de pruebas del SAT (no vale ante el SAT)"}
                  </span>
                </span>
                <Badge tono={f.ambiente === "produccion" ? "sello" : f.ambiente === "pruebas" ? "cobalto" : "alerta"}>{AMBIENTE[f.ambiente]}</Badge>
              </label>
            </li>
          ))}
        </ul>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="accent-cobalto" checked={conFacturas} onChange={(e) => setConFacturas(e.target.checked)} />
        Incluir las facturas timbradas con su XML (para ver el historial, cobranza y que los folios sigan)
      </label>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-[13px] text-grafito">Contraseña del archivo (mín. 10)
          <Input type="password" autoComplete="new-password" value={clave} onChange={(e) => setClave(e.target.value)} /></label>
        <label className="flex flex-col gap-1 text-[13px] text-grafito">Repítela
          <Input type="password" autoComplete="new-password" value={repetir} onChange={(e) => setRepetir(e.target.value)} /></label>
      </div>
      {clave && repetir && clave !== repetir && <p className="text-xs text-rojo">Las dos contraseñas no coinciden.</p>}
      <p className="flex gap-2 text-xs text-grafito"><ShieldCheck className="size-4 shrink-0 text-sello" />
        El archivo lleva tus llaves privadas (CSD): va cifrado con esta contraseña, que Timbra no guarda. Si la pierdes no se puede abrir.
        Bórralo cuando termines de importar.</p>
      <Button variant="primario" className="self-start" onClick={exportar} loading={trabajando} disabled={!sel.size || !claveOk}>
        <Download className="size-4" /> Exportar {sel.size ? `${sel.size} ${sel.size === 1 ? "emisor" : "emisores"}` : ""}
      </Button>
    </div>
  );
}

function Importar() {
  const { recargar, setEmisorId } = useEmisor();
  const entrada = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [clave, setClave] = useState("");
  const [trabajando, setTrabajando] = useState<"" | "revisar" | "importar">("");
  const [informe, setInforme] = useState<Informe | null>(null);
  const [error, setError] = useState("");

  const enviar = async (simular: boolean) => {
    if (!archivo) return;
    setTrabajando(simular ? "revisar" : "importar");
    setError("");
    try {
      const fd = new FormData();
      fd.append("archivo", archivo, archivo.name);
      fd.append("clave", clave);
      fd.append("simular", simular ? "true" : "false");
      const r = await api<Informe>("/migracion/importar", { method: "POST", body: fd });
      setInforme(r);
      if (!simular) {
        recargar();
        const primero = r.emisores.find((e) => e.estado === "nuevo");
        toast.success(`Listo: ${r.emisores.filter((e) => e.estado === "nuevo").length} emisor(es) importados.`, { duration: 9000 });
        if (primero) api<{ id: number; rfc: string }[]>("/emisores").then((es) => { const e = es.find((x) => x.rfc === primero.rfc); if (e) setEmisorId(e.id); }).catch(() => {});
        setClave("");
      }
    } catch (e) { setError((e as Error).message); setInforme(null); } finally { setTrabajando(""); }
  };
  const nuevos = informe?.emisores.filter((e) => e.estado === "nuevo").length ?? 0;
  const n = (x?: number) => (x ?? 0).toLocaleString("es-MX");

  return (
    <div className="flex flex-col gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea">
      <p className="flex items-center gap-2 font-semibold"><Upload className="size-4" /> 2 · Importar (donde los quieres)</p>
      <input ref={entrada} type="file" accept=".timbracuenta" hidden onChange={(e) => { setArchivo(e.target.files?.[0] ?? null); setInforme(null); setError(""); e.target.value = ""; }} />
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => entrada.current?.click()}><FileUp className="size-4" /> {archivo ? "Cambiar archivo" : "Elegir archivo .timbracuenta"}</Button>
        {archivo && <span className="min-w-0 truncate text-sm text-grafito">{archivo.name} · {(archivo.size / 1024).toLocaleString("es-MX", { maximumFractionDigits: 0 })} KB</span>}
      </div>
      <label className="flex flex-col gap-1 text-[13px] text-grafito">Contraseña del archivo
        <Input type="password" autoComplete="off" value={clave} onChange={(e) => { setClave(e.target.value); setError(""); }} disabled={!archivo} /></label>
      <Button className="self-start" onClick={() => enviar(true)} loading={trabajando === "revisar"} disabled={!archivo || !clave || !!trabajando}>
        <CheckCircle2 className="size-4" /> Revisar archivo (no guarda nada)
      </Button>
      {error && <p className="flex gap-2 rounded-xl bg-rojo-suave px-3 py-2 text-sm text-rojo"><TriangleAlert className="mt-0.5 size-4 shrink-0" /> {error}</p>}

      {informe && (
        <div className="flex flex-col gap-3" aria-live="polite">
          <p className="text-sm font-medium">{informe.simulacro ? "Esto es lo que pasaría al importar:" : "Esto se importó:"}</p>
          <ul className="flex flex-col gap-2">
            {informe.emisores.map((e) => (
              <li key={e.rfc} className="rounded-xl bg-papel p-3 text-sm ring-1 ring-linea">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0"><b className="font-mono text-xs">{e.rfc}</b> <span className="text-grafito">{e.nombre}</span></span>
                  <Badge tono={ESTADO[e.estado].tono}>{ESTADO[e.estado].t}</Badge>
                </div>
                {e.estado === "nuevo" ? (
                  <p className="mt-1 text-xs text-grafito">
                    {n(e.clientes)} clientes · {n(e.productos)} productos · {n(e.facturas)} facturas · {n(e.plantillas)} plantillas · {n(e.series)} series
                    · CSD: {e.csd === "ok" ? "cargado ✓" : e.csd === "no_valido" ? "no se pudo cargar" : "no traía"}
                  </p>
                ) : <p className="mt-1 text-xs text-grafito">{e.motivo}</p>}
                {e.avisos.map((a, i) => <p key={i} className="mt-1 text-xs text-alerta">· {a}</p>)}
              </li>
            ))}
          </ul>
          {informe.simulacro && nuevos > 0 && (
            <Button variant="primario" className="self-start" onClick={() => enviar(false)} loading={trabajando === "importar"} disabled={!!trabajando}>
              {trabajando === "importar" ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />} Importar {nuevos} {nuevos === 1 ? "emisor" : "emisores"}
            </Button>
          )}
          {informe.simulacro && nuevos === 0 && <p className="text-sm text-grafito">No hay nada nuevo que importar.</p>}
          {!informe.simulacro && nuevos > 0 && (
            <p className={cx("flex gap-2 rounded-xl bg-alerta-suave px-3 py-2 text-sm text-alerta")}><TriangleAlert className="mt-0.5 size-4 shrink-0" />
              Desde ahora factura sólo desde esta Timbra. Si sigues timbrando los mismos emisores en la otra, los folios se repetirían.
              Revisa en Emisores que cada uno tenga su PAC.</p>
          )}
        </div>
      )}
    </div>
  );
}
