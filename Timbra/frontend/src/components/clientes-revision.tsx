"use client";
/** Revisión de los clientes ya guardados: datos que el SAT rechazaría, duplicados y lista 69-B. */
import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, GitMerge, Info, ShieldAlert, Wand2, XCircle } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { mostrarError } from "@/lib/errores";
import type { AuditoriaCliente, GrupoDuplicados, Verificacion69b } from "@/lib/types";
import { Badge, Button, Modal, Tabs, cx } from "./ui";

type Vista = "problemas" | "duplicados" | "lista";

export function RevisionClientes({ emisorId, abierto, cerrar, inicial = "problemas", editar, cambio }: {
  emisorId: number; abierto: boolean; cerrar: () => void; inicial?: Vista; editar: (clienteId: number) => void; cambio: () => void;
}) {
  const [vista, setVista] = useState<Vista>(inicial);
  const [conInfo, setConInfo] = useState(false);
  const { data: aud = [], mutate: mAud, isLoading } = useSWR<AuditoriaCliente[]>(abierto ? `/clientes/auditoria?emisor_id=${emisorId}${conInfo ? "&incluir_info=true" : ""}` : null, fetcher);
  const { data: dups = [], mutate: mDups } = useSWR<GrupoDuplicados[]>(abierto ? `/clientes/duplicados?emisor_id=${emisorId}` : null, fetcher);
  const [elegido, setElegido] = useState<Record<string, number>>({});
  const [trabajando, setTrabajando] = useState("");
  const [v69, setV69] = useState<Verificacion69b | null>(null);
  const [err69, setErr69] = useState("");

  const refrescar = () => { mAud(); mDups(); cambio(); };
  const arreglables = aud.flatMap((a) => {
    const cambios = Object.assign({}, ...a.problemas.map((p) => p.arreglo ?? {}));
    return Object.keys(cambios).length ? [{ cliente_id: a.cliente_id, cambios }] : [];
  });

  const arreglar = async (lista: { cliente_id: number; cambios: Record<string, string> }[], etiqueta: string) => {
    setTrabajando(etiqueta);
    try {
      const r = await api<{ arreglados: number; saltados: number }>("/clientes/auditoria/arreglar", { method: "POST", json: { emisor_id: emisorId, arreglos: lista } });
      toast.success(`${r.arreglados} cliente(s) arreglados${r.saltados ? ` · ${r.saltados} saltados (quedarían repetidos: fusiónalos)` : ""}`);
      refrescar();
    } catch (e) { mostrarError(e); } finally { setTrabajando(""); }
  };
  const fusionar = async (g: GrupoDuplicados) => {
    const keep = elegido[g.clave] ?? g.sugerido ?? g.clientes[0].id;
    setTrabajando(g.clave);
    try {
      const r = await api<{ fusionados: number; facturas_movidas: number }>("/clientes/fusionar", { method: "POST", json: { emisor_id: emisorId, conservar_id: keep, fusionar_ids: g.clientes.map((c) => c.id).filter((i) => i !== keep) } });
      toast.success(`Fusionados ${r.fusionados} registro(s)${r.facturas_movidas ? ` · ${r.facturas_movidas} facturas pasaron al cliente conservado` : ""}`);
      refrescar();
    } catch (e) { mostrarError(e); } finally { setTrabajando(""); }
  };
  const verificar = async () => {
    setTrabajando("69b"); setErr69(""); setV69(null);
    try { setV69(await api<Verificacion69b>("/clientes/verificar-69b", { method: "POST", json: { emisor_id: emisorId } })); }
    catch (e) { setErr69((e as Error).message); } finally { setTrabajando(""); }
  };

  const graves = aud.filter((a) => a.gravedad === "error").length;
  return (
    <Modal open={abierto} onClose={cerrar} title="Revisar clientes" wide="xl">
      <Tabs value={vista} onChange={setVista} items={[
        { id: "problemas", label: "Datos por corregir", n: aud.length }, { id: "duplicados", label: "Duplicados", n: dups.length || undefined }, { id: "lista", label: "Lista 69-B del SAT" }]} />

      {vista === "problemas" && (
        <div className="grid gap-3">
          {isLoading ? <p className="text-sm text-grafito">Revisando…</p> : !aud.length ? (
            <p className="flex items-center gap-2 rounded-xl bg-sello-suave px-4 py-6 text-sello"><CheckCircle2 className="size-5" /> Todos tus clientes pasan las reglas del SAT.</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-grafito">{graves > 0 ? <><b className="text-rojo">{graves}</b> con errores que harían rechazar el CFDI · </> : null}{aud.length} en total</p>
                <label className="flex items-center gap-2 text-sm text-grafito"><input type="checkbox" checked={conInfo} onChange={(e) => setConInfo(e.target.checked)} /> Incluir clientes que sólo no tienen correo</label>
                {arreglables.length > 0 && <Button variant="primario" size="sm" onClick={() => arreglar(arreglables, "todo")} loading={trabajando === "todo"}><Wand2 className="size-4" /> Arreglar lo seguro ({arreglables.length})</Button>}
              </div>
              <ul className="max-h-[55vh] divide-y divide-linea overflow-auto rounded-xl ring-1 ring-linea">
                {aud.map((a) => {
                  const cambios = Object.assign({}, ...a.problemas.map((p) => p.arreglo ?? {}));
                  return (
                    <li key={a.cliente_id} className={cx("px-4 py-3", a.gravedad === "error" && "bg-rojo-suave/40")}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="min-w-0 flex-1"><b className="block truncate">{a.nombre}</b><span className="font-mono text-xs text-grafito">{a.rfc}</span></span>
                        {Object.keys(cambios).length > 0 && <Button size="sm" onClick={() => arreglar([{ cliente_id: a.cliente_id, cambios }], String(a.cliente_id))} loading={trabajando === String(a.cliente_id)}><Wand2 className="size-3.5" /> Arreglar</Button>}
                        <Button size="sm" variant="fantasma" onClick={() => { cerrar(); editar(a.cliente_id); }}>Editar</Button>
                      </div>
                      {a.problemas.map((p, i) => (
                        <p key={i} className={cx("mt-1 flex items-start gap-1.5 text-sm", p.nivel === "error" ? "text-rojo" : p.nivel === "aviso" ? "text-alerta" : "text-grafito")}>
                          {p.nivel === "error" ? <XCircle className="mt-0.5 size-3.5 shrink-0" /> : p.nivel === "aviso" ? <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> : <Info className="mt-0.5 size-3.5 shrink-0" />}
                          {p.mensaje}{p.arreglo && <span className="ml-1 text-xs text-sello">→ {Object.values(p.arreglo)[0]}</span>}
                        </p>
                      ))}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      )}

      {vista === "duplicados" && (
        <div className="grid gap-3">
          {!dups.length ? <p className="flex items-center gap-2 rounded-xl bg-sello-suave px-4 py-6 text-sello"><CheckCircle2 className="size-5" /> No hay clientes repetidos.</p> : dups.map((g) => (
            <div key={g.tipo + g.clave} className="rounded-xl p-4 ring-1 ring-linea">
              <p className="mb-2 flex flex-wrap items-center gap-2 text-sm font-medium">
                {g.tipo === "mismo_rfc" ? <>Mismo RFC <span className="font-mono">{g.clave}</span></> : <>Mismo nombre, RFC distinto</>}
                {!g.fusionable && <Badge tono="alerta">Sólo revisar: pueden ser personas distintas</Badge>}
              </p>
              <ul className="grid gap-1.5">
                {g.clientes.map((c) => (
                  <li key={c.id}>
                    <label className={cx("flex cursor-pointer flex-wrap items-center gap-3 rounded-lg px-3 py-2 text-sm ring-1", g.fusionable && (elegido[g.clave] ?? g.sugerido) === c.id ? "bg-cobalto-suave ring-cobalto/40" : "ring-linea")}>
                      {g.fusionable && <input type="radio" name={g.clave} checked={(elegido[g.clave] ?? g.sugerido) === c.id} onChange={() => setElegido({ ...elegido, [g.clave]: c.id })} />}
                      <span className="min-w-0 flex-1"><b>{c.nombre}</b> <span className="text-grafito">· CP {c.codigo_postal} · rég. {c.regimen_fiscal}{c.emails[0] ? ` · ${c.emails[0]}` : ""}{g.tipo === "mismo_nombre" ? ` · ${c.rfc}` : ""}</span></span>
                      <Badge tono={c.facturas ? "sello" : "neutro"}>{c.facturas} facturas</Badge>
                      {!g.fusionable && <Button size="sm" variant="fantasma" onClick={() => { cerrar(); editar(c.id); }}>Editar</Button>}
                    </label>
                  </li>
                ))}
              </ul>
              {g.fusionable && <div className="mt-3 flex items-center justify-between gap-2 text-xs text-grafito"><span>Se conserva el elegido; las facturas y plantillas de los demás pasan a él.</span>
                <Button size="sm" variant="primario" onClick={() => fusionar(g)} loading={trabajando === g.clave}><GitMerge className="size-3.5" /> Fusionar</Button></div>}
            </div>
          ))}
        </div>
      )}

      {vista === "lista" && (
        <div className="grid gap-4">
          <p className="max-w-2xl text-sm text-grafito">
            La lista 69-B del SAT señala a contribuyentes con operaciones presuntamente inexistentes. Aquí cruzas tus clientes con ella (también puedes verificar a tus
            proveedores en <b>Descarga SAT</b>). Necesita internet la primera vez; después usa la copia guardada.
          </p>
          <Button className="self-start" variant="primario" onClick={verificar} loading={trabajando === "69b"}><ShieldAlert className="size-4" /> Verificar mis clientes</Button>
          {err69 && <p className="rounded-lg bg-alerta-suave px-3 py-2 text-sm text-alerta">{err69}</p>}
          {v69 && (
            v69.en_lista.length === 0 ? <p className="flex items-center gap-2 rounded-xl bg-sello-suave px-4 py-5 text-sello"><CheckCircle2 className="size-5" /> {v69.revisados} RFC revisados: ninguno aparece en la lista.</p> : (
              <ul className="divide-y divide-linea rounded-xl ring-1 ring-linea">
                {v69.en_lista.map((x) => (
                  <li key={x.cliente_id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm"><span className="min-w-0 flex-1"><b>{x.nombre}</b> <span className="font-mono text-xs text-grafito">{x.rfc}</span></span>
                    <Badge tono={x.nivel === "rojo" ? "rojo" : x.nivel === "alerta" ? "alerta" : "neutro"}>{x.estatus}</Badge></li>
                ))}
              </ul>
            )
          )}
        </div>
      )}
    </Modal>
  );
}
