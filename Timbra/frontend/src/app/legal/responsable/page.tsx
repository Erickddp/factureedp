import type { Metadata } from "next";
import { PaginaLegal } from "@/components/legal";
import { RESPONSABLE } from "@/lib/legal";

// Sin enlace desde los menús y fuera de buscadores: el domicilio completo se da a quien lo necesita, no se exhibe.
export const metadata: Metadata = { title: "Datos del responsable · Timbra", robots: { index: false, follow: false } };

export default function Responsable() {
  const r = RESPONSABLE;
  return (
    <PaginaLegal titulo="Datos del responsable">
      <p>La ley pide que el responsable de tus datos personales se identifique y diga dónde se le puede ubicar. Son estos:</p>
      <ul>
        <li><b>Responsable:</b> {r.nombre}, que opera {r.marca} bajo el nombre comercial EDDP Servicios.</li>
        <li><b>RFC:</b> {r.rfc}</li>
        <li><b>Domicilio:</b> {r.domicilioCompleto}</li>
        <li><b>Contacto para datos personales:</b> <a className="underline" href={`mailto:${r.correo}`}>{r.correo}</a></li>
      </ul>
    </PaginaLegal>
  );
}
