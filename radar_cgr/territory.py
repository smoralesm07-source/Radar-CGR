"""Resolución territorial contra el índice canónico del Context Hub.

Este módulo reemplaza la tabla de alias privada que vivía en `fusion_export.py`.
El radar ya no mantiene su propio criterio de equivalencia: consume
`config/territory_resolution_index_v1.json`, publicado por Context Hub desde
CUT/Subdere, y aplica la misma receta de clave que el resto del ecosistema.

Reglas heredadas del hub, que este adaptador no puede relajar:

- Sólo igualdad exacta sobre la clave normalizada. Nada de fuzzy matching.
- La resolución es consciente del nivel: siete topónimos son a la vez nombre de
  región y de comuna, y «Los Lagos» es además una comuna de otra región. CGR
  resuelve a nivel REGION porque su glosa de origen es regional.
- Lo que no cruza queda `None` con un estado explícito, nunca se aproxima.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

INDEX_PATH = Path(__file__).resolve().parents[1] / "config" / "territory_resolution_index_v1.json"

_PREFIXES = (
    "REGION DE LA", "REGION DEL", "REGION DE", "REGION",
    "PROVINCIA DE LA", "PROVINCIA DEL", "PROVINCIA DE", "PROVINCIA",
    "COMUNA DE LA", "COMUNA DEL", "COMUNA DE", "COMUNA",
    "DE LA", "DEL", "DE",
)


def match_key(value: object) -> str:
    """Misma receta de clave que `context_hub.territory_resolve.match_key`."""
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text).strip()
    for prefix in _PREFIXES:
        if text == prefix:
            return ""
        if text.startswith(prefix + " "):
            text = text[len(prefix) + 1:].strip()
            break
    return text.replace(" ", "")


@lru_cache(maxsize=1)
def _index() -> dict:
    if not INDEX_PATH.exists():
        return {"index": {}, "max_key_len": 45}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def resolve(text: object, level: str = "REGION") -> tuple[str | None, str]:
    """Devuelve `(territory_id, mapping_status)`.

    Estados posibles: `VALIDATED_EXACT`, `CODE_EXACT`, `UNRESOLVED_NAME_ONLY`,
    `NOT_A_PLACE_NAME`, `UNKNOWN`.
    """
    raw = str(text or "").strip()
    if not raw:
        return None, "UNKNOWN"

    data = _index()
    digits = re.fullmatch(r"(?:CL-(?:REG|COM)-)?(\d{2}|\d{5})", raw.upper())
    if digits:
        code = digits.group(1)
        prefix = "REG" if len(code) == 2 else "COM"
        return f"CL-{prefix}-{code}", "CODE_EXACT"

    key = match_key(raw)
    if not key:
        return None, "UNKNOWN"
    if len(key) > data.get("max_key_len", 45):
        # Glosa demasiado larga para ser un topónimo: texto arrastrado por el
        # extractor. Se rechaza sin intentar cruzarla contra nada.
        return None, "NOT_A_PLACE_NAME"

    found = data.get("index", {}).get(level, {}).get(key)
    return (found, "VALIDATED_EXACT") if found else (None, "UNRESOLVED_NAME_ONLY")


def territory_id(text: object, level: str = "REGION") -> str | None:
    return resolve(text, level)[0]
