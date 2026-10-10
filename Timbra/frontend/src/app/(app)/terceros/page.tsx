"use client";
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { useEmisor } from "@/components/emisor-context";
import { CatSelect } from "@/components/catalogo";
import { Badge, Button, Field, Input, Modal, PageHeader, Vacio, cx, tabla } from "@/components/ui";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import { RFC_RE } from "@/lib/format";
import type { Tercero } from "@/lib/types";

type Edit = { id?: number; rfc: string; nombre: string; regimen_fiscal: string; codigo_postal: string; alias: string;
  concepto: { descripcion?: string; clave_prod_serv?: string } };
const vacio: Edit = { rfc: "", nombre: "", regimen_fiscal: "", codigo_postal: "", alias: "", concepto: {} };

export default function Terceros() {
  const { emisor } = useEmisor();
  const { data = [], mutate } = useSWR<Tercero[]>(emisor ? `/terceros?emisor_id=${emisor.id}` : null, fetcher);
  const [edit, setEdit] = useState<Edit | null>(null);
  const [cargando, setCargando] = useState(false);
  if (!emisor) return <Vacio titulo="Elige o da de alta un emisor" />;

  const guardar = async () => {
    if (!edit) return;
    setCargando(true);
    try {
      const { id, ...body } = edit;
      await api(id ? `/terceros/${id}` : "/terceros", { method: id ? "PUT" : "POST", json: { ...body, emisor_id: emisor.id, alias: body.alias || null } });
      toast.success("Tercero guardado");
      setEdit(null);
      mutate();
    } catch (e) { mostrarError(e); } finally { setCargando(false); }
  };

  return (
    <>
      <PageHeader title="A cuenta de terceros">
        <Button variant="primario" onClick={() => setEdit({ ...vacio })}><Plus className="size-4" /> Tercero</Button>
      </PageHeader>
      <p className="-mt-3 mb-6 max-w-3xl text-sm text-grafito">
        Para facturar a nombre de otro contribuyente (nodo «A cuenta de terceros» del CFDI 4.0): la renta que cobras por el dueño
        del inmueble, la comisión de un mandatario, los honorarios de otro profesionista. Guárdalos una vez y en Facturar se eligen
        por concepto. Actívalo en Facturar → Configurar → «A cuenta de terceros», o usa un perfil rápido.
      </p>
      {!data.length ? <Vacio titulo="Sin terceros todavía" /> : (
        <div className="overflow-x-auto rounded-2xl bg-hoja ring-1 ring-linea">
          <table className={tabla.base}>
            <thead><tr><th className={tabla.th}>Tercero</th><th className={tabla.th}>RFC</th><th className={tabla.th}>Régimen</th><th className={tabla.th}>CP</th>
              <th className={tabla.th}>Concepto típico</th><th className={cx(tabla.th, tabla.num)}>Usos</th><th className={tabla.th}></th></tr></thead>
            <tbody>
              {data.map((t) => (
                <tr key={t.id} className="cursor-pointer hover:bg-tinta/[.02]" onClick={() => setEdit({ id: t.id, rfc: t.rfc, nombre: t.nombre, regimen_fiscal: t.regimen_fiscal,
                  codigo_postal: t.codigo_postal, alias: t.alias ?? "", concepto: t.concepto ?? {} })}>
                  <td className={tabla.td}><p className="font-medium">{t.alias || t.nombre}</p>{t.alias && <p className="text-xs text-grafito">{t.nombre}</p>}</td>
                  <td className={cx(tabla.td, "font-mono text-xs")}>{t.rfc}</td>
                  <td className={tabla.td}><Badge>{t.regimen_fiscal}</Badge></td>
                  <td className={tabla.td}>{t.codigo_postal}</td>
                  <td className={cx(tabla.td, "max-w-64 truncate text-grafito")}>{t.concepto?.descripcion ?? "—"}</td>
                  <td className={cx(tabla.td, tabla.num)}>{t.usos}</td>
                  <td className={cx(tabla.td, "text-right")} onClick={(e) => e.stopPropagation()}>
                    <Button size="sm" variant="fantasma" aria-label="Borrar" onClick={() => api(`/terceros/${t.id}`, { method: "DELETE" }).then(() => mutate()).catch(mostrarError)}><Trash2 className="size-3.5" /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? "Editar tercero" : "Nuevo tercero"}
        footer={<><Button onClick={() => setEdit(null)}>Cancelar</Button><Button variant="primario" onClick={guardar} loading={cargando}>Guardar</Button></>}>
        {edit && (
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); guardar(); }}>
            <Field label="RFC" error={edit.rfc && !RFC_RE.test(edit.rfc) ? "RFC incompleto" : undefined}>
              <Input autoFocus value={edit.rfc} maxLength={13} onChange={(e) => setEdit({ ...edit, rfc: e.target.value.toUpperCase().trim() })} />
            </Field>
            <Field label="Alias (cómo lo reconoces)"><Input value={edit.alias} onChange={(e) => setEdit({ ...edit, alias: e.target.value })} placeholder="Dueño local Centro" /></Field>
            <Field label="Nombre como en su constancia (sin S.A. de C.V.)" className="sm:col-span-2"><Input value={edit.nombre} onChange={(e) => setEdit({ ...edit, nombre: e.target.value.toUpperCase() })} /></Field>
            <Field label="Régimen fiscal"><CatSelect catalogo="regimen_fiscal" value={edit.regimen_fiscal} onChange={(v) => setEdit({ ...edit, regimen_fiscal: v })} /></Field>
            <Field label="CP fiscal"><Input value={edit.codigo_postal} maxLength={5} inputMode="numeric" onChange={(e) => setEdit({ ...edit, codigo_postal: e.target.value.replace(/\D/g, "") })} /></Field>
            <Field label="Descripción típica del concepto (opcional)" className="sm:col-span-2" hint="Se llena sola al elegir este tercero en un concepto vacío">
              <Input value={edit.concepto.descripcion ?? ""} onChange={(e) => setEdit({ ...edit, concepto: { ...edit.concepto, descripcion: e.target.value } })} placeholder="Renta del local comercial por cuenta del propietario" />
            </Field>
            <Field label="Clave SAT típica (opcional)"><Input value={edit.concepto.clave_prod_serv ?? ""} maxLength={8} onChange={(e) => setEdit({ ...edit, concepto: { ...edit.concepto, clave_prod_serv: e.target.value } })} placeholder="80131500" /></Field>
            <button type="submit" hidden />
          </form>
        )}
      </Modal>
    </>
  );
}
