"use client";
import Link from "next/link";
import useSWR from "swr";
import { toast } from "sonner";
import { CalendarClock, Trash2, Zap } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { dinero } from "@/lib/format";
import type { Plantilla } from "@/lib/types";
import { useEmisor } from "@/components/emisor-context";
import { Badge, Button, Kbd, PageHeader, Vacio } from "@/components/ui";

function totalAprox(p: Plantilla["payload"]) {
  return (p.conceptos ?? []).reduce((s: number, c: any) => s + Number(c.cantidad || 0) * Number(c.valor_unitario || 0), 0);
}

export default function Plantillas() {
  const { emisor } = useEmisor();
  const { data = [], mutate } = useSWR<Plantilla[]>(emisor ? `/plantillas?emisor_id=${emisor.id}` : null, fetcher);

  const borrar = async (p: Plantilla) => {
    if (!confirm(`¿Borrar la plantilla "${p.nombre}"?`)) return;
    await api(`/plantillas/${p.id}`, { method: "DELETE" });
    toast.success("Plantilla borrada");
    mutate();
  };

  return (
    <>
      <PageHeader title="Plantillas">
        <Link href="/recurrentes"><Button><CalendarClock className="size-4" /> Recurrentes y favoritas</Button></Link>
      </PageHeader>
      {!data.length ? (
        <Vacio titulo="Aún no guardas plantillas">
          En Facturar arma la factura que repites cada mes (iguala, renta, honorarios) y presiona “Guardar como plantilla”.
        </Vacio>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center gap-3 rounded-2xl bg-hoja p-4 ring-1 ring-linea sm:flex-nowrap sm:gap-4 sm:p-5">
              <div className="min-w-0 basis-full sm:basis-auto sm:flex-1">
                <p className="truncate font-semibold">{p.nombre}</p>
                <p className="truncate text-sm text-grafito">
                  {p.payload.publico_general ? "Público en general" : p.cliente_nombre ?? "Cualquier cliente"} · {(p.payload.conceptos ?? []).length} concepto(s) · subtotal {dinero(totalAprox(p.payload))}
                </p>
                <p className="flex flex-wrap items-center gap-1.5 text-xs text-grafito/80">Usada {p.usos} {p.usos === 1 ? "vez" : "veces"}
                  {p.recurrente && <Badge tono="cobalto">Cada mes, día {p.dia}</Badge>}
                  {p.favorita && <Kbd>Alt ⇧ {p.favorita}</Kbd>}</p>
              </div>
              <Link href={`/facturar?plantilla=${p.id}`}>
                <Button variant="primario" size="sm"><Zap className="size-4" /> Facturar</Button>
              </Link>
              <button onClick={() => borrar(p)} aria-label="Borrar plantilla" className="rounded-md p-2 text-grafito hover:bg-rojo-suave hover:text-rojo">
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
