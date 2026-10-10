"""Descarga masiva del SAT (web service v1.5) con la e.firma del emisor.

Flujo del SAT: solicitar → (minutos u horas) verificar → descargar paquetes ZIP con los XML.
El programador llama a `revisar_pendientes` cada rato; no hay que esperar con la pantalla abierta.
Límites del SAT: una solicitud igual sólo se puede repetir pocas veces; CFDI recibidos cancelados no se
descargan en XML (sólo en Metadata).
"""
import base64
import io
import zipfile
from datetime import datetime
from decimal import Decimal

from satcfdi.cfdi import CFDI
from satcfdi.models import Signer
from sqlalchemy.orm import Session

from ..logs import log, paso
from ..models import CfdiSat, Emisor, SolicitudSat
from ..security import decrypt, encrypt
from .signer import CsdError, _vence, motivo


def cargar_fiel(emisor: Emisor, cer: bytes, key: bytes, password: str):
    try:
        s = Signer.load(certificate=cer, key=key, password=password)
    except Exception as e:
        raise CsdError(motivo(e, "e.firma")) from e
    if s.rfc.upper() != emisor.rfc.upper():
        raise CsdError(f"La e.firma es de {s.rfc}, no de {emisor.rfc}.")
    if getattr(s, "type", None) is not None and s.type.name.upper() != "FIEL":
        raise CsdError("Eso es un CSD, no la e.firma. La descarga masiva del SAT pide la e.firma (FIEL).")
    emisor.fiel_cer = cer
    emisor.fiel_key_enc = encrypt(key)
    emisor.fiel_password_enc = encrypt(password)
    emisor.fiel_vence = _vence(s)


def _sat(emisor: Emisor):
    from satcfdi.pacs.sat import SAT

    if not emisor.fiel_cer:
        raise CsdError(f"{emisor.rfc} no tiene e.firma cargada (Emisores → e.firma).")
    if emisor.fiel_vence and emisor.fiel_vence < datetime.now():
        raise CsdError(f"La e.firma de {emisor.rfc} venció el {emisor.fiel_vence:%d/%m/%Y}.")
    s = Signer.load(certificate=emisor.fiel_cer, key=decrypt(emisor.fiel_key_enc),
                    password=decrypt(emisor.fiel_password_enc).decode())
    return SAT(signer=s)


def solicitar(db: Session, emisor: Emisor, direccion: str, desde: datetime, hasta: datetime,
              tipo: str = "CFDI") -> SolicitudSat:
    sat = _sat(emisor)
    sol = SolicitudSat(emisor_id=emisor.id, direccion=direccion, tipo=tipo, desde=desde, hasta=hasta)
    with paso(f"Solicitar descarga SAT ({direccion}, {tipo})", rfc=emisor.rfc, desde=str(desde), hasta=str(hasta)):
        kw = dict(fecha_inicial=desde, fecha_final=hasta, tipo_solicitud=tipo)
        if direccion == "recibido":
            # XML de recibidos sólo se entregan vigentes
            r = sat.recover_comprobante_received_request(rfc_receptor=emisor.rfc,
                                                         estado_comprobante="Vigente" if tipo == "CFDI" else None, **kw)
        else:
            r = sat.recover_comprobante_emitted_request(rfc_emisor=emisor.rfc, **kw)
    log.info("Respuesta SAT: %s", r)
    sol.id_solicitud = r.get("IdSolicitud")
    cod, msg = str(r.get("CodEstatus", "")), r.get("Mensaje")
    sol.mensaje = f"{cod} {msg}".strip()
    sol.estado = "en_proceso" if cod == "5000" and sol.id_solicitud else "error"
    sol.actualizado = datetime.now()
    db.add(sol)
    db.commit()
    return sol


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _v(x):
    return getattr(x, "code", getattr(x, "value", x))


def _suma(nodo, impuesto: str) -> Decimal:
    """satcfdi entrega Traslados/Retenciones como dict {clave: {Impuesto: Code, Importe}}."""
    return sum((_d(t.get("Importe")) for t in (nodo or {}).values() if _v(t.get("Impuesto")) == impuesto), Decimal(0))


def _impuestos(c) -> tuple[Decimal, Decimal, Decimal]:
    imp = c.get("Impuestos") or {}
    return (_suma(imp.get("Traslados"), "002"), _suma(imp.get("Retenciones"), "002"),
            _suma(imp.get("Retenciones"), "001"))


def guardar_xml(db: Session, emisor: Emisor, xml: bytes) -> bool:
    c = CFDI.from_string(xml)
    uuid = c["Complemento"]["TimbreFiscalDigital"]["UUID"].upper()
    if db.query(CfdiSat).filter_by(emisor_id=emisor.id, uuid=uuid).first():
        return False
    iva, iva_r, isr_r = _impuestos(c)
    direccion = "emitido" if c["Emisor"]["Rfc"].upper() == emisor.rfc else "recibido"
    db.add(CfdiSat(
        emisor_id=emisor.id, uuid=uuid, direccion=direccion, tipo=_v(c["TipoDeComprobante"]), fecha=c["Fecha"],
        rfc_emisor=c["Emisor"]["Rfc"], nombre_emisor=c["Emisor"].get("Nombre"),
        rfc_receptor=c["Receptor"]["Rfc"], nombre_receptor=c["Receptor"].get("Nombre"),
        subtotal=_d(c["SubTotal"]), descuento=_d(c.get("Descuento")), iva=iva, iva_retenido=iva_r, isr_retenido=isr_r,
        total=_d(c["Total"]), moneda=_v(c.get("Moneda")), metodo_pago=_v(c.get("MetodoPago")),
        forma_pago=_v(c.get("FormaPago")), uso_cfdi=_v(c["Receptor"].get("UsoCFDI")), xml=xml,
    ))
    return True


def _metadata(db: Session, emisor: Emisor, txt: str) -> int:
    """Metadata: texto con ~ como separador. Trae el estatus (vigente/cancelado) aunque no traiga el XML."""
    n = 0
    lineas = txt.splitlines()
    if not lineas:
        return 0
    cab = [h.strip() for h in lineas[0].split("~")]
    for linea in lineas[1:]:
        v = dict(zip(cab, linea.split("~")))
        uuid = (v.get("Uuid") or "").upper()
        if not uuid:
            continue
        estado = "Cancelado" if v.get("Estatus") == "0" else "Vigente"
        ex = db.query(CfdiSat).filter_by(emisor_id=emisor.id, uuid=uuid).first()
        if ex:
            ex.estado = estado
            continue
        db.add(CfdiSat(
            emisor_id=emisor.id, uuid=uuid,
            direccion="emitido" if v.get("RfcEmisor", "").upper() == emisor.rfc else "recibido",
            tipo=v.get("EfectoComprobante"), fecha=datetime.fromisoformat(v["FechaEmision"]) if v.get("FechaEmision") else None,
            rfc_emisor=v.get("RfcEmisor", ""), nombre_emisor=v.get("NombreEmisor"), rfc_receptor=v.get("RfcReceptor", ""),
            nombre_receptor=v.get("NombreReceptor"), total=_d(v.get("Monto")), estado=estado,
        ))
        n += 1
    return n


def verificar(db: Session, sol: SolicitudSat) -> SolicitudSat:
    emisor = db.get(Emisor, sol.emisor_id)
    sat = _sat(emisor)
    with paso("Verificar solicitud SAT", id=sol.id_solicitud):
        r = sat.recover_comprobante_status(sol.id_solicitud)
    estado = int(r.get("EstadoSolicitud") or 0)
    sol.mensaje = f"{r.get('CodigoEstadoSolicitud', '')} {r.get('Mensaje', '')}".strip()
    sol.actualizado = datetime.now()
    if estado == 3:
        sol.paquetes = list(r.get("IdsPaquetes") or [])
        n = 0
        for paquete in sol.paquetes:
            with paso("Descargar paquete SAT", paquete=paquete):
                _, zb64 = sat.recover_comprobante_download(paquete)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(zb64))) as z:
                for nombre in z.namelist():
                    data = z.read(nombre)
                    if nombre.lower().endswith(".xml"):
                        n += guardar_xml(db, emisor, data)
                    elif nombre.lower().endswith(".txt"):
                        n += _metadata(db, emisor, data.decode("utf-8-sig", errors="replace"))
        sol.descargados = n
        sol.estado = "terminada"
    elif estado in (1, 2):
        sol.estado = "en_proceso"
    elif str(r.get("CodigoEstadoSolicitud")) == "5004":
        sol.estado = "sin_datos"
    else:
        sol.estado = "error"
    db.commit()
    return sol


def revisar_pendientes(db: Session) -> int:
    n = 0
    for sol in db.query(SolicitudSat).filter(SolicitudSat.estado == "en_proceso").all():
        try:
            verificar(db, sol)
            n += 1
        except Exception as e:
            db.rollback()
            log.warning("No se pudo verificar la solicitud SAT %s: %s", sol.id_solicitud, e)
    return n
