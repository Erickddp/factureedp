"""Flujo completo: armar -> sellar -> timbrar -> addenda -> guardar -> (correo)."""
import re
from decimal import Decimal

from satcfdi.cfdi import CFDI
from sqlalchemy.orm import Session

from ..models import Addenda, Cliente, Emisor, Empleado, Factura
from ..schemas import FacturaIn, NominaIn, PagoIn
from . import addenda as addenda_svc
from . import cfdi as cfdi_svc
from ..logs import log, paso
from . import folios, mailer, nomina as nomina_svc, pac as pac_svc, pdf as pdf_svc, respaldo, timbres, validacion
from .signer import signer_de


class FacturacionError(Exception):
    pass


class TimbradoSinGuardar(FacturacionError):
    """El PAC ya timbró pero la BD no lo guardó y no se pudo recuperar: NUNCA reintentar (duplicaría el timbre)."""

    def __init__(self, uuid: str, causa: Exception):
        super().__init__(f"Se timbró (UUID {uuid}) pero no se pudo guardar en la base: {causa}. "
                         "No vuelvas a timbrar: usa Facturas → Recuperar desde respaldo.")
        self.uuid = uuid


def _respaldar(rfc: str, uuid: str, xml: bytes) -> str | None:
    """Respaldo en disco tras timbrar. Si el disco falla, se avisa pero se sigue: la BD también guarda el XML."""
    try:
        return respaldo.guardar(rfc, uuid, xml)
    except Exception:
        log.exception("No se pudo escribir el respaldo XML de %s (se guarda sólo en la base)", uuid)
        return None


def _guardar(db: Session, obj: Factura, uuid: str, antes=None) -> Factura:
    """Commit tras timbrar. Si la BD falla, se intenta recuperar desde el respaldo en disco en ese momento."""
    try:
        if antes:
            antes()
        db.add(obj)
        db.commit()
        return obj
    except Exception as e:
        db.rollback()
        log.exception("La base falló al guardar %s; intento recuperarlo del respaldo", uuid)
        try:
            recuperar(db)
            f = db.query(Factura).filter_by(uuid=uuid).first()
        except Exception:
            db.rollback()
            f = None
        if f is None:
            raise TimbradoSinGuardar(uuid, e) from e
        f.payload = obj.payload
        f.empleado_id = obj.empleado_id
        f.error = "Recuperada automáticamente del respaldo tras un error de la base."
        # El rollback regresó el contador de folios: se adelanta para no repetir este folio
        from ..models import Serie
        s = db.query(Serie).filter_by(emisor_id=f.emisor_id, serie=f.serie).first()
        if s and str(f.folio or "").isdigit() and s.siguiente_folio <= int(f.folio):
            s.siguiente_folio = int(f.folio) + 1
        db.commit()
        return f


def _modo_pruebas(emisor: Emisor) -> bool:
    return emisor.pac is None or emisor.pac.proveedor == "demo" or emisor.pac.pruebas


def _cliente(db: Session, emisor: Emisor, data: FacturaIn) -> Cliente | None:
    if data.cliente_id:
        c = db.get(Cliente, data.cliente_id)
        if not c or c.emisor_id != emisor.id:
            raise FacturacionError("Ese cliente no es de este emisor.")
        return c
    if data.receptor and data.receptor.guardar:
        r = data.receptor
        c = db.query(Cliente).filter_by(emisor_id=emisor.id, rfc=r.rfc.upper(), nombre=r.nombre.upper()).first()
        if not c:
            c = Cliente(emisor_id=emisor.id, rfc=r.rfc.upper(), nombre=r.nombre.upper(),
                        regimen_fiscal=r.regimen_fiscal, codigo_postal=r.codigo_postal, uso_cfdi=r.uso_cfdi,
                        residencia_fiscal=r.residencia_fiscal, num_reg_id_trib=r.num_reg_id_trib)
            db.add(c)
            db.flush()
        return c
    return None


def previsualizar(db: Session, data: FacturaIn) -> dict:
    """Totales en vivo + validaciones SAT. Si aún no hay receptor, calcula con público en general."""
    emisor = db.get(Emisor, data.emisor_id)
    if not emisor:
        raise FacturacionError("Emisor no existe.")
    cliente = db.get(Cliente, data.cliente_id) if data.cliente_id else None
    val = validacion.validar(db, emisor, data, cliente)
    calc = data if (data.publico_general or cliente or data.receptor) else data.model_copy(update={"publico_general": True})
    try:
        comp = cfdi_svc.construir(emisor, calc, cliente, data.serie or "PREVIEW", "0")
        t = cfdi_svc.totales(comp)
        t["xml_preview"] = comp.xml_bytes().decode()
    except Exception as e:
        log.debug("Vista previa sin calcular: %s", e)
        t = {"subtotal": 0, "descuento": 0, "traslados": 0, "retenciones": 0, "total": 0, "xml_preview": None}
        if not val["errores"]:
            val["errores"].append({"campo": "cfdi", "mensaje": f"No se pudo armar el CFDI: {e}", "sugerencia": None})
    return {**t, **val}


def _hay_timbres(db: Session, emisor: Emisor):
    msg = timbres.bloqueo(emisor.pac, db) or timbres.sin_saldo(db, emisor)
    if msg:
        raise FacturacionError(msg)


def _timbrar(db: Session, emisor: Emisor, comp):
    """Timbra y, si la cuenta factura con el PAC de la plataforma, le descuenta un timbre (sólo si el PAC sí timbró).
    Antes de hablar con el PAC se confirma lo pendiente (el folio apartado): SQLite tiene UN solo escritor, y si la
    transacción siguiera abierta durante la llamada al PAC (segundos), todas las demás cuentas esperarían en fila y
    terminarían en «database is locked». Si el PAC falla, quien llama regresa el folio con folios.devolver."""
    msg = timbres.sin_saldo(db, emisor)
    if msg:
        raise FacturacionError(msg)
    db.commit()
    uuid, xml = pac_svc.timbrar(emisor.pac, comp)
    timbres.consumir(db, emisor)
    return uuid, xml


def _validar_o_fallar(db: Session, emisor: Emisor, data: FacturaIn, cliente: Cliente | None):
    _hay_timbres(db, emisor)
    val = validacion.validar(db, emisor, data, cliente)
    for a in val["avisos"]:
        log.info("Aviso: %s", a["mensaje"])
    if val["errores"]:
        msgs = [e["mensaje"] for e in val["errores"]]
        log.warning("Validación SAT detuvo el timbrado (%s errores)", len(msgs), extra={"datos": {"errores": msgs}})
        raise FacturacionError("No timbré, corrige esto: " + " · ".join(msgs))


def _post_timbrado(factura: Factura, xml: bytes, uuid: str):
    cfdi = CFDI.from_string(xml)
    factura.xml = xml
    factura.uuid = uuid
    factura.estado = "timbrada"
    tfd = cfdi["Complemento"]["TimbreFiscalDigital"]
    factura.fecha_timbrado = tfd["FechaTimbrado"]
    factura.fecha = cfdi["Fecha"]


def emitir(db: Session, data: FacturaIn, fila_id: int | None = None) -> Factura:
    emisor = db.get(Emisor, data.emisor_id)
    if not emisor:
        raise FacturacionError("Emisor no existe.")
    cliente = _cliente(db, emisor, data)
    _validar_o_fallar(db, emisor, data, cliente)
    try:
        if data.folio:  # folio explícito (el de tu hoja): se usa tal cual o no se timbra
            serie, folio = folios.tomar(db, emisor.id, data.tipo, data.serie, data.folio, fila_id=fila_id)
        else:
            serie, folio = folios.siguiente(db, emisor.id, data.tipo, data.serie)
    except folios.FolioError as e:
        raise FacturacionError(str(e)) from e
    receptor = "PUBLICO EN GENERAL" if data.publico_general else (cliente.rfc if cliente else data.receptor.rfc)
    log.info("Emitiendo %s %s%s para %s", {"I": "factura", "E": "nota de crédito", "T": "traslado"}[data.tipo],
             serie, folio, receptor)

    with paso("Armar CFDI 4.0", conceptos=len(data.conceptos)):
        comp = cfdi_svc.construir(emisor, data, cliente, serie, folio)

    # Addenda: la explícita, o la del cliente sólo en facturas de ingreso.
    # Se valida ANTES de timbrar para no quemar un timbre por un dato faltante.
    add_id = data.addenda.addenda_id if data.addenda else (
        cliente.addenda_id if cliente and data.tipo == "I" else None)
    tpl, datos = None, {}
    if add_id:
        tpl = db.get(Addenda, add_id)
        datos = {**((cliente.addenda_defaults if cliente else {}) or {}), **(data.addenda.datos if data.addenda else {})}
        addenda_svc.render(tpl.plantilla, datos, comp)

    try:
        with paso("Sellar con CSD", no_certificado=emisor.no_certificado):
            comp.sign(signer_de(emisor, permitir_vencido=_modo_pruebas(emisor)))
        try:
            uuid, xml = _timbrar(db, emisor, comp)
        except pac_svc.PacError as e:
            # Autocorrección segura: el PAC rechazó por fecha (nada se timbró) → re-armar con la hora actual y re-sellar
            if not (e.diag and e.diag.accion == "refechar" and data.fecha is None):
                raise
            log.warning("Fecha rechazada por el PAC: re-armo con la hora actual y reintento una vez")
            comp = cfdi_svc.construir(emisor, data, cliente, serie, folio)
            if tpl:
                addenda_svc.render(tpl.plantilla, datos, comp)
            comp.sign(signer_de(emisor, permitir_vencido=_modo_pruebas(emisor)))
            uuid, xml = _timbrar(db, emisor, comp)
    except Exception:
        folios.devolver(db, emisor.id, serie, folio)
        raise
    ruta = _respaldar(emisor.rfc, uuid, xml)  # primero al disco, luego a la BD
    log.info("Respaldo XML: %s", ruta)
    aviso_addenda = None
    if tpl:
        try:  # el timbre ya existe: si la addenda falla, la factura se guarda sin ella
            xml = addenda_svc.inyectar(xml, tpl.plantilla, datos, comp)
            _respaldar(emisor.rfc, uuid, xml)
            log.info("Addenda «%s» aplicada", tpl.nombre)
        except Exception as e:
            log.exception("La addenda falló después del timbre")
            aviso_addenda = f"Timbrada OK, pero la addenda no se pudo agregar: {e}"

    t = cfdi_svc.totales(comp)
    f = Factura(
        emisor_id=emisor.id, cliente_id=cliente.id if cliente else None, tipo=data.tipo,
        serie=serie, folio=folio, moneda=comp["Moneda"], tipo_cambio=data.tipo_cambio,
        metodo_pago=comp.get("MetodoPago"), forma_pago=comp.get("FormaPago"),
        subtotal=t["subtotal"], descuento=t["descuento"], total=t["total"],
        saldo=t["total"] if comp.get("MetodoPago") == "PPD" and data.tipo == "I" else Decimal(0),
        referencia=data.referencia,
        # sin folio/referencia: al clonar o repetir la factura no se hereda el folio de la hoja
        payload=data.model_dump(mode="json", exclude={"folio", "referencia"}),
    )
    _post_timbrado(f, xml, uuid)
    f.error = aviso_addenda
    f = _guardar(db, f, uuid)
    log.info("Guardada %s%s · UUID %s · total %s", serie, folio, uuid, t["total"])

    if data.enviar_email and cliente and cliente.emails:
        try:
            enviar(f, cliente.emails)
        except Exception as e:  # el correo no debe tumbar la factura
            log.exception("La factura se timbró pero el correo falló")
            f.error = f"Timbrada OK, pero el correo falló: {e}"
            db.commit()
    return f


def emitir_pago(db: Session, data: PagoIn) -> Factura:
    emisor = db.get(Emisor, data.emisor_id)
    cliente = db.get(Cliente, data.cliente_id)
    if not emisor or not cliente:
        raise FacturacionError("Emisor o cliente no existe.")
    docs, facturas = [], []
    for d in data.documentos:
        f = db.get(Factura, d.factura_id)
        if not f or f.estado != "timbrada" or f.tipo != "I":
            raise FacturacionError(f"La factura {d.factura_id} no está timbrada.")
        if f.metodo_pago != "PPD":
            raise FacturacionError(f"{f.serie}{f.folio} es PUE: no lleva complemento de pago.")
        if d.imp_pagado > f.saldo:
            raise FacturacionError(f"{f.serie}{f.folio}: pagas {d.imp_pagado} y el saldo es {f.saldo}.")
        docs.append((f.xml, f.parcialidades + 1, f.saldo, d.imp_pagado))
        facturas.append((f, d.imp_pagado))

    _hay_timbres(db, emisor)
    serie, folio = folios.siguiente(db, emisor.id, "P", data.serie)
    log.info("Emitiendo complemento de pago %s%s para %s (%s documentos)", serie, folio, cliente.rfc, len(docs))
    comp = cfdi_svc.construir_pago(emisor, cliente, docs, data.fecha_pago, data.forma_pago,
                                   serie, folio, data.tipo_cambio)
    try:
        comp.sign(signer_de(emisor, permitir_vencido=_modo_pruebas(emisor)))
        uuid, xml = _timbrar(db, emisor, comp)
    except Exception:
        folios.devolver(db, emisor.id, serie, folio)
        raise
    _respaldar(emisor.rfc, uuid, xml)

    rep = Factura(emisor_id=emisor.id, cliente_id=cliente.id, tipo="P", serie=serie, folio=folio,
                  moneda="XXX", subtotal=0, total=sum(p for _, p in facturas),
                  payload=data.model_dump(mode="json"))
    _post_timbrado(rep, xml, uuid)

    def _saldos():
        for f, pagado in facturas:
            f.saldo = f.saldo - pagado
            f.parcialidades += 1
    rep = _guardar(db, rep, uuid, antes=_saldos)
    if data.enviar_email and cliente.emails:
        try:
            enviar(rep, cliente.emails)
        except Exception as e:
            rep.error = f"Timbrado OK, correo falló: {e}"
            db.commit()
    return rep


def emitir_nomina(db: Session, data: NominaIn) -> list[dict]:
    """Timbra los recibos uno por uno: cada recibo es su propia transacción (si uno falla, los demás siguen
    y el folio del que falló se regresa)."""
    emisor = db.get(Emisor, data.emisor_id)
    if not emisor:
        raise FacturacionError("Emisor no existe.")
    out = []
    for r in data.recibos:
        emp = db.get(Empleado, r.empleado_id)
        if not emp or emp.emisor_id != emisor.id:
            out.append({"empleado_id": r.empleado_id, "ok": False, "error": "El empleado no es de este emisor."})
            continue
        serie = folio = uuid = None
        try:
            _hay_timbres(db, emisor)
            serie, folio = folios.siguiente(db, emisor.id, "N", data.serie)
            log.info("Emitiendo recibo de nómina %s%s para %s", serie, folio, emp.nombre)
            with paso("Armar nómina 1.2", empleado=emp.num_empleado):
                comp = nomina_svc.construir(emisor, emp, r, serie, folio, cfdi_svc.ahora_mx(emisor.lugar_expedicion))
            with paso("Sellar con CSD", no_certificado=emisor.no_certificado):
                comp.sign(signer_de(emisor, permitir_vencido=_modo_pruebas(emisor)))
            uuid, xml = _timbrar(db, emisor, comp)
            _respaldar(emisor.rfc, uuid, xml)
            f = Factura(emisor_id=emisor.id, empleado_id=emp.id, tipo="N", serie=serie, folio=folio, moneda="MXN",
                        metodo_pago="PUE", forma_pago="99", subtotal=comp["SubTotal"],
                        descuento=comp.get("Descuento") or Decimal(0), total=comp["Total"],
                        payload={**r.model_dump(mode="json"), "emisor_id": emisor.id})
            _post_timbrado(f, xml, uuid)
            f = _guardar(db, f, uuid)
            out.append({"empleado_id": emp.id, "ok": True, "factura_id": f.id, "uuid": uuid,
                        "folio": f"{serie}{folio}", "neto": str(f.total)})
        except Exception as e:
            db.rollback()
            if uuid is None and folio is not None:  # el PAC no timbró: se regresa el folio (ya estaba confirmado)
                folios.devolver(db, emisor.id, serie, folio)
            log.warning("Recibo de %s no se timbró: %s", emp.nombre, e)
            out.append({"empleado_id": emp.id, "ok": False, "error": str(e)})
            continue
        if data.enviar_email and emp.emails:
            try:
                enviar(f, emp.emails)
            except Exception as e:
                f.error = f"Timbrado OK, correo falló: {e}"
                db.commit()
    return out


_UUID = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")


def _liberar_pago(db: Session, rep: Factura):
    """Un REP cancelado ya no cuenta: cada factura que pagaba recupera el saldo y la parcialidad (sin esto, la factura
    quedaba «con complementos vivos» para siempre y no se podía cancelar). Se llama al pasar a «cancelada», una sola vez."""
    if rep.tipo != "P":
        return
    for d in (rep.payload or {}).get("documentos", []):
        f = db.get(Factura, d.get("factura_id"))
        if f and f.tipo == "I":
            f.saldo = f.saldo + Decimal(str(d.get("imp_pagado") or 0))
            f.parcialidades = max(0, f.parcialidades - 1)


def cancelar(db: Session, f: Factura, motivo: str, sustitucion: str | None) -> Factura:
    if f.estado not in ("timbrada", "cancelacion_pendiente"):
        raise FacturacionError(f"No se puede cancelar una factura en estado '{f.estado}'.")
    if motivo == "01":
        if not sustitucion:
            raise FacturacionError("Motivo 01 requiere el UUID de la factura que sustituye.")
        sustitucion = sustitucion.strip().upper()
        if not _UUID.fullmatch(sustitucion):
            raise FacturacionError("El UUID de la factura que sustituye no tiene formato válido (8-4-4-4-12 letras y números, "
                                   "por ejemplo 5FB2822E-396D-4725-8521-CDC4BDD20CCF).")
        if sustitucion == (f.uuid or "").upper():
            raise FacturacionError("La factura no puede sustituirse a sí misma: pon el UUID de la factura nueva.")
        local = db.query(Factura).filter(Factura.uuid == sustitucion).first()
        if local is not None:  # si es de este sistema se revisa; si la timbró otro sistema, el SAT es quien dice
            if local.emisor_id != f.emisor_id:
                raise FacturacionError("Ese UUID es de otro emisor: la factura que sustituye debe ser del mismo emisor.")
            if local.estado == "cancelada":
                raise FacturacionError("Ese UUID está cancelado: la factura que sustituye debe estar vigente.")
    else:
        sustitucion = None  # sólo el motivo 01 lleva sustitución
    if f.tipo == "I" and f.parcialidades > 0:
        raise FacturacionError("Tiene complementos de pago vivos. Cancela primero los REP.")
    emisor = f.emisor
    acuse = pac_svc.cancelar(emisor.pac, f.xml, motivo, sustitucion,
                             signer_de(emisor, permitir_vencido=_modo_pruebas(emisor)))
    f.acuse_cancelacion = acuse.acuse
    f.motivo_cancelacion = motivo
    # 201 sólo dice "solicitud recibida": el SAT decide si cancela directo o espera aceptación del receptor.
    # Se confirma con la consulta de estatus; si no se puede, queda pendiente (nunca "cancelada" a ciegas).
    try:
        nuevo = pac_svc.estado_sat(pac_svc.estatus(emisor.pac, f.xml))
    except Exception:
        log.exception("No se pudo confirmar el estatus tras cancelar; queda pendiente")
        nuevo = "?"
    f.estado = "cancelada" if nuevo == "cancelada" else "cancelacion_pendiente"
    if f.estado == "cancelada":
        f.saldo = Decimal(0)
        _liberar_pago(db, f)
    db.commit()
    return f


def actualizar_estatus(db: Session, f: Factura) -> dict:
    """Consulta al SAT y sincroniza el estado local (pendiente → cancelada, o de vuelta a timbrada si la rechazaron)."""
    st = pac_svc.estatus(f.emisor.pac, f.xml)
    nuevo = pac_svc.estado_sat(st)
    proceso = str(st.get("EstatusCancelacion") or "").strip()
    # «Vigente» SIN estatus de cancelación no es un rechazo: el SAT tarda en reflejar la solicitud. Sólo se regresa a
    # timbrada cuando el SAT lo dice expresamente (rechazada, plazo vencido…); si no, la solicitud sigue pendiente.
    if f.estado == "cancelacion_pendiente" and (nuevo == "cancelada" or (nuevo == "timbrada" and proceso)):
        f.estado = nuevo
        if nuevo == "cancelada":
            f.saldo = Decimal(0)
            _liberar_pago(db, f)
        elif "rechaz" in proceso.lower():
            f.error = "El receptor rechazó la cancelación."
        else:
            f.error = f"La cancelación no procedió: {proceso}."
        db.commit()
    elif f.estado == "timbrada" and nuevo == "cancelada":  # cancelada desde el portal del SAT u otro sistema
        f.estado, f.saldo = "cancelada", Decimal(0)
        _liberar_pago(db, f)
        db.commit()
    return st


def enviar(f: Factura, para: list[str], mensaje: str | None = None):
    para = mailer.destinatarios(f.emisor, para)  # en pruebas nunca al cliente
    nombre = f"{f.emisor.rfc}_{f.serie or ''}{f.folio or ''}_{f.uuid}"
    adj = [(f"{nombre}.xml", f.xml, "application/xml")]
    try:
        adj.append((f"{nombre}.pdf", pdf_svc.pdf(f.xml, f.emisor), "application/pdf"))
    except RuntimeError:
        adj.append((f"{nombre}.html", pdf_svc.html(f.xml, emisor=f.emisor).encode(), "text/html"))
    tipo = pdf_svc.TIPOS.get(f.tipo, "CFDI")
    cuerpo = mensaje or (
        f"Hola,\n\nTe compartimos tu {tipo.lower()} {f.serie or ''}{f.folio or ''} "
        f"por ${f.total:,.2f} {f.moneda}.\nUUID: {f.uuid}\n\nSaludos,\n{f.emisor.nombre}"
    )
    with paso(f"Enviar correo a {', '.join(para)}", adjuntos=[a[0] for a in adj]):
        mailer.enviar(para, f"{tipo} {f.serie or ''}{f.folio or ''} - {f.emisor.nombre}", cuerpo, adj,
                      nombre=f.emisor.nombre, responder_a=f.emisor.email)


def recuperar(db: Session) -> list[str]:
    """Importa a la BD los XML del respaldo que no estén registrados (p.ej. si la BD falló tras timbrar)."""
    nuevos = []
    for path in respaldo.todos():
        xml = open(path, "rb").read()
        try:
            c = CFDI.from_string(xml)
            uuid = c["Complemento"]["TimbreFiscalDigital"]["UUID"].upper()
        except Exception:
            continue
        if db.query(Factura).filter_by(uuid=uuid).first():
            continue
        emisor = db.query(Emisor).filter_by(rfc=c["Emisor"]["Rfc"]).first()
        if not emisor:
            continue
        rec = c["Receptor"]
        cli = db.query(Cliente).filter_by(emisor_id=emisor.id, rfc=rec["Rfc"]).first()
        def v(x):
            return getattr(x, "code", getattr(x, "value", x))
        tipo = v(c["TipoDeComprobante"])
        f = Factura(emisor_id=emisor.id, cliente_id=cli.id if cli else None, tipo=tipo,
                    serie=c.get("Serie"), folio=c.get("Folio"), moneda=v(c["Moneda"]),
                    metodo_pago=v(c.get("MetodoPago")), forma_pago=v(c.get("FormaPago")),
                    subtotal=c["SubTotal"], total=c["Total"],
                    saldo=c["Total"] if v(c.get("MetodoPago")) == "PPD" and tipo == "I" else 0,
                    payload={"recuperada": True})
        _post_timbrado(f, xml, uuid)
        db.add(f)
        nuevos.append(uuid)
    db.commit()
    return nuevos
