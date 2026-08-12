from __future__ import annotations

from .models import Entity
from .storage import read_jsonl, replace_jsonl, table_path
from .utils import normalize_name


def public_provider_collisions(organizations: list[dict], providers: list[dict]) -> set[str]:
    public_names={normalize_name(x.get("name", "")) for x in organizations if x.get("name")}
    return {x.get("provider_id", "") for x in providers if x.get("provider_id") and normalize_name(x.get("name", "")) in public_names}


def apply_entity_quality_gate() -> dict:
    organizations=read_jsonl(table_path("organizations"))
    providers=read_jsonl(table_path("providers"))
    persons=read_jsonl(table_path("persons"))
    enrichment=read_jsonl(table_path("finding_enrichment"))
    relationships=read_jsonl(table_path("relationships"))

    collisions=public_provider_collisions(organizations,providers)
    clean_providers=[x for x in providers if x.get("provider_id") not in collisions]
    provider_by_id={x.get("provider_id"):x for x in clean_providers if x.get("provider_id")}

    clean_enrichment=[]
    for row in enrichment:
        item=dict(row)
        ids=[x for x in (item.get("provider_ids") or []) if x not in collisions and x in provider_by_id]
        item["provider_ids"]=ids
        item["provider_names"]=[provider_by_id[x].get("name","") for x in ids]
        clean_enrichment.append(item)

    clean_relationships=[x for x in relationships if x.get("target_entity_id") not in collisions]

    entities={}
    for row in organizations:
        eid=row.get("organization_id")
        if eid:
            entities[eid]=Entity(eid,"PUBLIC_ORGANIZATION",row.get("name","") or "",row.get("normalized_name","") or "",row.get("rut","") or "",row.get("region","") or "",row.get("source_document_id","") or "",float(row.get("confidence") or 0.9)).to_dict()
    for row in clean_providers:
        eid=row.get("provider_id")
        if eid:
            entities[eid]=Entity(eid,"PROVIDER",row.get("name","") or "",row.get("normalized_name","") or "",row.get("rut","") or "",row.get("region","") or "",row.get("source_document_id","") or "",float(row.get("confidence") or 0.85)).to_dict()
    for row in persons:
        eid=row.get("person_id")
        if eid:
            entities[eid]=Entity(eid,"PERSON",row.get("name","") or "",row.get("normalized_name","") or "",row.get("rut","") or "","",row.get("source_document_id","") or "",float(row.get("confidence") or 0.5)).to_dict()

    replace_jsonl("providers",clean_providers,"provider_id")
    replace_jsonl("finding_enrichment",clean_enrichment,"finding_id")
    replace_jsonl("relationships",clean_relationships,"relationship_id")
    replace_jsonl("entities",entities.values(),"entity_id")
    return {"public_provider_collisions_removed":len(collisions),"providers_after_quality_gate":len(clean_providers)}
