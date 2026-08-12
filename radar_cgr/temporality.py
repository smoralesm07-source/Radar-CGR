from __future__ import annotations
import calendar,re
from datetime import date
from .storage import read_jsonl,replace_jsonl,table_path
from .utils import normalize_ws
MONTHS={"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
MONTH_RE="|".join(MONTHS); DATE_TEXT=rf"(\d{{1,2}})\s+de\s+({MONTH_RE})(?:\s+de\s+(\d{{4}}))?"
def _iso(y,m,d):
    try:return date(int(y),int(m),int(d)).isoformat()
    except Exception:return ""
def _year_bounds(y): y=int(y); return f"{y:04d}-01-01",f"{y:04d}-12-31"
def _month_bounds(y,m): y=int(y);m=int(m);return f"{y:04d}-{m:02d}-01",f"{y:04d}-{m:02d}-{calendar.monthrange(y,m)[1]:02d}"
def normalize_document_date(value):
    value=(value or "").strip()
    for pat,ymd in [(r"^(\d{2})-(\d{2})-(\d{4})$",False),(r"^(\d{2})/(\d{2})/(\d{4})$",False),(r"^(\d{4})-(\d{2})-(\d{2})$",True)]:
        m=re.match(pat,value)
        if m:return _iso(m.group(1),m.group(2),m.group(3)) if ymd else _iso(m.group(3),m.group(2),m.group(1))
    return ""
def _result(start,end,precision,basis,confidence): return {"occurrence_date_from":start,"occurrence_date_to":end,"occurrence_date_anchor":end or start,"occurrence_date_precision":precision,"occurrence_date_basis":normalize_ws(basis)[:220],"occurrence_date_confidence":round(float(confidence),2)}
def infer_from_text(text,basis_prefix="FINDING_TEXT"):
    t=normalize_ws(text or "")
    if not t:return None
    m=re.search(rf"(?:per[ií]odo\s+comprendido\s+)?(?:entre|desde)\s+(?:el\s+)?{DATE_TEXT}\s+(?:y|hasta)\s+(?:el\s+)?{DATE_TEXT}",t,re.I)
    if m:
        d1,mo1,y1,d2,mo2,y2=m.groups();y1=y1 or y2
        if y1 and y2:
            start=_iso(y1,MONTHS[mo1.lower()],d1);end=_iso(y2,MONTHS[mo2.lower()],d2)
            if start and end:return _result(start,end,"RANGE",f"{basis_prefix}: {m.group(0)}",.95)
    m=re.search(r"(?:entre|desde)\s+(?:el\s+)?(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s+(?:y|hasta)\s+(?:el\s+)?(\d{1,2})[/-](\d{1,2})[/-](\d{4})",t,re.I)
    if m:
        start=_iso(m.group(3),m.group(2),m.group(1));end=_iso(m.group(6),m.group(5),m.group(4))
        if start and end:return _result(start,end,"RANGE",f"{basis_prefix}: {m.group(0)}",.95)
    m=re.search(r"(?:durante|entre|en)\s+(?:los\s+)?años?\s+(\d{4})\s+(?:y|a|hasta)\s+(\d{4})",t,re.I)
    if m:
        start,_=_year_bounds(m.group(1));_,end=_year_bounds(m.group(2));return _result(start,end,"YEAR_RANGE",f"{basis_prefix}: {m.group(0)}",.86)
    m=re.search(r"(?:durante|en)\s+(?:el\s+)?año\s+(\d{4})",t,re.I)
    if m:
        start,end=_year_bounds(m.group(1));return _result(start,end,"YEAR",f"{basis_prefix}: {m.group(0)}",.84)
    m=re.search(rf"(?:durante|en)\s+(?:el\s+mes\s+de\s+)?({MONTH_RE})\s+de\s+(\d{{4}})",t,re.I)
    if m:
        start,end=_month_bounds(m.group(2),MONTHS[m.group(1).lower()]);return _result(start,end,"MONTH",f"{basis_prefix}: {m.group(0)}",.88)
    m=re.search(rf"\bal\s+{DATE_TEXT}",t,re.I)
    if m:
        context=t[max(0,m.start()-70):min(len(t),m.end()+70)].lower();day,month,year=m.groups()
        if year and "fecha de corte" not in context and "equival" not in context:
            exact=_iso(year,MONTHS[month.lower()],day)
            if exact:return _result(exact,exact,"AS_OF_DATE",f"{basis_prefix}: {m.group(0)}",.90)
    # Fecha contenida en un acto administrativo que el propio hallazgo vuelve a identificar como el día de ocurrencia.
    m=re.search(rf"\bdecreto\b.{{0,100}}?\bde\s+{DATE_TEXT}",t,re.I)
    if m:
        day,month,year=m.groups()
        repeated=rf"\bd[ií]a\s+{re.escape(day)}\s+de\s+{re.escape(month)}\s+de\s+la\s+presente\s+anualidad"
        if year and re.search(repeated,t,re.I):
            exact=_iso(year,MONTHS[month.lower()],day)
            if exact:return _result(exact,exact,"EXACT",f"{basis_prefix}: fecha del acto coincidente con día del hecho ({day} de {month} de {year})",.94)
    m=re.search(rf"(?:el\s+d[ií]a|del\s+d[ií]a|con\s+fecha|el)\s+{DATE_TEXT}",t,re.I)
    if m:
        context=t[max(0,m.start()-50):min(len(t),m.end()+50)].lower();day,month,year=m.groups()
        if year and not re.search(r"\b(?:ley|decreto|resoluci[oó]n|dictamen|oficio)\b",context):
            exact=_iso(year,MONTHS[month.lower()],day)
            if exact:return _result(exact,exact,"EXACT",f"{basis_prefix}: {m.group(0)}",.96)
    m=re.search(r"(?:el\s+d[ií]a|del\s+d[ií]a|con\s+fecha|el)\s+(\d{1,2})[/-](\d{1,2})[/-](\d{4})",t,re.I)
    if m:
        exact=_iso(m.group(3),m.group(2),m.group(1))
        if exact:return _result(exact,exact,"EXACT",f"{basis_prefix}: {m.group(0)}",.96)
    return None
def infer_occurrence_interval(finding_text,audit_objective="",document_date=""):
    direct=infer_from_text(finding_text,"FINDING_TEXT")
    if direct:return direct
    inherited=infer_from_text(audit_objective,"AUDIT_OBJECTIVE")
    if inherited:
        inherited["occurrence_date_precision"]="AUDIT_"+inherited["occurrence_date_precision"];inherited["occurrence_date_confidence"]=round(min(inherited["occurrence_date_confidence"],.68),2);return inherited
    return _result("","","UNKNOWN","NO_TEMPORAL_EVIDENCE",0.0)
def _objective(raw):
    m=re.search(r"OBJETIVO\s+(.*?)(?:CONCLUSIONES|$)",raw or "",re.I|re.S);return normalize_ws(m.group(1)) if m else ""
def backfill_finding_temporality():
    docs={x.get("document_id"):x for x in read_jsonl(table_path("documents")) if x.get("document_id")};findings=read_jsonl(table_path("findings"));rows=[];known=exact=inherited=0
    for row in findings:
        item=dict(row);doc=docs.get(item.get("document_id"),{});temporal=infer_occurrence_interval(item.get("description",""),_objective(doc.get("raw_text","")),doc.get("document_date",""));item.update(temporal);rows.append(item);known+=bool(temporal["occurrence_date_from"]);exact+=temporal["occurrence_date_precision"]=="EXACT";inherited+=temporal["occurrence_date_precision"].startswith("AUDIT_")
    replace_jsonl("findings",rows,"finding_id");return {"findings":len(rows),"temporal_known":known,"exact_dates":exact,"audit_period_inherited":inherited}
def propagate_temporality_to_enrichment():
    findings={x.get("finding_id"):x for x in read_jsonl(table_path("findings")) if x.get("finding_id")};rows=[];fields=("occurrence_date_from","occurrence_date_to","occurrence_date_anchor","occurrence_date_precision","occurrence_date_basis","occurrence_date_confidence")
    for row in read_jsonl(table_path("finding_enrichment")):
        item=dict(row);f=findings.get(item.get("finding_id"),{})
        for key in fields:item[key]=f.get(key,0.0 if key=="occurrence_date_confidence" else "")
        rows.append(item)
    replace_jsonl("finding_enrichment",rows,"finding_id")
