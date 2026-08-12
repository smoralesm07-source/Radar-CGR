from __future__ import annotations

import argparse
import json
import re
from calendar import monthrange
from datetime import date, datetime, timezone

from .storage import read_jsonl, replace_jsonl, table_path, upsert_jsonl

LANDING = "https://www.contraloria.cl/web/cgr/informes-de-auditoria"
AUDIT_PATH_RE = re.compile(r"/buscadorpdf/auditoria/([0-9a-fA-F]{32})/html", re.I)
DOCID_RE = re.compile(r"docIdcm[^0-9a-fA-F]{0,30}([0-9a-fA-F]{32})", re.I)
RESULT_RE = re.compile(r"(?:total\s*(?:de)?\s*)?(\d[\d\.]*)\s+(?:informes|resultados|registros)", re.I)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_url(audit_hash: str) -> str:
    return f"https://www.contraloria.cl/buscadorpdf/auditoria/{audit_hash.lower()}/html"


def extract_hashes(text: str) -> set[str]:
    text = text or ""
    out = {x.lower() for x in AUDIT_PATH_RE.findall(text)}
    out.update(x.lower() for x in DOCID_RE.findall(text))
    return out


def parse_result_count(text: str) -> int | None:
    matches = RESULT_RE.findall(text or "")
    if not matches:
        return None
    values = []
    for raw in matches:
        try:
            values.append(int(raw.replace(".", "")))
        except ValueError:
            pass
    return max(values) if values else None


def month_windows(start_year: int, end_year: int, end_month: int = 12) -> list[tuple[str, str, str]]:
    out = []
    for year in range(start_year, end_year + 1):
        last_month = end_month if year == end_year else 12
        for month in range(1, last_month + 1):
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])
            out.append((f"{year:04d}-{month:02d}", start.isoformat(), end.isoformat()))
    return out


def _date_cl(iso_date: str) -> str:
    d = date.fromisoformat(iso_date)
    return d.strftime("%d/%m/%Y")


def _window_state(start_year: int, end_year: int, end_month: int) -> dict[str, dict]:
    current = {x.get("window_id"): x for x in read_jsonl(table_path("official_search_windows")) if x.get("window_id")}
    for wid, start, end in month_windows(start_year, end_year, end_month):
        current.setdefault(wid, {
            "window_id": wid,
            "date_from": start,
            "date_to": end,
            "status": "PENDING",
            "attempts": 0,
            "audit_ids_found": 0,
            "expected_results": None,
            "pages_visited": 0,
            "last_error": "",
            "last_scanned": "",
        })
    return current


def _register_hashes(hashes: set[str], source: str, now: str) -> tuple[int, int]:
    existing = {x.get("audit_hash"): x for x in read_jsonl(table_path("audit_registry")) if x.get("audit_hash")}
    rows = []
    for ah in sorted(hashes):
        prev = existing.get(ah, {})
        rows.append({
            "registry_id": f"AUDREG-{ah}",
            "audit_hash": ah,
            "audit_url": canonical_url(ah),
            "status": prev.get("status", "DISCOVERED"),
            "attempts": int(prev.get("attempts") or 0),
            "first_seen": prev.get("first_seen") or now,
            "last_seen": now,
            "last_error": prev.get("last_error", ""),
            "document_id": prev.get("document_id", ""),
            "document_date": prev.get("document_date", ""),
            "document_number": prev.get("document_number", ""),
            "discovery_channel": prev.get("discovery_channel") or "CGR_OFFICIAL_SEARCH",
            "discovery_source": prev.get("discovery_source") or source,
        })
    return upsert_jsonl("audit_registry", rows, "registry_id") if rows else (0, 0)


def _input_for(frame, kind: str):
    pattern = re.compile(rf"fecha\s*{kind}", re.I)
    try:
        loc = frame.get_by_label(pattern)
        if loc.count():
            return loc.first
    except Exception:
        pass
    for inp in frame.locator("input").all():
        attrs = " ".join(filter(None, [inp.get_attribute("id"), inp.get_attribute("name"), inp.get_attribute("placeholder"), inp.get_attribute("aria-label"), inp.get_attribute("title")]))
        norm = attrs.lower().replace("_", " ").replace("-", " ")
        if "fecha" in norm and kind.lower() in norm:
            return inp
    return None


def _search_button(frame):
    for pattern in (re.compile(r"^\s*buscar\s*$", re.I), re.compile(r"buscar", re.I)):
        try:
            loc = frame.get_by_role("button", name=pattern)
            if loc.count():
                return loc.first
        except Exception:
            pass
    for selector in ('input[type="submit"]', 'button', 'a'):
        for el in frame.locator(selector).all():
            text = " ".join(filter(None, [el.inner_text() if selector != 'input[type="submit"]' else "", el.get_attribute("value"), el.get_attribute("title"), el.get_attribute("aria-label")]))
            if re.search(r"buscar", text, re.I):
                return el
    return None


def _find_search_frame(page):
    for frame in page.frames:
        try:
            if _input_for(frame, "desde") is not None and _input_for(frame, "hasta") is not None:
                return frame
        except Exception:
            continue
    return None


def _open_search(page, context):
    page.goto(LANDING, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    if _find_search_frame(page):
        return page
    before = len(context.pages)
    clicked = False
    for pattern in (re.compile(r"Buscador de Informes de Auditor", re.I), re.compile(r"Buscador", re.I)):
        try:
            loc = page.get_by_text(pattern)
            if loc.count():
                loc.first.click(timeout=15000)
                clicked = True
                break
        except Exception:
            pass
    if not clicked:
        raise RuntimeError("No fue posible activar el Buscador de Informes de Auditoría")
    page.wait_for_timeout(2500)
    target = context.pages[-1] if len(context.pages) > before else page
    try:
        target.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    return target


def _harvest(frame, response_hashes: set[str]) -> tuple[set[str], int | None, str]:
    html = frame.content()
    text = frame.locator("body").inner_text(timeout=10000) if frame.locator("body").count() else ""
    hashes = extract_hashes(html) | set(response_hashes)
    return hashes, parse_result_count(text), text


def _next_button(frame):
    selectors = [
        ".x-tbar-page-next:not(.x-item-disabled)",
        'button[title*="iguiente" i]:not([disabled])',
        'a[title*="iguiente" i]',
        'button[aria-label*="iguiente" i]:not([disabled])',
        'a[aria-label*="iguiente" i]',
    ]
    for selector in selectors:
        try:
            loc = frame.locator(selector)
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:
            pass
    try:
        loc = frame.get_by_role("button", name=re.compile(r"siguiente|next", re.I))
        if loc.count() and loc.first.is_enabled():
            return loc.first
    except Exception:
        pass
    return None


def _scan_window(target, date_from: str, date_to: str, response_hashes: set[str], max_pages: int) -> dict:
    frame = _find_search_frame(target)
    if frame is None:
        raise RuntimeError("No se localizaron los campos Fecha desde / Fecha hasta del buscador oficial")
    start_input = _input_for(frame, "desde")
    end_input = _input_for(frame, "hasta")
    button = _search_button(frame)
    if start_input is None or end_input is None or button is None:
        raise RuntimeError("Formulario oficial incompleto: faltan fechas o botón Buscar")
    start_input.fill(_date_cl(date_from))
    end_input.fill(_date_cl(date_to))
    response_hashes.clear()
    button.click(timeout=20000)
    try:
        target.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        target.wait_for_timeout(1800)
    hashes, expected, text = _harvest(frame, response_hashes)
    pages = 1
    seen_signatures = {tuple(sorted(hashes))}
    for _ in range(max(0, max_pages - 1)):
        nxt = _next_button(frame)
        if nxt is None:
            break
        try:
            nxt.click(timeout=10000)
            target.wait_for_timeout(900)
        except Exception:
            break
        new_hashes, new_expected, new_text = _harvest(frame, response_hashes)
        hashes.update(new_hashes)
        expected = max(x for x in (expected, new_expected) if x is not None) if any(x is not None for x in (expected, new_expected)) else None
        pages += 1
        sig = tuple(sorted(hashes))
        if sig in seen_signatures and new_text == text:
            break
        seen_signatures.add(sig)
        text = new_text
    zero_confirmed = bool(re.search(r"(?:0\s+(?:resultados|registros|informes)|no\s+(?:se\s+)?(?:encontraron|hubo)\s+resultados)", text, re.I))
    if expected is not None and len(hashes) < expected:
        status = "PARTIAL"
    elif not hashes and expected not in (0, None):
        status = "PARTIAL"
    elif not hashes and expected is None and not zero_confirmed:
        status = "PARTIAL"
    else:
        status = "SCANNED"
    return {"hashes": hashes, "expected": expected, "pages": pages, "status": status, "zero_confirmed": zero_confirmed}


def scan_official(start_year: int = 2009, months_per_run: int = 24, max_pages: int = 200, retry_errors: bool = True) -> dict:
    now = iso_now()
    today = date.today()
    state = _window_state(start_year, today.year, today.month)
    candidates = []
    for row in state.values():
        status = row.get("status", "PENDING")
        attempts = int(row.get("attempts") or 0)
        if status == "SCANNED":
            continue
        if status in {"ERROR", "PARTIAL"} and (not retry_errors or attempts >= 4):
            continue
        candidates.append(row)
    candidates.sort(key=lambda x: (x.get("date_from", ""), x.get("window_id", "")))
    selected = candidates[:max(0, months_per_run)]
    all_hashes: set[str] = set()
    errors = []
    scanned = partial = failed = 0
    if not selected:
        replace_jsonl("official_search_windows", state.values(), "window_id")
        return {"run_at": now, "selected": 0, "scanned": 0, "partial": 0, "failed": 0, "hashes_found": 0, "windows_total": len(state), "windows_complete": sum(x.get("status") == "SCANNED" for x in state.values())}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright no está instalado. Use requirements-historical.txt") from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = browser.new_context(locale="es-CL", timezone_id="America/Santiago")
        page = context.new_page()
        response_hashes: set[str] = set()

        def capture_response(response):
            try:
                if "contraloria.cl" not in response.url.lower():
                    return
                response_hashes.update(extract_hashes(response.url))
                ctype = (response.headers.get("content-type") or "").lower()
                if any(x in ctype for x in ("json", "text", "javascript", "xml", "html")):
                    length = int(response.headers.get("content-length") or 0)
                    if not length or length < 4_000_000:
                        response_hashes.update(extract_hashes(response.text()))
            except Exception:
                pass

        page.on("response", capture_response)
        try:
            target = _open_search(page, context)
            if target is not page:
                target.on("response", capture_response)
            for row in selected:
                wid = row["window_id"]
                row["attempts"] = int(row.get("attempts") or 0) + 1
                row["last_scanned"] = now
                try:
                    result = _scan_window(target, row["date_from"], row["date_to"], response_hashes, max_pages)
                    hashes = result["hashes"]
                    all_hashes.update(hashes)
                    row.update({
                        "status": result["status"],
                        "audit_ids_found": len(hashes),
                        "expected_results": result["expected"],
                        "pages_visited": result["pages"],
                        "last_error": "" if result["status"] == "SCANNED" else "No se pudo demostrar que todos los resultados visibles fueron capturados",
                    })
                    if result["status"] == "SCANNED": scanned += 1
                    else: partial += 1
                except Exception as exc:
                    row["status"] = "ERROR"
                    row["last_error"] = f"{type(exc).__name__}: {exc}"[:800]
                    failed += 1
                    errors.append({"window": wid, "error": row["last_error"]})
                state[wid] = row
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:800]
            for row in selected:
                row["attempts"] = int(row.get("attempts") or 0) + 1
                row["status"] = "ERROR"
                row["last_scanned"] = now
                row["last_error"] = error
                state[row["window_id"]] = row
            failed = len(selected)
            errors.append({"window": "SEARCH_BOOTSTRAP", "error": error})
        finally:
            browser.close()

    inserted, updated = _register_hashes(all_hashes, LANDING, now)
    replace_jsonl("official_search_windows", state.values(), "window_id")
    complete = sum(x.get("status") == "SCANNED" for x in state.values())
    partial_total = sum(x.get("status") == "PARTIAL" for x in state.values())
    error_total = sum(x.get("status") == "ERROR" for x in state.values())
    return {
        "run_at": now,
        "start_year": start_year,
        "selected": len(selected),
        "scanned": scanned,
        "partial": partial,
        "failed": failed,
        "hashes_found": len(all_hashes),
        "new_registry_items": inserted,
        "updated_registry_items": updated,
        "windows_total": len(state),
        "windows_complete": complete,
        "windows_partial": partial_total,
        "windows_error": error_total,
        "window_completion_pct": round(100 * complete / max(1, len(state)), 1),
        "errors": errors[:30],
        "method": "Automatización del buscador oficial CGR por intervalos mensuales; cada docIdcm descubierto se valida posteriormente contra la ficha oficial antes de entrar al corpus.",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Radar CGR - descubrimiento exhaustivo mediante buscador oficial")
    p.add_argument("--start-year", type=int, default=2009)
    p.add_argument("--months-per-run", type=int, default=24)
    p.add_argument("--max-pages", type=int, default=200)
    p.add_argument("--no-retry-errors", action="store_true")
    a = p.parse_args()
    print(json.dumps(scan_official(a.start_year, a.months_per_run, a.max_pages, not a.no_retry_errors), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
