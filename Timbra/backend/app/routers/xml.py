"""XML del SAT: poner la e.firma (no se guarda), descargar, leer XML propios, ver, exportar y estadísticas."""
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..db import get_db
from ..logs import log
from ..models import Emisor, XmlCfdi, XmlTrabajo
from ..security import current_user
from ..services import xml_firma, xml_indice, xml_tareas, xml_trabajos
from ..services.xml_indice import FORMATO_EDDP, Filtros, limpios
from ..xmlsat.exportar import a_tsv_cols

router = APIRouter(prefix="/xml", tags=["xml"], dependencies=[Depends(current_user)])

POR_PAGINA = 100
MAX_SUBIDA = 2000  # archivos por envío (la pantalla manda la carpeta en tandas)
DESCARGAS_POR_CUENTA = 3  # descargas del SAT a la vez por cuenta (distintos RFC)
DESCARGAS_EN_TOTAL = 8  # y en todo el servidor


def _emisor(db: Session, emisor_id: int) -> Emisor:
    e = db.get(Emisor, emisor_id)
    if not e:
        raise HTTPException(404, "Emisor no existe")
    return e


def adjunto(nombre: str, en_linea: bool = False) -> dict:
    """Encabezado para que el navegador guarde el archivo con su nombre (acentos incluidos)."""
    return {"Content-Disposition": f"{'inline' if en_linea else 'attachment'}; filename*=UTF-8''{quote(nombre)}"}


def _etiqueta(e: Emisor, f: Filtros) -> str:
    return f"CFDI {e.rfc} {f.mes or 'todo'}" + (f" {f.tipo.lower()}s" if f.tipo else "")


def _contribuyente(db: Session, rfc: str, nombre: str = "", regimen: str = "", cp: str = "") -> tuple[Emisor, bool]:
    """El emisor de ese RFC en tu cuenta; si no existe se da de alta con lo que se sepa (se completa después en Emisores).
    Así se puede bajar o leer lo de cualquier contribuyente sin capturarlo antes a mano."""
    from sqlalchemy import select

    from ..models import Producto, Serie
    from ..services.semillas import productos_base
    rfc = rfc.upper().strip()
    e = db.query(Emisor).filter_by(rfc=rfc).first()
    if e is not None:
        return e, False
    t = Emisor.__table__
    if db.connection().execute(select(t.c.id).where(t.c.rfc == rfc)).first():
        raise HTTPException(409, f"{rfc} ya está registrado en otra cuenta de Timbra.")
    e = Emisor(rfc=rfc, nombre=(nombre or rfc).upper()[:300], regimen_fiscal=(regimen or ("601" if len(rfc) == 12 else "612"))[:3],
               lugar_expedicion=(cp or "00000")[:5])
    e.series = [Serie(serie="A", tipo="I", default=True), Serie(serie="NC", tipo="E", default=True),
                Serie(serie="P", tipo="P", default=True), Serie(serie="T", tipo="T", default=True), Serie(serie="N", tipo="N", default=True)]
    db.add(e)
    db.flush()
    db.add_all(Producto(**p) for p in productos_base(e.id, e.region_fronteriza))
    db.commit()
    log.info("Contribuyente %s dado de alta desde el módulo de XML", e.rfc)
    return e, True


# ---------------------------------------------------------------- e.firma (sólo en memoria)
@router.post("/efirma")
async def efirma_de_quien_sea(cer: UploadFile = File(...), key: UploadFile = File(...), password: str = Form(...),
                              db: Session = Depends(get_db)):
    """Pon la e.firma de cualquier contribuyente: el RFC se lee del certificado y Timbra abre (o da de alta) ese RFC en tu
    cuenta. La e.firma queda sólo en memoria; no se escribe en disco ni en la base."""
    try:
        datos = xml_firma.leer(await cer.read(64 * 1024 + 1), await key.read(64 * 1024 + 1), password)
    except xml_firma.EfirmaError as ex:
        raise HTTPException(422, str(ex))
    e, creado = _contribuyente(db, datos["rfc"], datos["nombre"])
    log.info("e.firma de %s puesta en memoria (no se guarda)", e.rfc)
    return {**xml_firma.poner(e.id, db.info.get("uid_real"), datos), "emisor_id": e.id, "creado": creado}


@router.get("/efirma")
def efirma_estado(emisor_id: int, db: Session = Depends(get_db)):
    _emisor(db, emisor_id)
    return xml_firma.estado(emisor_id)


@router.post("/efirma/{emisor_id}")
async def efirma_poner(emisor_id: int, cer: UploadFile = File(...), key: UploadFile = File(...), password: str = Form(...),
                       db: Session = Depends(get_db)):
    """Valida la e.firma y la deja abierta EN MEMORIA para bajar del SAT. No se escribe en disco ni en la base."""
    e = _emisor(db, emisor_id)
    try:
        datos = xml_firma.leer(await cer.read(64 * 1024 + 1), await key.read(64 * 1024 + 1), password)
    except xml_firma.EfirmaError as ex:
        raise HTTPException(422, str(ex))
    if datos["rfc"].upper() != e.rfc.upper():
        raise HTTPException(422, f"Esa e.firma es de {datos['rfc']} y estás trabajando con {e.rfc}. Cambia de emisor arriba a la "
                                 "izquierda, o dalo de alta en Emisores si aún no existe.")
    log.info("e.firma de %s puesta en memoria (no se guarda)", e.rfc)
    return xml_firma.poner(emisor_id, db.info.get("uid_real"), datos)


@router.post("/efirma/{emisor_id}/probar")
def efirma_probar(emisor_id: int, db: Session = Depends(get_db)):
    _emisor(db, emisor_id)
    ok, mensaje = xml_tareas.probar_efirma(emisor_id)
    return {"ok": ok, "mensaje": mensaje, **xml_firma.estado(emisor_id)}


@router.delete("/efirma/{emisor_id}")
def efirma_olvidar(emisor_id: int, db: Session = Depends(get_db)):
    _emisor(db, emisor_id)
    if db.query(XmlTrabajo).filter_by(emisor_id=emisor_id, clase="sat", estado="curso").count():
        raise HTTPException(409, "Hay una descarga en curso que la está usando. Detén la descarga primero.")
    return {"ok": xml_firma.olvidar(emisor_id)}


# ---------------------------------------------------------------- descargar del SAT
class DescargaIn(BaseModel):
    emisor_id: int
    desde: date
    hasta: date
    tipo: str = "ambos"       # emitidos | recibidos | ambos
    cancelados: bool = True   # además pide al SAT la lista de estatus para marcar los cancelados


def _trabajo(db: Session, tid: int) -> XmlTrabajo:
    t = db.get(XmlTrabajo, tid)
    if not t:
        raise HTTPException(404, "Ese trabajo no existe.")
    return t


@router.post("/descargas")
def descargar(data: DescargaIn, db: Session = Depends(get_db)):
    if data.tipo not in ("emitidos", "recibidos", "ambos"):
        raise HTTPException(422, "tipo: emitidos, recibidos o ambos")
    if data.desde > data.hasta:
        raise HTTPException(422, "La fecha inicial no puede ser posterior a la final.")
    if data.hasta > date.today():
        raise HTTPException(422, "La fecha final no puede ser futura.")
    if (data.hasta - data.desde).days > 366 * 2:
        raise HTTPException(422, "Pide como máximo dos años a la vez.")
    e = _emisor(db, data.emisor_id)
    if xml_tareas.fabrica_cliente is None and not xml_firma.estado(e.id)["puesta"]:
        raise HTTPException(422, "Pon tu e.firma para descargar del SAT. Por seguridad no se guarda: se pide cada vez.")
    if db.query(XmlTrabajo).filter_by(emisor_id=e.id, clase="sat", estado="curso").count():
        raise HTTPException(409, "Ya hay una descarga en curso para este RFC. Espera a que termine o detenla.")
    # Topes: cada descarga es un hilo que habla con el SAT por minutos. Se cuentan las de TODAS las cuentas (sin filtro).
    from sqlalchemy import select
    tabla = XmlTrabajo.__table__
    en_curso = db.connection().execute(select(tabla.c.usuario_id).where(tabla.c.clase == "sat", tabla.c.estado == "curso")).scalars().all()
    if sum(1 for u in en_curso if u == db.info.get("uid_real")) >= DESCARGAS_POR_CUENTA:
        raise HTTPException(429, f"Ya tienes {DESCARGAS_POR_CUENTA} descargas del SAT en curso. Espera a que termine alguna.")
    if len(en_curso) >= DESCARGAS_EN_TOTAL:
        raise HTTPException(429, "Timbra está atendiendo muchas descargas del SAT en este momento. Intenta en unos minutos.")
    tid = xml_trabajos.crear(db, db.info.get("uid_real"), e.id, "sat", {
        "desde": data.desde.isoformat(), "hasta": data.hasta.isoformat(), "tipo": data.tipo, "cancelados": data.cancelados})
    desde, hasta = datetime.combine(data.desde, datetime.min.time()), datetime.combine(data.hasta, datetime.min.time())
    eid, rfc, nombre = e.id, e.rfc, e.nombre
    xml_firma.ocupar(eid, True)
    xml_trabajos.lanzar(tid, lambda t: xml_tareas.descargar_sat(t, eid, rfc, nombre, desde, hasta, data.tipo, data.cancelados),
                        al_terminar=lambda: xml_firma.ocupar(eid, False))
    return {"id": tid}


@router.get("/trabajos")
def trabajos(emisor_id: int, clase: str = "sat", db: Session = Depends(get_db)):
    _emisor(db, emisor_id)
    q = db.query(XmlTrabajo).filter_by(emisor_id=emisor_id, clase=clase).order_by(XmlTrabajo.id.desc()).limit(20)
    return [xml_trabajos.publico(t) for t in q]


@router.get("/trabajos/{tid}")
def trabajo(tid: int, db: Session = Depends(get_db)):
    return xml_trabajos.publico(_trabajo(db, tid), con_registro=True)


@router.post("/trabajos/{tid}/cancelar")
def trabajo_cancelar(tid: int, db: Session = Depends(get_db)):
    _trabajo(db, tid)
    return {"ok": xml_trabajos.cancelar(tid)}


@router.get("/trabajos/{tid}/archivo")
def trabajo_archivo(tid: int, db: Session = Depends(get_db)):
    t = _trabajo(db, tid)
    ruta = xml_indice.carpeta_tmp() / (Path(t.archivo).name if t.archivo else "-")
    if not t.archivo or not ruta.is_file():
        raise HTTPException(404, "Ese archivo ya caducó. Vuelve a generarlo.")
    return FileResponse(ruta, media_type="application/zip", headers=adjunto((t.params or {}).get("nombre", "cfdi.zip")))


# ---------------------------------------------------------------- comprobantes
@router.get("/cfdi")
def listar(emisor_id: int, mes: str = "", tipo: str = "", clase: str = "", estatus: str = "", q: str = "", pagina: int = 1,
           lista_69b: bool = False, db: Session = Depends(get_db)):
    """lista_69b=true cruza a quien te factura (recibidos) con la lista 69-B del SAT: necesita internet la primera vez."""
    _emisor(db, emisor_id)
    if pagina <= 1:
        xml_indice.al_dia_con_timbra(db, emisor_id)
    f = limpios(Filtros(emisor_id=emisor_id, mes=mes, tipo=tipo, clase=clase, estatus=estatus, q=q))
    base = xml_indice.consulta(db, f)
    n, suma = base.with_entities(func.count(), func.coalesce(func.sum(XmlCfdi.total), 0)).one()
    filas = (base.order_by(XmlCfdi.fecha.desc(), XmlCfdi.id.desc()).limit(POR_PAGINA).offset((max(pagina, 1) - 1) * POR_PAGINA)
             .with_entities(XmlCfdi.id, XmlCfdi.uuid, XmlCfdi.tipo, XmlCfdi.fecha, XmlCfdi.clase, XmlCfdi.comprobante, XmlCfdi.serie,
                            XmlCfdi.folio, XmlCfdi.rfc_emisor, XmlCfdi.nombre_emisor, XmlCfdi.rfc_receptor, XmlCfdi.nombre_receptor,
                            XmlCfdi.subtotal, XmlCfdi.iva, XmlCfdi.total, XmlCfdi.moneda, XmlCfdi.metodo, XmlCfdi.estatus,
                            XmlCfdi.cancelado_el, XmlCfdi.origen))
    # Las letras de clase cuentan lo filtrado SIN el filtro de clase: así se ve cuánto hay de cada una antes de elegir.
    clases = (xml_indice.consulta(db, f, con_clase=False)
              .with_entities(XmlCfdi.clase, func.count(), func.sum(XmlCfdi.total)).group_by(XmlCfdi.clase))
    cancelados = xml_indice.consulta(db, f, con_estatus=False).filter(XmlCfdi.estatus == "Cancelado").count()
    filas = [dict(r._mapping) for r in filas]
    aviso_69b = None
    if lista_69b:
        from ..services import clientes_io
        try:
            listado = clientes_io.listado_69b()
            for r in filas:
                r["lista_69b"] = listado.get(r["rfc_emisor"]) if r["tipo"] == "Recibido" else None
        except clientes_io.ListaNoDisponible as ex:
            aviso_69b = str(ex)
    return {"total": n, "suma": round(suma or 0, 2), "por_pagina": POR_PAGINA, "filas": filas, "aviso_69b": aviso_69b,
            "clases": {c: {"n": k, "total": round(t or 0, 2)} for c, k, t in clases}, "meses": xml_indice.meses(db, emisor_id),
            "cancelados": cancelados}


def _cfdi(db: Session, cfdi_id: int) -> tuple[Emisor, XmlCfdi]:
    x = db.get(XmlCfdi, cfdi_id)
    if not x:
        raise HTTPException(404, "Ese comprobante no existe.")
    return _emisor(db, x.emisor_id), x


@router.get("/cfdi/{cfdi_id}/pdf")
def pdf(cfdi_id: int, db: Session = Depends(get_db)):
    e, x = _cfdi(db, cfdi_id)
    try:
        nombre, contenido = xml_tareas.pdf_de(db, e, x)
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(422, f"No se pudo pintar el PDF de este comprobante: {ex}")
    return Response(contenido, media_type="application/pdf", headers=adjunto(nombre, en_linea=True))


@router.get("/cfdi/{cfdi_id}/xml")
def xml(cfdi_id: int, db: Session = Depends(get_db)):
    e, x = _cfdi(db, cfdi_id)
    ruta = xml_indice.carpeta_xml(e.id) / x.archivo if x.archivo else None
    if ruta is None or not ruta.is_file():
        raise HTTPException(404, "De este comprobante no hay XML (sólo se sabe que existe porque lo avisó el SAT).")
    return FileResponse(ruta, media_type="application/xml", headers=adjunto(f"{x.uuid}.xml"))


@router.post("/copiar", response_class=PlainTextResponse)
def copiar(f: Filtros, db: Session = Depends(get_db)):
    """La tabla en el formato maestro EDDP, lista para pegar en Excel o Sheets (Ctrl+V)."""
    _emisor(db, f.emisor_id)
    return a_tsv_cols(xml_indice.renglones(db, limpios(f)), FORMATO_EDDP)


@router.post("/excel")
def excel(f: Filtros, db: Session = Depends(get_db)):
    """Excel con todas las columnas (las del formato EDDP + clase, seguimiento de pago, archivo y estatus) y hoja Resumen."""
    e = _emisor(db, f.emisor_id)
    f = limpios(f)
    xml_trabajos.limpiar_temporales()
    destino = xml_tareas.excel(db, e, f)
    return FileResponse(destino, headers=adjunto(f"{_etiqueta(e, f)}.xlsx"), background=BackgroundTask(destino.unlink, True),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class ZipIn(BaseModel):
    filtros: Filtros
    incluir: str = "ambos"  # xml | pdf | ambos


@router.post("/zip")
def zip_(data: ZipIn, db: Session = Depends(get_db)):
    """Arma en segundo plano el ZIP de XML y/o PDF de lo filtrado. Devuelve el trabajo para seguir su avance."""
    if data.incluir not in ("xml", "pdf", "ambos"):
        raise HTTPException(422, "incluir: xml, pdf o ambos")
    f = limpios(data.filtros)
    e = _emisor(db, f.emisor_id)
    n = xml_indice.consulta(db, f).filter(XmlCfdi.archivo != "").count()
    if not n:
        raise HTTPException(422, "No hay comprobantes con XML en lo que estás viendo.")
    tid = xml_trabajos.crear(db, db.info.get("uid_real"), e.id, "zip", {"incluir": data.incluir, "nombre": f"{_etiqueta(e, f)}.zip", "n": n})
    xml_trabajos.limpiar_temporales()
    eid = e.id
    xml_trabajos.lanzar(tid, lambda t: xml_tareas.armar_zip(t, eid, f, data.incluir))
    return {"id": tid, "total": n}


@router.post("/subir")
async def subir(emisor_id: int, request: Request, archivos: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """XML sueltos o ZIP que ya tenías (o una carpeta completa, por tandas). Se acomodan solos en emitidos o recibidos."""
    e = _emisor(db, emisor_id)
    if len(archivos) > MAX_SUBIDA:
        raise HTTPException(422, f"Máximo {MAX_SUBIDA} archivos por envío.")
    leidos = [(Path(a.filename or "sin_nombre.xml").name, await a.read()) for a in archivos
              if (a.filename or "").lower().endswith((".xml", ".zip"))]
    # leer cientos de XML es pesado: fuera del ciclo de eventos, para no congelar a las demás cuentas
    return await run_in_threadpool(xml_indice.guardar_subidos, db, e, leidos)


@router.post("/leer")
async def leer(rfc: str = "", actual: str = "", archivos: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Lee XML de CUALQUIER contribuyente: el dueño se saca de los propios XML (el RFC que aparece en todos). Si ese RFC
    aún no está en tu cuenta, se da de alta con los datos que traen los XML. Devuelve a qué emisor entraron.
    Si no se puede saber de quién son (dos RFC aparecen igual de veces), no guarda nada y devuelve `elegir` para preguntar.
    `rfc`: el dueño ya elegido. `actual`: el RFC con el que se está trabajando (desempata a su favor)."""
    if len(archivos) > MAX_SUBIDA:
        raise HTTPException(422, f"Máximo {MAX_SUBIDA} archivos por envío.")
    leidos = [(Path(a.filename or "sin_nombre.xml").name, await a.read()) for a in archivos
              if (a.filename or "").lower().endswith((".xml", ".zip"))]
    return await run_in_threadpool(_leer, db, leidos, rfc, actual)


def _leer(db: Session, leidos: list, rfc: str, actual: str) -> dict:
    """Cada CFDI va con su dueño (puede haber varios contribuyentes en una misma carpeta): ver xml_indice.repartir.
    Devuelve `contribuyentes` (uno por RFC, con sus nuevos y repetidos) y, para la pantalla, el principal arriba."""
    r = xml_indice.repartir(db, leidos, lambda *a: _contribuyente(db, *a), rfc, actual)
    if r.get("vacio"):
        raise HTTPException(422, "Ahí no encontré ningún CFDI. Elige la carpeta donde están los XML (o un ZIP con ellos).")
    if "elegir" in r:
        return r
    cs = r["contribuyentes"]
    if not cs and r["otra_cuenta"]:
        raise HTTPException(409, "Esos XML son de un RFC que está registrado en otra cuenta de Timbra.")
    p = cs[0] if cs else {"emisor_id": 0, "rfc": "", "nombre": "", "creado": False}
    return {"emisor_id": p["emisor_id"], "rfc": p["rfc"], "nombre": p["nombre"], "creado": p["creado"],
            "nuevos": sum(c["nuevos"] for c in cs), "repetidos": sum(c["repetidos"] for c in cs),
            "ajenos": r["otra_cuenta"] + r["sin_dueno"], "otra_cuenta": r["otra_cuenta"], "sin_dueno": r["sin_dueno"],
            "invalidos": r["invalidos"], "contribuyentes": cs}


@router.post("/borrar")
def borrar(f: Filtros, db: Session = Depends(get_db)):
    """Quita de Timbra los XML que estás viendo (los puedes volver a bajar o a leer). No toca nada en el SAT."""
    _emisor(db, f.emisor_id)
    if db.query(XmlTrabajo).filter_by(emisor_id=f.emisor_id, estado="curso").count():
        raise HTTPException(409, "Hay un trabajo en curso con estos XML. Espera a que termine.")
    return {"borrados": xml_indice.borrar(db, limpios(f))}


@router.post("/resumen")
def resumen(f: Filtros, db: Session = Depends(get_db)):
    """Números para las gráficas, sacados de los XML: ingresos, gastos, impuestos, clientes, proveedores, cancelados."""
    _emisor(db, f.emisor_id)
    xml_indice.al_dia_con_timbra(db, f.emisor_id)
    return xml_indice.resumen(db, limpios(f))
