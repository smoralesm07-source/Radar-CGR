from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlencode

from .collectors import HTTPClient
from .storage import read_jsonl, replace_jsonl, table_path, upsert_jsonl

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
    if m: return m.group(1).lower()
    m = DOCID_RE.search(url or "")
    if not m: return ""
    value = re.sub(r"[^0-9a-fA-F]", "", m.group(1)).lower()
    return value if len(value) == 32 else ""

def official_url(audit_hash: str) -> str:
    return f"https://www.contraloria.cl/buscadorpdf/auditoria/{audit_hash}/html"

def _all_indexes(client: HTTPClient, min_year: int, max_year: int) -> list[dict]:
    rows = client.get(COLLINFO).json(); selected=[]
    for row in rows:
        m=re.search(r"CC-MAIN-(\d{4})-",row.get("id",""))
        if m and min_year<=int(m.group(1))<=max_year:selected.append(row)
    return sorted(selected,key=lambda x:x.get("id",""))

def _query_url(api: str, prefix: str, **extra) -> str:
    return f"{api}?{urlencode({'url':prefix,'matchType':'prefix',**extra})}"

def _raw_get(client: HTTPClient, url: str):
    r=client.session.get(url,timeout=client.timeout,allow_redirects=True)
    if r.status_code==404:return None
    r.raise_for_status();return r

def _num_pages(client: HTTPClient, api: str, prefix: str, page_size: int) -> int:
    r=_raw_get(client,_query_url(api,prefix,showNumPages="true",pageSize=page_size))
    if r is None:return 0
    try:payload=r.json()
    except Exception:return 1 if r.text.strip() else 0
    return max(0,int(payload.get("pages") or 0)) if isinstance(payload,dict) else 0

def _parse_hash_lines(text:str)->set[str]:
    hashes=set()
    for line in text.splitlines():
        line=line.strip()
        if not line:continue
        try:row=json.loads(line)
        except json.JSONDecodeError:continue
        ah=extract_hash(row.get("url",""))
        if ah:hashes.add(ah)
    return hashes

def _page_hashes(client: HTTPClient, api: str, prefix: str, page: int, page_size: int) -> set[str]:
    url=_query_url(api,prefix,output="json",page=page,pageSize=page_size)
    r=client.session.get(url,timeout=client.timeout,allow_redirects=True)
    if r.status_code==404:return set()
    if r.status_code==400 and page==0:
        # Algunos índices antiguos aceptan showNumPages pero no la paginación explícita.
        fallback=_query_url(api,prefix,output="json")
        r=client.session.get(fallback,timeout=client.timeout,allow_redirects=True)
        if r.status_code==404:return set()
    r.raise_for_status()
    return _parse_hash_lines(r.text)

def _state_rows()->dict[str,dict]:
    return {x.get("collection_id"):x for x in read_jsonl(table_path("cc_collections")) if x.get("collection_id")}

def discover(min_year:int=2013,max_year:int=2026,max_pages_per_query:int=20,page_size:int=5,max_collections:int=0,rescan:bool=False)->dict:
    client=HTTPClient(timeout=45);now=iso_now();existing={x.get("audit_hash"):x for x in read_jsonl(table_path("audit_registry")) if x.get("audit_hash")};state=_state_rows();indexes=_all_indexes(client,min_year,max_year);candidates=[x for x in indexes if rescan or state.get(x.get("id"),{}).get("status")!="SCANNED"]
    if max_collections>0:candidates=candidates[:max_collections]
    found=defaultdict(set);errors=[];queries=pages_read=scanned=failed=0
    for collection in candidates:
        cid=collection.get("id","");api=collection.get("cdx-api") or f"https://index.commoncrawl.org/{cid}-index";collection_errors=[]
        for prefix in PREFIXES:
            queries+=1
            try:
                pages=_num_pages(client,api,prefix,page_size)
                for page in range(min(pages,max_pages_per_query)):
                    found[cid].update(_page_hashes(client,api,prefix,page,page_size));pages_read+=1;time.sleep(.35)
            except Exception as exc:collection_errors.append(f"{type(exc).__name__}: {exc}"[:350])
            time.sleep(.45)
        state[cid]={"collection_id":cid,"name":collection.get("name",""),"from":collection.get("from",""),"to":collection.get("to",""),"status":"ERROR" if collection_errors else "SCANNED","hashes_found":len(found[cid]),"last_scanned":now,"last_error":" | ".join(collection_errors)[:800]}
        if collection_errors:failed+=1;errors.append({"collection":cid,"errors":collection_errors})
        else:scanned+=1
    all_hashes=set().union(*found.values()) if found else set();rows=[]
    for ah in sorted(all_hashes):
        prev=existing.get(ah,{});collections=sorted(cid for cid,values in found.items() if ah in values)
        rows.append({"registry_id":f"AUDREG-{ah}","audit_hash":ah,"audit_url":official_url(ah),"status":prev.get("status","DISCOVERED"),"attempts":int(prev.get("attempts") or 0),"first_seen":prev.get("first_seen") or now,"last_seen":now,"last_error":prev.get("last_error",""),"document_id":prev.get("document_id",""),"document_date":prev.get("document_date",""),"document_number":prev.get("document_number",""),"discovery_channel":prev.get("discovery_channel") or "COMMON_CRAWL_INDEX","discovery_source":prev.get("discovery_source") or ",".join(collections[:12]),"discovery_collections":sorted(set((prev.get("discovery_collections") or [])+collections))})
    inserted,updated=upsert_jsonl("audit_registry",rows,"registry_id");replace_jsonl("cc_collections",state.values(),"collection_id");remaining=sum(x.get("status")!="SCANNED" for x in state.values())+sum(x.get("id") not in state for x in indexes)
    return {"run_at":now,"min_year":min_year,"max_year":max_year,"collections_available":len(indexes),"collections_attempted":len(candidates),"collections_scanned_ok":scanned,"collections_failed":failed,"collections_remaining":remaining,"queries":queries,"pages_read":pages_read,"unique_hashes_found_this_run":len(all_hashes),"new_registry_items":inserted,"updated_registry_items":updated,"errors":errors[:50],"top_collections":sorted(({"collection":cid,"unique_hashes":len(values)} for cid,values in found.items()),key=lambda x:x["unique_hashes"],reverse=True)[:30],"validation_rule":"Common Crawl solo descubre docIdcm; cada URL se acepta como documento únicamente si la ficha oficial CGR responde y es parseable."}

def main()->None:
    p=argparse.ArgumentParser(description="Descubrimiento historico de docIdcm CGR mediante Common Crawl");p.add_argument("--min-year",type=int,default=2013);p.add_argument("--max-year",type=int,default=datetime.now().year);p.add_argument("--max-pages-per-query",type=int,default=20);p.add_argument("--page-size",type=int,default=5);p.add_argument("--max-collections",type=int,default=0);p.add_argument("--rescan",action="store_true");a=p.parse_args();print(json.dumps(discover(a.min_year,a.max_year,a.max_pages_per_query,a.page_size,a.max_collections,a.rescan),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
