from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlencode

from .collectors import HTTPClient
from .models import stable_id
from .storage import read_jsonl, table_path, upsert_jsonl

COLLINFO = "https://index.commoncrawl.org/collinfo.json"
DOCID_RE = re.compile(r"[?&]docIdcm=([0-9a-fA-F-]{32,40})")
MODERN_RE = re.compile(r"/buscadorpdf/auditoria/([0-9a-fA-F]{32})/html", re.I)

PREFIXES = [
    "www.contraloria.cl/SicaProd/SICAv3-BIFAPortalCGR/faces/detalleInforme",
    "www.contraloria.cl/SicaProd/SICAv3-BI-FAPortalCGR/faces/detalleInforme",
    "www.contraloria.cl/buscadorpdf/auditoria/",
]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_hash(url: str) -> str:
    m = MODERN_RE.search(url or "")
    if m:
        return m.group(1).lower()
    m = DOCID_RE.search(url or "")
    if not m:
        return ""
    value = re.sub(r"[^0-9a-fA-F]", "", m.group(1)).lower()
    return value if len(value) == 32 else ""


def official_url(audit_hash: str) -> str:
    return f"https://www.contraloria.cl/buscadorpdf/auditoria/{audit_hash}/html"


def _selected_indexes(client: HTTPClient, min_year: int, max_year: int) -> list[dict]:
    rows = client.get(COLLINFO).json()
    by_year: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        m = re.search(r"CC-MAIN-(\d{4})-", row.get("id", ""))
        if not m:
            continue
        year = int(m.group(1))
        if min_year <= year <= max_year:
            by_year[year].append(row)
    selected = []
    for year in sorted(by_year):
        # collinfo suele venir de más reciente a más antiguo; escogemos el crawl más reciente del año.
        selected.append(sorted(by_year[year], key=lambda x: x.get("id", ""), reverse=True)[0])
    return selected


def _query_url(api: str, prefix: str, **extra) -> str:
    params = {"url": prefix, "matchType": "prefix", **extra}
    return f"{api}?{urlencode(params)}"


def _num_pages(client: HTTPClient, api: str, prefix: str, page_size: int) -> int:
    url = _query_url(api, prefix, showNumPages="true", pageSize=page_size)
    r = client.get(url)
    payload = r.json()
    if isinstance(payload, dict):
        return max(1, int(payload.get("pages") or 1))
    return 1


def _page_hashes(client: HTTPClient, api: str, prefix: str, page: int, page_size: int) -> set[str]:
    url = _query_url(api, prefix, output="json", page=page, pageSize=page_size)
    r = client.get(url)
    hashes = set()
    for line in r.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ah = extract_hash(row.get("url", ""))
        if ah:
            hashes.add(ah)
    return hashes


def discover(min_year: int = 2013, max_year: int = 2026, max_pages_per_query: int = 8, page_size: int = 5) -> dict:
    client = HTTPClient(timeout=45)
    now = iso_now()
    existing = {x.get("audit_hash"): x for x in read_jsonl(table_path("audit_registry")) if x.get("audit_hash")}
    selected = _selected_indexes(client, min_year, max_year)
    found: dict[str, set[str]] = defaultdict(set)
    errors = []
    queries = pages_read = 0

    for collection in selected:
        cid = collection.get("id", "")
        api = collection.get("cdx-api") or f"https://index.commoncrawl.org/{cid}-index"
        for prefix in PREFIXES:
            queries += 1
            try:
                pages = _num_pages(client, api, prefix, page_size)
                for page in range(min(pages, max_pages_per_query)):
                    found[cid].update(_page_hashes(client, api, prefix, page, page_size))
                    pages_read += 1
                    time.sleep(0.8)
            except Exception as exc:
                errors.append({"collection": cid, "prefix": prefix, "error": f"{type(exc).__name__}: {exc}"[:300]})
            time.sleep(1.0)

    all_hashes = set().union(*found.values()) if found else set()
    rows = []
    for ah in sorted(all_hashes):
        prev = existing.get(ah, {})
        collections = sorted(cid for cid, values in found.items() if ah in values)
        row = {
            "registry_id": f"AUDREG-{ah}",
            "audit_hash": ah,
            "audit_url": official_url(ah),
            "status": prev.get("status", "DISCOVERED"),
            "attempts": int(prev.get("attempts") or 0),
            "first_seen": prev.get("first_seen") or now,
            "last_seen": now,
            "last_error": prev.get("last_error", ""),
            "document_id": prev.get("document_id", ""),
            "document_date": prev.get("document_date", ""),
            "document_number": prev.get("document_number", ""),
            "discovery_channel": prev.get("discovery_channel") or "COMMON_CRAWL_INDEX",
            "discovery_source": prev.get("discovery_source") or ",".join(collections[:8]),
            "discovery_collections": collections,
        }
        rows.append(row)
    inserted, updated = upsert_jsonl("audit_registry", rows, "registry_id")
    return {
        "run_at": now,
        "min_year": min_year,
        "max_year": max_year,
        "collections_checked": [x.get("id") for x in selected],
        "queries": queries,
        "pages_read": pages_read,
        "unique_hashes_found": len(all_hashes),
        "new_registry_items": inserted,
        "updated_registry_items": updated,
        "errors": errors[:40],
        "by_collection": [{"collection": cid, "unique_hashes": len(values)} for cid, values in sorted(found.items())],
        "validation_rule": "Common Crawl solo descubre docIdcm; cada URL debe ser validada posteriormente contra la ficha oficial CGR.",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Descubrimiento historico de docIdcm CGR mediante Common Crawl")
    p.add_argument("--min-year", type=int, default=2013)
    p.add_argument("--max-year", type=int, default=datetime.now().year)
    p.add_argument("--max-pages-per-query", type=int, default=8)
    p.add_argument("--page-size", type=int, default=5)
    args = p.parse_args()
    print(json.dumps(discover(args.min_year, args.max_year, args.max_pages_per_query, args.page_size), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
