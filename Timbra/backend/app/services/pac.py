"""Capa de PAC. Tú compras el PAC, lo das de alta en /pacs y listo.

Todos los PACs soportados por satcfdi exponen la misma interfaz:
    stamp(cfdi) -> Document(document_id=UUID, xml=bytes)
    cancel(cfdi, reason, substitution_id, signer) -> CancelationAcknowledgment
    status(cfdi) -> dict
Si cambias de PAC, no tocas nada más.
"""
import uuid as uuidlib
from datetime import datetime

from lxml import etree
from satcfdi.cfdi import CFDI
from satcfdi.pacs import CancelationAcknowledgment, CancelReason, Document, Environment

from ..logs import log, paso
from ..models import Pac
from ..security import decrypt


class PacError(Exception):
    def __init__(self, msg: str, diag=None):
        super().__init__(msg)
        self.diag = diag  # errores_pac.Diagnostico o None


def _dec(b):
    v = decrypt(b)
    return v.decode() if v else None


class DemoPac:
    """PAC falso para desarrollar sin gastar timbres.
    Agrega un TimbreFiscalDigital de mentira. NO es válido ante el SAT."""

    TFD_NS = "http://www.sat.gob.mx/TimbreFiscalDigital"
    cancelados: set[str] = set()  # para que /estatus refleje la cancelación como lo haría el SAT

    def stamp(self, cfdi, accept=None) -> Document:
        uid = str(uuidlib.uuid4()).upper()
        root = etree.fromstring(cfdi.xml_bytes())
        cfdi_ns = root.nsmap.get("cfdi")
        comp = root.find(f"{{{cfdi_ns}}}Complemento")
        if comp is None:
            comp = etree.SubElement(root, f"{{{cfdi_ns}}}Complemento")
        tfd = etree.SubElement(comp, f"{{{self.TFD_NS}}}TimbreFiscalDigital", nsmap={"tfd": self.TFD_NS})
        tfd.set("Version", "1.1")
        tfd.set("UUID", uid)
        tfd.set("FechaTimbrado", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        tfd.set("RfcProvCertif", "SPR190613I52")
        tfd.set("SelloCFD", root.get("Sello", ""))
        tfd.set("NoCertificadoSAT", "00000000000000000000")
        tfd.set("SelloSAT", "DEMO")
        xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
        return Document(document_id=uid, xml=xml)

    def cancel(self, cfdi, reason, substitution_id=None, signer=None):
        self.cancelados.add(cfdi["Complemento"]["TimbreFiscalDigital"]["UUID"].upper())
        return CancelationAcknowledgment(code="201", acuse=b"<Acuse demo='1'/>")

    def status(self, cfdi):
        if cfdi["Complemento"]["TimbreFiscalDigital"]["UUID"].upper() in self.cancelados:
            return {"Estado": "Cancelado", "EstatusCancelacion": "Cancelado sin aceptación", "demo": True}
        return {"Estado": "Vigente", "EsCancelable": "Cancelable sin aceptacion", "demo": True}


def get_pac(pac: Pac | None):
    if pac is None or pac.proveedor == "demo":
        return DemoPac()
    env = Environment.TEST if pac.pruebas else Environment.PRODUCTION
    pwd, tok, ex = _dec(pac.password_enc), _dec(pac.token_enc), pac.extra or {}
    p = pac.proveedor
    if p == "finkok":
        from satcfdi.pacs.finkok import Finkok
        return Finkok(username=pac.usuario, password=pwd, environment=env)
    if p == "swsapien":
        from satcfdi.pacs.swsapien import SWSapien
        return SWSapien(token=tok, user=pac.usuario, password=pwd, environment=env)
    if p == "diverza":
        from satcfdi.pacs.diverza import Diverza
        return Diverza(rfc=ex.get("rfc"), id=pac.usuario, token=tok, environment=env)
    if p == "prodigia":
        from satcfdi.pacs.prodigia import Prodigia
        return Prodigia(user=pac.usuario, password=pwd, contrato=ex.get("contrato"), environment=env)
    if p == "facturama":
        raise PacError("Facturama no timbra XML ya sellado por tu sistema (sella con sus propios servicios). "
                       "Usa Finkok o SW Sapien.")
    if p == "comerciodigital":
        from satcfdi.pacs.comerciodigital import ComercioDigital
        return ComercioDigital(user=pac.usuario, password=pwd, environment=env)
    if p == "mysuite":
        from satcfdi.pacs.mysuite import MYSuite
        return MYSuite(requestor=ex.get("requestor"), country=ex.get("country", "MX"),
                       user_name=pac.usuario, environment=env)
    raise PacError(f"PAC no soportado: {p}")


def registrar_emisor(pac: Pac, rfc: str) -> str:
    """Da de alta el RFC emisor en la cuenta de Finkok (tipo OnDemand: se paga lo que se timbra). Sin esto Finkok responde
    702 al timbrar. Es seguro repetirlo: si ya existe, Finkok lo dice y no pasa nada. Devuelve el mensaje de Finkok."""
    import requests
    from lxml import etree
    if pac is None or pac.proveedor != "finkok":
        raise PacError("El alta automática del RFC sólo existe para Finkok.")
    host = "https://demo-facturacion.finkok.com" if pac.pruebas else "https://facturacion.finkok.com"
    ns = "http://facturacion.finkok.com/registration"
    env = etree.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope", nsmap={"soapenv": "http://schemas.xmlsoap.org/soap/envelope/", "reg": ns})
    etree.SubElement(env, "{http://schemas.xmlsoap.org/soap/envelope/}Header")
    add = etree.SubElement(etree.SubElement(env, "{http://schemas.xmlsoap.org/soap/envelope/}Body"), f"{{{ns}}}add")
    for campo, valor in (("reseller_username", pac.usuario), ("reseller_password", _dec(pac.password_enc)),
                         ("taxpayer_id", rfc.upper()), ("type_user", "O")):
        etree.SubElement(add, f"{{{ns}}}{campo}").text = valor or ""
    with paso(f"Dar de alta {rfc} en {_nombre(pac)}"):
        r = requests.post(f"{host}/servicios/soap/registration", data=etree.tostring(env, xml_declaration=True, encoding="UTF-8"),
                          headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "add"}, timeout=30)
    try:
        raiz = etree.fromstring(r.content)
    except etree.XMLSyntaxError:
        raise PacError(f"Finkok no contestó bien al dar de alta {rfc} (HTTP {r.status_code}).")
    dato = {etree.QName(n).localname: (n.text or "") for n in raiz.iter() if isinstance(n.tag, str) and not len(n)}
    mensaje = dato.get("message") or dato.get("faultstring") or r.text[:200]
    ok = dato.get("success", "").lower() == "true" or "already" in mensaje.lower() or "ya exist" in mensaje.lower()
    log.info("Alta de %s en Finkok: %s", rfc, mensaje)
    if not ok:
        if "authentication" in mensaje.lower():
            raise PacError(f"Finkok rechazó el usuario o la contraseña de {pac.nombre}: revísalos en Ajustes → PAC ({mensaje}).")
        raise PacError(f"Finkok no dio de alta el RFC {rfc}: {mensaje}")
    if "already" in mensaje.lower():
        return "ya estaba dado de alta"
    if "created" in mensaje.lower():
        return "dado de alta ahora"
    return mensaje


def _nombre(pac: Pac | None) -> str:
    if pac is None or pac.proveedor == "demo":
        return "PAC demo"
    return f"{pac.nombre} ({pac.proveedor}, {'pruebas' if pac.pruebas else 'PRODUCCIÓN'})"


REINTENTOS = 2
ESPERA = (2, 5)  # segundos entre reintentos de red


def _texto_error(e: Exception) -> str:
    r = getattr(e, "response", None)
    cuerpo = getattr(r, "text", None) or getattr(r, "content", None) or ""
    return f"{e} {cuerpo!s}"[:4000]


def _recuperar(obj, cfdi):
    """El PAC dice que ya lo timbró: pedirle ese XML (mismo sello → mismo UUID). Sólo Finkok lo expone en satcfdi."""
    if hasattr(obj, "stamped"):
        return obj.stamped(cfdi)
    return None


def timbrar(pac: Pac | None, cfdi) -> tuple[str, bytes]:
    import time

    from .errores_pac import diagnosticar

    obj = get_pac(pac)
    alta_hecha = False
    for intento in range(REINTENTOS + 2):
        try:
            with paso(f"Timbrar con {_nombre(pac)}", serie=cfdi.get("Serie"), folio=cfdi.get("Folio"),
                      total=str(cfdi.get("Total")), intento=intento + 1):
                doc = obj.stamp(cfdi)
            break
        except Exception as e:  # los PACs regresan errores muy variados: se guarda el texto exacto
            texto = _texto_error(e)
            d = diagnosticar(texto)
            log.error("Respuesta del PAC: %s", texto[:600],
                      extra={"datos": {"tipo": type(e).__name__, "texto": texto, "diagnostico": d.clave if d else None}})
            if d and d.accion == "recuperar":
                try:
                    doc = _recuperar(obj, cfdi)
                except Exception as e2:
                    log.warning("No se pudo recuperar el timbre previo: %s", e2)
                    doc = None
                if doc is not None:
                    log.info("Recuperado el timbre previo del mismo CFDI (no se duplicó)")
                    break
            if d and d.clave == "rfc_pac" and pac is not None and pac.proveedor == "finkok" and not alta_hecha:
                # El RFC aún no está en la cuenta de Finkok: se da de alta y se vuelve a intentar con el mismo XML sellado
                alta_hecha = True
                try:
                    registrar_emisor(pac, str(cfdi["Emisor"]["Rfc"]))
                    continue
                except Exception as e3:  # noqa: BLE001
                    log.warning("No se pudo dar de alta el RFC en Finkok: %s", e3)
            if d and d.accion == "reintentar" and intento < REINTENTOS:
                log.warning("Reintento %s/%s con el mismo XML sellado en %ss", intento + 1, REINTENTOS, ESPERA[intento])
                time.sleep(ESPERA[intento])
                continue
            msg = d.texto(str(e)) if d else f"El PAC rechazó el CFDI: {e}"
            raise PacError(msg, d) from e
    log.info("Timbre recibido UUID %s", doc.document_id.upper())
    return doc.document_id.upper(), doc.xml


def probar(pac: Pac, emisor, signer, ciclo: bool = False) -> dict:
    """Timbra un CFDI mínimo en el AMBIENTE DE PRUEBAS del PAC (no cuesta ni tiene validez fiscal).
    ciclo=True además lo cancela (motivo 02) y consulta su estatus: las 3 pruebas que pide Finkok para producción."""
    from datetime import datetime
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from satcfdi.create.cfd import cfdi40

    if not pac.pruebas:
        raise PacError("La prueba sólo corre con el PAC en ambiente de pruebas (para no gastar un timbre real).")
    from .cfdi import ahora_mx
    ahora = ahora_mx(emisor.lugar_expedicion)
    comp = cfdi40.Comprobante(
        emisor=cfdi40.Emisor(rfc=emisor.rfc, nombre=emisor.nombre, regimen_fiscal=emisor.regimen_fiscal),
        lugar_expedicion=emisor.lugar_expedicion,
        receptor=cfdi40.Receptor(rfc="XAXX010101000", nombre="PUBLICO EN GENERAL",
                                 domicilio_fiscal_receptor=emisor.lugar_expedicion,
                                 regimen_fiscal_receptor="616", uso_cfdi="S01"),
        informacion_global=cfdi40.InformacionGlobal(periodicidad="04", meses=f"{ahora.month:02d}", ano=ahora.year),
        conceptos=[cfdi40.Concepto(clave_prod_serv="01010101", cantidad=1, clave_unidad="ACT", descripcion="Venta",
                                   valor_unitario=Decimal("1.00"), objeto_imp="02",
                                   impuestos=cfdi40.Impuestos(traslados=cfdi40.Traslado(
                                       impuesto="002", tipo_factor="Tasa", tasa_o_cuota=Decimal("0.160000"))))],
        forma_pago="01", metodo_pago="PUE", serie="PRUEBA", folio="1", fecha=ahora,
    )
    comp.sign(signer)
    import time
    t0 = time.perf_counter()
    uuid, xml = timbrar(pac, comp)
    out = {"ok": True, "uuid": uuid, "ms": round((time.perf_counter() - t0) * 1000), "emisor": emisor.rfc}
    if not ciclo:
        return out
    t0 = time.perf_counter()
    ack = cancelar(pac, xml, "02", None, signer)
    out["cancelacion"] = {"codigo": str(ack.code), "aceptada": cancelacion_aceptada(ack.code),
                          "ms": round((time.perf_counter() - t0) * 1000)}
    try:  # en sandbox el SAT a veces aún no "ve" el CFDI de prueba: se reporta, no truena
        out["estatus"] = estatus(pac, xml)
    except Exception as e:
        out["estatus"] = {"error": str(e)}
    out["ok"] = out["cancelacion"]["aceptada"]
    return out


# Códigos de EstatusUUID del SAT al pedir una cancelación (los regresan Finkok y SW tal cual).
CANCEL_OK = {"201": "Solicitud de cancelación recibida", "202": "Ya estaba cancelado"}
CANCEL_ERRORES = {
    "203": "El UUID no corresponde al emisor", "204": "El UUID no aplica para cancelación",
    "205": "El UUID no existe (o el SAT aún no lo registra; reintenta en unos minutos)",
    "206": "El UUID no corresponde a un CFDI del sector primario", "207": "Falta el UUID que sustituye (motivo 01)",
    "208": "El UUID sustituto no es válido", "209": "El UUID sustituto es el mismo que se cancela",
    "210": "No es cancelable: tiene CFDI relacionados vigentes (REP o notas de crédito)",
    "211": "Ya hay una solicitud de cancelación en proceso",
    "212": "No cancelable: el receptor ya rechazó la cancelación o fuera de plazo",
    "708": "el SAT no respondió al PAC (falla de conexión del SAT). La factura sigue vigente: reintenta en unos minutos",
}


def _codigo(code) -> str:
    """El acuse trae el código como texto ("201"), dict (SW) o con texto pegado; se saca el número."""
    import re
    if isinstance(code, dict):
        code = code.get("estatusUUID") or code.get("EstatusUUID") or next(iter(code.values()), "")
    m = re.search(r"\b(\d{3})\b", str(code or ""))
    return m.group(1) if m else str(code or "")


def cancelacion_aceptada(code) -> bool:
    return _codigo(code) in CANCEL_OK


def estado_sat(st: dict) -> str:
    """Traduce la consulta de estatus a nuestro estado: cancelada | cancelacion_pendiente | timbrada | ? (no se sabe)."""
    estado = str(st.get("Estado", "")).lower()
    proceso = str(st.get("EstatusCancelacion", "")).lower()
    if estado.startswith("cancelado"):
        return "cancelada"
    if "proceso" in proceso:
        return "cancelacion_pendiente"
    if estado == "vigente":  # incluye "Solicitud rechazada" por el receptor y "Plazo vencido"
        return "timbrada"
    return "?"


def cancelar(pac: Pac | None, xml: bytes, motivo: str, sustitucion: str | None, signer):
    cfdi = CFDI.from_string(xml)
    try:
        with paso(f"Cancelar con {_nombre(pac)}", motivo=motivo, sustitucion=sustitucion):
            ack = get_pac(pac).cancel(cfdi, CancelReason(motivo), sustitucion, signer)
    except Exception as e:
        from .errores_pac import diagnosticar
        d = diagnosticar(_texto_error(e))
        raise PacError(d.texto(str(e)) if d else f"No se pudo cancelar: {e}", d) from e
    cod = _codigo(ack.code)
    log.info("Acuse de cancelación: %s (%s)", ack.code, CANCEL_OK.get(cod) or CANCEL_ERRORES.get(cod, "código desconocido"))
    if cod not in CANCEL_OK:
        raise PacError(f"El SAT no aceptó la cancelación: {cod} {CANCEL_ERRORES.get(cod, ack.code)}")
    return ack


def _finkok_get_sat_status(pac_obj, cfdi) -> dict:
    """get_sat_status de Finkok (cancel.wsdl). Finkok lo pide para dar el pase a producción."""
    ns = pac_obj.namespaces["cancel"]
    op = etree.Element(etree.QName(ns, "get_sat_status"))
    pac_obj._add_auth(op, ns)
    for tag, val in (("taxpayer_id", cfdi["Emisor"]["Rfc"]), ("rtaxpayer_id", cfdi["Receptor"]["Rfc"]),
                     ("uuid", cfdi["Complemento"]["TimbreFiscalDigital"]["UUID"]), ("total", str(cfdi["Total"]))):
        etree.SubElement(op, etree.QName(ns, tag)).text = val
    root = pac_obj._perform_request(pac_obj.get_service_url("cancel"), pac_obj._build_envelope(op))
    out = {}
    for campo in ("CodigoEstatus", "Estado", "EsCancelable", "EstatusCancelacion", "error"):
        el = root.find(f".//{{*}}{campo}")
        if el is not None and (el.text or "").strip():
            out[campo] = el.text.strip()
    return out


def estatus(pac: Pac | None, xml: bytes) -> dict:
    """Estatus ante el SAT. Finkok → get_sat_status; demo → simulado; otros → su método o el servicio público del SAT."""
    cfdi = CFDI.from_string(xml)
    obj = get_pac(pac)
    with paso(f"Consultar estatus SAT vía {_nombre(pac)}"):
        if pac is not None and pac.proveedor == "finkok":
            r = _finkok_get_sat_status(obj, cfdi)
        else:
            try:
                r = obj.status(cfdi)
            except (AttributeError, NotImplementedError):
                from satcfdi.pacs.sat import SAT
                r = SAT().status(cfdi)
    log.info("Estatus SAT: %s", r)
    return r
