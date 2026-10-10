"use client";
import useSWR from "swr";
import { useRouter } from "next/navigation";
import { forwardRef, useEffect, useRef, useState } from "react";
import { AlertTriangle, Ban, Telescope } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import type { Cat } from "@/lib/types";
import { Input, Select, cx } from "./ui";

/** Select alimentado por catálogos SAT. */
export function CatSelect({ catalogo, value, onChange, filtro, ...p }: {
  catalogo: string;
  value: string;
  onChange: (v: string) => void;
  filtro?: (c: Cat) => boolean;
} & Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "onChange">) {
  const { data = [] } = useSWR<Cat[]>(`/catalogos/${catalogo}`, fetcher, { revalidateOnFocus: false });
  const items = filtro ? data.filter(filtro) : data;
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value)} {...p}>
      <option value="">Elige…</option>
      {items.map((c) => (
        <option key={c.clave} value={c.clave}>
          {c.clave} · {c.descripcion}
        </option>
      ))}
    </Select>
  );
}

/**
 * Buscador de ClaveProdServ / ClaveUnidad (52 mil claves, búsqueda en servidor).
 * Teclado: escribe → ↑↓ para moverte → Enter elige → Esc cierra.
 * Si la lista está cerrada, ↑↓ y Enter se los deja a la cuadrícula de conceptos.
 */
export const ClaveSearch = forwardRef<HTMLInputElement, {
  tipo: "prod_serv" | "unidad";
  value: string;
  onChange: (clave: string, descripcion: string) => void;
  placeholder?: string;
  inputProps?: React.InputHTMLAttributes<HTMLInputElement> & Record<string, unknown>;
}>(function ClaveSearch({ tipo, value, onChange, placeholder, inputProps }, ref) {
  const [q, setQ] = useState(value);
  const [open, setOpen] = useState(false);
  const [res, setRes] = useState<(Cat & { alertas?: { nivel: string; texto: string }[]; bloqueada?: boolean })[]>([]);
  const [act, setAct] = useState(0);
  const router = useRouter();
  const t = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => setQ(value), [value]);
  useEffect(() => {
    if (!open || q.length < 2 || q === value) return setRes([]);
    if (t.current) clearTimeout(t.current);
    t.current = setTimeout(async () => {
      try {
        setRes(await api<typeof res>(`/catalogos/buscar/${tipo}?q=${encodeURIComponent(q)}`));
        setAct(0);
      } catch {}
    }, 160);
  }, [q, open, tipo, value]);

  const elegir = (c: Cat) => {
    onChange(c.clave, c.descripcion);
    setQ(c.clave);
    setOpen(false);
    setRes([]);
  };
  const abierto = open && res.length > 0;

  return (
    <div className="relative min-w-0">
      <Input
        ref={ref}
        {...inputProps}
        value={q}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={abierto}
        autoComplete="off"
        onFocus={(e) => { setOpen(true); e.currentTarget.select(); }}
        onBlur={() => setTimeout(() => {
          setOpen(false);
          // Si escribió la clave exacta a mano, respétala
          if (q !== value && /^[A-Z0-9]{2,8}$/i.test(q)) onChange(q.toUpperCase(), "");
        }, 150)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onKeyDown={(e) => {
          if (!abierto) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setAct((a) => Math.min(a + 1, res.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setAct((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter" || e.key === "Tab") { if (res[act]) { if (e.key === "Enter") e.preventDefault(); elegir(res[act]); } }
          else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); }
        }}
      />
      {abierto && (
        <ul role="listbox" className="absolute left-0 z-30 mt-1 max-h-72 w-[min(28rem,85vw)] overflow-auto rounded-xl border border-linea bg-hoja p-1 shadow-xl">
          {res.map((c, i) => (
            <li key={c.clave} role="option" aria-selected={i === act}>
              <button type="button" tabIndex={-1} onMouseDown={() => elegir(c)} className={cx("flex w-full gap-3 rounded-lg px-3 py-2 text-left text-sm", i === act && "bg-cobalto-suave")}>
                <span className="font-semibold tabular-nums">{c.clave}</span>
                <span className="min-w-0 flex-1 text-grafito">{c.descripcion}</span>
                {c.bloqueada ? <Ban className="mt-0.5 size-4 shrink-0 text-rojo" aria-label="Bloqueada" /> : c.alertas?.length ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-alerta" aria-label={c.alertas[0].texto} /> : null}
              </button>
            </li>
          ))}
          {tipo === "prod_serv" && (
            <li className="border-t border-linea">
              <button type="button" tabIndex={-1} onMouseDown={() => router.push(`/claves?q=${encodeURIComponent(q)}`)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-cobalto hover:bg-cobalto-suave">
                <Telescope className="size-4" /> Investigar “{q}” en Claves SAT
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
});
