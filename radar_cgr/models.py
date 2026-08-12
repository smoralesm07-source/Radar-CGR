from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: Any) -> str:
    normalized = "|".join(str(p or "").strip().upper() for p in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"

@dataclass
class Document:
    document_id: str
    source_system: str
    source_module: str
    source_url: str
    title: str = ""
    document_number: str = ""
    document_date: str = ""
    document_type: str = ""
    region: str = ""
    unit_cgr: str = ""
    level: str = ""
    pdf_url: str = ""
    content_hash: str = ""
    retrieved_at: str = field(default_factory=utcnow_iso)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Event:
    event_id: str
    document_id: str
    event_type: str
    event_date: str
    title: str
    entity_name: str = ""
    region: str = ""
    source_url: str = ""
    source_module: str = ""
    status: str = "PUBLISHED"
    retrieved_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Finding:
    finding_id: str
    event_id: str
    document_id: str
    finding_order: int
    description: str
    finding_type: str
    risk_family: str
    severity: str
    aml_relevance: str
    aml_score: int
    amount_clp: int | None = None
    enforcement: list[str] = field(default_factory=list)
    source_url: str = ""
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Evidence:
    evidence_id: str
    document_id: str
    finding_id: str
    source_url: str
    source_section: str
    source_text: str
    page: int | None = None
    paragraph: int | None = None
    content_hash: str = ""
    retrieved_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Entity:
    entity_id: str
    entity_type: str
    name: str
    normalized_name: str
    rut: str = ""
    region: str = ""
    source_document_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class Relationship:
    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    document_id: str
    event_id: str = ""
    evidence_id: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
