from __future__ import annotations

from .models import EnforcementEvent, stable_id
from .storage import read_jsonl, replace_jsonl, table_path
from .temporality import normalize_document_date

STAGES={
    "DISCIPLINARY":"ORDERED",
    "REPARO":"ANNOUNCED_OR_FILED",
    "CRIMINAL_REFERRAL":"REFERRED",
    "CDE_REFERRAL":"REFERRED",
}


def rebuild_enforcement_events()->dict:
    findings=read_jsonl(table_path("findings")); documents={x.get("document_id"):x for x in read_jsonl(table_path("documents")) if x.get("document_id")}; enrichment={x.get("finding_id"):x for x in read_jsonl(table_path("finding_enrichment")) if x.get("finding_id")}
    rows=[]
    for finding in findings:
        fid=finding.get("finding_id",""); did=finding.get("document_id",""); doc=documents.get(did,{}); e=enrichment.get(fid,{})
        action_date=normalize_document_date(doc.get("document_date",""))
        for enforcement_type in finding.get("enforcement") or []:
            if enforcement_type not in STAGES: continue
            tribunal="PENDING_TRIBUNAL_LINK" if enforcement_type=="REPARO" else "NOT_APPLICABLE"
            row=EnforcementEvent(
                enforcement_event_id=stable_id("ENF",fid,enforcement_type),finding_id=fid,document_id=did,
                organization_id=e.get("organization_id","") or "",enforcement_type=enforcement_type,
                action_date=action_date,stage=STAGES[enforcement_type],source_url=finding.get("source_url","") or "",
                occurrence_date_from=finding.get("occurrence_date_from","") or "",occurrence_date_to=finding.get("occurrence_date_to","") or "",
                amount_clp=finding.get("amount_clp") if isinstance(finding.get("amount_clp"),(int,float)) else None,
                tribunal_link_status=tribunal,
            )
            rows.append(row.to_dict())
    replace_jsonl("enforcement_events",rows,"enforcement_event_id")
    return {
        "enforcement_events":len(rows),
        "reparos":sum(x["enforcement_type"]=="REPARO" for x in rows),
        "criminal_referrals":sum(x["enforcement_type"]=="CRIMINAL_REFERRAL" for x in rows),
        "cde_referrals":sum(x["enforcement_type"]=="CDE_REFERRAL" for x in rows),
        "disciplinary":sum(x["enforcement_type"]=="DISCIPLINARY" for x in rows),
    }
