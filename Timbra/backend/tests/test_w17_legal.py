"""La versión legal del frontend y la del backend tienen que ser la misma, y el historial tiene que conocerla."""
import re
from pathlib import Path

from app.legal import TERMINOS_VERSION

RAIZ = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_la_version_legal_es_la_misma_en_front_y_back_y_esta_en_el_historial():
    ts = (RAIZ / "lib" / "legal.ts").read_text(encoding="utf-8")
    version = re.search(r'export const VERSION = "([^"]+)"', ts).group(1)
    assert version == TERMINOS_VERSION, f"lib/legal.ts dice {version} y backend/app/legal.py dice {TERMINOS_VERSION}: súbelas juntas"
    assert f'version: "{version}"' in ts, "agrega la versión vigente al HISTORIAL de lib/legal.ts"


def test_el_domicilio_completo_no_sale_en_el_aviso_ni_en_los_terminos():
    ts = (RAIZ / "lib" / "legal.ts").read_text(encoding="utf-8")
    calle = re.search(r'domicilioCompleto: "([^,]+),', ts).group(1)
    for pagina in ("privacidad", "terminos"):
        assert calle not in (RAIZ / "app" / "legal" / pagina / "page.tsx").read_text(encoding="utf-8")
    assert "domicilioCompleto" not in (RAIZ / "app" / "legal" / "page.tsx").read_text(encoding="utf-8")
