from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .aml import assess
from .models import Document, Entity, Event, Evidence, Finding, stable_id
from .utils import normalize_name, normalize_ws, parse_clp_amounts, sha256_text

AUDIT_URL_RE = re.compile(r"https?://[^\s\"']*contraloria\.cl/buscadorpdf/auditoria/[a-f0-9]+/html", re.I)
DATE_RE = re.compile(r"\b(\d{2}-\d{2}-\d{4})\b")

@dataclass
class AuditParseResult:
    document: Document
    event: Event
    findings: list[Finding]
    evidence: list[Evidence]
    entities: list[Entity]


def extract_audit_links(html: str, base_url: str = "") -> list[str]:
    soup = BeautifulSoup(html or "", "lxml")
    urls: set[str] = set(AUDIT_URL_RE.findall(html or ""))
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/buscadorpdf/auditoria/" in href and href.endswith("/html"):
            if href.startswith("http"):
                urls.add(href)
            elif base_url:
                from urllib.parse import urljoin
                urls.add(urljoin(base_url, href))
    return sorted(urls)


def _section(text: str, start: str, end: str | None = None) -> str:
    up = text.upper()
    s = up.find(start.upper())
    if s < 0:
        return ""
    s += len(start)
    if end:
        e = up.find(end.upper(), s)
        if e >= 0:
            return text[s:e].strip()
    return text[s:].strip()


def _metadata(text: str, key: str, next_keys: list[str]) -> str:
    up = text.upper()
    s = up.find(key.upper())
    if s < 0:
        return ""
    s += len(key)
    candidates = []
    for nk in next_keys:
        idx = up.find(nk.upper(), s)
        if idx >= 0:
            candidates.append(idx)
    e = min(candidates) if candidates else min(len(text), s + 400)
    return normalize_ws(text[s:e]).strip(": ")


def _split_findings(conclusions: str) -> list[str]:
    if not conclusions:
        return []
    parts = re.split(r"(?=\n\s*(?:\d+\)|\d+\.|[-•])\s*)", conclusions)
    cleaned = [normalize_ws(p) for p in parts if len(normalize_ws(p)) >= 80]
    if len(cleaned) <= 1:
        parts = re.split(r"\n\s*\n+", conclusions)
        cleaned = [normalize_ws(p) for p in parts if len(normalize_ws(p)) >= 80]
    if len(cleaned) <= 1 and len(conclusions) > 180:
        sentences = re.split(r"(?<=[\.;])\s+(?=[A-ZÁÉÍÓÚÑ0-9])", normalize_ws(conclusions))
        buf, out = [], []
        for sentence in sentences:
            buf.append(sentence)
            if sum(map(len, buf)) > 600:
                out.append(" ".join(buf)); buf = []
        if buf:
            out.append(" ".join(buf))
        cleaned = [x for x in out if len(x) >= 80]
    return cleaned[:120]


def _guess_entity(title: str) -> str:
    for p in [r"-([^-]+?)-AUDITOR[IÍ]A", r"-([^-]+?)-MAYO\s+\d{4}", r"-([^-]+?)-DICIEMBRE\s+\d{4}"]:
        m = re.search(p, title, re.I)
        if m:
            return normalize_ws(m.group(1)).title()
    return ""


def parse_audit_detail(html: str, url: str) -> AuditParseResult:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["br", "p", "div", "li", "h1", "h2", "h3", "h4"]):
        tag.append("\n")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    title_el = soup.find(["h4", "h3", "h2"], string=re.compile(r"INFORME", re.I))
    title = normalize_ws(title_el.get_text(" ", strip=True) if title_el else "")
    if not title:
        m = re.search(r"(INFORME\s+(?:FINAL|DE INVESTIGACI[ÓO]N)[^\n]{10,300})", text, re.I)
        title = normalize_ws(m.group(1)) if m else "Informe CGR"

    number = _metadata(text, "NÚMERO", ["FECHA DOCUMENTO", "NIVEL:"])
    if not number:
        m = re.search(r"INFORME(?: FINAL)?(?: N[°º])?\s*([0-9]+(?:[/\-][0-9]{2,4})?)", title, re.I)
        number = m.group(1) if m else ""
    date = _metadata(text, "FECHA DOCUMENTO", ["NIVEL:", "UNIDAD CGR:"])
    dm = DATE_RE.search(date); date = dm.group(1) if dm else date[:10]
    level = _metadata(text, "NIVEL:", ["UNIDAD CGR:", "TIPO:", "REGIÓN:", "NOMBRE:"])
    unit = _metadata(text, "UNIDAD CGR:", ["TIPO:", "REGIÓN:", "NOMBRE:"])
    dtype = _metadata(text, "TIPO:", ["REGIÓN:", "NOMBRE:", "OBJETIVO"])
    region = _metadata(text, "REGIÓN:", ["NOMBRE:", "OBJETIVO"])
    name_meta = _metadata(text, "NOMBRE:", ["Documento Asociado", "OBJETIVO"])
    if name_meta and len(name_meta) > len(title):
        title = name_meta

    objective = _section(text, "OBJETIVO", "CONCLUSIONES")
    conclusions = _section(text, "CONCLUSIONES")
    conclusions = re.split(r"CONTRALORÍA GENERAL DE LA REPÚBLICA ·", conclusions, flags=re.I)[0].strip()

    token = url.rstrip("/").split("/")[-2] if "/auditoria/" in url else sha256_text(url)[:32]
    document_id = f"CGR-AUD-{token}"
    content_hash = sha256_text(text)
    pdf_url = ""
    mtoken = re.search(r"/auditoria/([a-f0-9]+)/html", url, re.I)
    if mtoken:
        pdf_url = f"https://www.contraloria.cl/SicaProd/SICAv3-BIFAPortalCGR/servletfichainformegoogle?docIdcm={mtoken.group(1)}&pdf=1"

    doc = Document(document_id=document_id,source_system="CGR",source_module="AUDITORIAS",source_url=url,title=title,document_number=number,document_date=date,document_type=dtype,region=region,unit_cgr=unit,level=level,pdf_url=pdf_url,content_hash=content_hash,raw_text=text)
    entity_name = _guess_entity(title)
    entity = Entity(entity_id=stable_id("ENT", normalize_name(entity_name)),entity_type="PUBLIC_ORGANIZATION",name=entity_name,normalized_name=normalize_name(entity_name),region=region,source_document_id=document_id) if entity_name else None
    event_id = stable_id("EVT", document_id, date, title)
    event = Event(event_id=event_id,document_id=document_id,event_type="AUDIT_REPORT",event_date=date,title=title,entity_name=entity_name,region=region,source_url=url,source_module="AUDITORIAS")

    findings=[]; evidence=[]
    for idx, chunk in enumerate(_split_findings(conclusions), start=1):
        amounts = parse_clp_amounts(chunk); amount = max(amounts) if amounts else None
        aml = assess(chunk, bool(amounts))
        finding_id = stable_id("FND", document_id, idx, sha256_text(chunk)[:16]); evidence_id = stable_id("EVD", document_id, idx, sha256_text(chunk)[:16])
        findings.append(Finding(finding_id=finding_id,event_id=event_id,document_id=document_id,finding_order=idx,description=chunk,finding_type=aml.finding_type,risk_family=aml.risk_family,severity=aml.severity,aml_relevance=aml.relevance,aml_score=aml.score,amount_clp=amount,enforcement=aml.enforcement,source_url=url,evidence_id=evidence_id))
        evidence.append(Evidence(evidence_id=evidence_id,document_id=document_id,finding_id=finding_id,source_url=url,source_section="CONCLUSIONES",source_text=chunk,content_hash=sha256_text(chunk)))
    if objective:
        evidence.append(Evidence(evidence_id=stable_id("EVD", document_id, "OBJECTIVE"),document_id=document_id,finding_id="",source_url=url,source_section="OBJETIVO",source_text=normalize_ws(objective),content_hash=sha256_text(normalize_ws(objective))))
    return AuditParseResult(doc,event,findings,evidence,[entity] if entity else [])
