import type { Metadata } from "next";
import Link from "next/link";
import { PaginaLegal } from "@/components/legal";
import { GUIA, REVISION, VALIDADO } from "@/lib/fiscal";

export const metadata: Metadata = { title: "Guía fiscal de facturación · Timbra" };

/** Guía fiscal: lo esencial de facturar en México, cada punto con su fuente. Los datos viven en lib/fiscal.ts. */
export default function GuiaFiscal() {
  return (
    <PaginaLegal titulo="Guía fiscal de facturación">
      <p className="rounded-lg bg-alerta-suave px-3 py-2 text-sm text-alerta">
        Orientación general, no asesoría fiscal. Última revisión de Timbra: {REVISION}.{" "}
        {VALIDADO ? "Validada por un contador." : "Pendiente de validación por un contador o abogado: confirma los números de regla con la Resolución Miscelánea Fiscal vigente."}
      </p>
      <p>
        Esto es lo que más se pregunta al facturar y por qué Timbra valida lo que valida. Las reglas cambian cada año (sobre todo la Resolución Miscelánea Fiscal y
        el Anexo 20): ante la duda, consulta a tu contador. Los <Link className="underline" href="/legal/terminos/">Términos de uso</Link> explican qué te toca a ti.
      </p>
      {GUIA.map((g) => (
        <section key={g.titulo}>
          <h2>{g.titulo}</h2>
          <ul>
            {g.puntos.map((p) => (
              <li key={p.t}>
                <b>{p.t}.</b> {p.r}
                <span className="mt-0.5 block text-sm text-grafito">Fuente: {p.f}</span>
              </li>
            ))}
          </ul>
        </section>
      ))}
      <p className="text-sm text-grafito">
        CFF: Código Fiscal de la Federación · LISR: Ley del Impuesto sobre la Renta · LIVA: Ley del Impuesto al Valor Agregado · RMF: Resolución Miscelánea Fiscal.
      </p>
    </PaginaLegal>
  );
}
