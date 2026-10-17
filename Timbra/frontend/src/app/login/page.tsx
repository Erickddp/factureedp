"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Eye, EyeOff } from "lucide-react";
import { api, setToken } from "@/lib/api";
import { Aurora, FacturaViva } from "@/components/inicio-piezas";
import { Button, Field, Input } from "@/components/ui";
import "../inicio/inicio.css";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  const [google, setGoogle] = useState(false);
  const [yendo, setYendo] = useState(false);
  const [ver, setVer] = useState(false);  // mostrar la contraseña

  // Regreso de Google: el token (o el error) llega en el fragmento "#", que no viaja a ningún servidor
  useEffect(() => {
    const h = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    if (h.get("token") || h.get("error")) history.replaceState(null, "", window.location.pathname);
    const token = h.get("token");
    if (token) {
      setToken(token);
      const aviso = h.get("aviso");
      if (aviso) toast.success(aviso);
      router.replace(aviso ? "/" : "/facturar");
      return;
    }
    if (h.get("error")) setError(h.get("error")!);
    api<{ google: boolean }>("/auth/config").then((c) => setGoogle(c.google)).catch(() => {});
  }, [router]);

  async function entrar(e: React.FormEvent) {
    e.preventDefault();
    setCargando(true);
    setError("");
    try {
      const { token } = await api<{ token: string }>("/auth/login", { method: "POST", json: { email, password } });
      setToken(token);
      router.push("/facturar");
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
        <form onSubmit={entrar} className="lp-tarjeta-login entra" style={{ animationDelay: "120ms" }}>
          <h2>Entra a tu cuenta</h2>
          <p>Tus emisores, clientes y facturas te esperan donde los dejaste.</p>
          <div className="mt-7 flex flex-col gap-4">
            <Field label="Usuario o correo">
              <Input type="text" name="usuario" autoComplete="username" autoCapitalize="none" spellCheck={false} value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus className="h-12" />
            </Field>
            <Field label="Contraseña">
              <div className="relative">
                <Input type={ver ? "text" : "password"} name="contrasena" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required className="h-12 pr-12" />
                <button type="button" onClick={() => setVer((v) => !v)} aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"} aria-pressed={ver}
                  className="absolute right-1 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-lg text-grafito hover:text-tinta">
                  {ver ? <EyeOff className="size-[18px]" /> : <Eye className="size-[18px]" />}
                </button>
              </div>
            </Field>
            {error && <p role="alert" className="rounded-lg bg-rojo-suave px-3 py-2 text-sm text-rojo animate-entrar">{error}</p>}
            <button type="submit" disabled={cargando} className="lp-boton mediano mt-1 disabled:opacity-60">{cargando ? "Entrando…" : "Entrar"}</button>
            {google && (
              <>
                <div className="flex items-center gap-3 text-xs text-grafito"><span className="h-px flex-1 bg-linea" />o<span className="h-px flex-1 bg-linea" /></div>
                <Button size="lg" onClick={conGoogle} loading={yendo}>
                  <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden>
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38z" />
                  </svg>
                  Continuar con Google
                </Button>
              </>
            )}
          </div>
          <p className="!mt-6 text-center text-[13px]">¿Olvidaste tu contraseña? Pídele al administrador que la restablezca.<br />El acceso es por invitación. <Link href="/inicio#precios" className="text-[#86a4ff] underline-offset-4 hover:underline">Conoce Timbra</Link></p>
        </form>
      </section>
    </main>
  );
}
