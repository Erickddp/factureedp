"use client";
/**
 * Página de inicio pública (antes de entrar). Todo el movimiento es CSS + un solo escucha de scroll:
 * barra de avance, parallax del héroe, aparición al hacer scroll y la sección fija «pega → revisa → timbra».
 * Video opcional: si existe /inicio.mp4 (carpeta public) se usa difuminado como fondo del héroe; si no, no pasa nada.
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, BadgeDollarSign, Check, FileText, HandCoins, Repeat, ScanSearch, ShieldCheck, Table2, Zap } from "lucide-react";
import { getToken } from "@/lib/api";
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

export default function Inicio() {
  const raiz = useRef<HTMLDivElement>(null);
  const fija = useRef<HTMLElement>(null);
  const [avance, setAvance] = useState(0); // 0..1 de la sección fija
  const [dentro, setDentro] = useState(false);

  useEffect(() => {
    setDentro(!!getToken());
    const el = raiz.current!;
    let pendiente = 0;
    const medir = () => {
      pendiente = 0;
      const total = document.documentElement.scrollHeight - window.innerHeight;
      el.style.setProperty("--y", String(window.scrollY));
      el.style.setProperty("--total", total > 0 ? String(window.scrollY / total) : "0");
      const s = fija.current;
      if (s) {
        const r = s.getBoundingClientRect();
        setAvance(Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - window.innerHeight))));
      }
    };
    const alScroll = () => { if (!pendiente) pendiente = requestAnimationFrame(medir); };
    const alMouse = (e: MouseEvent) => {
      el.style.setProperty("--mx", String(e.clientX / window.innerWidth - 0.5));
      el.style.setProperty("--my", String(e.clientY / window.innerHeight - 0.5));
    };
    // Aparición al entrar en pantalla
    const io = new IntersectionObserver((entradas) => entradas.forEach((x) => x.isIntersecting && x.target.classList.add("visto")), { threshold: 0.18 });
    el.querySelectorAll(".aparece").forEach((x) => io.observe(x));
    medir();
    window.addEventListener("scroll", alScroll, { passive: true });
    window.addEventListener("resize", alScroll);
    window.addEventListener("mousemove", alMouse, { passive: true });
    return () => { window.removeEventListener("scroll", alScroll); window.removeEventListener("resize", alScroll); window.removeEventListener("mousemove", alMouse); io.disconnect(); cancelAnimationFrame(pendiente); };
  }, []);

  const paso = avance < 0.34 ? 0 : avance < 0.67 ? 1 : 2;
  const revisadas = Math.min(FILAS.length, Math.round(Math.min(1, avance / 0.5) * FILAS.length));
  const timbradas = Math.min(FILAS.length, Math.round(Math.max(0, (avance - 0.55) / 0.4) * FILAS.length));
  const entrar = dentro ? "/" : "/login";

  return (
    <div ref={raiz} className="lp">
      <div className="lp-avance" aria-hidden />

      <header className="lp-nav">
        <Link href="/inicio" className="lp-marca">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="" /> <b>Timbra</b>
        </Link>
        <nav>
          <a href="#funciones">Funciones</a>
          <a href="#como">Cómo funciona</a>
          <Link href={entrar} className="lp-boton chico">{dentro ? "Abrir Timbra" : "Entrar"}</Link>
        </nav>
      </header>

      {/* ---------------- Héroe ---------------- */}
      <section className="lp-heroe">
        <video className="lp-video" src="/inicio.mp4" autoPlay muted loop playsInline aria-hidden onError={(e) => { e.currentTarget.style.display = "none"; }} />
        <div className="lp-aurora" aria-hidden><i /><i /><i /></div>
        <div className="lp-rejilla" aria-hidden />

        <div className="lp-heroe-texto">
          <p className="lp-ceja entra" style={{ animationDelay: "60ms" }}><span /> Facturación CFDI 4.0</p>
          <h1 className="entra" style={{ animationDelay: "140ms" }}>Factura en segundos.<br /><em>Sin gastar timbres en errores.</em></h1>
          <p className="lp-sub entra" style={{ animationDelay: "240ms" }}>
            Timbra revisa cada factura contra las reglas del SAT antes de enviarla, y convierte tu tabla de Excel en un lote completo de CFDI.
          </p>
          <div className="lp-acciones entra" style={{ animationDelay: "340ms" }}>
            <Link href={entrar} className="lp-boton">{dentro ? "Abrir Timbra" : "Entrar a Timbra"} <ArrowRight className="size-5" /></Link>
            <a href="#como" className="lp-enlace">Ver cómo funciona</a>
          </div>
        </div>

        <div className="lp-escena entra" style={{ animationDelay: "420ms" }} aria-hidden>
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
            <article key={t} className="lp-tarjeta aparece" style={{ transitionDelay: `${(i % 4) * 70}ms` }}
              onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); e.currentTarget.style.setProperty("--lx", `${e.clientX - r.left}px`); e.currentTarget.style.setProperty("--ly", `${e.clientY - r.top}px`); }}>
              <span className="lp-icono"><Icono className="size-5" /></span>
              <h3>{t}</h3>
              <p>{d}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---------------- Sección fija: pega → revisa → timbra ---------------- */}
      <section id="como" ref={fija} className="lp-fija">
        <div className="lp-fija-dentro">
          <div className="lp-fija-texto">
            <p className="lp-ceja"><span /> De tu hoja al SAT</p>
            <h2>Una tabla entra.<br />Facturas timbradas salen.</h2>
            <ol>
              {PASOS.map((p, i) => (
                <li key={p.t} className={i === paso ? "activo" : i < paso ? "hecho" : ""}>
                  <span>{i < paso ? <Check className="size-4" /> : i + 1}</span>
                  <div><b>{p.t}</b><p>{p.d}</p></div>
                </li>
              ))}
            </ol>
          </div>
          <div className="lp-hoja" aria-hidden>
            <div className="lp-hoja-barra"><i /><i /><i /><span>lote de octubre</span><b>{timbradas}/{FILAS.length} timbradas</b></div>
            {FILAS.map((f, i) => (
              <div key={f[0]} className={`lp-fila ${i < timbradas ? "timbrada" : i < revisadas ? "revisada" : ""}`} style={{ transitionDelay: `${i * 30}ms` }}>
                <span className="mono">{f[0]}</span><span>{f[1]}</span><b>{f[2]}</b>
                <em>{i < timbradas ? "Timbrada" : i < revisadas ? "Lista" : "…"}</em>
              </div>
            ))}
            <div className="lp-hoja-pie"><span style={{ width: `${Math.round(avance * 100)}%` }} /></div>
          </div>
        </div>
      </section>

      {/* ---------------- Cierre ---------------- */}
      <section className="lp-cierre">
        <div className="lp-aurora tenue" aria-hidden><i /><i /></div>
        <h2 className="aparece">Tu siguiente factura,<br />a un atajo de distancia.</h2>
        <Link href={entrar} className="lp-boton aparece">{dentro ? "Abrir Timbra" : "Entrar a Timbra"} <ArrowRight className="size-5" /></Link>
      </section>

      <footer className="lp-pie">
        <span>Timbra · EDDP Servicios</span>
        <span>El timbrado lo realiza un PAC autorizado por el SAT.</span>
      </footer>
    </div>
  );
}
