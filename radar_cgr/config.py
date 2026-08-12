from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
DOCS_DIR = ROOT / "docs"
CONFIG_DIR = ROOT / "config"

DEFAULT_HEADERS = {
    "User-Agent": "Radar-CGR/0.1 (+https://github.com/smoralesm07-source/Radar-CGR; OSINT publico)",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.6",
}

@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    collector: str
    enabled: bool = True
    max_items: int = 40
    priority: int = 5
    notes: str = ""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_sources() -> list[Source]:
    raw = load_json(CONFIG_DIR / "sources.json")
    return [Source(**item) for item in raw["sources"] if item.get("enabled", True)]


def load_seed_audits() -> list[str]:
    path = CONFIG_DIR / "seed_audits.json"
    if not path.exists():
        return []
    return [x["url"] for x in load_json(path).get("audits", []) if x.get("enabled", True)]
