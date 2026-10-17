"""Términos de uso y aviso de privacidad: qué versión está vigente.

Los textos viven en las pantallas (frontend/src/app/legal/*). Cuando cambien en algo de fondo, sube TERMINOS_VERSION:
cada cuenta tendrá que aceptarlos otra vez al entrar (el administrador no, él es el proveedor).
"""
TERMINOS_VERSION = "2026-10-16"


def pendiente(u) -> bool:
    return not u.admin and u.terminos_version != TERMINOS_VERSION
