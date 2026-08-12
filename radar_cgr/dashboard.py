from __future__ import annotations
import json
from collections import Counter
from .config import DOCS_DIR
from .dashboard_base import build_dashboard as build_base_dashboard
from .storage import read_jsonl,table_path

def _min_date(a,b):return b if not a else a if not b else min(a,b)
def _max_date(a,b):return b if not a else a if not b else max(a,b)
def build_dashboard():
    payload=build_base_dashboard();findings=read_jsonl(table_path("findings"));enrichment=read_jsonl(table_path("finding_enrichment"));watches=read_jsonl(table_path("watch_items"));enforcement=read_jsonl(table_path("enforcement_events"));tribunal=read_jsonl(table_path("tribunal_cases"));fau_catalog=read_jsonl(table_path("fau_catalog"));fau_matches=read_jsonl(table_path("fau_matches"));f_by={x.get("finding_id"):x for x in findings};e_by={x.get("finding_id"):x for x in enrichment};org_by={x.get("organization_id"):x for x in payload.get("organizations",[])};prv_by={x.get("provider_id"):x for x in payload.get("providers",[])}
    year_counts=Counter();precision=Counter();known=0;org_dates={};prv_dates={}
    for f in findings:
        anchor=f.get("occurrence_date_anchor","");precision[f.get("occurrence_date_precision","UNKNOWN")]+=1
        if anchor:known+=1;year_counts[anchor[:4]]+=1
    for e in enrichment:
        start=e.get("occurrence_date_from","");end=e.get("occurrence_date_to","");oid=e.get("organization_id","")
        if oid:
            cur=org_dates.get(oid,["",""]);cur[0]=_min_date(cur[0],start);cur[1]=_max_date(cur[1],end);org_dates[oid]=cur
        for pid in e.get("provider_ids") or []:
            cur=prv_dates.get(pid,["",""]);cur[0]=_min_date(cur[0],start);cur[1]=_max_date(cur[1],end);prv_dates[pid]=cur
    for oid,x in org_by.items():x["first_occurrence"],x["last_occurrence"]=org_dates.get(oid,["",""])
    for pid,x in prv_by.items():x["first_occurrence"],x["last_occurrence"]=prv_dates.get(pid,["",""])
    for p in payload.get("penal_cases",[]):
        f=f_by.get(p.get("finding_id"),{});p["occurrence_date_from"]=f.get("occurrence_date_from","");p["occurrence_date_to"]=f.get("occurrence_date_to","");p["occurrence_date_anchor"]=f.get("occurrence_date_anchor","");p["occurrence_date_precision"]=f.get("occurrence_date_precision","UNKNOWN")
    enforcement_out=[]
    for x in sorted(enforcement,key=lambda y:(y.get("action_date","") or "",y.get("enforcement_event_id","")),reverse=True):
        e=e_by.get(x.get("finding_id"),{});f=f_by.get(x.get("finding_id"),{});enforcement_out.append({**x,"organization_name":e.get("organization_name",""),"region":e.get("region",""),"finding_text":f.get("description","")})
    fau_out=[]
    for x in sorted(fau_matches,key=lambda y:(y.get("score",0),y.get("fau_match_id","")),reverse=True):
        e=e_by.get(x.get("finding_id"),{});f=f_by.get(x.get("finding_id"),{});fau_out.append({**x,"organization_name":e.get("organization_name",""),"region":e.get("region",""),"finding_text":f.get("description",""),"occurrence_date_from":f.get("occurrence_date_from",""),"occurrence_date_to":f.get("occurrence_date_to",""),"occurrence_date_anchor":f.get("occurrence_date_anchor","")})
    payload["version"]="0.3.0";payload["disclaimer"]="Las señales son antecedentes OSINT para priorización analítica. Una observación CGR, una coincidencia FAU o una hipótesis de relevancia penal no acredita LA/FT, dolo ni responsabilidad penal individual. La fecha de ocurrencia distingue fecha exacta, intervalo y período auditado heredado; la fecha de publicación del informe no se usa como sustituto."
    payload["watch_items"]=sorted(watches,key=lambda x:(x.get("status")=="OPEN",x.get("last_seen","") or ""),reverse=True)[:300];payload["enforcement_events"]=enforcement_out[:400];payload["tribunal_cases"]=sorted(tribunal,key=lambda x:(x.get("state_date","") or "",x.get("role","") or ""),reverse=True)[:300];payload["fau_catalog"]=fau_catalog;payload["fau_matches"]=fau_out[:400];payload["temporal_summary"]={"known":known,"unknown":len(findings)-known,"coverage_pct":round(100*known/max(1,len(findings)),1),"by_year":[{"year":y,"count":c} for y,c in sorted(year_counts.items(),reverse=True)],"by_precision":[{"name":k,"count":v} for k,v in precision.most_common()]}
    k=payload.setdefault("kpis",{});k["open_watch"]=sum(x.get("status")=="OPEN" for x in watches);k["enforcement_events"]=len(enforcement);k["tribunal_cases"]=len(tribunal);k["fau_matches"]=len(fau_matches);k["temporal_known"]=known;k["temporal_coverage_pct"]=round(100*known/max(1,len(findings)),1);k["criminal_referrals"]=sum(x.get("enforcement_type")=="CRIMINAL_REFERRAL" for x in enforcement);k["reparos"]=sum(x.get("enforcement_type")=="REPARO" for x in enforcement)
    payload["question_catalog"]=[{"id":"temporal","label":"¿Cuándo ocurrieron los hallazgos?"},{"id":"watch","label":"¿Qué fiscalizaciones siguen en curso?"},{"id":"enforcement","label":"¿Qué hallazgos escalaron a reparo, MP, CDE o disciplina?"},{"id":"fau","label":"¿Qué hallazgos coinciden con tipologías FAU?"},{"id":"providers","label":"¿Qué casos involucran proveedores?"},{"id":"organizations","label":"¿Qué organismos concentran irregularidades?"}]
    out=DOCS_DIR/"data"/"dashboard.json";out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");return payload
