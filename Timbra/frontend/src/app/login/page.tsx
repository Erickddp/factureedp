"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setToken } from "@/lib/api";
import { Button, Field, Input } from "@/components/ui";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

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
          <Field label="Correo">
            <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          </Field>
          <Field label="Contraseña">
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          {error && <p className="rounded-lg bg-rojo-suave px-3 py-2 text-sm text-rojo animate-entrar">{error}</p>}
          <Button variant="acento" size="lg" loading={cargando} type="submit" className="mt-2">
            Entrar
          </Button>
        </div>
      </form>
    </main>
  );
}
