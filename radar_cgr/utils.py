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
