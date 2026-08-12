from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .collectors import HTTPClient
from .config import CONFIG_DIR
from .dashboard import build_dashboard
from .early_warning import refresh_watch_matches
from .enforcement import rebuild_enforcement_events
from .extract import extract_audit_links, parse_audit_detail
from .fau import rebuild_fau_matches
from .intelligence import rebuild_intelligence
from .quality import apply_entity_quality_gate
from .resolution import clean_entity_resolution
from .storage import export_parquet, read_jsonl, replace_jsonl, table_path, upsert_jsonl
from .temporality import backfill_finding_temporality, propagate_temporality_to_enrichment
from .tribunal import refresh_tribunal_reparo_candidates
from .coverage import write_coverage

AUDIT_RE = re.compile(r"/buscadorpdf/auditoria/([0-9a-f]{32})/html", re.I)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_audit_url(url: str) -> str:
    m = AUDIT_RE.search(url or "")
    if not m:
        return ""
    return f"https://www.contraloria.cl/buscadorpdf/auditoria/{m.group(1).lower()}/html"


def audit_hash(url: str) -> str:
    m = AUDIT_RE.search(url or "")
    return m.group(1).lower() if m else ""


def load_history_config() -> dict:
    path = CONFIG_DIR / "historical_sources.json"
    if not path.exists():
        return {"news_archives": [], "reference_pages": [], "known_audits": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _existing_registry() -> dict[str, dict]:
    return {x.get("audit_hash"): x for x in read_jsonl(table_path("audit_registry")) if x.get("audit_hash")}


def _sync_documents(registry: dict[str, dict], now: str) -> None:
    for doc in read_jsonl(table_path("documents")):
        url = canonical_audit_url(doc.get("source_url", ""))
        ah = audit_hash(url)
        if not ah:
            continue
        row = registry.get(ah, {})
        row.update({
            "registry_id": f"AUDREG-{ah}",
            "audit_hash": ah,
            "audit_url": url,
            "status": "FETCHED",
            "document_id": doc.get("document_id", ""),
            "document_date": doc.get("document_date", ""),
            "document_number": doc.get("document_number", ""),
            "last_error": "",
            "last_seen": now,
        })
        row.setdefault("first_seen", doc.get("retrieved_at") or now)
        row.setdefault("discovery_channel", "EXISTING_DOCUMENT")
        row.setdefault("discovery_source", url)
        row.setdefault("attempts", 1)
        registry[ah] = row


def register_urls(registry: dict[str, dict], urls: list[str] | set[str], channel: str, source: str, now: str) -> int:
    inserted = 0
    for raw in urls:
        url = canonical_audit_url(raw)
        ah = audit_hash(url)
        if not ah:
            continue
        row = registry.get(ah)
        if row is None:
            inserted += 1
            row = {
                "registry_id": f"AUDREG-{ah}",
                "audit_hash": ah,
                "audit_url": url,
                "status": "DISCOVERED",
                "attempts": 0,
                "first_seen": now,
                "last_seen": now,
                "last_error": "",
                "document_id": "",
                "document_date": "",
                "document_number": "",
                "discovery_channel": channel,
                "discovery_source": source,
            }
        else:
            row["last_seen"] = now
            if not row.get("discovery_channel"):
                row["discovery_channel"] = channel
                row["discovery_source"] = source
        registry[ah] = row
    return inserted


def _news_article_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a.get("href", ""))
        p = urlparse(href)
        if not (p.hostname or "").endswith("contraloria.cl"):
            continue
        if "/noticias/" not in p.path or "/content/" not in p.path:
            continue
        clean = href.split("#", 1)[0]
        if clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _pagination_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a.get("href", ""))
        p = urlparse(href)
        if not (p.hostname or "").endswith("contraloria.cl") or "/noticias" not in p.path or "/content/" in p.path:
            continue
        q = parse_qs(p.query)
        keys = " ".join(q).lower()
        text = a.get_text(" ", strip=True).lower()
        is_page = any(k in keys for k in ("cur", "page", "delta")) or text in {"siguiente", "next", ">", "›", "»"}
        if is_page and href not in seen:
            seen.add(href)
            out.append(href)
    return out


def discover_news_archive(client: HTTPClient, start_url: str, max_pages: int, max_articles: int, now: str) -> tuple[set[str], dict]:
    page_queue = [start_url]
    seen_pages, article_urls, audits = set(), set(), set()
    errors = 0
    while page_queue and len(seen_pages) < max_pages:
        page_url = page_queue.pop(0)
        if page_url in seen_pages:
            continue
        seen_pages.add(page_url)
        try:
            r = client.get(page_url)
            html = r.text
            article_urls.update(_news_article_links(html, r.url))
            for nxt in _pagination_links(html, r.url):
                if nxt not in seen_pages and nxt not in page_queue:
                    page_queue.append(nxt)
        except Exception:
            errors += 1
        time.sleep(0.12)
    checked = 0
    for article_url in sorted(article_urls)[:max_articles]:
        try:
            r = client.get(article_url)
            audits.update(canonical_audit_url(x) for x in extract_audit_links(r.text, r.url))
            checked += 1
        except Exception:
            errors += 1
        time.sleep(0.12)
    audits.discard("")
    return audits, {"pages_checked": len(seen_pages), "articles_discovered": len(article_urls), "articles_checked": checked, "audit_urls_found": len(audits), "errors": errors, "run_at": now}


def discover_reference_pages(client: HTTPClient, pages: list[dict], now: str) -> tuple[list[tuple[set[str], str, str]], dict]:
    batches = []
    checked = errors = found = 0
    for item in pages:
        url = item.get("url", "")
        if not url:
            continue
        try:
            r = client.get(url)
            urls = {canonical_audit_url(x) for x in extract_audit_links(r.text, r.url)}
            urls.discard("")
            batches.append((urls, item.get("channel", "REFERENCE_PAGE"), r.url))
            found += len(urls)
            checked += 1
        except Exception:
            errors += 1
        time.sleep(0.12)
    return batches, {"pages_checked": checked, "audit_urls_found": found, "errors": errors, "run_at": now}


def save_registry(registry: dict[str, dict]) -> None:
    replace_jsonl("audit_registry", registry.values(), "registry_id")


def discover(client: HTTPClient, max_pages: int, max_articles: int, now: str) -> dict:
    cfg = load_history_config()
    registry = _existing_registry()
    _sync_documents(registry, now)
    inserted = 0
    for item in cfg.get("known_audits", []):
        if item.get("enabled", True):
            inserted += register_urls(registry, {item.get("url", "")}, item.get("channel", "KNOWN_SEED"), item.get("source", "CONFIG"), now)
    news_stats = []
    for item in cfg.get("news_archives", []):
        if not item.get("enabled", True):
            continue
        urls, stats = discover_news_archive(client, item["url"], min(max_pages, int(item.get("max_pages", max_pages))), min(max_articles, int(item.get("max_articles", max_articles))), now)
        inserted += register_urls(registry, urls, item.get("channel", "NEWS_ARCHIVE"), item["url"], now)
        news_stats.append({"url": item["url"], **stats})
    ref_batches, ref_stats = discover_reference_pages(client, cfg.get("reference_pages", []), now)
    for urls, channel, source in ref_batches:
        inserted += register_urls(registry, urls, channel, source, now)
    save_registry(registry)
    return {"registry_total": len(registry), "new_registry_items": inserted, "news": news_stats, "references": ref_stats}


def process_queue(client: HTTPClient, batch_size: int, now: str) -> dict:
    registry = _existing_registry()
    _sync_documents(registry, now)
    pending = [x for x in registry.values() if x.get("status") != "FETCHED" and int(x.get("attempts") or 0) < 4]
    priority = {"KNOWN_SEED": 0, "CEA_REFERENCE": 1, "FOUNDATIONS": 2, "NEWS_ARCHIVE": 3}
    pending.sort(key=lambda x: (priority.get(x.get("discovery_channel", ""), 9), x.get("first_seen", ""), x.get("audit_hash", "")))
    selected = pending[:max(0, batch_size)]
    fetched = failed = new_docs = new_findings = 0
    for row in selected:
        ah = row["audit_hash"]
        row["attempts"] = int(row.get("attempts") or 0) + 1
        row["last_attempt_at"] = now
        try:
            parsed = parse_audit_detail(client.get(row["audit_url"]).text, row["audit_url"])
            i, _ = upsert_jsonl("documents", [parsed.document.to_dict()], "document_id")
            new_docs += i
            upsert_jsonl("events", [parsed.event.to_dict()], "event_id")
            i, _ = upsert_jsonl("findings", [x.to_dict() for x in parsed.findings], "finding_id")
            new_findings += i
            upsert_jsonl("evidence", [x.to_dict() for x in parsed.evidence], "evidence_id")
            upsert_jsonl("entities", [x.to_dict() for x in parsed.entities], "entity_id")
            row.update({"status": "FETCHED", "document_id": parsed.document.document_id, "document_date": parsed.document.document_date, "document_number": parsed.document.document_number, "last_error": "", "last_seen": now})
            fetched += 1
        except Exception as exc:
            row["status"] = "ERROR"
            row["last_error"] = f"{type(exc).__name__}: {exc}"[:500]
            failed += 1
        registry[ah] = row
        time.sleep(0.25)
    save_registry(registry)
    return {"selected": len(selected), "fetched": fetched, "failed": failed, "new_documents": new_docs, "new_findings": new_findings, "remaining": sum(x.get("status") != "FETCHED" and int(x.get("attempts") or 0) < 4 for x in registry.values())}


def rebuild_products() -> dict:
    temporality = backfill_finding_temporality()
    intelligence = rebuild_intelligence()
    resolution = clean_entity_resolution()
    quality = apply_entity_quality_gate()
    propagate_temporality_to_enrichment()
    watch = refresh_watch_matches()
    enforcement = rebuild_enforcement_events()
    tribunal = refresh_tribunal_reparo_candidates()
    fau = rebuild_fau_matches()
    parquet = export_parquet()
    coverage = write_coverage()
    dashboard = build_dashboard()
    return {"temporality": temporality, "intelligence": intelligence, "resolution": resolution, "quality": quality, "watch": watch, "enforcement": enforcement, "tribunal": tribunal, "fau": fau, "parquet": parquet, "coverage": coverage, "dashboard_kpis": dashboard.get("kpis", {})}


def run_historical(batch_size: int = 120, max_pages: int = 80, max_articles: int = 1200, discover_only: bool = False) -> dict:
    now = iso_now()
    client = HTTPClient(timeout=40)
    discovery = discover(client, max_pages, max_articles, now)
    queue = {"selected": 0, "fetched": 0, "failed": 0, "new_documents": 0, "new_findings": 0, "remaining": 0}
    if not discover_only:
        queue = process_queue(client, batch_size, now)
    products = rebuild_products()
    return {"started_at": now, "discovery": discovery, "queue": queue, "products": products}


def main() -> None:
    p = argparse.ArgumentParser(description="Radar CGR - barrido historico acumulativo")
    p.add_argument("--batch-size", type=int, default=120)
    p.add_argument("--max-pages", type=int, default=80)
    p.add_argument("--max-articles", type=int, default=1200)
    p.add_argument("--discover-only", action="store_true")
    a = p.parse_args()
    print(json.dumps(run_historical(a.batch_size, a.max_pages, a.max_articles, a.discover_only), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
