import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import logs
from .config import settings
from .db import SessionLocal, engine
from .models import Addenda
from .routers import (addendas, auth, catalogos, clientes, cobranza, correo, dashboard, debug, emisores, facturas, nomina,
                      claves, lotes, pacs, pendientes, plantillas, portal, productos, sat, terceros)
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
        from .services import lotes as lotes_svc
        if lotes_svc.recuperar_interrumpidas(db):
            log.warning("Había filas de lote a medio timbrar: quedaron marcadas para revisión")
        auth.asegurar_admin(db)
        ya = {n for (n,) in db.query(Addenda.nombre)}  # las básicas que falten (sin tocar las que editaste)
        faltan = [Addenda(**s) for s in SEMILLAS if s["nombre"] not in ya]
        if faltan:
            db.add_all(faltan)
            db.commit()
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


app = FastAPI(title="Timbra API", version="2.6.0", description="Facturación CFDI 4.0 multi-emisor", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

for r in (auth, pacs, emisores, clientes, productos, plantillas, addendas, facturas, catalogos, dashboard, debug,
          nomina, sat, cobranza, portal, terceros, lotes, claves, pendientes, correo):
    app.include_router(r.router, prefix="/api")
app.include_router(portal.publico, prefix="/api")  # autofactura: sin login

SILENCIO = ("/api/debug/logs", "/api/health", "/api/facturas/preview")


@app.middleware("http")
async def registro(request: Request, call_next):
    """Cada petición lleva un folio (X-Request-ID) que liga el error de la pantalla con su traza."""
    rid = request.headers.get("x-request-id") or secrets.token_hex(4)
    tok = logs.request_id.set(rid)
    t0 = time.perf_counter()
    try:
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
    return {"ok": True, "version": app.version}


if STATIC.exists():
    app.mount("/_next", StaticFiles(directory=STATIC / "_next"), name="next")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        # /facturar -> static/facturar/index.html ; archivos sueltos tal cual
        p = (STATIC / ruta).resolve()
        if STATIC.resolve() not in p.parents and p != STATIC.resolve():
            return FileResponse(STATIC / "index.html")
        if p.is_file():
            return FileResponse(p)
        if (p / "index.html").is_file():
            return FileResponse(p / "index.html")
        return FileResponse(STATIC / "index.html")
