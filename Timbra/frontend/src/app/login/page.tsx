"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Eye, EyeOff } from "lucide-react";
import { api, getToken, setToken } from "@/lib/api";
import { Aurora, FacturaViva } from "@/components/inicio-piezas";
import { Button, Field, Input } from "@/components/ui";
import "../inicio/inicio.css";

type Modo = "entrar" | "crear" | "olvide" | "restablecer";

const TITULOS: Record<Modo, { h: string; p: string }> = {
  entrar: { h: "Entra a tu cuenta", p: "Tus emisores, clientes y facturas te esperan donde los dejaste." },
  crear: { h: "Crea tu cuenta", p: "Gratis para empezar. Tus datos se guardan en tu cuenta y ahí siguen cuando vuelvas, desde cualquier equipo." },
  olvide: { h: "Recupera tu contraseña", p: "Escribe tu correo y te mandamos un enlace para elegir una nueva." },
  restablecer: { h: "Elige tu contraseña nueva", p: "Mínimo 8 caracteres. Al guardarla entras a tu cuenta." },
};

export default function Login() {
  const router = useRouter();
  const [modo, setModo] = useState<Modo>("entrar");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nombre, setNombre] = useState("");
  const [acepto, setAcepto] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [cargando, setCargando] = useState(false);
  const [google, setGoogle] = useState(false);
  const [registro, setRegistro] = useState(false);  // el registro abierto lo decide el servidor
  const [yendo, setYendo] = useState(false);
  const [ver, setVer] = useState(false);  // mostrar la contraseña
  const [tokenRestablecer, setTokenRestablecer] = useState("");

  // Regreso de Google o de un enlace del correo: llegan en el fragmento "#", que no viaja a ningún servidor
  useEffect(() => {
    const h = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    if (h.get("token") || h.get("error") || h.get("verificar") || h.get("restablecer")) history.replaceState(null, "", window.location.pathname);
    const token = h.get("token");
    if (token) {
      setToken(token);
      const avisoGoogle = h.get("aviso");
      if (avisoGoogle) toast.success(avisoGoogle);
      router.replace(avisoGoogle ? "/" : "/facturar");
      return;
    }
    if (h.get("error")) setError(h.get("error")!);
    api<{ google: boolean; registro?: boolean }>("/auth/config").then((c) => { setGoogle(c.google); setRegistro(!!c.registro); }).catch(() => {});

    const verificar = h.get("verificar");
    if (verificar) {
      api<{ ya_estaba: boolean; timbres: number }>("/auth/verificar", { method: "POST", json: { token: verificar } })
        .then((r) => {
          const msg = r.ya_estaba ? "Tu correo ya estaba confirmado." : `¡Correo confirmado! Ya tienes ${r.timbres} timbres de regalo.`;
          if (getToken()) { toast.success(msg); router.replace("/"); } else setAviso(`${msg} Entra con tu correo y contraseña.`);
        })
        .catch((e) => setError((e as Error).message));
    }
    const restablecer = h.get("restablecer");
    if (restablecer) { setTokenRestablecer(restablecer); setModo("restablecer"); }
  }, [router]);

  const cambiar = (m: Modo) => { setModo(m); setError(""); setAviso(""); };

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setCargando(true);
    setError("");
    setAviso("");
    try {
      if (modo === "entrar") {
        const { token } = await api<{ token: string }>("/auth/login", { method: "POST", json: { email, password } });
        setToken(token);
        router.push("/facturar");
      } else if (modo === "crear") {
        const r = await api<{ token: string; correo_enviado: boolean }>("/auth/registro", { method: "POST", json: { email, password, nombre, acepto } });
        setToken(r.token);
        toast.success(r.correo_enviado ? "¡Cuenta creada! Te mandamos un correo para confirmarla y recibir tus timbres de regalo."
          : "¡Cuenta creada! No pudimos mandar el correo de confirmación: pídelo de nuevo desde la aplicación.", { duration: 9000 });
        router.push("/facturar");
      } else if (modo === "olvide") {
        await api("/auth/olvide", { method: "POST", json: { email } });
        setAviso("Si ese correo tiene cuenta, te mandamos un enlace (sirve 1 hora). Revisa también la carpeta de spam.");
      } else {
        const { token } = await api<{ token: string }>("/auth/restablecer", { method: "POST", json: { token: tokenRestablecer, nueva: password } });
        setToken(token);
        toast.success("Contraseña nueva guardada.");
        router.push("/facturar");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCargando(false);
    }
  }

  async function conGoogle() {
    setYendo(true);
    setError("");
    try {
      const { url } = await api<{ url: string }>("/auth/google/entrar");
      window.location.href = url;
    } catch (err) {
      setError((err as Error).message);
      setYendo(false);
    }
  }

  const t = TITULOS[modo];
  const conClave = modo !== "olvide";
  const boton = { entrar: "Entrar", crear: "Crear mi cuenta", olvide: "Mandarme el enlace", restablecer: "Guardar y entrar" }[modo];
  const enviando = { entrar: "Entrando…", crear: "Creando…", olvide: "Enviando…", restablecer: "Guardando…" }[modo];

  return (
    <main className="lp lp-login">
      <Aurora />
      <div className="lp-rejilla" aria-hidden />
      <Link href="/inicio" className="lp-volver">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="" /> <b>Timbra</b>
      </Link>

      <section className="lp-login-lado">
        <p className="lp-ceja entra"><span /> Facturación CFDI 4.0</p>
        <h1 className="entra" style={{ animationDelay: "80ms" }}>Factura en segundos.<br /><em>Sin gastar timbres en errores.</em></h1>
        <ul className="entra" style={{ animationDelay: "160ms" }}>
          <li><Check className="size-4" /> Valida RFC, régimen, uso y claves SAT antes de gastar un timbre.</li>
          <li><Check className="size-4" /> Convierte tu tabla de Excel en un lote completo de CFDI.</li>
          <li><Check className="size-4" /> PDF con tu marca, cobranza, pagos y nómina en un solo lugar.</li>
        </ul>
        <div className="entra" style={{ animationDelay: "260ms" }}><FacturaViva chica /></div>
      </section>

      <section className="lp-login-forma">
        <form onSubmit={enviar} className="lp-tarjeta-login entra" style={{ animationDelay: "120ms" }}>
          <h2>{t.h}</h2>
          <p>{t.p}</p>
          <div className="mt-7 flex flex-col gap-4">
            {modo === "crear" && (
              <Field label="Tu nombre">
                <Input type="text" name="nombre" autoComplete="name" value={nombre} onChange={(e) => setNombre(e.target.value)} className="h-12" />
              </Field>
            )}
            {modo !== "restablecer" && (
              <Field label={modo === "entrar" ? "Usuario o correo" : "Correo"}>
                <Input type={modo === "entrar" ? "text" : "email"} name="usuario" autoComplete={modo === "entrar" ? "username" : "email"} autoCapitalize="none" spellCheck={false}
                  value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus className="h-12" />
              </Field>
            )}
            {conClave && (
              <Field label={modo === "entrar" ? "Contraseña" : modo === "crear" ? "Elige una contraseña (mín. 8)" : "Contraseña nueva (mín. 8)"}>
                <div className="relative">
                  <Input type={ver ? "text" : "password"} name="contrasena" autoComplete={modo === "entrar" ? "current-password" : "new-password"} value={password}
                    onChange={(e) => setPassword(e.target.value)} required minLength={modo === "entrar" ? undefined : 8} autoFocus={modo === "restablecer"} className="h-12 pr-12" />
                  <button type="button" onClick={() => setVer((v) => !v)} aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"} aria-pressed={ver}
                    className="absolute right-1 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-lg text-grafito hover:text-tinta">
                    {ver ? <EyeOff className="size-[18px]" /> : <Eye className="size-[18px]" />}
                  </button>
                </div>
              </Field>
            )}
            {modo === "crear" && (
              <label className="flex items-start gap-2 text-[13px] leading-snug">
                <input type="checkbox" className="mt-0.5 accent-cobalto" checked={acepto} onChange={(e) => setAcepto(e.target.checked)} required />
                <span>Acepto los <Link href="/legal/terminos/" target="_blank" className="underline underline-offset-2">Términos de uso</Link> y el{" "}
                  <Link href="/legal/privacidad/" target="_blank" className="underline underline-offset-2">Aviso de privacidad</Link>.</span>
              </label>
            )}
            {error && <p role="alert" className="rounded-lg bg-rojo-suave px-3 py-2 text-sm text-rojo animate-entrar">{error}</p>}
            {aviso && <p role="status" className="rounded-lg bg-sello-suave px-3 py-2 text-sm text-sello animate-entrar">{aviso}</p>}
            <button type="submit" disabled={cargando || (modo === "crear" && !acepto)} className="lp-boton mediano mt-1 disabled:opacity-60">{cargando ? enviando : boton}</button>
            {google && (modo === "entrar" || modo === "crear") && (
              <>
                <div className="flex items-center gap-3 text-xs text-grafito"><span className="h-px flex-1 bg-linea" />o<span className="h-px flex-1 bg-linea" /></div>
                <Button size="lg" onClick={conGoogle} loading={yendo}>
                  <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden>
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38z" />
                  </svg>
                  {modo === "crear" ? "Registrarme con Google" : "Continuar con Google"}
                </Button>
              </>
            )}
          </div>
          {modo === "entrar" && (
            <p className="!mt-5 text-center text-[12px] leading-relaxed opacity-80">
              Al entrar aceptas los <Link href="/legal/terminos/" className="underline underline-offset-2">Términos de uso</Link> y el{" "}
              <Link href="/legal/privacidad/" className="underline underline-offset-2">Aviso de privacidad</Link>.
            </p>
          )}
          <p className="!mt-4 text-center text-[13px] leading-relaxed">
            {modo === "entrar" && (<>
              <button type="button" onClick={() => cambiar("olvide")} className="text-[#86a4ff] underline-offset-4 hover:underline">¿Olvidaste tu contraseña?</button><br />
              {registro
                ? <>¿Aún no tienes cuenta? <button type="button" onClick={() => cambiar("crear")} className="text-[#86a4ff] underline-offset-4 hover:underline">Crea la tuya gratis</button></>
                : <>El acceso es por invitación. <Link href="/inicio#precios" className="text-[#86a4ff] underline-offset-4 hover:underline">Conoce Timbra</Link></>}
            </>)}
            {modo !== "entrar" && (
              <button type="button" onClick={() => cambiar("entrar")} className="text-[#86a4ff] underline-offset-4 hover:underline">← Volver a entrar</button>
            )}
          </p>
        </form>
      </section>
    </main>
  );
}
