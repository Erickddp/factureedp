"""Pasar los emisores de una instalación de Timbra a otra (de tu PC a la web, o al revés) sin subirlos a mano uno por uno.

El archivo (.timbracuenta) lleva, por emisor: sus datos, el CSD (cer, key y contraseña), series y folios, clientes,
productos, terceros, empleados, perfiles de lote, plantillas y, si se pide, las facturas con su XML.

Seguridad: el archivo trae llaves privadas, así que SIEMPRE va cifrado con una contraseña que elige quien exporta (scrypt +
Fernet). Las llaves se descifran con la SECRET_KEY de quien exporta y se vuelven a cifrar con la de quien importa: las dos
instalaciones no necesitan compartir llaves. Nunca se exportan: PAC y sus credenciales, e.firma, usuarios, contraseñas,
la clave pública del portal de autofactura ni lo que el XML del SAT haya bajado (eso se vuelve a leer o bajar).
"""
import base64
import copy
import json
import os
import zlib
from datetime import datetime
from decimal import Decimal

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..logs import log
from ..models import (Addenda, Cliente, Emisor, Empleado, Factura, PerfilLote, Plantilla, Producto, Serie, Tercero)
from ..security import decrypt
from . import signer

MAGIA = b"TIMBRA-CUENTA/1\n"
MIN_CLAVE = 10
MAX_DESCOMPRIMIDO = 200 * 1024 * 1024  # un archivo de 25 MB comprimido no debe poder inflarse sin límite

# Datos del emisor que viajan (el CSD, las series y lo que depende de la cuenta o del PAC van aparte o no van)
CAMPOS_EMISOR = ("rfc", "nombre", "regimen_fiscal", "lugar_expedicion", "email", "logo_b64", "color", "region_fronteriza",
                 "registro_patronal", "curp", "portal_config", "cobranza_auto", "config_facturar", "activo", "creado")
# (nombre en el archivo, modelo, columnas que apuntan a otras tablas: columna -> tabla del archivo)
HIJAS = [
    ("clientes", Cliente, {"addenda_id": "@addendas"}),
    ("productos", Producto, {}),
    ("terceros", Tercero, {}),
    ("empleados", Empleado, {}),
    ("perfiles_lote", PerfilLote, {}),
    ("facturas", Factura, {"cliente_id": "clientes", "empleado_id": "empleados"}),
    ("plantillas", Plantilla, {"cliente_id": "clientes", "ultima_factura_id": "facturas"}),
]
MODELO = {n: m for n, m, _ in HIJAS}


class MigracionError(Exception):
    pass


# ---------------------------------------------------------------- cifrado del archivo
def _llave(clave: str, sal: bytes) -> bytes:
    return base64.urlsafe_b64encode(Scrypt(salt=sal, length=32, n=2 ** 15, r=8, p=1).derive(clave.encode("utf-8")))


def _cerrar(datos: dict, clave: str) -> bytes:
    sal = os.urandom(16)
    crudo = zlib.compress(json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
    return MAGIA + sal + Fernet(_llave(clave, sal)).encrypt(crudo)


def abrir(archivo: bytes, clave: str) -> dict:
    if not archivo.startswith(MAGIA) or len(archivo) < len(MAGIA) + 40:
        raise MigracionError("Ese archivo no es una exportación de Timbra (debe terminar en .timbracuenta).")
    sal = archivo[len(MAGIA):len(MAGIA) + 16]
    try:
        crudo = Fernet(_llave(clave, sal)).decrypt(archivo[len(MAGIA) + 16:])
    except InvalidToken:
        raise MigracionError("La contraseña no abre ese archivo (o el archivo está dañado). Es la que escribiste al exportar.") from None
    d = zlib.decompressobj()
    datos = d.decompress(crudo, MAX_DESCOMPRIMIDO)
    if d.unconsumed_tail:
        raise MigracionError("El archivo es demasiado grande para importarlo.")
    try:
        paquete = json.loads(datos.decode("utf-8"))
    except ValueError as e:
        raise MigracionError(f"El archivo está dañado: {e}") from e
    if not isinstance(paquete, dict) or paquete.get("formato") != 1 or not isinstance(paquete.get("emisores"), list):
        raise MigracionError("El archivo es de una versión que esta Timbra no entiende.")
    return paquete


# ---------------------------------------------------------------- filas <-> diccionarios
def _a_json(v):
    if isinstance(v, datetime):
        return {"$d": v.isoformat()}
    if isinstance(v, Decimal):
        return {"$n": str(v)}
    if isinstance(v, (bytes, bytearray)):
        return {"$b": base64.b64encode(bytes(v)).decode("ascii")}
    return v


def _de_json(v):
    if isinstance(v, dict) and len(v) == 1:
        (k, x), = v.items()
        if k == "$d":
            return datetime.fromisoformat(x)
        if k == "$n":
            return Decimal(x)
        if k == "$b":
            return base64.b64decode(x)
    return v


def _fila(obj, omitir: set) -> dict:
    cols = obj.__table__.columns
    return {c.name: _a_json(getattr(obj, c.key)) for c in cols if c.name not in omitir}


# ---------------------------------------------------------------- exportar
def es_de_pruebas(e: Emisor, rfc_pruebas: set) -> bool:
    """Los CSD de prueba del SAT tienen número 30001000000…; los de verdad, 00001000000…. Un RFC de prueba conocido también cuenta."""
    return e.rfc.upper() in rfc_pruebas or str(e.no_certificado or "").startswith("30001000000")


def lista_exportable(db: Session) -> list[dict]:
    """Los emisores de esta cuenta con lo que llevarían, para elegir cuáles exportar."""
    from .validacion import RFC_PRUEBAS_SAT
    cuenta = lambda modelo: dict(db.query(modelo.emisor_id, func.count()).group_by(modelo.emisor_id).all())  # noqa: E731
    clientes, productos, facturas = cuenta(Cliente), cuenta(Producto), dict(
        db.query(Factura.emisor_id, func.count()).filter(Factura.uuid.isnot(None)).group_by(Factura.emisor_id).all())
    return [{"id": e.id, "rfc": e.rfc, "nombre": e.nombre, "ambiente": e.ambiente, "tiene_csd": bool(e.cer and e.key_enc),
             "clientes": clientes.get(e.id, 0), "productos": productos.get(e.id, 0), "facturas": facturas.get(e.id, 0),
             # lo de PRUEBAS del SAT (EKU…, o cualquier emisor con un CSD de prueba) no se lleva a la web de forma predeterminada
             "sugerido": not es_de_pruebas(e, RFC_PRUEBAS_SAT)}
            for e in db.query(Emisor).filter(Emisor.activo.is_(True)).order_by(Emisor.rfc)]


def exportar(db: Session, emisor_ids: list[int], con_facturas: bool, clave: str) -> tuple[bytes, list[dict]]:
    if len(clave or "") < MIN_CLAVE:
        raise MigracionError(f"La contraseña del archivo debe tener al menos {MIN_CLAVE} caracteres.")
    emisores = db.query(Emisor).filter(Emisor.id.in_(emisor_ids)).order_by(Emisor.rfc).all() if emisor_ids else []
    if len(emisores) != len(set(emisor_ids)):
        raise MigracionError("Alguno de los emisores elegidos no existe en esta cuenta.")
    if not emisores:
        raise MigracionError("Elige al menos un emisor.")
    paquete: dict = {"formato": 1, "creado": datetime.now().isoformat(timespec="seconds"), "con_facturas": con_facturas, "emisores": [],
                     "addendas": {str(a.id): a.nombre for a in db.query(Addenda)}}
    resumen = []
    for e in emisores:
        item: dict = {"_id": e.id, **{c: _a_json(getattr(e, c)) for c in CAMPOS_EMISOR}, "series": [], "csd": None}
        avisos = []
        if e.cer and e.key_enc and e.key_password_enc:
            try:
                item["csd"] = {"cer": _a_json(e.cer), "key": _a_json(decrypt(e.key_enc)), "password": decrypt(e.key_password_enc).decode("utf-8")}
            except Exception:  # la llave de este servidor ya no abre lo guardado (BD de otra instalación)
                avisos.append("El CSD no se pudo descifrar con la llave de este servidor: no va en el archivo.")
        item["series"] = [_fila(s, {"id", "emisor_id"}) for s in db.query(Serie).filter(Serie.emisor_id == e.id)]
        cuentas = {}
        for nombre, modelo, fks in HIJAS:
            if nombre == "facturas" and not con_facturas:
                continue
            q = db.query(modelo).filter(modelo.emisor_id == e.id)
            if modelo is Factura:
                q = q.filter(Factura.uuid.isnot(None))  # sólo lo timbrado: borradores y errores no se llevan
            filas = q.order_by(modelo.id).all()  # en orden: un REP debe llegar después de las facturas que paga
            item[nombre] = [{"_id": r.id, **_fila(r, {"id", "emisor_id"})} for r in filas]
            cuentas[nombre] = len(filas)
        paquete["emisores"].append(item)
        resumen.append({"rfc": e.rfc, "nombre": e.nombre, "csd": bool(item["csd"]), "avisos": avisos, **cuentas, "series": len(item["series"])})
    archivo = _cerrar(paquete, clave)
    log.warning("MIGRACIÓN: se exportaron %s emisores (%s KB, con facturas=%s)", len(emisores), len(archivo) // 1024, con_facturas)
    return archivo, resumen


# ---------------------------------------------------------------- importar
def _remapear_payload(p, emisor_id: int, clientes: dict, facturas: dict, addendas: dict):
    """El payload de una factura o plantilla guarda ids de la instalación de origen: se cambian por los nuevos."""
    if not isinstance(p, dict):
        return p
    p = copy.deepcopy(p)
    if "emisor_id" in p:
        p["emisor_id"] = emisor_id
    if p.get("cliente_id") is not None:
        p["cliente_id"] = clientes.get(p["cliente_id"])
    for d in p.get("documentos") or []:
        if isinstance(d, dict) and d.get("factura_id") is not None:
            d["factura_id"] = facturas.get(d["factura_id"])
    add = p.get("addenda")
    if isinstance(add, dict) and add.get("addenda_id") is not None:
        nuevo = addendas.get(add["addenda_id"])
        p["addenda"] = {**add, "addenda_id": nuevo} if nuevo else None
    return p


def _remapear_config(cfg, terceros: dict):
    """Los perfiles rápidos de Facturar apuntan a un tercero por id."""
    cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    for p in cfg.get("perfiles") or []:
        if isinstance(p, dict) and p.get("tercero_id") is not None:
            p["tercero_id"] = terceros.get(p["tercero_id"])
    return cfg


def _columnas(modelo, omitir: set) -> set[str]:
    return {c.name for c in modelo.__table__.columns} - omitir


def importar(db: Session, paquete: dict, pac_id: int | None) -> list[dict]:
    """Crea lo que falta. NUNCA pisa un emisor que ya existe en esta cuenta (se salta). Quien llama hace commit o rollback
    (rollback = simulacro: el informe sale igual de exacto)."""
    ids_addendas = {a.nombre: a.id for a in db.query(Addenda)}
    addendas = {int(k): ids_addendas.get(v) for k, v in (paquete.get("addendas") or {}).items()}
    informe = []
    for item in paquete["emisores"]:
        rfc = str(item.get("rfc") or "").upper().strip()
        r = {"rfc": rfc, "nombre": item.get("nombre") or rfc, "estado": "nuevo", "motivo": "", "csd": "sin_csd", "avisos": []}
        informe.append(r)
        if not rfc:
            r["estado"], r["motivo"] = "error", "El emisor del archivo no trae RFC."
            continue
        if db.query(Emisor).filter(Emisor.rfc == rfc).first() is not None:
            r["estado"], r["motivo"] = "ya_existe", "Ya está en esta cuenta: no se toca (para volver a traerlo, bórralo primero en Emisores)."
            continue
        e = Emisor(**{c: _de_json(item[c]) for c in CAMPOS_EMISOR if c in item and c != "creado"}, pac_id=pac_id)
        if item.get("creado"):
            e.creado = _de_json(item["creado"])
        e.portal_activo, e.portal_clave = False, None
        db.add(e)
        db.flush()  # el emisor ya existe y es de esta cuenta: lo que cuelga de él pasa la revisión de dueño
        csd = item.get("csd")
        if csd:
            try:
                signer.cargar_csd(e, _de_json(csd["cer"]), _de_json(csd["key"]), csd["password"])
                r["csd"] = "ok"
            except signer.CsdError as ex:
                r["csd"] = "no_valido"
                r["avisos"].append(f"El CSD no se pudo cargar: {ex} Súbelo de nuevo en Emisores y CSD.")
        for s in item.get("series") or []:
            db.add(Serie(emisor_id=e.id, **{k: _de_json(v) for k, v in s.items() if k in _columnas(Serie, {"id", "emisor_id"})}))
        mapas: dict[str, dict] = {"@addendas": addendas}
        for nombre, modelo, fks in HIJAS:
            filas = item.get(nombre) or []
            mapas[nombre] = {}
            validas = _columnas(modelo, {"id", "emisor_id"} | set(fks))
            existen: set[str] = set()
            if modelo is Factura:  # un UUID ya registrado (aquí o en otra cuenta) no se duplica
                uuids = [f["uuid"] for f in filas if f.get("uuid")]
                tf = Factura.__table__
                for i in range(0, len(uuids), 400):
                    existen.update(db.connection().execute(select(tf.c.uuid).where(tf.c.uuid.in_(uuids[i:i + 400]))).scalars())
            nuevos = omitidas = 0
            for f in filas:
                if modelo is Factura and f.get("uuid") in existen:
                    omitidas += 1
                    continue
                datos = {k: _de_json(v) for k, v in f.items() if k in validas}
                for col, tabla in fks.items():
                    viejo = f.get(col)
                    datos[col] = mapas.get(tabla, {}).get(viejo) if viejo is not None else None
                if "payload" in datos:
                    datos["payload"] = _remapear_payload(datos["payload"], e.id, mapas["clientes"], mapas.get("facturas", {}), addendas)
                obj = modelo(emisor_id=e.id, **datos)
                db.add(obj)
                db.flush()
                if f.get("_id") is not None:
                    mapas[nombre][f["_id"]] = obj.id
                nuevos += 1
            r[nombre] = nuevos
            if omitidas:
                r["avisos"].append(f"{omitidas} factura(s) ya existían (mismo UUID) y no se repitieron.")
        e.config_facturar = _remapear_config(e.config_facturar, mapas["terceros"])
        _alcanzar_folios(db, e.id)
        r["series"] = len(item.get("series") or [])
        # el PAC no viaja: el emisor queda con el de la plataforma (si lo hay) o en modo demo hasta que le asignes uno
        if pac_id is None:
            r["avisos"].append("No hay PAC asignado: el emisor queda en modo demo. Elígele su PAC en Emisores.")
    return informe


def _alcanzar_folios(db: Session, emisor_id: int) -> None:
    """Que el siguiente folio de cada serie nunca quede por debajo de lo ya emitido (evita repetir un folio)."""
    mayor: dict[str, int] = {}
    for serie, folio in db.query(Factura.serie, Factura.folio).filter(Factura.emisor_id == emisor_id, Factura.uuid.isnot(None)):
        if serie is not None and str(folio or "").isdigit():
            mayor[serie] = max(mayor.get(serie, 0), int(folio))
    for s in db.query(Serie).filter(Serie.emisor_id == emisor_id):
        if s.serie in mayor and s.siguiente_folio <= mayor[s.serie]:
            s.siguiente_folio = mayor[s.serie] + 1
