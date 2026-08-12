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
    occurrence_date_from: str = ""
    occurrence_date_to: str = ""
    occurrence_date_anchor: str = ""
    occurrence_date_precision: str = "UNKNOWN"
    occurrence_date_basis: str = ""
    occurrence_date_confidence: float = 0.0

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
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Organization:
    organization_id: str
    name: str
    normalized_name: str
    organization_type: str
    region: str = ""
    commune: str = ""
    rut: str = ""
    source_document_id: str = ""
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Provider:
    provider_id: str
    name: str
    normalized_name: str
    provider_type: str = "PRIVATE_LEGAL_ENTITY"
    rut: str = ""
    region: str = ""
    source_document_id: str = ""
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Person:
    person_id: str
    name: str
    normalized_name: str
    role: str = ""
    organization_id: str = ""
    rut: str = ""
    source_document_id: str = ""
    confidence: float = 0.5

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
    finding_id: str = ""
    evidence_id: str = ""
    source_url: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Irregularity:
    irregularity_id: str
    finding_id: str
    document_id: str
    code: str
    label: str
    family: str
    cgr_weight: int
    evidence_id: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PenalHypothesis:
    hypothesis_id: str
    finding_id: str
    document_id: str
    code: str
    label: str
    score: int
    relevance: str
    evidence_level: str
    basis: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    evidence_id: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WatchItem:
    watch_id: str
    source_id: str
    watch_type: str
    title: str
    source_url: str
    stage: str = "WATCH"
    first_seen: str = field(default_factory=utcnow_iso)
    last_seen: str = field(default_factory=utcnow_iso)
    matched_document_id: str = ""
    match_confidence: float = 0.0
    status: str = "OPEN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EnforcementEvent:
    enforcement_event_id: str
    finding_id: str
    document_id: str
    organization_id: str
    enforcement_type: str
    action_date: str
    stage: str
    source_url: str
    occurrence_date_from: str = ""
    occurrence_date_to: str = ""
    amount_clp: int | None = None
    tribunal_link_status: str = "NOT_APPLICABLE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FAUMatch:
    fau_match_id: str
    finding_id: str
    document_id: str
    pattern_code: str
    pattern_label: str
    score: int
    match_basis: list[str] = field(default_factory=list)
    source_url: str = ""
    origin: str = "CGR_FAU_PUBLIC_THEME"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
