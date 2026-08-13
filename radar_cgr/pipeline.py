from __future__ import annotations
import argparse,time
from datetime import datetime,timezone
from .cic import extract_cic_articles,persist_cic
from .collectors import HTTPClient,collect_news_articles,collect_page
from .config import load_seed_audits,load_sources
from .dashboard import build_dashboard
from .early_warning import extract_watch_candidates,merge_watch_candidates,refresh_watch_matches
from .enforcement import rebuild_enforcement_events
from .extract import parse_audit_detail
from .fau import rebuild_fau_matches
from .intelligence import rebuild_intelligence
from .interop import materialize_entity_hub
from .models import Event,stable_id
from .quality import apply_entity_quality_gate
from .resolution import clean_entity_resolution
from .semaforo import parse_semaforo,persist_semaforo
from .storage import export_parquet,upsert_jsonl,write_snapshot
from .temporality import backfill_finding_temporality,propagate_temporality_to_enrichment
from .tribunal import extract_tribunal_cases,merge_tribunal_cases,refresh_tribunal_reparo_candidates

def iso_now():return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def run(source_filter=None,skip_network=False):
    started=iso_now();client=HTTPClient();totals={"new_documents":0,"updated_documents":0,"new_findings":0,"errors":0};discovered=set(load_seed_audits());runs=[];watch_candidates=[];tribunal_candidates=[];semaforo_result={};cic_result={}
    if not skip_network:
        for source in load_sources():
            if source_filter and source.id!=source_filter:continue
            page,html=collect_page(client,source);write_snapshot(source.id,started[:10],page.to_dict())
            if page.error:totals["errors"]+=1
            discovered.update(page.audit_links);news_count=0
            if html:
                watch_candidates.extend(extract_watch_candidates(source.id,page.source_url or source.url,html,started))
                if source.id=="cgr_tribunal_cuentas":tribunal_candidates.extend(extract_tribunal_cases(html,page.source_url or source.url,started))
                if source.id=="cgr_semaforo":
                    semaforo_rows=parse_semaforo(html,started,page.source_url or source.url);semaforo_result=persist_semaforo(semaforo_rows)
                    if semaforo_rows and not semaforo_result.get("complete_expected_345"):totals["errors"]+=1
            if source.collector=="news_index" and html:
                articles=collect_news_articles(client,source,html,page.source_url);news_count=len(articles);cic_result=persist_cic(extract_cic_articles(articles))
                for art in articles:
                    discovered.update(art.get("audit_links",[]))
                    if art.get("title") and not art.get("error"):
                        ev=Event(stable_id("EVT","CGR_NEWS",art.get("url"),art.get("date"),art.get("title")),"","CGR_NEWS",art.get("date",""),art.get("title",""),source_url=art.get("url",""),source_module="NOTICIAS");upsert_jsonl("events",[ev.to_dict()],"event_id")
                write_snapshot(source.id+"_articles",started[:10],{"articles":articles})
            runs.append({"run_id":stable_id("RUN",source.id,started),"source_id":source.id,"source_name":source.name,"source_url":page.source_url,"started_at":started,"finished_at":iso_now(),"status":"ERROR" if page.error else "OK","http_status":page.status_code,"content_hash":page.content_hash,"links_found":len(page.links),"audit_links_found":len(page.audit_links),"news_articles_checked":news_count,"watch_candidates":sum(x.get("source_id")==source.id for x in watch_candidates),"tribunal_cases":len(tribunal_candidates) if source.id=="cgr_tribunal_cuentas" else 0,"municipalities":semaforo_result.get("municipalities",0) if source.id=="cgr_semaforo" else 0,"cic_records":cic_result.get("rows",0) if source.id=="cgr_noticias" else 0,"error":page.error})
        for url in sorted(discovered):
            try:
                parsed=parse_audit_detail(client.get(url).text,url);i,u=upsert_jsonl("documents",[parsed.document.to_dict()],"document_id");totals["new_documents"]+=i;totals["updated_documents"]+=u;upsert_jsonl("events",[parsed.event.to_dict()],"event_id");i,_=upsert_jsonl("findings",[x.to_dict() for x in parsed.findings],"finding_id");totals["new_findings"]+=i;upsert_jsonl("evidence",[x.to_dict() for x in parsed.evidence],"evidence_id");upsert_jsonl("entities",[x.to_dict() for x in parsed.entities],"entity_id")
            except Exception as exc:totals["errors"]+=1;runs.append({"run_id":stable_id("RUN","audit_detail",url,started),"source_id":"audit_detail","source_name":"Ficha de auditoria CGR","source_url":url,"started_at":started,"finished_at":iso_now(),"status":"ERROR","error":f"{type(exc).__name__}: {exc}"})
            finally:time.sleep(.2)
    if runs:upsert_jsonl("source_runs",runs,"run_id")
    if watch_candidates:merge_watch_candidates(watch_candidates)
    if tribunal_candidates:merge_tribunal_cases(tribunal_candidates)
    temporality=backfill_finding_temporality();intelligence=rebuild_intelligence();resolution=clean_entity_resolution();quality=apply_entity_quality_gate();interop=materialize_entity_hub();propagate_temporality_to_enrichment();watch=refresh_watch_matches();enforcement=rebuild_enforcement_events();tribunal=refresh_tribunal_reparo_candidates();fau=rebuild_fau_matches();parquet=export_parquet();dashboard=build_dashboard()
    return {"started_at":started,"totals":totals,"semaforo":semaforo_result,"cic":cic_result,"temporality":temporality,"intelligence":intelligence,"resolution":resolution,"quality":quality,"interop_entity_hub":interop,"watch":watch,"enforcement":enforcement,"tribunal":tribunal,"fau":fau,"parquet":parquet,"dashboard_kpis":dashboard["kpis"]}
def main():
    p=argparse.ArgumentParser(description="Radar CGR - pipeline OSINT");p.add_argument("--source");p.add_argument("--skip-network",action="store_true");a=p.parse_args();import json;print(json.dumps(run(a.source,a.skip_network),ensure_ascii=False,indent=2))
if __name__=="__main__":main()