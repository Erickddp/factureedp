from fastapi import HTTPException, Request
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker, with_loader_criteria

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_estable(conn, _):
        """WAL: lectores no bloquean al que escribe (pantalla + programador a la vez). busy_timeout: espera, no truena."""
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ======================================================================================================================
# Cada cuenta ve SÓLO lo suyo.
#
# La separación vive aquí, en la sesión de base de datos, y no en cada ruta: así una pantalla nueva queda protegida aunque
# a nadie se le ocurra filtrar. Cuando la sesión trae `info["uid"]` (usuario normal):
#   · toda lectura de Emisor y Pac se limita a los de ese usuario,
#   · toda lectura de cualquier tabla con `emisor_id` (clientes, facturas, productos, lotes…) se limita a sus emisores,
#   · antes de guardar se verifica que no escriba en un emisor o PAC ajeno (403).
# Sin `uid` no hay límite: sólo tareas en segundo plano (lotes, programador) y el portal público de autofactura.
# El ADMINISTRADOR también ve sólo lo suyo. Para ayudar a alguien entra en «modo soporte» a ESA cuenta (encabezado
# X-Soporte): es explícito, vence solo y queda registrado en `accesos_soporte`, que el dueño de la cuenta puede ver.
# tests/test_w1_cuentas.py lo vigila.
# ======================================================================================================================
def _modelos():
    from . import models
    con_emisor = [m.class_ for m in models.Base.registry.mappers if hasattr(m.class_, "emisor_id")]
    return models, con_emisor


def _mis_emisores(models, uid: int):
    t = models.Emisor.__table__
    return select(t.c.id).where(t.c.usuario_id == uid)


@event.listens_for(SessionLocal, "do_orm_execute")
def _solo_lo_mio(estado):
    uid = estado.session.info.get("uid")
    if uid is None or not estado.is_select:
        return
    models, con_emisor = _modelos()
    mios = _mis_emisores(models, uid)
    estado.statement = estado.statement.options(
        with_loader_criteria(models.Emisor, models.Emisor.usuario_id == uid, include_aliases=True),
        with_loader_criteria(models.Pac, models.Pac.usuario_id == uid, include_aliases=True),
        *[with_loader_criteria(m, m.emisor_id.in_(mios), include_aliases=True) for m in con_emisor],
    )


@event.listens_for(SessionLocal, "before_flush")
def _no_escribir_en_lo_ajeno(session, _ctx, _instancias):
    real = session.info.get("uid_real")
    if real is None:
        return  # sesión del sistema
    uid = session.info.get("uid")
    models, _ = _modelos()
    permitidos = None
    for o in list(session.new) + list(session.dirty):
        if isinstance(o, (models.Emisor, models.Pac)):
            if o.usuario_id is None:
                o.usuario_id = uid or real  # lo nuevo es de quien lo crea (en modo soporte, de la cuenta atendida)
            elif uid is not None and o.usuario_id != uid:
                raise HTTPException(403, "Ese registro es de otra cuenta.")
            if uid is not None and isinstance(o, models.Emisor) and o.pac_id is not None:
                t = models.Pac.__table__
                if session.connection().execute(select(t.c.usuario_id).where(t.c.id == o.pac_id)).scalar() != uid:
                    raise HTTPException(403, "Ese PAC es de otra cuenta.")
        elif uid is not None and getattr(o, "emisor_id", None) is not None:
            if permitidos is None:
                permitidos = set(session.connection().execute(_mis_emisores(models, uid)).scalars())
            if o.emisor_id not in permitidos:
                raise HTTPException(403, "Ese emisor es de otra cuenta.")


def _identificar(db, request: Request | None):
    """Lee el token de la petición y marca la sesión con quién es. Token de un usuario borrado o inactivo = 401."""
    if request is None:
        return
    auto = request.headers.get("authorization") or ""
    if not auto.lower().startswith("bearer "):
        return
    import jwt
    try:
        datos = jwt.decode(auto[7:].strip(), settings.jwt_secret, algorithms=["HS256"])
        correo = datos["sub"]
    except Exception:
        return  # current_user responde 401 con el mensaje adecuado
    from .models import Usuario
    from .security import huella_clave
    t = Usuario.__table__
    fila = db.execute(select(t.c.id, t.c.admin, t.c.activo, t.c.password_hash).where(t.c.email == correo)).first()
    if fila is None or not fila.activo:
        raise HTTPException(401, "Tu sesión ya no es válida. Vuelve a entrar.")
    if datos.get("k") and datos["k"] != huella_clave(fila.password_hash):  # la contraseña cambió después de abrir esta sesión
        raise HTTPException(401, "La contraseña de esta cuenta cambió. Vuelve a entrar.")
    db.info["uid_real"] = fila.id
    db.info["es_admin"] = bool(fila.admin)
    db.info["uid"] = fila.id
    atendido = (request.headers.get("x-soporte") or "").strip()
    if atendido:
        from datetime import datetime

        from .models import AccesoSoporte
        a = AccesoSoporte.__table__
        if not (fila.admin and atendido.isdigit()) or db.execute(
                select(a.c.id).where(a.c.admin_id == fila.id, a.c.usuario_id == int(atendido), a.c.hasta > datetime.now())).first() is None:
            raise HTTPException(403, "El modo soporte no está activo o ya venció. Vuelve a entrar desde Cuentas.")
        db.info["uid"] = int(atendido)
        db.info["soporte"] = True


def get_db(request: Request = None):  # type: ignore[assignment]
    db = SessionLocal()
    try:
        _identificar(db, request)
        yield db
    finally:
        db.close()


def solo_admin(request: Request):
    """Dependencia para rutas que sólo usa el administrador (usuarios, consola, correo de la plataforma)."""
    with SessionLocal() as db:
        _identificar(db, request)
        if not db.info.get("es_admin"):
            raise HTTPException(403, "Sólo el administrador puede hacer esto.")
