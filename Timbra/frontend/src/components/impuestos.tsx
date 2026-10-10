"use client";
import { GRUPOS_IMPUESTOS } from "@/lib/format";

/** <option>s agrupados de combinaciones de impuestos (usar dentro de un <Select>). */
export function OpcionesImpuestos({ frontera }: { frontera?: boolean }) {
  const grupos = frontera
    ? GRUPOS_IMPUESTOS.map((g) => ({ ...g, items: Object.fromEntries(Object.entries(g.items).sort(([a], [b]) => Number(b.includes("8%")) - Number(a.includes("8%")))) }))
    : GRUPOS_IMPUESTOS;
  return (
    <>
      {grupos.map((g) => (
        <optgroup key={g.grupo} label={g.grupo}>
          {Object.keys(g.items).map((k) => <option key={k} value={k}>{k}</option>)}
        </optgroup>
      ))}
      <option value="Personalizado" disabled>Personalizado</option>
    </>
  );
}
