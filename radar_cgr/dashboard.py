from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from .config import DOCS_DIR
from .storage import read_jsonl, table_path


def _fmt_amount(value):
    if value in (None,""): return None
    try: return int(value)
    except Exception: return None


def build_dashboard()->dict:
    documents=read_jsonl(table_path("documents")); events=read_jsonl(table_path("events")); findings=read_jsonl(table_path("findings")); entities=read_jsonl(table_path("entities")); source_runs=read_jsonl(table_path("source_runs"))
    findings_sorted=sorted(findings,key=lambda x:(x.get("aml_score",0),x.get("finding_id","")),reverse=True); latest_events=sorted(events,key=lambda x:(x.get("event_date",""),x.get("retrieved_at","")),reverse=True)
    high=[x for x in findings if x.get("aml_relevance")=="HIGH"]; total_amount=sum(_fmt_amount(x.get("amount_clp")) or 0 for x in findings); by_family=Counter(x.get("risk_family") or "SIN_CLASIFICAR" for x in findings); by_region=Counter(x.get("region") or "SIN_REGION" for x in events)
    payload={"generated_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"version":"0.1.0","disclaimer":"Las señales son antecedentes OSINT para priorización analítica. Una observación CGR no constituye por sí sola evidencia de LA/FT ni atribución de responsabilidad penal.","kpis":{"documents":len(documents),"events":len(events),"findings":len(findings),"high_relevance":len(high),"entities":len(entities),"amounts_indexed_clp":total_amount},"risk_families":[{"name":k,"count":v} for k,v in by_family.most_common()],"regions":[{"name":k,"count":v} for k,v in by_region.most_common()],"priority_findings":findings_sorted[:80],"latest_events":latest_events[:80],"source_health":sorted(source_runs,key=lambda x:x.get("finished_at",""),reverse=True)[:30]}
    out=DOCS_DIR/"data"/"dashboard.json"; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); return payload
