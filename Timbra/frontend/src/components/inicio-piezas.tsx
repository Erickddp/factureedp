"use client";
/** Piezas visuales que comparten la página de inicio y la pantalla de entrada. Estilos en app/inicio/inicio.css. */
import { useEffect, useRef } from "react";
import { Check, FileText, Table2 } from "lucide-react";

/** Fondo de luces: degradados (sin filtros de desenfoque, que son lo caro) que sólo se mueven con transform. */
export function Aurora({ tenue }: { tenue?: boolean }) {
  return <div className={`lp-aurora${tenue ? " tenue" : ""}`} aria-hidden><i /><i /><i /></div>;
}

/** La factura en 3D: se inclina con el ratón y gira al bajar. Sólo trabaja mientras está en pantalla. */
export function FacturaViva({ chica }: { chica?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current!;
    let visible = true, pendiente = 0, mx = 0, my = 0;
    const pintar = () => {
      pendiente = 0;
      if (!visible) return;
      el.style.setProperty("--y", String(Math.min(window.scrollY, 900)));
      el.style.setProperty("--mx", mx.toFixed(3));
      el.style.setProperty("--my", my.toFixed(3));
    };
    const pedir = () => { if (!pendiente) pendiente = requestAnimationFrame(pintar); };
    const alMouse = (e: MouseEvent) => { mx = e.clientX / window.innerWidth - 0.5; my = e.clientY / window.innerHeight - 0.5; pedir(); };
    const io = new IntersectionObserver(([x]) => { visible = x.isIntersecting; });
    io.observe(el);
    window.addEventListener("scroll", pedir, { passive: true });
    window.addEventListener("mousemove", alMouse, { passive: true });
    return () => { io.disconnect(); window.removeEventListener("scroll", pedir); window.removeEventListener("mousemove", alMouse); cancelAnimationFrame(pendiente); };
  }, []);
  return (
    <div ref={ref} className={`lp-escena${chica ? " chica" : ""}`} aria-hidden>
      <div className="lp-factura">
        <div className="lp-f-cab">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="" />
          <span><b>Factura</b><small>A 128</small></span>
        </div>
        <div className="lp-f-lineas"><i style={{ width: "72%" }} /><i style={{ width: "54%" }} /><i style={{ width: "63%" }} /></div>
        <div className="lp-f-tabla">
          <span>Servicios profesionales</span><b>$10,000.00</b>
          <span>IVA 16%</span><b>$1,600.00</b>
        </div>
        <div className="lp-f-total"><span>Total</span><b>$11,600.00</b></div>
        <div className="lp-sello">TIMBRADA</div>
      </div>
      <div className="lp-ficha f1"><Check className="size-4" /> Cumple CFDI 4.0</div>
      <div className="lp-ficha f2"><FileText className="size-4" /> PDF + XML</div>
      <div className="lp-ficha f3"><Table2 className="size-4" /> Folio de tu hoja</div>
    </div>
  );
}
