"""Consola de depuración: registro en vivo, estado de servicios y diagnóstico."""
import os
import platform
import socket
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import logs
from ..config import settings
from ..db import get_db, solo_admin
from ..models import Cliente, Emisor, Factura, Pac
from ..security import current_user

router = APIRouter(prefix="/debug", tags=["debug"], dependencies=[Depends(current_user)])
INICIO = time.time()

URLS_PAC = {
    "finkok": ("https://facturacion.finkok.com", "https://demo-facturacion.finkok.com"),
    "swsapien": ("https://services.sw.com.mx", "https://services.test.sw.com.mx"),
    "facturama": ("https://api.facturama.mx", "https://apisandbox.facturama.mx"),
    "prodigia": ("https://timbrado.pade.mx", "https://timbrado.pade.mx"),
    "diverza": ("https://servicios.diverza.com", "https://serviciosdemo.diverza.com"),
    "comerciodigital": ("https://ws.comercio-digital.mx", "https://pruebas.comercio-digital.mx"),
    "mysuite": ("https://www.mysuitecfdi.com", "https://www.mysuitetest.com"),
}


@router.get("/logs", dependencies=[Depends(solo_admin)])
def ver_logs(despues: int = 0, nivel: str | None = None, q: str | None = None, req: str | None = None,
             limite: int = 500):
    return {"items": logs.BUFFER.consultar(despues, nivel, q, req, limite), "ultimo": logs.BUFFER.ultimo_id()}


class ClienteLog(BaseModel):
    nivel: str = "error"
    mensaje: str
    datos: dict | None = None


@router.post("/cliente")
def log_navegador(data: ClienteLog):
    nivel = {"error": 40, "warn": 30, "info": 20}.get(data.nivel, 40)
    logs.logging.getLogger("navegador").log(nivel, data.mensaje[:2000], extra={"datos": data.datos})
    return {"ok": True}


@router.get("/descargar", dependencies=[Depends(solo_admin)])
def descargar_log():
    if not logs.ARCHIVO or not os.path.exists(logs.ARCHIVO):
        raise HTTPException(404, "Todavía no hay archivo de registro")
    return FileResponse(logs.ARCHIVO, filename=f"timbra_{datetime.now():%Y%m%d_%H%M}.log", media_type="text/plain")


def _chk(nombre, estado, detalle, ms=None, grupo="sistema"):
    return {"nombre": nombre, "estado": estado, "detalle": detalle, "ms": ms, "grupo": grupo}


def _http(url: str) -> tuple[bool, int, str]:
    t0 = time.perf_counter()
    try:
        r = httpx.get(url, timeout=5, follow_redirects=True)
        ms = round((time.perf_counter() - t0) * 1000)
        return r.status_code < 500, ms, f"HTTP {r.status_code}"
    except Exception as e:
        ms = round((time.perf_counter() - t0) * 1000)
        return False, ms, f"{type(e).__name__}: {e}"


@router.get("/servicios", dependencies=[Depends(solo_admin)])
def servicios(db: Session = Depends(get_db)):
    out = []
    up = int(time.time() - INICIO)
    out.append(_chk("API", "ok", f"Timbra {os.environ.get('TIMBRA_VERSION', '1.1')} · Python {platform.python_version()} "
                    f"· arriba {up // 3600}h {up % 3600 // 60}m · modo depuración {'sí' if settings.debug else 'no'}"))
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        ms = round((time.perf_counter() - t0) * 1000)
        out.append(_chk("Base de datos", "ok",
                        f"{settings.database_url.split('///')[-1]} · {db.query(Factura).count()} comprobantes · "
                        f"{db.query(Cliente).count()} clientes", ms))
    except Exception as e:
        out.append(_chk("Base de datos", "error", f"{type(e).__name__}: {e}"))
    resp = os.path.join(settings.data_dir, "respaldo_xml")
    try:
        prueba = os.path.join(resp, ".escritura")
        open(prueba, "w").write("ok")
        os.remove(prueba)
        n = sum(len(f) for _, _, f in os.walk(resp))
        out.append(_chk("Respaldo en disco", "ok", f"{n} XML en {os.path.abspath(resp)}"))
    except Exception as e:
        out.append(_chk("Respaldo en disco", "error", f"No se puede escribir: {e}"))
    try:
        from satcfdi.catalogs import select_all
        out.append(_chk("Catálogos SAT", "ok", f"satcfdi {version('satcfdi')} · "
                        f"{len(select_all('C756_c_ClaveProdServ')):,} claves prod/serv · "
                        f"{len(select_all('C756_c_CodigoPostal')):,} códigos postales"))
    except Exception as e:
        out.append(_chk("Catálogos SAT", "error", str(e)))
    try:
        import satcfdi.render  # noqa: F401
        import weasyprint  # noqa: F401
        out.append(_chk("PDF", "ok", "weasyprint disponible: PDF directo"))
    except Exception:
        out.append(_chk("PDF", "aviso", "Sin weasyprint/GTK: el botón PDF abre la factura para imprimir a PDF"))
    if settings.smtp_host:
        t0 = time.perf_counter()
        try:
            with socket.create_connection((settings.smtp_host, settings.smtp_port), timeout=5):
                pass
            out.append(_chk("Correo (SMTP)", "ok", f"{settings.smtp_host}:{settings.smtp_port} alcanzable",
                            round((time.perf_counter() - t0) * 1000)))
        except Exception as e:
            out.append(_chk("Correo (SMTP)", "error", f"{settings.smtp_host}:{settings.smtp_port} → {e}"))
    else:
        out.append(_chk("Correo (SMTP)", "aviso", "Sin configurar: llena SMTP_* en backend\\.env para mandar facturas"))

    for p in db.query(Pac).order_by(Pac.nombre):
        if p.proveedor == "demo":
            out.append(_chk(f"PAC {p.nombre}", "aviso", "Demo: no timbra ante el SAT", grupo="pac"))
            continue
        url = URLS_PAC.get(p.proveedor, ("", ""))[1 if p.pruebas else 0]
        cred = bool(p.usuario or p.token_enc)
        ok, ms, det = _http(url) if url else (False, None, "URL desconocida")
        estado = "ok" if ok and cred else ("aviso" if ok else "error")
        out.append(_chk(f"PAC {p.nombre}", estado,
                        f"{p.proveedor} · {'pruebas' if p.pruebas else 'PRODUCCIÓN'} · {url} → {det}"
                        f"{'' if cred else ' · faltan credenciales'}", ms, grupo="pac"))

    hoy = datetime.now(timezone.utc).replace(tzinfo=None)
    for e in db.query(Emisor).order_by(Emisor.rfc):
        if not e.cer:
            out.append(_chk(f"CSD {e.rfc}", "error", "Sin CSD cargado", grupo="emisor"))
            continue
        dias = (e.csd_vence - hoy).days if e.csd_vence else None
        estado = "error" if dias is not None and dias < 0 else ("aviso" if dias is not None and dias < 30 else "ok")
        pac = e.pac.nombre if e.pac else "demo"
        out.append(_chk(f"CSD {e.rfc}", estado,
                        f"No. {e.no_certificado} · vence {e.csd_vence:%d/%m/%Y} ({dias} días) · PAC: {pac}",
                        grupo="emisor"))
    logs.log.debug("Diagnóstico de servicios ejecutado")
    return out


class CorreoPrueba(BaseModel):
    para: str


@router.post("/probar-correo", dependencies=[Depends(solo_admin)])
def probar_correo(data: CorreoPrueba):
    from ..services import mailer
    try:
        with logs.paso("Correo de prueba", para=data.para):
            mailer.enviar([data.para], "Prueba de Timbra", "Si lees esto, el correo de Timbra funciona.", [])
    except Exception as e:
        raise HTTPException(502, f"El correo falló: {type(e).__name__}: {e}")
    return {"ok": True}


@router.get("/info", dependencies=[Depends(solo_admin)])
def info():
    return {"python": sys.version, "plataforma": platform.platform(), "satcfdi": version("satcfdi"),
            "data_dir": os.path.abspath(settings.data_dir), "log": logs.ARCHIVO, "debug": settings.debug}


@router.get("/errores-comunes")
def errores_comunes():
    """Catálogo de errores frecuentes del PAC/SAT con su solución (y cuáles Timbra corrige solo)."""
    from ..services.errores_pac import catalogo
    return catalogo()
