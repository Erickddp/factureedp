import type { Metadata } from "next";
import Link from "next/link";
import { PaginaLegal } from "@/components/legal";
import { HISTORIAL, PROVEEDORES, RESPONSABLE } from "@/lib/legal";

export const metadata: Metadata = { title: "Centro legal y fiscal · Timbra" };

/** Punto de entrada: el resumen en lenguaje claro y los textos completos. Los datos viven en lib/legal.ts. */
export default function CentroLegal() {
  const r = RESPONSABLE;
  return (
    <PaginaLegal titulo="Centro legal y fiscal">
      <p>Lo esencial de cómo {r.marca} cuida tus datos y qué reglas aplican, en corto. Los textos completos están abajo.</p>

      <h2>En 30 segundos</h2>
      <ul>
        <li><b>Qué guardamos:</b> tu nombre, correo y contraseña (sólo como huella cifrada), los datos de tus emisores y clientes, y tus facturas y XML.</li>
        <li><b>Qué nunca guardamos:</b> tu e.firma (se usa en memoria y se olvida) ni los datos de tu tarjeta.</li>
        <li><b>Con quién lo compartimos:</b> con el SAT y el PAC lo que lleva el CFDI, y con los proveedores que operan el servicio (lista abajo). No vendemos tus datos ni los usamos para publicidad.</li>
        <li><b>Tus derechos:</b> consultar, corregir o borrar tus datos y cerrar tu cuenta tú mismo, desde Mi perfil → Mis datos.</li>
        <li><b>Lo fiscal es tuyo:</b> Timbra valida y ayuda, pero lo que facturas y cómo lo declaras lo decides tú con tu contador.</li>
      </ul>

      <h2>Los textos completos</h2>
      <ul>
        <li><Link className="underline" href="/legal/privacidad/">Aviso de privacidad</Link>: qué datos usamos, para qué y cómo ejercer tus derechos.</li>
        <li><Link className="underline" href="/legal/terminos/">Términos de uso</Link>: las reglas del servicio, los timbres y los pagos.</li>
        <li><Link className="underline" href="/legal/fiscal/">Guía fiscal de facturación</Link>: lo esencial de facturar en México, con su fuente.</li>
        <li>Contacto del responsable: <a className="underline" href={`mailto:${r.correo}`}>{r.correo}</a>.</li>
      </ul>

      <h2>Quién recibe qué</h2>
      <ul>
        {PROVEEDORES.map((p) => <li key={p.nombre}><b>{p.nombre}</b> ({p.donde}): {p.para}.</li>)}
      </ul>

      <h2>Qué ha cambiado</h2>
      {HISTORIAL.map((h) => (
        <div key={h.version}>
          <p><b>{h.fecha}</b></p>
          <ul>{h.cambios.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
      ))}
    </PaginaLegal>
  );
}
