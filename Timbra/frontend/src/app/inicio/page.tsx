"use client";
/**
 * Página de inicio pública (antes de entrar).
 * Rendimiento: nada de desenfoques animados; el scroll sólo toca transform/opacity, las variables CSS se ponen en el
 * elemento que las usa (no en la raíz) y cada sección animada es su propio componente para no repintar toda la página.
 * Video opcional: si existe /inicio.mp4 (carpeta public) se usa como fondo del héroe; si no, no pasa nada.
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, BadgeDollarSign, Check, FileText, HandCoins, Repeat, ScanSearch, ShieldCheck, Table2, Zap } from "lucide-react";
import { getToken } from "@/lib/api";
import { Aurora, FacturaViva } from "@/components/inicio-piezas";
import "./inicio.css";

const FUNCIONES = [
  { icono: Table2, t: "Lotes desde tu tabla", d: "Pega las filas de Excel o Sheets y timbra decenas de facturas con el folio que tú pusiste." },
  { icono: ShieldCheck, t: "Valida antes de timbrar", d: "Revisa RFC, régimen, uso y claves contra las reglas del SAT antes de gastar un timbre." },
  { icono: ScanSearch, t: "Claves SAT sin adivinar", d: "Escribe lo que vendes y encuentra la clave correcta en el catálogo completo, con avisos." },
  { icono: FileText, t: "PDF con tu marca", d: "Logo, color y un diseño limpio, con todos los requisitos de la representación impresa." },
  { icono: HandCoins, t: "Cobranza y pagos", d: "Saldos por cliente, complementos de pago y recordatorios para lo que te deben." },
  { icono: Repeat, t: "Recurrentes y plantillas", d: "Las facturas de cada mes, listas con un clic o programadas para el día que toca." },
  { icono: BadgeDollarSign, t: "Nómina 1.2", d: "Recibos por periodo con las recetas de cada empleado ya armadas." },
  { icono: Zap, t: "Hecha para el teclado", d: "Atajos en todo: de cliente a timbrado sin soltar las manos." },
];

const PASOS = [
  { t: "Pega tu tabla", d: "Copia las filas de tu hoja tal como están. Timbra entiende tus columnas con el perfil que configuras una sola vez." },
  { t: "Revisa cada fila", d: "Ves cliente, conceptos y total cuadrado al centavo. Lo que tenga un problema se aparta con su folio, listo para corregir." },
  { t: "Timbra y entrega", d: "Un clic timbra todo. Descargas PDF y XML juntos, con el nombre que necesitas." },
];

const FILAS = [
  ["C-101", "Consulta de especialidad", "$1,500.00"], ["C-102", "Servicios contables", "$3,480.00"], ["C-103", "Arrendamiento de local", "$9,280.00"],
  ["C-104", "Desarrollo de software", "$11,600.00"], ["C-105", "Capacitación", "$2,320.00"], ["C-106", "Honorarios", "$4,640.00"],
];

// Precios de lanzamiento. Cámbialos aquí: `porTimbre` se calcula solo.
const PLANES = [
  { nombre: "Prueba", precio: 0, timbres: 3, nota: "Para conocer Timbra", puntos: ["3 facturas gratis", "Todas las funciones", "Sin tarjeta"], destacado: false },
  { nombre: "Recarga 30", precio: 50, timbres: 30, nota: "Para empezar", puntos: ["30 timbres", "Vigencia de 12 meses", "Sin renta mensual"], destacado: false },
  { nombre: "Recarga 65", precio: 100, timbres: 65, nota: "Para despachos y negocios con movimiento", puntos: ["65 timbres", "Vigencia de 12 meses", "Sin renta mensual"], destacado: true },
  { nombre: "Recarga 140", precio: 200, timbres: 140, nota: "Mejor precio por factura", puntos: ["140 timbres", "Vigencia de 12 meses", "Sin renta mensual"], destacado: false },
];

/** Sección fija: la tabla pasa de «…» a «Lista» y a «Timbrada» conforme bajas. Sólo se repinta cuando cambia un número. */
function Demostracion() {
  const ref = useRef<HTMLElement>(null);
  const barra = useRef<HTMLSpanElement>(null);
  const [e, setE] = useState({ paso: 0, revisadas: 0, timbradas: 0 });
  useEffect(() => {
    let pendiente = 0;
    const medir = () => {
      pendiente = 0;
      const r = ref.current!.getBoundingClientRect();
      if (r.bottom < 0 || r.top > window.innerHeight) return;
      const a = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - window.innerHeight)));
      if (barra.current) barra.current.style.transform = `scaleX(${a})`;
      const n = FILAS.length;
      const sig = { paso: a < 0.34 ? 0 : a < 0.67 ? 1 : 2, revisadas: Math.min(n, Math.round(Math.min(1, a / 0.5) * n)), timbradas: Math.min(n, Math.round(Math.max(0, (a - 0.55) / 0.4) * n)) };
      setE((p) => (p.paso === sig.paso && p.revisadas === sig.revisadas && p.timbradas === sig.timbradas ? p : sig));
    };
    const pedir = () => { if (!pendiente) pendiente = requestAnimationFrame(medir); };
    medir();
    window.addEventListener("scroll", pedir, { passive: true });
    window.addEventListener("resize", pedir);
    return () => { window.removeEventListener("scroll", pedir); window.removeEventListener("resize", pedir); cancelAnimationFrame(pendiente); };
  }, []);
  return (
    <section id="como" ref={ref} className="lp-fija">
      <div className="lp-fija-dentro">
        <div className="lp-fija-texto">
          <p className="lp-ceja"><span /> De tu hoja al SAT</p>
          <h2>Una tabla entra.<br />Facturas timbradas salen.</h2>
          <ol>
            {PASOS.map((p, i) => (
              <li key={p.t} className={i === e.paso ? "activo" : i < e.paso ? "hecho" : ""}>
                <span>{i < e.paso ? <Check className="size-4" /> : i + 1}</span>
                <div><b>{p.t}</b><p>{p.d}</p></div>
              </li>
            ))}
          </ol>
        </div>
        <div className="lp-hoja" aria-hidden>
          <div className="lp-hoja-barra"><i /><i /><i /><span>lote de octubre</span><b>{e.timbradas}/{FILAS.length} timbradas</b></div>
          {FILAS.map((f, i) => (
            <div key={f[0]} className={`lp-fila ${i < e.timbradas ? "timbrada" : i < e.revisadas ? "revisada" : ""}`}>
              <span className="mono">{f[0]}</span><span>{f[1]}</span><b>{f[2]}</b>
              <em>{i < e.timbradas ? "Timbrada" : i < e.revisadas ? "Lista" : "…"}</em>
            </div>
          ))}
          <div className="lp-hoja-pie"><span ref={barra} /></div>
        </div>
      </div>
    </section>
  );
}

export default function Inicio() {
  const raiz = useRef<HTMLDivElement>(null);
  const avance = useRef<HTMLDivElement>(null);
  const [dentro, setDentro] = useState(false);

  useEffect(() => {
    setDentro(!!getToken());
    let pendiente = 0;
    const medir = () => {
      pendiente = 0;
      const total = document.documentElement.scrollHeight - window.innerHeight;
      if (avance.current) avance.current.style.transform = `scaleX(${total > 0 ? window.scrollY / total : 0})`;
    };
    const pedir = () => { if (!pendiente) pendiente = requestAnimationFrame(medir); };
    // Aparición al entrar en pantalla (una sola vez por elemento)
    const io = new IntersectionObserver((xs) => xs.forEach((x) => { if (x.isIntersecting) { x.target.classList.add("visto"); io.unobserve(x.target); } }), { threshold: 0.15 });
    raiz.current!.querySelectorAll(".aparece").forEach((x) => io.observe(x));
    window.addEventListener("scroll", pedir, { passive: true });
    return () => { window.removeEventListener("scroll", pedir); io.disconnect(); cancelAnimationFrame(pendiente); };
  }, []);

  const entrar = dentro ? "/" : "/login";

  return (
    <div ref={raiz} className="lp">
      <div ref={avance} className="lp-avance" aria-hidden />

      <header className="lp-nav">
        <Link href="/inicio" className="lp-marca">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="" /> <b>Timbra</b>
        </Link>
        <nav>
          <a href="#funciones">Funciones</a>
          <a href="#como">Cómo funciona</a>
          <a href="#precios">Precios</a>
          <Link href={entrar} className="lp-boton chico">{dentro ? "Abrir Timbra" : "Entrar"}</Link>
        </nav>
      </header>

      {/* ---------------- Héroe ---------------- */}
      <section className="lp-heroe">
        <video className="lp-video" src="/inicio.mp4" autoPlay muted loop playsInline preload="metadata" aria-hidden onError={(e) => { e.currentTarget.remove(); }} />
        <Aurora />
        <div className="lp-rejilla" aria-hidden />

        <div className="lp-heroe-texto">
          <p className="lp-ceja entra" style={{ animationDelay: "60ms" }}><span /> Facturación CFDI 4.0</p>
          <h1 className="entra" style={{ animationDelay: "140ms" }}>Factura en segundos.<br /><em>Sin gastar timbres en errores.</em></h1>
          <p className="lp-sub entra" style={{ animationDelay: "240ms" }}>
            Timbra revisa cada factura contra las reglas del SAT antes de enviarla, y convierte tu tabla de Excel en un lote completo de CFDI.
          </p>
          <div className="lp-acciones entra" style={{ animationDelay: "340ms" }}>
            <Link href={entrar} className="lp-boton">{dentro ? "Abrir Timbra" : "Entrar a Timbra"} <ArrowRight className="size-5" /></Link>
            <a href="#precios" className="lp-enlace">3 facturas gratis para probar</a>
          </div>
        </div>
        <div className="entra" style={{ animationDelay: "420ms" }}><FacturaViva /></div>
      </section>

      {/* ---------------- Cinta ---------------- */}
      <div className="lp-cinta" aria-hidden>
        <div>
          {[0, 1].map((k) => (
            <span key={k}>
              Ingreso · Nota de crédito · Complemento de pago · Factura global · Nómina · Traslado · Cancelación · A cuenta de terceros · Addendas ·
              Retenciones · IEPS · Impuestos locales ·{" "}
            </span>
          ))}
        </div>
      </div>

      {/* ---------------- Funciones ---------------- */}
      <section id="funciones" className="lp-seccion">
        <p className="lp-ceja aparece"><span /> Todo en un lugar</p>
        <h2 className="aparece">Lo que haces cada mes,<br />sin las vueltas de siempre.</h2>
        <div className="lp-tarjetas">
          {FUNCIONES.map(({ icono: Icono, t, d }, i) => (
            <article key={t} className="lp-tarjeta aparece" style={{ transitionDelay: `${(i % 4) * 60}ms` }}
              onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); e.currentTarget.style.setProperty("--lx", `${e.clientX - r.left}px`); e.currentTarget.style.setProperty("--ly", `${e.clientY - r.top}px`); }}>
              <span className="lp-icono"><Icono className="size-5" /></span>
              <h3>{t}</h3>
              <p>{d}</p>
            </article>
          ))}
        </div>
      </section>

      <Demostracion />

      {/* ---------------- Precios ---------------- */}
      <section id="precios" className="lp-seccion">
        <p className="lp-ceja aparece"><span /> Precios</p>
        <h2 className="aparece">Paga sólo lo que timbras.<br />Sin rentas ni anualidades.</h2>
        <div className="lp-planes">
          {PLANES.map((p, i) => (
            <article key={p.nombre} className={`lp-plan aparece${p.destacado ? " destacado" : ""}`} style={{ transitionDelay: `${i * 70}ms` }}>
              {p.destacado && <span className="lp-plan-cinta">Recomendada</span>}
              <h3>{p.nombre}</h3>
              <p className="lp-plan-nota">{p.nota}</p>
              <p className="lp-plan-precio">{p.precio ? <><small>$</small>{p.precio}<small> MXN</small></> : "Gratis"}</p>
              <p className="lp-plan-unidad">{p.precio ? `$${(p.precio / p.timbres).toFixed(2)} por factura` : "3 facturas, una sola vez"}</p>
              <ul>{p.puntos.map((x) => <li key={x}><Check className="size-4" /> {x}</li>)}</ul>
              <Link href={entrar} className={p.destacado ? "lp-boton mediano" : "lp-boton mediano hueco"}>{p.precio ? "Elegir" : "Probar gratis"}</Link>
            </article>
          ))}
        </div>
        <p className="lp-aviso aparece">Precios en pesos mexicanos, IVA incluido. Los timbres vencen a los 12 meses de la recarga. El acceso es por invitación mientras terminamos el lanzamiento; las recargas en línea se activan en breve.</p>
      </section>

      {/* ---------------- Cierre ---------------- */}
      <section className="lp-cierre">
        <Aurora tenue />
        <h2 className="aparece">Tu siguiente factura,<br />a un atajo de distancia.</h2>
        <Link href={entrar} className="lp-boton aparece">{dentro ? "Abrir Timbra" : "Entrar a Timbra"} <ArrowRight className="size-5" /></Link>
      </section>

      <footer className="lp-pie">
        <span>Timbra · EDDP Servicios</span>
        <span>El timbrado lo realiza un PAC autorizado por el SAT.</span>
        <span className="flex gap-5"><Link href="/legal/terminos/" className="lp-enlace !text-[13px]">Términos de uso</Link><Link href="/legal/privacidad/" className="lp-enlace !text-[13px]">Aviso de privacidad</Link></span>
      </footer>
    </div>
  );
}
