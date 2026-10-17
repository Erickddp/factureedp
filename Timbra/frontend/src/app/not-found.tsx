import Link from "next/link";
import { Aurora } from "@/components/inicio-piezas";
import "./inicio/inicio.css";

export const metadata = { title: "Página no encontrada · Timbra" };

export default function NoEncontrada() {
  return (
    <main className="lp" style={{ display: "grid", placeItems: "center", minHeight: "100dvh", padding: 24, textAlign: "center" }}>
      <Aurora tenue />
      <div style={{ position: "relative", display: "grid", gap: 18, justifyItems: "center" }}>
        <p className="lp-ceja"><span /> Error 404</p>
        <h1 style={{ fontSize: "clamp(32px, 5vw, 52px)", lineHeight: 1.05, letterSpacing: "-.04em", fontWeight: 650 }}>No encontramos esa página</h1>
        <p style={{ color: "var(--gris)", maxWidth: 420 }}>El enlace está mal escrito o la página ya no existe. Tus facturas no se tocaron.</p>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "center", marginTop: 8 }}>
          <Link href="/" className="lp-boton mediano" style={{ width: "auto", padding: "0 24px" }}>Ir a Timbra</Link>
          <Link href="/inicio" className="lp-boton mediano hueco" style={{ width: "auto", padding: "0 24px" }}>Página de inicio</Link>
        </div>
      </div>
    </main>
  );
}
