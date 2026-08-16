from __future__ import annotations
import re
from typing import Any
from .storage import read_jsonl,replace_jsonl,table_path
from .territory import resolve as resolve_territory
from .utils import normalize_name
INTEROP_VERSION="1.0";RADAR_ID="RADAR_CGR"
def _dv(body):
    total=0;m=2
    for d in reversed(body):total+=int(d)*m;m=m+1 if m<7 else 2
    v=11-(total%11);return "0" if v==11 else ("K" if v==10 else str(v))
def normalize_rut(value):
    c=re.sub(r"[^0-9Kk]","",str(value or "")).upper()
    if not re.fullmatch(r"\d{1,8}[0-9K]",c):return None
    body,dv=c[:-1],c[-1]
    if _dv(body)!=dv:return None
    return f"{int(body)}-{dv}"
def global_entity_id(rut):
    r=normalize_rut(rut);return f"ENT-RUT-{r}" if r else None
def _role(t):
    v=str(t or "").upper()
    if "PROVIDER" in v:return "PROVIDER"
    if "PUBLIC" in v or "ORGANIZATION" in v:return "PUBLIC_BODY"
    if "PERSON" in v:return "PERSON_MENTIONED"
    return "SOURCE_ENTITY"
def adapt_entity(record:dict[str,Any]):
    rut=normalize_rut(record.get("rut"));eid=global_entity_id(rut);source=str(record.get("entity_id") or "");name=str(record.get("name") or "");resolved=bool(eid)
    return {"interop_version":INTEROP_VERSION,"radar_id":RADAR_ID,"entity_id":eid,"source_entity_id":source or None,"candidate_entity_id":None if resolved else (source or None),"entity_type":record.get("entity_type") or "SOURCE_ENTITY","entity_role":_role(record.get("entity_type")),"rut":rut,"rut_valid":resolved,"canonical_name":name,"normalized_name":record.get("normalized_name") or normalize_name(name),"identity_status":"RESOLVED" if resolved else "UNRESOLVED","identity_method":"RUT_EXACT" if resolved else "SOURCE_LOCAL_ONLY","identity_confidence":1.0 if resolved else 0.0,"candidate_confidence":None if resolved else float(record.get("confidence") or 0.0),"source_document_id":record.get("source_document_id") or "","region_name":record.get("region") or "",**_territory_fields(record.get("region"))}
def _territory_fields(region):
    """Resuelve la región contra el índice canónico en vez de dejarla sin clave."""
    tid,status=resolve_territory(region,"REGION")
    return {"territory_id":tid,"territory_mapping_status":status}
def materialize_entity_hub():
    rows=[adapt_entity(x) for x in read_jsonl(table_path("entities")) if x.get("entity_id")]
    i,u,d=replace_jsonl("entity_hub_v1",rows,"source_entity_id")
    return {"rows":len(rows),"resolved":sum(bool(x.get("entity_id")) for x in rows),"unresolved":sum(not bool(x.get("entity_id")) for x in rows),"inserted":i,"updated":u,"deleted":d}
