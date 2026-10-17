"use client";
/** Modo invitado: franja con el tiempo que le queda y ventana «Crea tu cuenta» (backend services/invitados.py). */
import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Clock, Eye, EyeOff } from "lucide-react";
import { api, setToken } from "@/lib/api";
import { Button, Field, Input, Modal } from "./ui";

export const EVENTO_CUENTA = "timbra:requiere-cuenta";

/** Entra sin registrarse (cuenta temporal de 1 hora) y va directo a XML del SAT. Hacer clic aquí es aceptar los términos y la privacidad (se dice junto al botón). */
export async function entrarComoInvitado() {
  const r = await api<{ token: string }>("/auth/invitado", { method: "POST", json: { acepto: true } });
  setToken(r.token);
  window.location.href = "/sat/";
}

export function pedirCuenta() { window.dispatchEvent(new Event(EVENTO_CUENTA)); }

const minutos = (iso: string) => Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 60000));

export function BannerInvitado({ expira }: { expira: string }) {
  const [min, setMin] = useState(() => minutos(expira));
  useEffect(() => { const t = setInterval(() => setMin(minutos(expira)), 20_000); return () => clearInterval(t); }, [expira]);
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl bg-alerta-suave px-4 py-3 text-sm text-alerta ring-1 ring-alerta/25 animate-entrar">
      <Clock className="size-4 shrink-0" />
      <p className="min-w-0 flex-1">
        <b>Modo invitado.</b> Puedes explorar y bajar tus XML; <b>todo se borra en {min} {min === 1 ? "minuto" : "minutos"}</b>. Para timbrar o conservar tu trabajo, crea tu cuenta.
      </p>
      <Button size="sm" variant="acento" onClick={pedirCuenta}>Crear mi cuenta</Button>
    </div>
  );
}

/** Se abre sola cuando el servidor dice «Crea tu cuenta…» y desde el botón de la franja. La misma cuenta pasa a ser normal. */
export function ModalCrearCuenta() {
  const [abierto, setAbierto] = useState(false);
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acepto, setAcepto] = useState(false);
  const [ver, setVer] = useState(false);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  useEffect(() => { const f = () => { setError(""); setAbierto(true); }; window.addEventListener(EVENTO_CUENTA, f); return () => window.removeEventListener(EVENTO_CUENTA, f); }, []);

  const crear = async (e: React.FormEvent) => {
    e.preventDefault();
    setCargando(true);
    setError("");
    try {
      const r = await api<{ token: string; correo_enviado: boolean }>("/auth/convertir", { method: "POST", json: { email, password, nombre, acepto } });
      setToken(r.token);
      toast.success(r.correo_enviado ? "¡Cuenta creada! Tu trabajo se conservó. Te mandamos un correo para confirmarla y recibir tus timbres de regalo."
        : "¡Cuenta creada! Tu trabajo se conservó.", { duration: 9000 });
      window.location.reload();
    } catch (err) { setError((err as Error).message); } finally { setCargando(false); }
  };

  return (
    <Modal open={abierto} onClose={() => setAbierto(false)} title="Crea tu cuenta para continuar">
      <form onSubmit={crear} className="grid gap-4">
        <p className="text-sm text-grafito">Tu trabajo de invitado se queda: lo que ya bajaste y capturaste pasa a tu cuenta. Los timbres de regalo llegan al confirmar tu correo.</p>
        <Field label="Tu nombre"><Input value={nombre} onChange={(e) => setNombre(e.target.value)} autoComplete="name" /></Field>
        <Field label="Correo"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" autoCapitalize="none" /></Field>
        <Field label="Contraseña (mínimo 8)">
          <div className="relative">
            <Input type={ver ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" className="pr-12" />
            <button type="button" onClick={() => setVer((v) => !v)} aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"}
              className="absolute right-1 top-1/2 grid size-9 -translate-y-1/2 place-items-center rounded-lg text-grafito hover:text-tinta">{ver ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
          </div>
        </Field>
        <label className="flex items-start gap-2 text-sm text-grafito">
          <input type="checkbox" checked={acepto} onChange={(e) => setAcepto(e.target.checked)} className="mt-1" />
          <span>Acepto los <Link href="/legal/terminos/" target="_blank" className="underline">Términos de uso</Link> y el <Link href="/legal/privacidad/" target="_blank" className="underline">Aviso de privacidad</Link>.</span>
        </label>
        {error && <p role="alert" className="rounded-lg bg-rojo-suave px-3 py-2 text-sm text-rojo">{error}</p>}
        <div className="flex justify-end gap-2"><Button onClick={() => setAbierto(false)}>Ahora no</Button><Button type="submit" variant="acento" loading={cargando} disabled={!acepto}>Crear mi cuenta</Button></div>
      </form>
    </Modal>
  );
}
