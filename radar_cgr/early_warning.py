from __future__ import annotations
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .models import WatchItem,stable_id
from .storage import read_jsonl,upsert_jsonl,table_path
from .utils import normalize_name,normalize_ws,official_cgr_url
WATCH_SOURCE_TYPES={"cgr_fiscalizaciones":"FISCALIZATION"}
GENERIC_TEXT={normalize_name(x) for x in ["Fiscalizaciones en curso","Contribuir a una Auditoría en Curso","Informes de Auditorías","Sugerir una fiscalización","Auditorías a las transferencias relacionadas con Fundaciones","Función de Fiscalización","Ámbito de la Función"]}
EXCLUDED_URLS=("contribuir-a-una-auditoria-en-curso","informes-de-auditor","sugerir-una-fiscalizacion","auditorias-a-las-transferencias","ambito-de-la-funcion")
SIGNAL_RE=re.compile(r"fiscaliz|auditor|investigaci[oó]n|inspecci[oó]n|revisi[oó]n",re.I)
STOP={"DE","DEL","LA","LAS","LOS","EL","Y","EN","A","AL","POR","PARA","SOBRE","CON","UN","UNA","N","FINAL","INFORME","CGR","2026","2025","2024"}
def _elements(html):
    soup=BeautifulSoup(html or "","lxml");seen=set()
    for node in soup.find_all(["article","li","tr","h2","h3","h4","p","a"]):
        text=normalize_ws(node.get_text(" ",strip=True))
        if not (18<=len(text)<=420):continue
        key=normalize_name(text)
        if key in seen:continue
        seen.add(key);link=node if getattr(node,"name","")=="a" and node.get("href") else node.find("a",href=True);yield text,(link.get("href") if link else "")
def extract_watch_candidates(source_id,source_url,html,observed_at):
    watch_type=WATCH_SOURCE_TYPES.get(source_id)
    if not watch_type or not html:return []
    rows=[];seen=set()
    for text,href in _elements(html):
        norm=normalize_name(text)
        if norm in GENERIC_TEXT or not SIGNAL_RE.search(text):continue
        url=urljoin(source_url,href) if href else source_url
        if href and not official_cgr_url(url):continue
        if any(x in url for x in EXCLUDED_URLS):continue
        tokens={x for x in norm.split() if len(x)>=4 and x not in STOP and not x.isdigit()}
        if len(tokens)<3:continue
        identity=url if href and url!=source_url else norm;wid=stable_id("WAT",source_id,identity)
        if wid in seen:continue
        seen.add(wid);rows.append(WatchItem(wid,source_id,watch_type,text[:350],url,first_seen=observed_at,last_seen=observed_at).to_dict())
        if len(rows)>=80:break
    return rows
def merge_watch_candidates(candidates):
    existing={x.get("watch_id"):x for x in read_jsonl(table_path("watch_items")) if x.get("watch_id")};rows=[]
    for row in candidates:
        item=dict(row);old=existing.get(item.get("watch_id"),{})
        if old.get("first_seen"):item["first_seen"]=old["first_seen"]
        if old.get("matched_document_id"):item.update({k:old.get(k) for k in ("matched_document_id","match_confidence","stage","status")})
        rows.append(item)
    return upsert_jsonl("watch_items",rows,"watch_id") if rows else (0,0)
def _tokens(v):return {x for x in normalize_name(v or "").split() if len(x)>=4 and x not in STOP and not x.isdigit()}
def _similarity(a,b):
    x,y=_tokens(a),_tokens(b)
    if not x or not y:return 0.0
    inter=len(x&y)
    if inter<2:return 0.0
    return inter/max(1,min(len(x),len(y)))
def refresh_watch_matches():
    watches=read_jsonl(table_path("watch_items"));docs=read_jsonl(table_path("documents"));matched=0;rows=[]
    for watch in watches:
        item=dict(watch);best_doc="";best=0.0
        for doc in docs:
            score=_similarity(item.get("title",""),doc.get("title",""))
            if score>best:best=score;best_doc=doc.get("document_id","")
        if best_doc and best>=.62:item["matched_document_id"]=best_doc;item["match_confidence"]=round(best,2);item["stage"]="REPORT_PUBLISHED";item["status"]="CLOSED_MATCHED";matched+=1
        else:item["stage"]="WATCH";item["status"]="OPEN";item["matched_document_id"]="";item["match_confidence"]=0.0
        rows.append(item)
    if rows:upsert_jsonl("watch_items",rows,"watch_id")
    return {"watch_items":len(rows),"matched_reports":matched,"open_watch":sum(x.get("status")=="OPEN" for x in rows)}
