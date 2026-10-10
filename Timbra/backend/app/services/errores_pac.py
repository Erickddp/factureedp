"""Errores comunes de PAC/SAT: qué significan, qué hacer y cuáles se corrigen solos.

Acciones automáticas (sólo las que NUNCA pueden duplicar un timbre):
- "reintentar": falla de red/PAC caído → se reenvía el MISMO XML sellado (mismo sello = mismo CFDI);
  si el PAC ya lo había timbrado contesta "previamente timbrado" y se recupera ese UUID.
- "recuperar":  "previamente timbrado" → se pide al PAC el XML ya timbrado (Finkok `stamped`).
- "refechar":   fecha fuera de rango (reloj de la PC o el XML tardó) → se re-arma con la hora actual y se re-sella.
Todo lo demás se explica en lenguaje de contador con la solución y el campo a corregir.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostico:
    clave: str
    titulo: str
    solucion: str
    accion: str | None = None  # reintentar | recuperar | refechar
    campo: str | None = None   # a dónde llevar al usuario en Facturar

    def texto(self, original: str) -> str:
        return f"{self.titulo}. Qué hacer: {self.solucion} [Detalle del PAC: {original[:300]}]"


# (patrón, diagnóstico) — el primero que coincide gana. Patrones en minúsculas sobre el texto del error.
REGLAS: list[tuple[str, Diagnostico]] = [
    (r"previamente timbrado|307\b|cfdi3307|already stamped|ya fue timbrado",
     Diagnostico("previo", "El PAC ya había timbrado este mismo CFDI",
                 "Timbra lo recupera solo; si no, usa Facturas → Recuperar.", "recuperar")),
    (r"timed? ?out|timeout|connection(error| reset| aborted| refused)|max retries|temporarily unavailable|"
     r"remote ?disconnected|\b50[234]\b|bad gateway|service unavailable|name resolution|getaddrinfo|ssl",
     Diagnostico("red", "No hubo respuesta del PAC (internet o PAC caído)",
                 "Timbra reintentó con el mismo XML (no duplica). Si sigue, revisa tu internet y vuelve a intentar en unos minutos.",
                 "reintentar")),
    (r"fecha.{0,40}(fuera de rango|no est[aá] dentro|mayor|posterior|72 horas)|cfdi40101|\b401\b.{0,30}fecha",
     Diagnostico("fecha", "La fecha del CFDI quedó fuera del rango que acepta el SAT",
                 "Timbra lo re-armó con la hora actual. Si se repite, ajusta el reloj y la zona horaria de Windows a la de tu ciudad.",
                 "refechar", "fecha")),
    (r"\b702\b|no se encontr[oó] el rfc|rfc.{0,30}no (est[aá]|se encuentra) (registrado|dado de alta)|emisor no registrado|"
     r"no tiene permiso para timbrar",
     Diagnostico("rfc_pac", "Ese RFC no está dado de alta en tu cuenta del PAC",
                 "En el panel del PAC (Finkok: Clientes → Agregar, tipo OnDemand) agrega el RFC emisor y vuelve a timbrar.")),
    (r"lco|lista de contribuyentes obligados|no se encuentra en la l\.?c\.?o|cfdi40102|certificado.{0,40}(revocado|no vigente|caduc)|\b305\b",
     Diagnostico("csd_sat", "El SAT no reconoce el CSD como vigente",
                 "Un CSD nuevo tarda de 24 a 72 h en activarse. Si ya pasó ese tiempo, revisa en el SAT que no esté revocado o "
                 "renueva el CSD y súbelo en Emisores y CSD.", None, "emisor.csd")),
    (r"\b302\b|sello.{0,30}(inv[aá]lido|no corresponde)|cfdi40103",
     Diagnostico("sello", "El sello no corresponde al certificado",
                 "Vuelve a subir el CSD (.cer y .key del MISMO trámite) en Emisores y CSD.", None, "emisor.csd")),
    (r"cfdi40145|cfdi40144|nombre.{0,40}receptor.{0,40}(no coincide|no corresponde|no se encuentra)",
     Diagnostico("nombre_receptor", "El nombre del receptor no coincide con el del SAT",
                 "Captúralo EXACTO como en su constancia de situación fiscal, sin S.A. de C.V. ni acentos de más.", None, "receptor.nombre")),
    (r"cfdi40147|cfdi40149|domiciliofiscalreceptor|c[oó]digo postal.{0,40}receptor",
     Diagnostico("cp_receptor", "El código postal del receptor no coincide con el del SAT",
                 "Pide la constancia de situación fiscal actualizada y corrige el CP fiscal del cliente.", None, "receptor.codigo_postal")),
    (r"cfdi40157|cfdi40158|r[eé]gimen.{0,40}receptor|regimenfiscalreceptor",
     Diagnostico("regimen_receptor", "El régimen del receptor no coincide con el registrado en el SAT",
                 "Revisa su constancia: el régimen debe ser uno que tenga activo. Corrígelo en el cliente.", None, "receptor.regimen_fiscal")),
    (r"cfdi40161|cfdi40162|usocfdi|uso.{0,20}cfdi.{0,40}(no corresponde|no aplica)",
     Diagnostico("uso", "El uso del CFDI no corresponde al régimen del receptor",
                 "Elige un uso permitido para su régimen (G03 para empresas, D01-D10 sólo personas físicas).", None, "receptor.uso_cfdi")),
    (r"rfc.{0,30}receptor.{0,40}(no existe|no se encuentra|no est[aá] en la lista|inv[aá]lido)|cfdi40143",
     Diagnostico("rfc_receptor", "El RFC del receptor no existe en el padrón del SAT",
                 "Verifica el RFC con la constancia (letras, homoclave). Si es extranjero usa XEXX010101000.", None, "receptor.rfc")),
    (r"tasaocuota|cfdi40(2|3)\d\d.{0,40}tasa",
     Diagnostico("tasa", "Una tasa de impuesto no es válida para el SAT",
                 "Usa las combinaciones del menú Impuestos (16%, 8% frontera, 0%, exento y retenciones 2/3).", None, "impuestos")),
    (r"saldo|cr[eé]ditos? insuficiente|sin timbres|no cuenta con timbres|paquete agotado|\b708\b",
     Diagnostico("saldo", "Tu cuenta del PAC no tiene timbres disponibles",
                 "Compra timbres en tu PAC y regístralos en Timbres para que Timbra te avise antes.")),
    (r"usuario|contrase[ñn]a|password|autentica|unauthorized|\b401\b|token",
     Diagnostico("credenciales", "El PAC rechazó usuario o contraseña",
                 "Revisa las credenciales en PAC y usuarios (las de pruebas y producción son distintas).")),
    (r"llave privada|private key|bad decrypt|mac check failed",
     Diagnostico("llave", "La contraseña de la llave privada (.key) no es correcta",
                 "Vuelve a subir el CSD con la contraseña correcta.", None, "emisor.csd")),
    (r"database is locked|disk i/o|readonly database|no space left",
     Diagnostico("bd", "La base de datos estaba ocupada o sin espacio",
                 "Espera unos segundos y reintenta. Si dice sin espacio, libera disco.", "reintentar")),
    (r"smtp|authentication failed.{0,40}mail|535|username and password not accepted",
     Diagnostico("correo", "No se pudo mandar el correo",
                 "Gmail pide una 'contraseña de aplicación' (no tu contraseña normal) en SMTP_PASSWORD del .env.")),
]


def diagnosticar(texto: str) -> Diagnostico | None:
    t = (texto or "").lower()
    for patron, d in REGLAS:
        if re.search(patron, t):
            return d
    return None


def catalogo() -> list[dict]:
    """Para la ayuda dentro de la app (consola → Errores comunes)."""
    return [{"clave": d.clave, "titulo": d.titulo, "solucion": d.solucion, "automatico": bool(d.accion)} for _, d in REGLAS]
