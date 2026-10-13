# -*- coding: utf-8 -*-
"""Diseño del PDF: qué secciones lleva, título, logo, color y nombre de archivo.
Es la parte de perfiles.py de escritorio que usa pdf.py."""
import copy
from typing import Dict, Optional

# Secciones del PDF que se activan/desactivan por perfil: clave -> (etiqueta, default)
SECCIONES = {
    "letra_clase": ("Letra grande de clase (I/G/N/P/E/T)", True),
    "datos_fiscales": ("Datos fiscales (régimen, domicilio, lugar, exportación…)", True),
    "conceptos_detalle": ("Conceptos con claves, unidad, objeto e impuestos", True),
    "complementos": ("Complementos de concepto y otros complementos", True),
    "complemento_pago": ("Complemento de pago (REP)", True),
    "relacionados": ("CFDI relacionados", True),
    "inteligencia": ("Seguimiento de pago (calculado)", True),
    "timbre": ("Timbre fiscal completo", True),
    "sellos": ("Sellos y cadena original del timbre", False),
    "qr": ("Código QR de verificación del SAT", True),
}

# Cómo organizar los PDF en subcarpetas: clave -> etiqueta
SUBCARPETAS = {"": "Todo en la misma carpeta", "mes": "Por mes (202609/…)",
               "mes/clase": "Por mes y clase (202609/G/…)"}

DISENO_DEFAULT = {
    "titulo": "",
    "subtitulo": "Representación impresa de CFDI",
    "logo": "",
    "color_primario": "#1F4E78",
    "pie": "Generado con Timbra",
    "nombre_archivo": "{fecha}_{clase}_{rfc_contraparte}_{serie}{folio}_{uuid8}",
    "subcarpetas": "",
    "secciones": {k: v[1] for k, v in SECCIONES.items()},
}

# claves viejas de pdf_config.json -> sección nueva
_LEGADO = {"mostrar_letra_clase": "letra_clase", "mostrar_inteligencia": "inteligencia",
           "mostrar_sello_sat": "sellos"}

def completar_diseno(d: Optional[Dict]) -> Dict:
    """Diseño completo: lo que falte se llena con los defaults (un JSON a medias
    no truena) y las claves viejas mostrar_* se traducen a secciones."""
    final = copy.deepcopy(DISENO_DEFAULT)
    d = dict(d or {})
    secciones = dict(d.pop("secciones", None) or {})
    for viejo, nuevo in _LEGADO.items():
        if viejo in d:
            secciones.setdefault(nuevo, bool(d.pop(viejo)))
    for k, v in d.items():
        if k in final and v is not None:
            final[k] = v
    for k, v in secciones.items():
        if k in final["secciones"]:
            final["secciones"][k] = bool(v)
    if final["subcarpetas"] not in SUBCARPETAS:
        final["subcarpetas"] = ""
    return final
