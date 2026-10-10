"use client";
import { API } from "@/lib/api";
/** Página pública: el cliente factura su ticket. Sin login, sin menú; con la marca del negocio. */
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { CheckCircle2, FileDown } from "lucide-react";
import { Button, Field, Input, Select } from "@/components/ui";
import { RFC_RE } from "@/lib/format";

const REGIMENES: [string, string][] = [["601", "General de Ley Personas Morales"], ["603", "Personas Morales sin fines de lucro"],
  ["605", "Sueldos y Salarios"], ["606", "Arrendamiento"], ["612", "Actividades Empresariales y Profesionales"],
  ["621", "Incorporación Fiscal"], ["625", "Plataformas Tecnológicas"], ["626", "Régimen Simplificado de Confianza (RESICO)"],
  ["616", "Sin obligaciones fiscales"], ["607", "Enajenación o adquisición de bienes"], ["608", "Demás ingresos"],
  ["610", "Residentes en el extranjero"], ["611", "Dividendos"], ["614", "Intereses"], ["615", "Premios"], ["620", "Cooperativas de producción"],
  ["622", "Actividades agrícolas, ganaderas, silvícolas y pesqueras"], ["623", "Opcional para grupos de sociedades"], ["624", "Coordinados"]];
const USOS: [string, string][] = [["G03", "Gastos en general"], ["G01", "Adquisición de mercancías"], ["D01", "Honorarios médicos y hospitalarios"],
  ["D02", "Gastos médicos por incapacidad"], ["D10", "Colegiaturas"], ["I04", "Equipo de cómputo"], ["S01", "Sin efectos fiscales"], ["CP01", "Pagos"]];

type Info = { nombre: string; rfc: string; logo_b64: string | null; color: string | null };
type Hecho = { uuid: string; folio: string; total: string; firma: string };

async function pedir<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${url}`, init);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "No se pudo. Intenta de nuevo.");
  return j as T;
}

export default function Pagina() {
  return <Suspense><Autofactura /></Suspense>;
}

function Autofactura() {
  const clave = useSearchParams().get("c") ?? "";
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState("");
  const [f, setF] = useState({ folio: "", total: "", rfc: "", nombre: "", regimen_fiscal: "601", codigo_postal: "", uso_cfdi: "G03", email: "" });
  const [hecho, setHecho] = useState<Hecho | null>(null);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    if (!clave) { setError("Liga incompleta. Pídela de nuevo al negocio."); return; }
    pedir<Info>(`/portal/${encodeURIComponent(clave)}`).then(setInfo).catch((e) => setError(e.message));
  }, [clave]);

  const color = info?.color || "#111111";
  const rfcOk = RFC_RE.test(f.rfc.trim().toUpperCase());
  const enviar = async () => {
    setError("");
    if (!rfcOk) return setError("Revisa tu RFC (12 o 13 caracteres, sin guiones).");
    if (!/^\d{5}$/.test(f.codigo_postal)) return setError("El código postal debe ser el de tu constancia fiscal (5 dígitos).");
    setCargando(true);
    try {
      setHecho(await pedir<Hecho>(`/portal/${encodeURIComponent(clave)}/facturar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...f, total: f.total.replace(/[$,]/g, ""), email: f.email || null }),
      }));
    } catch (e) { setError((e as Error).message); } finally { setCargando(false); }
  };
  const liga = (formato: string) => hecho ? `${API}/portal/${encodeURIComponent(clave)}/descarga/${hecho.uuid}?firma=${hecho.firma}&formato=${formato}` : "#";

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col px-4 py-10">
      <header className="mb-8 flex items-center gap-4 pb-4" style={{ borderBottom: `3px solid ${color}` }}>
        {info?.logo_b64 && <img src={info.logo_b64} alt="" className="max-h-12 max-w-32 object-contain" />}
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold">{info?.nombre ?? "Facturación"}</h1>
          <p className="text-sm text-grafito">Factura tu ticket</p>
        </div>
      </header>

      {hecho ? (
        <section className="flex flex-col items-center gap-4 rounded-2xl bg-hoja p-8 text-center ring-1 ring-linea">
          <CheckCircle2 className="size-12" style={{ color }} />
          <div>
            <p className="text-lg font-semibold">Tu factura {hecho.folio} está lista</p>
            <p className="mt-1 break-all font-mono text-xs text-grafito">{hecho.uuid}</p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            <a href={liga("pdf")} target="_blank" rel="noreferrer"><Button variant="primario"><FileDown className="size-4" /> PDF</Button></a>
            <a href={liga("xml")}><Button><FileDown className="size-4" /> XML</Button></a>
          </div>
          {f.email && <p className="text-sm text-grafito">También la mandamos a {f.email}.</p>}
        </section>
      ) : (
        <form className="grid gap-4 rounded-2xl bg-hoja p-5 ring-1 ring-linea sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); enviar(); }}>
          <Field label="Folio del ticket"><Input autoFocus required value={f.folio} onChange={(e) => setF({ ...f, folio: e.target.value })} /></Field>
          <Field label="Total del ticket"><Input required inputMode="decimal" placeholder="$0.00" value={f.total} onChange={(e) => setF({ ...f, total: e.target.value })} /></Field>
          <Field label="RFC" className="sm:col-span-2" error={f.rfc && !rfcOk ? "RFC incompleto" : undefined}>
            <Input required value={f.rfc} onChange={(e) => setF({ ...f, rfc: e.target.value.toUpperCase().replace(/[\s-]/g, "") })} maxLength={13} autoComplete="off" />
          </Field>
          <Field label="Nombre o razón social (como en tu constancia, sin S.A. de C.V.)" className="sm:col-span-2">
            <Input required value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="Régimen fiscal" className="sm:col-span-2">
            <Select value={f.regimen_fiscal} onChange={(e) => setF({ ...f, regimen_fiscal: e.target.value })}>{REGIMENES.map(([k, t]) => <option key={k} value={k}>{k} · {t}</option>)}</Select>
          </Field>
          <Field label="Código postal fiscal"><Input required inputMode="numeric" maxLength={5} value={f.codigo_postal} onChange={(e) => setF({ ...f, codigo_postal: e.target.value.replace(/\D/g, "") })} /></Field>
          <Field label="Uso del CFDI">
            <Select value={f.uso_cfdi} onChange={(e) => setF({ ...f, uso_cfdi: e.target.value })}>{USOS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</Select>
          </Field>
          <Field label="Correo (opcional)" className="sm:col-span-2"><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          {error && <p className="rounded-lg bg-rojo-suave px-3 py-2 text-sm text-rojo sm:col-span-2">{error}</p>}
          <Button type="submit" variant="primario" size="lg" className="sm:col-span-2" loading={cargando} disabled={!info} style={{ background: color, color: "#fff" }}>Generar mi factura</Button>
        </form>
      )}
      <p className="mt-auto pt-10 text-center text-xs text-grafito">Factura electrónica CFDI 4.0 · Timbra</p>
    </main>
  );
}
