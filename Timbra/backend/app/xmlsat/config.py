# -*- coding: utf-8 -*-
"""Lo mínimo que flujo.py necesita saber de un RFC y de cómo descargar.
En escritorio esto vivía en config.json; en web lo arma app/sat.py desde la base."""
from dataclasses import dataclass


@dataclass
class Opciones:
    carpeta_salida: str = "descargas_cfdi"
    max_solicitudes_dia: int = 200
    poll_intervalo_seg: int = 30
    poll_max_intentos: int = 40
    reintentos: int = 4
    backoff_base_seg: float = 3.0
    dividir_por_mes: bool = True


@dataclass
class Perfil:
    """Un RFC y dónde guarda el historial de sus solicitudes al SAT."""
    rfc: str = ""
    nombre: str = ""
    carpeta_estado: str = "."
    id: str = ""

    def __post_init__(self):
        self.rfc = (self.rfc or "").strip().upper()
        self.nombre = self.nombre or self.rfc

    def archivo_estado(self, op: Opciones) -> str:
        return f"{self.carpeta_estado}/estado_solicitudes_{self.id}.json"

    def archivo_contador(self, op: Opciones) -> str:
        return f"{self.carpeta_estado}/contador_solicitudes_{self.id}.json"


Config = None  # flujo.py lo importa sólo por compatibilidad; en web no existe config.json
