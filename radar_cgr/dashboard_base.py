from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .config import DOCS_DIR
from .storage import read_jsonl, table_path


def _amount(value):
    try: return int(value or 0)
    except Exception: return 0


def _top_counter(counter:Counter, n=6):
    return [{"name":k,"count":v} for k,v in counter.most_common(n)]


def build_dashboard()->dict:
    documents=read_jsonl(table_path("documents")); events=read_jsonl(table_path("events")); findings=read_jsonl(table_path("findings")); source_runs=read_jsonl(table_path("source_runs"))
    organizations=read_jsonl(table_path("organizations")); providers=read_jsonl(table_path("providers")); persons=read_jsonl(table_path("persons")); enrichment=read_jsonl(table_path("finding_enrichment")); hypotheses=read_jsonl(table_path("penal_hypotheses"))
    org_by_id={x["organization_id"]:x for x in organizations if x.get("organization_id")}; prv_by_id={x["provider_id"]:x for x in providers if x.get("provider_id")}; finding_by_id={x["finding_id"]:x for x in findings if x.get("finding_id")}; hyp_by_f=defaultdict(list)
    for h in hypotheses: hyp_by_f[h.get("finding_id","")].append(h)

    org_stats=defaultdict(lambda:{"documents":set(),"findings":0,"providers":set(),"amount":0,"cgr_max":0,"penal_max":0,"aml_max":0,"penal_high":0,"disciplinary":0,"reparos":0,"criminal_referrals":0,"cde_referrals":0,"irregularities":Counter(),"sources":set()})
    provider_stats=defaultdict(lambda:{"documents":set(),"findings":0,"organizations":set(),"regions":set(),"amount":0,"cgr_max":0,"penal_max":0,"penal_high":0,"irregularities":Counter(),"sources":set()})
    region_stats=defaultdict(lambda:{"organizations":set(),"providers":set(),"documents":set(),"findings":0,"penal_high":0,"criminal_referrals":0,"reparos":0,"amount":0,"irregularities":Counter()})

    enriched_findings=[]
    for e in enrichment:
        f=finding_by_id.get(e.get("finding_id"),{}); oid=e.get("organization_id",""); region=e.get("region") or "Sin región"
        merged=dict(f); merged.update({k:v for k,v in e.items() if k not in {"finding_id","document_id","event_id"}}); merged["hypothesis_details"]=sorted(hyp_by_f.get(e.get("finding_id",""),[]),key=lambda x:x.get("score",0),reverse=True)
        merged["priority_score"]=max(int(e.get("cgr_score") or 0),int(e.get("penal_score") or 0),int(e.get("aml_score") or 0)); enriched_findings.append(merged)
        if oid:
            s=org_stats[oid]; s["documents"].add(e.get("document_id")); s["findings"]+=1; s["providers"].update(e.get("provider_ids") or []); s["amount"]+=_amount(e.get("amount_clp")); s["cgr_max"]=max(s["cgr_max"],int(e.get("cgr_score") or 0)); s["penal_max"]=max(s["penal_max"],int(e.get("penal_score") or 0)); s["aml_max"]=max(s["aml_max"],int(e.get("aml_score") or 0)); s["penal_high"]+=e.get("penal_relevance")=="HIGH"; s["disciplinary"]+=bool(e.get("disciplinary")); s["reparos"]+=bool(e.get("reparo")); s["criminal_referrals"]+=bool(e.get("criminal_referral")); s["cde_referrals"]+=bool(e.get("cde_referral")); s["irregularities"].update(e.get("irregularity_labels") or []); s["sources"].add(e.get("source_url",""))
        for pid in e.get("provider_ids") or []:
            p=provider_stats[pid]; p["documents"].add(e.get("document_id")); p["findings"]+=1; p["organizations"].add(oid); p["regions"].add(region); p["amount"]+=_amount(e.get("amount_clp")); p["cgr_max"]=max(p["cgr_max"],int(e.get("cgr_score") or 0)); p["penal_max"]=max(p["penal_max"],int(e.get("penal_score") or 0)); p["penal_high"]+=e.get("penal_relevance")=="HIGH"; p["irregularities"].update(e.get("irregularity_labels") or []); p["sources"].add(e.get("source_url",""))
        r=region_stats[region];
        if oid: r["organizations"].add(oid)
        r["providers"].update(e.get("provider_ids") or []); r["documents"].add(e.get("document_id")); r["findings"]+=1; r["penal_high"]+=e.get("penal_relevance")=="HIGH"; r["criminal_referrals"]+=bool(e.get("criminal_referral")); r["reparos"]+=bool(e.get("reparo")); r["amount"]+=_amount(e.get("amount_clp")); r["irregularities"].update(e.get("irregularity_labels") or [])

    org_profiles=[]
    for oid,s in org_stats.items():
        org=org_by_id.get(oid,{"organization_id":oid,"name":"Organismo sin normalizar","region":""})
        recurrence=min(100,s["findings"]*3+len(s["documents"])*6+s["penal_high"]*6+s["criminal_referrals"]*12+s["reparos"]*8+len(s["providers"])*2)
        priority=min(100,round(.55*s["cgr_max"]+.25*s["penal_max"]+.20*recurrence))
        org_profiles.append({**org,"documents":len(s["documents"]),"findings":s["findings"],"providers_count":len(s["providers"]),"provider_ids":sorted(s["providers"]),"providers":[prv_by_id.get(x,{}).get("name",x) for x in sorted(s["providers"])],"amounts_indexed_clp":s["amount"],"cgr_risk":s["cgr_max"],"penal_relevance_score":s["penal_max"],"aml_relevance_score":s["aml_max"],"recurrence_score":recurrence,"priority_score":priority,"disciplinary":s["disciplinary"],"reparos":s["reparos"],"criminal_referrals":s["criminal_referrals"],"cde_referrals":s["cde_referrals"],"penal_high_findings":s["penal_high"],"top_irregularities":_top_counter(s["irregularities"]),"source_urls":[x for x in sorted(s["sources"]) if x][:10]})
    org_profiles.sort(key=lambda x:(x["priority_score"],x["findings"]),reverse=True)

    provider_profiles=[]
    for pid,s in provider_stats.items():
        p=prv_by_id.get(pid,{"provider_id":pid,"name":"Proveedor sin normalizar"}); exposure=min(100,len(s["organizations"])*15+len(s["documents"])*8+s["findings"]*4+s["penal_high"]*8)
        provider_profiles.append({**p,"documents":len(s["documents"]),"findings":s["findings"],"organizations_count":len([x for x in s["organizations"] if x]),"organizations":[org_by_id.get(x,{}).get("name",x) for x in sorted(s["organizations"]) if x],"regions":sorted(s["regions"]),"associated_finding_amounts_clp":s["amount"],"cgr_context_max":s["cgr_max"],"penal_context_max":s["penal_max"],"penal_high_findings":s["penal_high"],"exposure_recurrence_score":exposure,"top_irregularities":_top_counter(s["irregularities"]),"source_urls":[x for x in sorted(s["sources"]) if x][:10]})
    provider_profiles.sort(key=lambda x:(x["exposure_recurrence_score"],x["organizations_count"],x["findings"]),reverse=True)

    regions=[]
    for name,s in region_stats.items():
        regions.append({"name":name,"organizations":len(s["organizations"]),"providers":len(s["providers"]),"documents":len(s["documents"]),"findings":s["findings"],"penal_high":s["penal_high"],"criminal_referrals":s["criminal_referrals"],"reparos":s["reparos"],"amounts_indexed_clp":s["amount"],"top_irregularities":_top_counter(s["irregularities"],4)})
    regions.sort(key=lambda x:(x["penal_high"],x["findings"]),reverse=True)

    penal_cases=[]
    for h in sorted(hypotheses,key=lambda x:x.get("score",0),reverse=True):
        f=finding_by_id.get(h.get("finding_id"),{}); e=next((x for x in enrichment if x.get("finding_id")==h.get("finding_id")),{})
        penal_cases.append({**h,"organization_name":e.get("organization_name",""),"region":e.get("region",""),"provider_names":e.get("provider_names") or [],"amount_clp":f.get("amount_clp"),"finding_text":f.get("description",""),"enforcement":f.get("enforcement") or []})

    high_aml=sum(1 for f in findings if f.get("aml_relevance")=="HIGH"); high_penal=sum(1 for e in enrichment if e.get("penal_relevance")=="HIGH"); total_amount=sum(_amount(f.get("amount_clp")) for f in findings)
    kpis={"documents":len(documents),"events":len(events),"findings":len(findings),"organizations":len(organizations),"providers":len(providers),"persons":len(persons),"aml_high":high_aml,"penal_high":high_penal,"criminal_referrals":sum(bool(e.get("criminal_referral")) for e in enrichment),"reparos":sum(bool(e.get("reparo")) for e in enrichment),"amounts_indexed_clp":total_amount}

    payload={"generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"version":"0.2.0","disclaimer":"Las señales son antecedentes OSINT para priorización analítica. Una observación CGR o una hipótesis de relevancia penal no acredita LA/FT, dolo ni responsabilidad penal individual. Los montos indexados corresponden a valores mencionados en hallazgos y no equivalen necesariamente a perjuicio fiscal.","kpis":kpis,"organizations":org_profiles[:250],"providers":provider_profiles[:250],"regions":regions,"penal_cases":penal_cases[:250],"priority_findings":sorted(enriched_findings,key=lambda x:(x.get("priority_score",0),x.get("finding_id","")),reverse=True)[:250],"source_health":sorted(source_runs,key=lambda x:x.get("finished_at",""),reverse=True)[:40],"question_catalog":[{"id":"organizations","label":"¿Qué organismos públicos están involucrados en irregularidades?"},{"id":"regions","label":"¿En qué regiones se concentran los hallazgos?"},{"id":"providers","label":"¿Qué casos involucran proveedores?"},{"id":"penal","label":"¿Qué hallazgos tienen posible relevancia penal?"},{"id":"referrals","label":"¿Qué casos fueron remitidos al Ministerio Público?"}]}
    out=DOCS_DIR/"data"/"dashboard.json"; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); return payload
