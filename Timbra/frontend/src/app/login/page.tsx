"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, setToken } from "@/lib/api";
import { Button, Field, Input } from "@/components/ui";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  const [google, setGoogle] = useState(false);
  const [yendo, setYendo] = useState(false);

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
    <main className="panel-heroe grid min-h-screen place-items-center px-4 py-10">
      <form onSubmit={entrar} className="w-full max-w-sm rounded-3xl bg-hoja p-8 text-tinta shadow-[0_0_0_1px_rgb(255_255_255/.08),0_40px_80px_-24px_rgb(3_10_30/.7)] animate-subir sm:p-9">
        <div className="mb-8 flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="" className="size-11 rounded-xl bg-black shadow-[0_8px_16px_-8px_rgb(12_22_41/.6)]" />
          <span className="leading-tight">
            <b className="block text-xl font-semibold tracking-tight">Timbra</b>
            <span className="block text-[13px] text-grafito">Facturación CFDI 4.0</span>
          </span>
        </div>
        <div className="flex flex-col gap-4">
          <Field label="Usuario o correo">
            <Input type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          </Field>
          <Field label="Contraseña">
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          {error && <p className="rounded-lg bg-rojo-suave px-3 py-2 text-sm text-rojo animate-entrar">{error}</p>}
          <Button variant="acento" size="lg" loading={cargando} type="submit" className="mt-2">
            Entrar
          </Button>
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
      </form>
    </main>
  );
}
