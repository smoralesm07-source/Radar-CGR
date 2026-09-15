from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_name(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^A-Za-z0-9 ]+", " ", value.upper())
    value = re.sub(r"\s+", " ", value).strip()
    replacements = {" S A ": " SA ", " S P A ": " SPA ", " LTDA ": " LIMITADA "}
    padded = f" {value} "
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return padded.strip()


def parse_clp_amounts(text: str) -> list[int]:
    values: list[int] = []
    for raw in re.findall(r"\$\s*([0-9][0-9\.\,]{2,})", text or ""):
        digits = re.sub(r"\D", "", raw)
        if digits:
            try:
                values.append(int(digits))
            except ValueError:
                pass
    return values


def official_cgr_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return host.endswith("contraloria.cl") or host.endswith("infoprobidad.cl")
    except Exception:
        return False


def absolutize(base: str, href: str) -> str:
    return urljoin(base, href)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


# El RUT aparece en los informes de auditoría como prosa del fiscalizador, no
# como campo estructurado: «con el proveedor X, RUT 76.787.460-K». Se exige la
# etiqueta literal porque en castellano las letras r-u-t abundan dentro de
# palabras corrientes —«Frutería», «ruta 11-CH», «Urrutia»— y sin ella el
# reconocimiento devuelve apellidos y caminos en vez de contribuyentes.
RUT_LABELED_RE = re.compile(
    r"R\.?\s?U\.?\s?T\.?\s*(?:N[°ºo]s?\.?)?\s*:?\s*(\d{1,2}[\.\s]?\d{3}[\.\s]?\d{3})\s*[-‐–—]\s*([0-9kK])",
    re.IGNORECASE,
)


def rut_check_digit(body: str) -> str:
    """Dígito verificador de módulo 11 sobre el cuerpo del RUT, sin puntos."""
    total = 0
    factor = 2
    for char in reversed(body):
        total += int(char) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    return {11: "0", 10: "K"}.get(remainder, str(remainder))


def normalize_rut(raw: str) -> str:
    """Devuelve `cuerpo-DV` sólo si el dígito verificador cuadra; si no, cadena vacía.

    Un RUT que no valida no es un RUT con una errata: es cualquier otra cosa con
    forma de RUT. La Contraloría además enmascara los de personas naturales
    —«RUT Nos 6.429.XXX-X»— y esa máscara debe morir aquí, no aguas abajo.
    """
    if not raw:
        return ""
    cleaned = re.sub(r"[\.\s]", "", str(raw)).upper()
    match = re.fullmatch(r"(\d{7,8})-([0-9K])", cleaned)
    if not match:
        return ""
    body, verifier = match.groups()
    return f"{body}-{verifier}" if rut_check_digit(body) == verifier else ""


def rut_near(text: str, start: int, end: int, window: int = 60) -> str:
    """RUT etiquetado que sigue inmediatamente a un nombre entre `start` y `end`.

    La ventana es corta y mira sólo hacia adelante a propósito: un RUT que está
    tres líneas más abajo pertenece a otra entidad, y atribuirlo aquí sería
    exactamente el error que el enlace CANDIDATE existe para evitar.
    """
    if not text:
        return ""
    tail = text[end:min(len(text), end + window)]
    match = RUT_LABELED_RE.search(tail)
    if not match:
        return ""
    # Entre el nombre y la etiqueta sólo puede haber puntuación. Cualquier
    # palabra intermedia significa que el RUT es de otra cosa.
    if not re.fullmatch(r"[\s,;:.()\-–—]*", tail[: match.start()]):
        return ""
    return normalize_rut(f"{match.group(1)}-{match.group(2)}")
