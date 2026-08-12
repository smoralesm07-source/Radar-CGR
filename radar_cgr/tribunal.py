from __future__ import annotations
import re
from bs4 import BeautifulSoup
from .models import stable_id
from .storage import read_jsonl,upsert_jsonl,replace_jsonl,table_path
from .temporality import normalize_document_date
from .utils import normalize_name,normalize_ws
STOP={"CONTRALORIA","REGIONAL","DE","DEL","LA","LOS","LAS","DIVISION","Y","GENERAL","REPUBLICA"}
def _tokens(v): return {x for x in normalize_name(v or "").split() if len(x)>=3 and x not in STOP}
def _similarity(a,b):
    x,y=_tokens(a),_tokens(b)
    if not x or not y:return 0.0
    return len(x&y)/max(1,min(len(x),len(y)))
def _iso_dmy(v): return normalize_document_date((v or "").replace("/","-"))
def extract_tribunal_cases(html,source_url,observed_at):
    soup=BeautifulSoup(html or "","lxml");rows=[];seen=set()
    for tr in soup.find_all("tr"):
        cells=[normalize_ws(td.get_text(" ",strip=True)) for td in tr.find_all(["td","th"])]
        cells=[x for x in cells if x]
        if not cells:continue
        date_idx=next((i for i,x in enumerate(cells) if re.fullmatch(r"\d{2}/\d{2}/\d{4}",x)),None)
        if date_idx is None:continue
        role_idx=next((i for i,x in enumerate(cells[date_idx+1:],date_idx+1) if re.fullmatch(r"\d+\s*/\s*\d{4}",x)),None)
        if role_idx is None:continue
        res_indices=[i for i,x in enumerate(cells[role_idx+1:],role_idx+1) if re.search(r"RES\.?\s*N?[º°]?\s*\d+",x,re.I)]
        if not res_indices:continue
        last_res=res_indices[-1];date_raw=cells[date_idx];role=re.sub(r"\s+","",cells[role_idx]);resolution=cells[res_indices[0]]
        tail=[]
        for x in cells[last_res+1:]:
            if x not in tail:tail.append(x)
        claimant=tail[0] if tail else "";defendants=" | ".join(tail[1:]) if len(tail)>1 else ""
        cid=stable_id("TDC",date_raw,role,resolution,claimant)
        if cid in seen:continue
        seen.add(cid);rows.append({"tribunal_case_event_id":cid,"state_date":_iso_dmy(date_raw),"state_date_raw":date_raw,"role":role,"resolution":resolution,"claimant":claimant,"defendants_raw":defendants,"source_url":source_url,"first_seen":observed_at,"last_seen":observed_at,"status":"STATE_DAILY_PUBLISHED","candidate_reparo_ids":[],"match_status":"UNLINKED","match_confidence":0.0})
    return rows
def merge_tribunal_cases(candidates):
    existing={x.get("tribunal_case_event_id"):x for x in read_jsonl(table_path("tribunal_cases")) if x.get("tribunal_case_event_id")};rows=[]
    for row in candidates:
        item=dict(row);old=existing.get(item.get("tribunal_case_event_id"),{})
        if old.get("first_seen"):item["first_seen"]=old["first_seen"]
        if old.get("candidate_reparo_ids"):item["candidate_reparo_ids"]=old["candidate_reparo_ids"];item["match_status"]=old.get("match_status","UNLINKED");item["match_confidence"]=old.get("match_confidence",0.0)
        rows.append(item)
    return upsert_jsonl("tribunal_cases",rows,"tribunal_case_event_id") if rows else (0,0)
def refresh_tribunal_reparo_candidates():
    cases=read_jsonl(table_path("tribunal_cases"));enforcement=[x for x in read_jsonl(table_path("enforcement_events")) if x.get("enforcement_type")=="REPARO"];docs={x.get("document_id"):x for x in read_jsonl(table_path("documents")) if x.get("document_id")};rows=[];linked=0
    for case in cases:
        item=dict(case);candidates=[];best=0.0
        for ev in enforcement:
            doc=docs.get(ev.get("document_id"),{});unit=doc.get("unit_cgr","");score=_similarity(case.get("claimant",""),unit)
            if score<.55:continue
            action=ev.get("action_date","");state=case.get("state_date","")
            if action and state and action>state:continue
            candidates.append(ev.get("enforcement_event_id"));best=max(best,score)
        item["candidate_reparo_ids"]=sorted(set(x for x in candidates if x));item["match_confidence"]=round(best,2);item["match_status"]="CANDIDATE_REPARO_LINK" if candidates else "UNLINKED";linked+=bool(candidates);rows.append(item)
    replace_jsonl("tribunal_cases",rows,"tribunal_case_event_id");return {"tribunal_cases":len(rows),"candidate_links":linked}
