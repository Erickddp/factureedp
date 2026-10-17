import Link from "next/link";
import { RESPONSABLE, VIGENTE_DESDE, PENDIENTE } from "@/lib/legal";

/** Marco común de las páginas legales: legible, imprimible y sin sesión. */
export function PaginaLegal({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div className="min-h-dvh bg-papel text-tinta">
      <header className="border-b border-linea bg-hoja">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link href="/inicio/" className="flex items-center gap-2 font-semibold">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="" className="size-7" /> {RESPONSABLE.marca}
          </Link>
          <nav className="flex gap-4 text-sm text-grafito">
            <Link href="/legal/" className="hover:text-tinta">Centro legal</Link>
            <Link href="/legal/terminos/" className="hover:text-tinta">Términos</Link>
            <Link href="/legal/privacidad/" className="hover:text-tinta">Privacidad</Link>
            <Link href="/legal/fiscal/" className="hover:text-tinta">Guía fiscal</Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6 [&_h2]:mt-10 [&_h2]:text-lg [&_h2]:font-semibold [&_li]:mt-1.5 [&_p]:mt-3 [&_p]:leading-relaxed [&_ul]:mt-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:leading-relaxed">
        <h1 className="text-3xl font-semibold tracking-tight">{titulo}</h1>
        <p className="!mt-2 text-sm text-grafito">Vigente desde el {VIGENTE_DESDE}.</p>
        {children}
        <p className="!mt-12 border-t border-linea pt-6 text-sm text-grafito">
          Dudas sobre este documento: <a className="underline" href={`mailto:${RESPONSABLE.correo}`}>{RESPONSABLE.correo}</a>
        </p>
      </main>
    </div>
  );
}

/** Dato del responsable; si falta llenarlo se ve resaltado para que nadie lo publique así sin darse cuenta. */
export function Dato({ v }: { v: string }) {
  return PENDIENTE(v) ? <mark className="rounded bg-alerta-suave px-1 text-alerta">{v}</mark> : <>{v}</>;
}
