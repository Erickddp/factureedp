"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Receipt } from "lucide-react";
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
    <main className="grid min-h-screen place-items-center bg-tinta px-4">
      <form onSubmit={entrar} className="w-full max-w-sm rounded-2xl bg-hoja p-8 shadow-2xl">
        <div className="mb-8 flex items-center gap-2">
          <Receipt className="size-7 text-cobalto" />
          <span className="text-2xl font-semibold tracking-tight">Timbra</span>
        </div>
        <div className="flex flex-col gap-4">
          <Field label="Correo">
            <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          </Field>
          <Field label="Contraseña">
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          {error && <p className="text-sm text-rojo">{error}</p>}
          <Button variant="primario" size="lg" loading={cargando} type="submit">
            Entrar
          </Button>
        </div>
      </form>
    </main>
  );
}
