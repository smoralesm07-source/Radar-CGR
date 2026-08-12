from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import DEFAULT_HEADERS, Source
from .extract import extract_audit_links
from .utils import official_cgr_url, normalize_ws, sha256_text

@dataclass
class PageResult:
    source_id: str
    source_url: str
    status_code: int | None
    fetched_at: str
    content_hash: str = ""
    title: str = ""
    text_excerpt: str = ""
    links: list[dict] = field(default_factory=list)
    audit_links: list[str] = field(default_factory=list)
    error: str = ""
    def to_dict(self) -> dict: return self.__dict__.copy()

class HTTPClient:
    """Cliente HTTP conservador para fuentes CGR con reintentos ante cortes transitorios."""
    def __init__(self, timeout: int = 35):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.timeout = timeout

    def get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        response.raise_for_status()
        return response


def collect_page(client: HTTPClient, source: Source) -> tuple[PageResult, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        response = client.get(source.url); html = response.text; soup = BeautifulSoup(html, "lxml")
        title = normalize_ws(soup.title.get_text(" ", strip=True) if soup.title else source.name)
        links=[]; seen=set()
        for a in soup.find_all("a", href=True):
            href = urljoin(response.url, a.get("href", ""))
            if not official_cgr_url(href) or href in seen: continue
            seen.add(href); links.append({"url":href,"text":normalize_ws(a.get_text(" ",strip=True))[:250]})
            if len(links) >= source.max_items: break
        return PageResult(source.id,response.url,response.status_code,now,sha256_text(html),title,normalize_ws(soup.get_text(" ",strip=True))[:3000],links,extract_audit_links(html,response.url)), html
    except Exception as exc:
        return PageResult(source.id,source.url,None,now,error=f"{type(exc).__name__}: {exc}"), ""


def collect_news_articles(client: HTTPClient, source: Source, index_html: str, index_url: str) -> list[dict]:
    soup=BeautifulSoup(index_html,"lxml"); candidates=[]; seen=set()
    for a in soup.find_all("a",href=True):
        href=urljoin(index_url,a.get("href",""))
        if "/noticias/" not in href or href in seen: continue
        if "asset_publisher" not in href and "/content/" not in href: continue
        seen.add(href); candidates.append(href)
        if len(candidates)>=source.max_items: break
    rows=[]
    for url in candidates:
        try:
            r=client.get(url); art=BeautifulSoup(r.text,"lxml"); title_tag=art.find(["h1","h2","h3"])
            title=normalize_ws(title_tag.get_text(" ",strip=True) if title_tag else ""); text=normalize_ws(art.get_text(" ",strip=True)); dm=re.search(r"\b(\d{2}/\d{2}/\d{4})\b",text)
            rows.append({"url":r.url,"title":title,"date":dm.group(1) if dm else "","content_hash":sha256_text(text),"text_excerpt":text[:5000],"audit_links":extract_audit_links(r.text,r.url)})
        except Exception as exc:
            rows.append({"url":url,"error":f"{type(exc).__name__}: {exc}"})
        time.sleep(0.15)
    return rows
