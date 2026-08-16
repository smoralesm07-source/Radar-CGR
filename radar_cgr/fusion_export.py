from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

RADAR_ID = "RADAR_CGR"
VERSION = "1.0"

from .territory import territory_id as _resolve_territory


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _iso(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        return text
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat() + "T00:00:00+00:00"
        except ValueError:
            pass
    return None


def _norm(value: object) -> str:
    text = str(value or "").upper().strip()
    text = text.translate(str.maketrans("ÁÉÍÓÚÜÑ", "AEIOUUN"))
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _territory(region: object) -> str | None:
    """Resuelve la glosa regional contra el índice canónico del Context Hub."""
    return _resolve_territory(region, "REGION")


def _direct_evidence_id(seed: str) -> str:
    return "EVD-CGR-DOC-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def build(root: Path) -> dict[str, Any]:
    silver = root / "data" / "silver"
    docs = root / "docs" / "data"
    native_evidence = _rows(silver / "evidence.jsonl")
    native_events = _rows(silver / "events.jsonl")
    hub = _rows(silver / "entity_hub_v1.jsonl")
    native_relationships = _rows(silver / "relationships.jsonl")
    documents = _rows(silver / "documents.jsonl")

    if not native_events and not native_evidence:
        raise RuntimeError("CGR silver outputs empty; refusing false-zero Fusion export")

    evidence: dict[str, dict[str, Any]] = {}
    evidence_by_document: dict[str, list[str]] = {}
    for row in native_evidence:
        eid = str(row.get("evidence_id") or "").strip()
        retrieved = _iso(row.get("retrieved_at"))
        if not eid or not retrieved:
            continue
        content_hash = str(row.get("content_hash") or "").strip() or None
        evidence[eid] = {
            "evidence_id": eid,
            "producer_id": RADAR_ID,
            "source_id": "CGR_AUDIT_EVIDENCE",
            "ultimate_source_id": "CGR",
            "source_url": row.get("source_url") or None,
            "source_tier": "OFFICIAL",
            "capture_method": "RADAR_CGR_FINDING_EXTRACTION",
            "source_run_id": None,
            "content_sha256": content_hash,
            "quality_status": "VALID",
            "source_published_at": None,
            "retrieved_at": retrieved,
            "ingested_at": retrieved,
            "excerpt": row.get("source_text") or None,
            "schema_version": VERSION,
        }
        document_id = str(row.get("document_id") or "")
        if document_id:
            evidence_by_document.setdefault(document_id, []).append(eid)

    for document in documents:
        document_id = str(document.get("document_id") or "").strip()
        retrieved = _iso(document.get("retrieved_at"))
        if not document_id or not retrieved:
            continue
        if document_id in evidence_by_document:
            continue
        eid = _direct_evidence_id(document_id + "|" + str(document.get("source_url") or ""))
        hash_value = str(document.get("content_hash") or "").strip() or None
        evidence[eid] = {
            "evidence_id": eid,
            "producer_id": RADAR_ID,
            "source_id": str(document.get("source_module") or "CGR_DOCUMENT"),
            "ultimate_source_id": "CGR",
            "source_url": document.get("source_url") or None,
            "source_tier": "OFFICIAL",
            "capture_method": "RADAR_CGR_DOCUMENT",
            "source_run_id": None,
            "content_sha256": hash_value,
            "quality_status": "VALID",
            "source_published_at": _iso(document.get("document_date")),
            "retrieved_at": retrieved,
            "ingested_at": retrieved,
            "excerpt": document.get("raw_text_excerpt") or None,
            "schema_version": VERSION,
        }
        evidence_by_document.setdefault(document_id, []).append(eid)

    local_to_global: dict[str, str] = {}
    canonical_entities: dict[str, dict[str, Any]] = {}
    unresolved_entities = 0
    for row in hub:
        local_id = str(row.get("source_entity_id") or "").strip()
        entity_id = str(row.get("entity_id") or "").strip()
        if not entity_id.startswith("ENT-RUT-"):
            unresolved_entities += 1
            continue
        if local_id:
            local_to_global[local_id] = entity_id
        ev_ids = list(evidence_by_document.get(str(row.get("source_document_id") or ""), []))
        if not ev_ids:
            continue
        role = str(row.get("entity_role") or "SOURCE_ENTITY")
        source_type = str(row.get("entity_type") or "").upper()
        entity_type = "PERSON" if "PERSON" in source_type else ("PUBLIC_BODY" if role == "PUBLIC_BODY" else "LEGAL_ENTITY")
        current = canonical_entities.setdefault(entity_id, {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "canonical_name": row.get("canonical_name") or None,
            "rut_normalized": row.get("rut") or None,
            "aliases": [],
            "roles": [],
            "producer_ids": [RADAR_ID],
            "evidence_ids": [],
            "identity_method": "RUT_EXACT",
            "identity_confidence": 1.0,
            "attributes": {},
        })
        if role not in current["roles"]:
            current["roles"].append(role)
        current["evidence_ids"] = sorted(set(current["evidence_ids"]) | set(ev_ids))

    canonical_events: list[dict[str, Any]] = []
    unresolved_event_evidence = 0
    territory_resolved = 0
    for row in native_events:
        event_id = str(row.get("event_id") or "").strip()
        if not event_id:
            continue
        document_id = str(row.get("document_id") or "")
        ev_ids = list(evidence_by_document.get(document_id, []))
        if not ev_ids:
            retrieved = _iso(row.get("retrieved_at"))
            if not retrieved:
                unresolved_event_evidence += 1
                continue
            eid = _direct_evidence_id(event_id + "|" + str(row.get("source_url") or ""))
            evidence[eid] = {
                "evidence_id": eid,
                "producer_id": RADAR_ID,
                "source_id": str(row.get("source_module") or "CGR_EVENT"),
                "ultimate_source_id": "CGR",
                "source_url": row.get("source_url") or None,
                "source_tier": "OFFICIAL",
                "capture_method": "RADAR_CGR_EVENT",
                "source_run_id": None,
                "content_sha256": None,
                "quality_status": "VALID",
                "source_published_at": _iso(row.get("event_date")),
                "retrieved_at": retrieved,
                "ingested_at": retrieved,
                "schema_version": VERSION,
            }
            ev_ids = [eid]
        territory_id = _territory(row.get("region"))
        if territory_id:
            territory_resolved += 1
        canonical_events.append({
            "event_id": event_id,
            "event_type": str(row.get("event_type") or "CGR_OBSERVATION"),
            "producer_id": RADAR_ID,
            "entity_ids": [],
            "territory_ids": [territory_id] if territory_id else [],
            "sector_ids": [],
            "evidence_ids": sorted(set(ev_ids)),
            "temporal": {
                "valid_from": _iso(row.get("event_date")),
                "valid_to": None,
                "source_published_at": _iso(row.get("event_date")),
                "observed_at": _iso(row.get("retrieved_at")),
                "retrieved_at": _iso(row.get("retrieved_at")),
                "ingested_at": _iso(row.get("retrieved_at")),
                "last_seen_at": None,
                "freshness_state": "CURRENT",
            },
            "attributes": {
                "document_id": document_id or None,
                "title": row.get("title") or None,
                "status": row.get("status") or None,
                "entity_name_unresolved": row.get("entity_name") or None,
                "region_name": row.get("region") or None,
            },
        })

    event_by_id = {row["event_id"]: row for row in canonical_events}
    canonical_relationships: list[dict[str, Any]] = []
    relationship_candidates = 0
    for row in native_relationships:
        source = local_to_global.get(str(row.get("source_entity_id") or ""))
        target = local_to_global.get(str(row.get("target_entity_id") or ""))
        eid = str(row.get("evidence_id") or "")
        if not source or not target or eid not in evidence:
            relationship_candidates += 1
            continue
        related_event = event_by_id.get(str(row.get("event_id") or ""), {})
        canonical_relationships.append({
            "relationship_id": str(row.get("relationship_id") or ""),
            "source_entity_id": source,
            "target_entity_id": target,
            "relationship_type": str(row.get("relationship_type") or "CGR_RELATION"),
            "assertion_type": "DERIVED",
            "method": "RADAR_CGR_RELATIONSHIP_EXTRACTION",
            "confidence": float(row.get("confidence") or 0.0),
            "evidence_ids": [eid],
            "temporal": related_event.get("temporal", {}),
            "attributes": {
                "source_relationship_id": row.get("relationship_id") or None,
                "finding_id": row.get("finding_id") or None,
                "event_id": row.get("event_id") or None,
                "document_id": row.get("document_id") or None,
            },
        })

    evidence_count = _write(silver / "evidence_fusion_v1.jsonl", evidence.values())
    entity_count = _write(silver / "entities_fusion_v1.jsonl", canonical_entities.values())
    event_count = _write(silver / "events_fusion_v1.jsonl", canonical_events)
    relationship_count = _write(silver / "relationships_fusion_v1.jsonl", canonical_relationships)
    status = {
        "interop_version": VERSION,
        "radar_id": RADAR_ID,
        "status": "FUSION_EXPORT_READY_TERRITORY_PARTIAL",
        "evidence": evidence_count,
        "entities": entity_count,
        "events": event_count,
        "relationships": relationship_count,
        "unresolved_entity_candidates": unresolved_entities,
        "unpromoted_relationship_candidates": relationship_candidates,
        "events_with_canonical_region": territory_resolved,
        "events_skipped_without_evidence": unresolved_event_evidence,
        "source_failure_is_zero": False,
    }
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "fusion_interop_status_v1.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status
