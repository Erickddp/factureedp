"use client";
/** Descarga SAT: portada que manda a la app de descarga y administración de XML (vive aparte). */
import Link from "next/link";
import { ArrowUpRight, FileUp } from "lucide-react";

// Dirección de la app de XML. Cámbiala aquí cuando quede publicada.
const URL_XML = "https://xml.erickddp.com";

const HOJAS = [
  { t: "Recibidos", s: "CFDI de tus proveedores", c: "hoja-a" },
  { t: "Emitidos", s: "Todo lo que has facturado", c: "hoja-b" },
  { t: "Conciliación", s: "SAT contra tu contabilidad", c: "hoja-c" },
];

export default function DescargaSat() {
  return (
    <div className="portada-xml relative grid min-h-[calc(100dvh-7rem)] place-items-center overflow-hidden rounded-3xl bg-primario px-6 py-14 text-center text-sobre-primario">
      <div aria-hidden className="portada-brillo" />
      <div className="relative z-10 flex max-w-xl flex-col items-center">
        <div aria-hidden className="escena-xml mb-12">
          <div className="pila-xml">
            {HOJAS.map((h) => (
              <div key={h.t} className={`hoja-xml ${h.c}`}>
                <span className="font-mono text-[10px] tracking-widest opacity-60">&lt;cfdi:Comprobante&gt;</span>
                <b className="mt-1 block text-sm text-tinta">{h.t}</b>
                <span className="block text-[11px] text-grafito">{h.s}</span>
                <i /><i /><i />
              </div>
            ))}
          </div>
        </div>
        <p className="text-[11px] font-medium uppercase tracking-[.2em] opacity-60">Descarga y administración de XML</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-[40px] sm:leading-[1.1]">Tus XML del SAT, en un solo lugar</h1>
        <p className="mt-4 max-w-md text-sm opacity-75">
          La descarga masiva, el resguardo y la conciliación de tus CFDI viven en su propia aplicación. Entra con un clic.
        </p>
        <a href={URL_XML} target="_blank" rel="noopener noreferrer" className="boton-xml group mt-9 inline-flex h-14 items-center gap-3 rounded-2xl bg-acento px-8 text-base font-semibold text-white">
          Abrir Descarga XML SAT
          <ArrowUpRight className="size-5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
        </a>
        <p className="mt-3 font-mono text-xs opacity-50">{URL_XML.replace("https://", "")}</p>
        <Link href="/sat/importar" className="mt-10 inline-flex items-center gap-2 text-sm opacity-70 underline-offset-4 hover:underline hover:opacity-100">
          <FileUp className="size-4" /> Subir XML que ya tengo y conciliar aquí
        </Link>
      </div>
    </div>
  );
}
