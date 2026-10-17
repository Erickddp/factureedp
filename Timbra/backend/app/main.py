import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import logs
from .config import EN_WEB, settings
from .db import SessionLocal, engine
from .models import Addenda
from .routers import (addendas, auth, catalogos, clientes, cobranza, correo, dashboard, debug, emisores, facturas, nomina,
                      claves, lotes, migracion, pacs, pagos, pendientes, plantillas, portal, productos, xml, terceros)
from .services import almacen
from .services.addenda import SEMILLAS

BASE = Path(__file__).resolve().parent.parent
STATIC = BASE / "static"  # frontend compilado (next export)


def migrar():
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE / "migraciones"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


logs.configurar(settings.data_dir, settings.debug)
log = logs.log


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Arrancando Timbra %s · datos en %s", app.version, Path(settings.data_dir).resolve())
    migrar()
    with SessionLocal() as db:
        from sqlalchemy import func

        from .models import Usuario
        try:  # es sólo un indicador: si el disco está lleno o falla, Timbra igual debe arrancar
            almacen.registrar_arranque(app.version, db.query(func.min(Usuario.creado)).scalar())
        except Exception:
            log.exception("No se pudo anotar el arranque en almacen.json (¿disco lleno?)")
        from .services import lotes as lotes_svc
        if lotes_svc.recuperar_interrumpidas(db):
            log.warning("Había filas de lote a medio timbrar: quedaron marcadas para revisión")
        from .services import xml_indice, xml_trabajos
        xml_trabajos.recuperar_interrumpidos()  # la e.firma vive en memoria: tras reiniciar hay que volver a ponerla
        auth.asegurar_admin(db)
        ya = {n for (n,) in db.query(Addenda.nombre)}  # las básicas que falten (sin tocar las que editaste)
        faltan = [Addenda(**s) for s in SEMILLAS if s["nombre"] not in ya]
        if faltan:
            db.add_all(faltan)
            db.commit()
    # Trabajos de mantenimiento de los XML: en segundo plano. Con miles de XML tardan, y si se hacen antes de abrir,
    # el servidor no contesta a tiempo la revisión de salud del despliegue (Railway da 120 s) y nunca arranca.
    import threading

    def _mantenimiento_xml():
        from .services import xml_indice
        with SessionLocal() as db2:
            try:
                pasados = xml_indice.importar_heredados(db2)
                if pasados:
                    log.info("XML del módulo SAT anterior pasados al nuevo: %s", pasados)
                completos = xml_indice.completar_nomina(db2)
                if completos:
                    log.info("Recibos de nómina con su detalle leído: %s", completos)
            except Exception:
                db2.rollback()
                log.exception("Mantenimiento de XML al arrancar falló")
    threading.Thread(target=_mantenimiento_xml, name="mantenimiento-xml", daemon=True).start()
    log.info("Timbra listo en http://localhost:8000")
    tarea = None
    if settings.programador:
        import asyncio

        from .services import programador
        tarea = asyncio.create_task(programador.correr())
    yield
    if tarea:
        tarea.cancel()
    log.info("Timbra apagado")


# En internet la documentación interactiva de la API no se publica: es el mapa completo para quien busca por dónde entrar.
app = FastAPI(title="Timbra API", version="2.14.2", description="Facturación CFDI 4.0 multi-emisor", lifespan=lifespan,
              docs_url=None if EN_WEB else "/docs", redoc_url=None, openapi_url=None if EN_WEB else "/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=1024)  # pantallas y respuestas grandes viajan comprimidas (3-4 veces menos)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

for r in (auth, pacs, emisores, clientes, productos, plantillas, addendas, facturas, catalogos, dashboard, debug,
          nomina, xml, cobranza, portal, terceros, lotes, claves, pendientes, correo, pagos, migracion):
    app.include_router(r.router, prefix="/api")
app.include_router(portal.publico, prefix="/api")  # autofactura: sin login

SILENCIO = ("/api/debug/logs", "/api/health", "/api/facturas/preview")
MAX_CUERPO = 25 * 1024 * 1024  # nada legítimo pesa más: un ZIP de XML, un Excel de clientes o un CSD
# Qué puede cargar y a dónde puede hablar la página: sólo este mismo sitio. Un script inyectado no puede traer código de
# fuera ni mandar datos a otro servidor. (Next necesita 'unsafe-inline' para sus scripts de arranque.)
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; object-src 'self' blob:; base-uri 'self'; "
       "form-action 'self'; frame-ancestors 'none'")


@app.middleware("http")
async def registro(request: Request, call_next):
    """Cada petición lleva un folio (X-Request-ID) que liga el error de la pantalla con su traza."""
    rid = (request.headers.get("x-request-id") or secrets.token_hex(4))[:40]
    tok = logs.request_id.set(rid)
    t0 = time.perf_counter()
    try:
        largo = request.headers.get("content-length")
        if largo and largo.isdigit() and int(largo) > MAX_CUERPO:
            resp = JSONResponse({"detail": "El archivo es demasiado grande (máximo 25 MB). Divídelo.", "request_id": rid}, status_code=413)
        else:
            resp = await call_next(request)
    except Exception as e:  # error no controlado: traza completa al registro
        log.exception("Error no controlado en %s %s", request.method, request.url.path)
        from .services.errores_pac import diagnosticar
        d = diagnosticar(f"{type(e).__name__} {e}")
        cuerpo = {"detail": d.texto(str(e)) if d else f"Error interno: {type(e).__name__}: {e}", "request_id": rid}
        if settings.debug:
            import traceback
            cuerpo["traza"] = traceback.format_exc()
        resp = JSONResponse(cuerpo, status_code=500)
    ms = round((time.perf_counter() - t0) * 1000)
    ruta = request.url.path
    if ruta.startswith("/api") and not ruta.startswith(SILENCIO):
        nivel = 40 if resp.status_code >= 500 else 30 if resp.status_code >= 400 else 20
        log.log(nivel, "%s %s → %s (%s ms)", request.method, ruta, resp.status_code, ms)
    elif ruta.startswith("/api/facturas/preview") and resp.status_code >= 400:
        log.warning("%s %s → %s (%s ms)", request.method, ruta, resp.status_code, ms)
    resp.headers["X-Request-ID"] = rid
    if ruta.startswith("/api"):
        resp.headers.setdefault("Cache-Control", "no-store")  # datos fiscales: ni el navegador ni un proxy guardan copia
    elif ruta.startswith("/_next/static/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # el nombre del archivo cambia con cada versión
    elif resp.headers.get("content-type", "").startswith("text/html"):
        resp.headers.setdefault("Cache-Control", "no-cache")  # la pantalla siempre es la de la versión vigente
    if EN_WEB:  # el navegador sólo usará HTTPS con este sitio, no lo incrusta nadie y no adivina tipos de archivo
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        if not ruta.startswith("/api"):
            resp.headers.setdefault("Content-Security-Policy", CSP)
    logs.request_id.reset(tok)
    return resp


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code >= 400 and exc.status_code != 401:
        log.warning("%s %s: %s", exc.status_code, request.url.path, exc.detail)
    return JSONResponse({"detail": exc.detail, "request_id": logs.request_id.get()}, status_code=exc.status_code,
                        headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validacion_error(request: Request, exc: RequestValidationError):
    """Datos mal formados: mensaje legible + detalle técnico para la consola."""
    partes = []
    for err in exc.errors():
        campo = ".".join(str(x) for x in err.get("loc", []) if x not in ("body",))
        partes.append(f"{campo}: {err.get('msg')}")
    msg = "Datos inválidos → " + "; ".join(partes[:6])
    limpios = [{"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")}
               for e in exc.errors()[:10]]
    log.warning("422 %s: %s", request.url.path, msg, extra={"datos": {"errores": limpios}})
    return JSONResponse({"detail": msg, "request_id": logs.request_id.get(), "errores": limpios}, status_code=422)


@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version, "web": EN_WEB, "almacen": almacen.estado()}


if STATIC.exists():
    app.mount("/_next", StaticFiles(directory=STATIC / "_next"), name="next")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        # /facturar -> static/facturar/index.html ; archivos sueltos tal cual
        if ruta == "api" or ruta.startswith("api/"):  # una ruta de la API que no existe no es una pantalla
            return JSONResponse({"detail": "Esa ruta de la API no existe."}, status_code=404)
        p = (STATIC / ruta).resolve()
        if STATIC.resolve() not in p.parents and p != STATIC.resolve():
            return FileResponse(STATIC / "index.html")
        if p.is_file():
            return FileResponse(p)
        if (p / "index.html").is_file():
            return FileResponse(p / "index.html")
        if (STATIC / "404.html").is_file():  # ruta que no existe: página 404 de verdad (antes caía en el login)
            return FileResponse(STATIC / "404.html", status_code=404)
        return FileResponse(STATIC / "index.html")
