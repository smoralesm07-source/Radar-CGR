from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from .collectors import HTTPClient, collect_news_articles, collect_page
from .config import load_seed_audits, load_sources
from .dashboard import build_dashboard
from .extract import parse_audit_detail
from .intelligence import rebuild_intelligence
from .models import Event, stable_id
from .resolution import clean_entity_resolution
from .storage import export_parquet, upsert_jsonl, write_snapshot


def iso_now()->str: return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run(source_filter:str|None=None,skip_network:bool=False)->dict:
    started=iso_now(); client=HTTPClient(); totals={"new_documents":0,"updated_documents":0,"new_findings":0,"errors":0}; discovered_audits=set(load_seed_audits()); source_run_rows=[]
    if not skip_network:
        for source in load_sources():
            if source_filter and source.id!=source_filter: continue
            page,html=collect_page(client,source); run_date=started[:10]; write_snapshot(source.id,run_date,page.to_dict()); status="OK" if not page.error else "ERROR"
            if page.error: totals["errors"]+=1
            discovered_audits.update(page.audit_links); news_count=0
            if source.collector=="news_index" and html:
                articles=collect_news_articles(client,source,html,page.source_url); news_count=len(articles)
                for art in articles:
                    discovered_audits.update(art.get("audit_links",[]))
                    if art.get("title") and not art.get("error"):
                        ev=Event(event_id=stable_id("EVT","CGR_NEWS",art.get("url"),art.get("date"),art.get("title")),document_id="",event_type="CGR_NEWS",event_date=art.get("date",""),title=art.get("title",""),source_url=art.get("url",""),source_module="NOTICIAS"); upsert_jsonl("events",[ev.to_dict()],"event_id")
                write_snapshot(source.id+"_articles",run_date,{"articles":articles})
            source_run_rows.append({"run_id":stable_id("RUN",source.id,started),"source_id":source.id,"source_name":source.name,"source_url":page.source_url,"started_at":started,"finished_at":iso_now(),"status":status,"http_status":page.status_code,"content_hash":page.content_hash,"links_found":len(page.links),"audit_links_found":len(page.audit_links),"news_articles_checked":news_count,"error":page.error})
        for url in sorted(discovered_audits):
            try:
                html=client.get(url).text; parsed=parse_audit_detail(html,url); i,u=upsert_jsonl("documents",[parsed.document.to_dict()],"document_id"); totals["new_documents"]+=i; totals["updated_documents"]+=u; upsert_jsonl("events",[parsed.event.to_dict()],"event_id"); i,_=upsert_jsonl("findings",[x.to_dict() for x in parsed.findings],"finding_id"); totals["new_findings"]+=i; upsert_jsonl("evidence",[x.to_dict() for x in parsed.evidence],"evidence_id"); upsert_jsonl("entities",[x.to_dict() for x in parsed.entities],"entity_id")
            except Exception as exc:
                totals["errors"]+=1; source_run_rows.append({"run_id":stable_id("RUN","audit_detail",url,started),"source_id":"audit_detail","source_name":"Ficha de auditoria CGR","source_url":url,"started_at":started,"finished_at":iso_now(),"status":"ERROR","error":f"{type(exc).__name__}: {exc}"})
            finally:
                time.sleep(0.2)
    if source_run_rows: upsert_jsonl("source_runs",source_run_rows,"run_id")
    intelligence=rebuild_intelligence()
    resolution=clean_entity_resolution()
    parquet=export_parquet(); dashboard=build_dashboard(); return {"started_at":started,"totals":totals,"intelligence":intelligence,"resolution":resolution,"parquet":parquet,"dashboard_kpis":dashboard["kpis"]}


def main()->None:
    parser=argparse.ArgumentParser(description="Radar CGR - pipeline OSINT"); parser.add_argument("--source"); parser.add_argument("--skip-network",action="store_true"); args=parser.parse_args(); result=run(args.source,args.skip_network); import json; print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
