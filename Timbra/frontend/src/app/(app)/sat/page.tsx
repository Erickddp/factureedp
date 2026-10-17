"use client";
/** XML del SAT: descargar con la e.firma (que no se guarda), ver lo descargado y los números que salen de esos XML. */
import { useCallback, useState } from "react";
import Link from "next/link";
import { BarChart3, CloudDownload } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { Vacio, cx } from "@/components/ui";
import { Comprobantes } from "@/components/xml/comprobantes";
import { Datos } from "@/components/xml/datos";
import { Descargar } from "@/components/xml/descargar";
import { DriveTarjeta } from "@/components/drive";

type Pestana = "descargar" | "datos";

export default function XmlSat() {
  const { emisor } = useEmisor();
  const [pestana, setPestana] = useState<Pestana>("descargar");
  const [version, setVersion] = useState(0);  // sube cada vez que entran XML nuevos: refresca tabla y gráficas
  const refrescar = useCallback(() => setVersion((v) => v + 1), []);

  if (!emisor)
    return <Vacio titulo="Da de alta el RFC con el que vas a trabajar"><Link href="/emisores" className="text-cobalto underline">Ir a Emisores</Link></Vacio>;

  return (
    <>
      <div className="mb-5">
        <p className="text-[11px] font-medium uppercase tracking-[.16em] text-grafito">XML del SAT</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">{emisor.nombre}</h1>
        <p className="font-mono text-sm text-grafito">{emisor.rfc}</p>
      </div>
      <div role="tablist" className="mb-7 grid grid-cols-2 gap-2 rounded-3xl bg-hoja p-2 ring-1 ring-linea">
        {([["descargar", "Descargar", "Baja del SAT o lee tus XML", CloudDownload], ["datos", "Datos", "Gráficas y números de esos XML", BarChart3]] as const).map(([id, texto, sub, Icono]) => (
          <button key={id} role="tab" aria-selected={pestana === id} onClick={() => setPestana(id)}
            className={cx("flex h-[72px] items-center justify-center gap-3.5 rounded-2xl px-4 text-left transition-[background,color,box-shadow] duration-150",
              pestana === id ? "bg-acento text-white shadow-boton" : "text-grafito hover:bg-tinta/5 hover:text-tinta")}>
            <Icono className="size-8 shrink-0" strokeWidth={1.75} />
            <span><span className="block text-xl font-semibold leading-tight">{texto}</span><span className={cx("hidden text-xs sm:block", pestana === id ? "opacity-85" : "opacity-70")}>{sub}</span></span>
          </button>
        ))}
      </div>

      {pestana === "descargar" ? (
        <div className="grid gap-8">
          <Descargar emisor={emisor} alCambiar={refrescar} />
          <DriveTarjeta />
          <Comprobantes emisor={emisor} version={version} />
        </div>
      ) : (
        <Datos emisor={emisor} version={version} />
      )}
    </>
  );
}
