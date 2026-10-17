"use client";
/** «Mis datos» (dentro de Mi perfil): qué guarda Timbra de la cuenta, aviso de novedades y cerrar la cuenta. */
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { api, fetcher, setToken } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { Button, Input } from "./ui";

type Datos = {
  cuenta: { email: string; nombre: string | null; creado: string | null; google: string | null; correo_verificado: boolean };
  aceptacion: { version: string | null; vigente: string; cuando: string | null; ip: string | null };
  novedades: boolean;
  guardado: { emisores: number; clientes: number; facturas: number; plantillas: number; xml: number };
  admin: boolean;
};

const fecha = (s: string | null) => (s ? new Date(s).toLocaleString("es-MX", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

export function MisDatos() {
  const [abierto, setAbierto] = useState(false);
  const { data, mutate } = useSWR<Datos>(abierto ? "/mis-datos" : null, fetcher);
  const [cerrando, setCerrando] = useState(false);
  const [confirmar, setConfirmar] = useState("");
  const [trabajando, setTrabajando] = useState(false);

  const novedades = (acepta: boolean) =>
    api("/mis-datos/novedades", { method: "PUT", json: { acepta } }).then(() => mutate()).catch(mostrarError);
  const cerrar = async () => {
    setTrabajando(true);
    try {
      await api("/mis-datos/cerrar", { method: "POST", json: { confirmar } });
      toast.success("Tu cuenta quedó cerrada. Borraremos tus datos en un máximo de 90 días.", { duration: 9000 });
      setToken(null);
      window.location.href = "/inicio/";
    } catch (e) { mostrarError(e); setTrabajando(false); }
  };

  return (
    <div className="rounded-xl text-sm ring-1 ring-linea">
      <button type="button" onClick={() => setAbierto((a) => !a)} aria-expanded={abierto} className="flex w-full items-center justify-between px-4 py-3 text-left font-medium">
        Mis datos y privacidad <span className="text-grafito">{abierto ? "−" : "+"}</span>
      </button>
      {abierto && (
        <div className="grid gap-4 border-t border-linea px-4 py-4">
          {!data ? <p className="text-grafito">Cargando…</p> : (<>
            <div>
              <p className="mb-1.5 font-medium">Lo que Timbra guarda en tu cuenta</p>
              <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-grafito">
                <li>Emisores: <b className="text-tinta">{data.guardado.emisores}</b></li>
                <li>Clientes: <b className="text-tinta">{data.guardado.clientes}</b></li>
                <li>Facturas: <b className="text-tinta">{data.guardado.facturas}</b></li>
                <li>Plantillas: <b className="text-tinta">{data.guardado.plantillas}</b></li>
                <li>XML del SAT: <b className="text-tinta">{data.guardado.xml}</b></li>
              </ul>
              <p className="mt-2 text-grafito">Además tu nombre, correo y contraseña (sólo como huella cifrada). Tu e.firma nunca se guarda.
                Para llevarte tus emisores usa «Pasar mis emisores a otra Timbra» en <Link className="underline" href="/ajustes/">Ajustes</Link>.</p>
            </div>
            <div>
              <p className="mb-1.5 font-medium">Lo que aceptaste</p>
              <p className="text-grafito">Versión {data.aceptacion.version ?? "—"} de los Términos y el Aviso de privacidad · {fecha(data.aceptacion.cuando)}
                {data.aceptacion.ip ? ` · desde la IP ${data.aceptacion.ip}` : ""}. <Link className="underline" href="/legal/" target="_blank">Centro legal y fiscal</Link></p>
            </div>
            <label className="flex items-start gap-2">
              <input type="checkbox" className="mt-0.5 accent-cobalto" checked={data.novedades} onChange={(e) => novedades(e.target.checked)} />
              <span>Quiero recibir avisos de novedades de Timbra (opcional; no afecta el servicio).</span>
            </label>
            {!data.admin && (
              <div className="rounded-lg bg-rojo-suave px-3 py-3">
                {!cerrando ? (
                  <button type="button" className="text-rojo underline" onClick={() => setCerrando(true)}>Cerrar mi cuenta…</button>
                ) : (
                  <div className="grid gap-2">
                    <p className="text-rojo">Se cierra de inmediato y ya no podrás entrar. Borramos tus datos en un máximo de 90 días, salvo los CFDI que la ley obliga a
                      conservar. Antes, descarga tus XML y PDF. Para confirmar escribe tu correo ({data.cuenta.email}):</p>
                    <Input value={confirmar} onChange={(e) => setConfirmar(e.target.value)} placeholder={data.cuenta.email} aria-label="Correo para confirmar" />
                    <div className="flex gap-2">
                      <Button variant="peligro" size="sm" loading={trabajando} disabled={confirmar.trim().toLowerCase() !== data.cuenta.email.toLowerCase()} onClick={cerrar}>Cerrar mi cuenta</Button>
                      <Button variant="fantasma" size="sm" onClick={() => { setCerrando(false); setConfirmar(""); }}>Mejor no</Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>)}
        </div>
      )}
    </div>
  );
}
