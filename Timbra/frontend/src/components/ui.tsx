"use client";
import { forwardRef, useEffect, useRef, useState } from "react";
import { MoreHorizontal, X } from "lucide-react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primario" | "acento" | "secundario" | "fantasma" | "peligro";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
};
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = "secundario", size = "md", loading, className, children, disabled, type = "button", ...p },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      {...p}
      disabled={disabled || loading}
      className={cx(
        "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-[10px] font-medium transition-[background-color,border-color,box-shadow,filter,transform] duration-150 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" && "h-8 px-3 text-sm",
        size === "md" && "h-10 px-4 text-sm",
        size === "lg" && "h-12 px-6 text-base",
        variant === "primario" && "bg-primario text-sobre-primario shadow-[inset_0_1px_0_rgb(255_255_255/.14),0_1px_2px_rgb(12_22_41/.25),0_8px_18px_-10px_rgb(12_22_41/.6)] hover:-translate-y-px hover:brightness-125 active:translate-y-0 active:scale-[.98]",
        variant === "acento" && "bg-acento bg-linear-to-b from-white/12 to-transparent text-white shadow-boton hover:-translate-y-px hover:brightness-110 active:translate-y-0 active:scale-[.98]",
        variant === "secundario" && "border border-linea bg-hoja shadow-[0_1px_2px_rgb(12_22_41/.05)] hover:border-grafito/40 hover:shadow-[0_2px_6px_rgb(12_22_41/.08)] active:scale-[.98]",
        variant === "fantasma" && "hover:bg-tinta/5",
        variant === "peligro" && "bg-rojo text-white shadow-[inset_0_1px_0_rgb(255_255_255/.18),0_1px_2px_rgb(12_22_41/.2)] hover:brightness-90 active:scale-[.98]",
        className,
      )}
    >
      {loading && <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
});

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return (
    <input
      ref={ref}
      {...p}
      className={cx(
        "h-10 w-full min-w-0 rounded-[10px] border border-linea bg-hoja px-3 text-sm placeholder:text-grafito/60 hover:border-grafito/40 focus:border-acento focus:outline-none",
        className,
      )}
    />
  );
});

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...p }, ref) {
  return (
    <select ref={ref} {...p} className={cx("h-10 w-full min-w-0 rounded-[10px] border border-linea bg-hoja px-3 text-sm hover:border-grafito/40 focus:border-acento focus:outline-none", className)}>
      {children}
    </select>
  );
});

export function Field({ label, hint, children, className, error }: { label: string; hint?: string; children: React.ReactNode; className?: string; error?: string }) {
  return (
    <label className={cx("flex min-w-0 flex-col gap-1.5", className)}>
      <span className="text-[13px] font-medium text-grafito">{label}</span>
      {children}
      {error ? <span className="text-xs text-rojo">{error}</span> : hint && <span className="text-xs text-grafito/80">{hint}</span>}
    </label>
  );
}

type Tono = "neutro" | "sello" | "alerta" | "rojo" | "cobalto";
export function Badge({ tono = "neutro", children, className, punto }: { tono?: Tono; children: React.ReactNode; className?: string; punto?: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium",
        tono === "neutro" && "bg-tinta/5 text-grafito",
        tono === "sello" && "bg-sello-suave text-sello",
        tono === "alerta" && "bg-alerta-suave text-alerta",
        tono === "rojo" && "bg-rojo-suave text-rojo",
        tono === "cobalto" && "bg-cobalto-suave text-cobalto",
        className,
      )}
    >
      {punto && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="whitespace-nowrap rounded-md border border-linea bg-papel px-1.5 py-0.5 text-[11px] font-medium text-grafito shadow-[0_1px_0_var(--color-linea)]">{children}</kbd>;
}

/** Modal: hoja completa en móvil, diálogo centrado en escritorio. Esc cierra y regresa el foco. */
export function Modal({ open, onClose, title, children, wide, footer }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  wide?: boolean | "xl";
  footer?: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cerrar = useRef(onClose);
  cerrar.current = onClose;
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && cerrar.current();
    window.addEventListener("keydown", k);
    const prev = document.activeElement as HTMLElement | null;
    const t = setTimeout(() => ref.current?.querySelector<HTMLElement>("input:not([type=file]),select,textarea,[data-autofocus]")?.focus(), 30);
    document.body.style.overflow = "hidden";
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", k);
      document.body.style.overflow = "";
      prev?.focus?.();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-tinta/40 backdrop-blur-[3px] animate-velo sm:items-start sm:p-4 sm:pt-[6vh]" onMouseDown={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
        className={cx(
          "flex max-h-[100dvh] w-full flex-col rounded-t-2xl bg-hoja shadow-flotante animate-subir sm:max-h-[88vh] sm:rounded-2xl",
          wide === "xl" ? "sm:max-w-6xl" : wide ? "sm:max-w-3xl" : "sm:max-w-lg",
        )}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-linea px-5 py-4 sm:px-6">
          <h2 className="min-w-0 truncate text-lg font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg p-1.5 text-grafito transition-colors hover:bg-tinta/5 hover:text-tinta">
            <X className="size-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">{children}</div>
        {footer && <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-linea px-5 py-3 sm:px-6">{footer}</div>}
      </div>
    </div>
  );
}

/** Menú de acciones (⋯). Flechas para moverse, Enter elige, Esc cierra. */
export function Menu({ items, label = "Más acciones" }: {
  items: { label: string; icon?: React.ReactNode; onClick: () => void; peligro?: boolean; oculto?: boolean }[];
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  // Posición fija en pantalla: así una tabla con `overflow-hidden` no recorta el menú (antes escondía "Cancelar" con pocas filas)
  const [pos, setPos] = useState<{ top?: number; bottom?: number; right: number }>({ top: 0, right: 0 });
  const visibles = items.filter((i) => !i.oculto);
  const abrir = () => {
    const r = ref.current?.getBoundingClientRect();
    if (r) {
      const alto = visibles.length * 38 + 14;
      const cabeAbajo = r.bottom + alto + 8 <= window.innerHeight;
      setPos(cabeAbajo ? { top: r.bottom + 4, right: window.innerWidth - r.right } : { bottom: window.innerHeight - r.top + 4, right: window.innerWidth - r.right });
    }
    setOpen((o) => !o);
  };
  useEffect(() => {
    if (!open) return;
    const fuera = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const cerrar = () => setOpen(false);
    document.addEventListener("mousedown", fuera);
    window.addEventListener("scroll", cerrar, true);
    window.addEventListener("resize", cerrar);
    setTimeout(() => ref.current?.querySelector<HTMLButtonElement>("[role=menuitem]")?.focus(), 10);
    return () => { document.removeEventListener("mousedown", fuera); window.removeEventListener("scroll", cerrar, true); window.removeEventListener("resize", cerrar); };
  }, [open]);
  const teclas = (e: React.KeyboardEvent) => {
    const btns = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? []);
    const i = btns.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowDown") { e.preventDefault(); btns[(i + 1) % btns.length]?.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); btns[(i - 1 + btns.length) % btns.length]?.focus(); }
    if (e.key === "Escape") { e.stopPropagation(); setOpen(false); }
  };
  return (
    <div ref={ref} className="relative" onKeyDown={teclas}>
      <button aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open} onClick={abrir} className="rounded-md p-2 text-grafito hover:bg-tinta/5 hover:text-tinta">
        <MoreHorizontal className="size-4" />
      </button>
      {open && (
        <div role="menu" style={pos} className={cx("fixed z-50 w-60 rounded-xl border border-linea bg-hoja p-1 shadow-flotante animate-aparecer", pos.bottom === undefined ? "origin-top-right" : "origin-bottom-right")}>
          {visibles.map((it) => (
            <button
              key={it.label}
              role="menuitem"
              onClick={() => { setOpen(false); it.onClick(); }}
              className={cx("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-papel focus:bg-papel focus:outline-none", it.peligro && "text-rojo")}
            >
              {it.icon}
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Vacio({ titulo, children }: { titulo: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-grafito/25 bg-hoja/50 px-6 py-16 text-center animate-entrar">
      <p className="font-medium">{titulo}</p>
      {children && <div className="mt-2 text-sm text-grafito">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-center justify-between gap-3">
      <h1 className="min-w-0 text-2xl font-semibold tracking-tight sm:text-[26px]">{title}</h1>
      {children && <div className="flex flex-wrap gap-2">{children}</div>}
    </div>
  );
}

/** Pestañas accesibles: ← → cambian, Tab entra al contenido. */
export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: string; n?: number }[] }) {
  return (
    <div role="tablist" className="mb-5 inline-flex max-w-full gap-1 overflow-x-auto rounded-xl bg-tinta/[.045] p-1 shadow-[inset_0_1px_2px_rgb(12_22_41/.05)]"
      onKeyDown={(e) => {
        const i = items.findIndex((x) => x.id === value);
        if (e.key === "ArrowRight") { e.preventDefault(); onChange(items[(i + 1) % items.length].id); }
        if (e.key === "ArrowLeft") { e.preventDefault(); onChange(items[(i - 1 + items.length) % items.length].id); }
      }}>
      {items.map((t) => (
        <button key={t.id} role="tab" aria-selected={t.id === value} tabIndex={t.id === value ? 0 : -1} onClick={() => onChange(t.id)}
          className={cx("whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm transition-[color,background-color,box-shadow] duration-150",
            t.id === value ? "bg-hoja font-medium shadow-[0_1px_2px_rgb(12_22_41/.08),0_4px_10px_-4px_rgb(12_22_41/.12)] ring-1 ring-linea" : "text-grafito hover:bg-hoja/60 hover:text-tinta")}>
          {t.label}{t.n !== undefined && <span className="ml-1.5 text-xs text-grafito">{t.n}</span>}
        </button>
      ))}
    </div>
  );
}

export function Interruptor({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
        className={cx("relative mt-0.5 h-5 w-9 shrink-0 rounded-full shadow-[inset_0_1px_2px_rgb(12_22_41/.12)] transition-colors duration-200", checked ? "bg-acento" : "bg-grafito/25")}>
        <span className={cx("absolute top-0.5 size-4 rounded-full bg-white shadow-[0_1px_3px_rgb(12_22_41/.3)] transition-all duration-200", checked ? "left-[18px]" : "left-0.5")} />
      </button>
      <span className="min-w-0 text-sm"><span className="font-medium">{label}</span>{hint && <span className="block text-xs text-grafito">{hint}</span>}</span>
    </label>
  );
}

export function Cifra({ titulo, valor, nota, tono }: { titulo: string; valor: React.ReactNode; nota?: React.ReactNode; tono?: "rojo" | "alerta" | "sello" }) {
  return (
    <div className="rounded-2xl bg-hoja p-5 shadow-tarjeta ring-1 ring-linea">
      <p className="text-[11px] font-medium uppercase tracking-[.08em] text-grafito">{titulo}</p>
      <p className={cx("mt-1.5 text-[26px] font-semibold leading-tight tabular-nums tracking-tight", tono === "rojo" && "text-rojo", tono === "alerta" && "text-alerta", tono === "sello" && "text-sello")}>{valor}</p>
      {nota && <p className="mt-0.5 text-xs text-grafito">{nota}</p>}
    </div>
  );
}

export const tabla = {
  base: "w-full text-sm",
  th: "border-b border-linea bg-papel/60 px-3 py-2.5 text-left text-[11px] font-medium uppercase tracking-[.08em] text-grafito",
  td: "border-b border-linea/70 px-3 py-2.5 align-middle",
  num: "text-right tabular-nums",
};
