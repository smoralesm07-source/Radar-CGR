from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from .config import DOCS_DIR
from .storage import read_jsonl, table_path


def _iso_document_date(value: str) -> str:
    try:
        return datetime.strptime(value or "", "%d-%m-%Y").date().isoformat()
    except Exception:
        return ""


def _min(values: list[str]) -> str:
    vals = [x for x in values if x]
    return min(vals) if vals else ""


def _max(values: list[str]) -> str:
    vals = [x for x in values if x]
    return max(vals) if vals else ""


def summarize_coverage() -> dict:
    documents = read_jsonl(table_path("documents"))
    findings = read_jsonl(table_path("findings"))
    registry = read_jsonl(table_path("audit_registry"))
    tribunal = read_jsonl(table_path("tribunal_cases"))
    runs = read_jsonl(table_path("source_runs"))

    pub_dates = [_iso_document_date(x.get("document_date", "")) for x in documents]
    occurrence_from = [x.get("occurrence_date_from", "") for x in findings]
    occurrence_to = [x.get("occurrence_date_to", "") for x in findings]
    tribunal_dates = [x.get("state_date", "") for x in tribunal]

    document_years = Counter(x[:4] for x in pub_dates if x)
    occurrence_years = Counter((x.get("occurrence_date_anchor", "") or "")[:4] for x in findings if x.get("occurrence_date_anchor"))
    status_counts = Counter(x.get("status", "UNKNOWN") for x in registry)
    channel_counts = Counter(x.get("discovery_channel", "UNKNOWN") for x in registry)

    benchmark_start, benchmark_end, benchmark_total = "2024-04-01", "2025-03-31", 792
    loaded_in_benchmark = sum(benchmark_start <= d <= benchmark_end for d in pub_dates if d)

    source_latest = {}
    for row in sorted(runs, key=lambda x: x.get("finished_at", "")):
        sid = row.get("source_id", "")
        if sid:
            source_latest[sid] = {"status": row.get("status", ""), "finished_at": row.get("finished_at", ""), "error": row.get("error", "")}

    pending = sum(x.get("status") != "FETCHED" and int(x.get("attempts") or 0) < 4 for x in registry)
    exhausted_errors = sum(x.get("status") == "ERROR" and int(x.get("attempts") or 0) >= 4 for x in registry)
    fetched = status_counts.get("FETCHED", 0)

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "coverage_status": "BACKFILLING" if pending or exhausted_errors else "DISCOVERY_QUEUE_EMPTY",
        "warning": "Una cola vacía no acredita por sí sola cobertura histórica completa: depende de la exhaustividad de los canales públicos de descubrimiento disponibles.",
        "audit_registry": {
            "total_discovered": len(registry),
            "fetched": fetched,
            "pending": pending,
            "exhausted_errors": exhausted_errors,
            "fetch_pct_of_discovered": round(100 * fetched / max(1, len(registry)), 1),
            "by_status": [{"name": k, "count": v} for k, v in status_counts.most_common()],
            "by_discovery_channel": [{"name": k, "count": v} for k, v in channel_counts.most_common()],
        },
        "documents": {
            "count": len(documents),
            "publication_oldest": _min(pub_dates),
            "publication_newest": _max(pub_dates),
            "by_year": [{"year": y, "count": c} for y, c in sorted(document_years.items())],
        },
        "findings": {
            "count": len(findings),
            "occurrence_oldest": _min(occurrence_from),
            "occurrence_newest": _max(occurrence_to),
            "known_temporality": sum(bool(x.get("occurrence_date_anchor")) for x in findings),
            "unknown_temporality": sum(not bool(x.get("occurrence_date_anchor")) for x in findings),
            "by_anchor_year": [{"year": y, "count": c} for y, c in sorted(occurrence_years.items())],
        },
        "tribunal": {
            "records": len(tribunal),
            "state_date_oldest": _min(tribunal_dates),
            "state_date_newest": _max(tribunal_dates),
        },
        "official_reference_benchmark": {
            "period": "2024-04-01/2025-03-31",
            "cgr_reported_audits": benchmark_total,
            "loaded_documents_with_publication_date_in_period": loaded_in_benchmark,
            "orientation_ratio_pct": round(100 * loaded_in_benchmark / benchmark_total, 2),
            "interpretation": "Referencia de magnitud solamente. CGR reporta auditorías efectuadas en el período; la fecha de publicación de un informe no necesariamente coincide con la fecha de ejecución de la auditoría.",
            "source": "CGR - Principales resultados de fiscalización, publicado 20-06-2025",
        },
        "source_latest": source_latest,
        "scope": {
            "productive_layers": ["Informes de auditoría", "Tribunal de Cuentas", "FAU como reglas", "enforcement", "temporalidad"],
            "identified_but_not_yet_full_historical": ["Fiscalizaciones en curso", "Fundaciones", "Semáforo Municipal", "CIC", "bases financieras/patrimoniales", "InfoProbidad", "jurisprudencia"],
        },
    }


def write_coverage() -> dict:
    payload = summarize_coverage()
    out = DOCS_DIR / "data" / "coverage.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
