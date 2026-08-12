from __future__ import annotations

import re

from .intelligence import classify_org_type, normalize_region
from .models import Entity, Organization, Provider, Relationship, stable_id
from .storage import read_jsonl, replace_jsonl, table_path
from .utils import normalize_name, normalize_ws

ORG_ALIASES = {
    "MUN VILLARRICA": "Municipalidad de Villarrica",
    "MUNICIPALIDAD DE VILLARRICA": "Municipalidad de Villarrica",
    "CNR": "Comisión Nacional de Riego",
    "COMISION NACIONAL DE RIEGO": "Comisión Nacional de Riego",
    "CARABINEROS": "Carabineros de Chile",
    "CARABINEROS DE CHILE": "Carabineros de Chile",
    "CONAF": "Corporación Nacional Forestal",
    "CORPORACION NACIONAL FORESTAL": "Corporación Nacional Forestal",
    "DIRECCION REGIONAL METROPOLITANA DEL INDAP": "Dirección Regional Metropolitana del INDAP",
}

ORG_KEYWORDS = (
    "MUNICIPALIDAD", "HOSPITAL", "UNIVERSIDAD", "SERVICIO DE SALUD",
    "SERVICIO LOCAL DE EDUCACION PUBLICA", "GOBIERNO REGIONAL", "INSTITUTO",
    "COMISION NACIONAL", "CARABINEROS", "CORPORACION NACIONAL FORESTAL",
    "DIRECCION REGIONAL", "MINISTERIO", "SEREMI", "SUPERINTENDENCIA",
)

TITLE_PATTERNS = [
    r"\b(MUNICIPALIDAD DE .+?)(?=\s+(?:INSPECCI[ÓO]N|AUDITOR[IÍ]A|INVESTIGACI[ÓO]N|SOBRE)\b|\s*[-–,]|$)",
    r"\b(SERVICIO LOCAL DE EDUCACI[ÓO]N P[ÚU]BLICA DE .+?)(?=\s*[,–-]|\s+(?:INSPECCI[ÓO]N|AUDITOR[IÍ]A|SOBRE)\b|$)",
    r"\b(SERVICIO DE SALUD .+?)(?=\s*[,–-]|\s+(?:INVESTIGACI[ÓO]N|AUDITOR[IÍ]A|SOBRE)\b|$)",
    r"\b(HOSPITAL .+?)(?=\s*[,–-]|\s+(?:INVESTIGACI[ÓO]N|AUDITOR[IÍ]A|SOBRE)\b|$)",
    r"\b(UNIVERSIDAD (?:DE|DEL) .+?)(?=\s*[,–-]|\s+(?:INVESTIGACI[ÓO]N|AUDITOR[IÍ]A|SOBRE)\b|$)",
    r"\b(DIRECCI[ÓO]N REGIONAL .+? DEL INDAP)(?=\s+(?:SOBRE|AUDITOR[IÍ]A)\b|\s*[,–-]|$)",
    r"\b(COMISI[ÓO]N NACIONAL DE RIEGO)\b",
    r"\b(CARABINEROS(?: DE CHILE)?)\b",
    r"\b(CORPORACI[ÓO]N NACIONAL FORESTAL)\b",
]

OBJECTIVE_PATTERNS = [
    r"\b(Corporaci[oó]n Nacional Forestal)\b",
    r"\b(Carabineros de Chile)\b",
    r"\b(Servicio Local de Educaci[oó]n P[uú]blica de [A-ZÁÉÍÓÚÑa-záéíóúñ ]{2,80})",
    r"\b(Municipalidad de [A-ZÁÉÍÓÚÑa-záéíóúñ ]{2,80})",
    r"\b(Servicio de Salud [A-ZÁÉÍÓÚÑa-záéíóúñ ]{2,80})",
    r"\b(Hospital [A-ZÁÉÍÓÚÑa-záéíóúñ ]{2,100})",
    r"\b(Universidad (?:de|del) [A-ZÁÉÍÓÚÑa-záéíóúñ -]{2,100})",
    r"\b(Comisi[oó]n Nacional de Riego)\b",
    r"\b(Instituto de Desarrollo Agropecuario)\b",
]

LEGAL_SUFFIX = r"(?:SpA|S\.?A\.?|Ltda\.?|Limitada|E\.?I\.?R\.?L\.?)"
CONNECTORS = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "E", "EMPRESA", "SOCIEDAD"}
LEGAL_TOKENS = {"SPA", "SA", "S", "A", "LTDA", "LIMITADA", "EIRL", "E", "I", "R", "L"}


def _clean_org(name: str) -> str:
    value=normalize_ws(name).strip(" ,.;:-–")
    value=re.sub(r"\s+(?:INSPECCI[ÓO]N EN TERRENO|AUDITOR[IÍ]A|INVESTIGACI[ÓO]N ESPECIAL|SOBRE)\b.*$", "", value, flags=re.I)
    norm=normalize_name(value)
    if norm in ORG_ALIASES:
        return ORG_ALIASES[norm]
    return normalize_ws(value)


def plausible_org(name: str) -> bool:
    norm=normalize_name(name)
    return 4 <= len(norm) <= 180 and any(k in norm for k in ORG_KEYWORDS)


def infer_organization(document: dict, current_name: str = "") -> str:
    title=document.get("title","") or ""
    raw=document.get("raw_text","") or ""
    objective=""
    match=re.search(r"OBJETIVO\s+(.*?)(?:CONCLUSIONES|$)",raw,re.I|re.S)
    if match:
        objective=normalize_ws(match.group(1))

    for pattern in TITLE_PATTERNS:
        m=re.search(pattern,title,re.I)
        if m:
            candidate=_clean_org(m.group(1))
            if plausible_org(candidate):
                return candidate

    if current_name:
        candidate=_clean_org(current_name)
        if plausible_org(candidate):
            return candidate

    for pattern in OBJECTIVE_PATTERNS:
        m=re.search(pattern,objective,re.I)
        if m:
            candidate=_clean_org(m.group(1))
            if plausible_org(candidate):
                return candidate
    return ""


def _split_compound_provider(name: str) -> list[str]:
    parts=[normalize_ws(name).strip(" ,.;:-")]
    out=[]
    for part in parts:
        current=part
        while True:
            m=re.search(rf"({LEGAL_SUFFIX})\s+y\s+(?=[A-ZÁÉÍÓÚÑ])",current,re.I)
            if not m:
                out.append(current); break
            first=current[:m.start()+len(m.group(1))]
            second=current[m.end():]
            out.append(first)
            current=second
    return [x for x in out if x]


def clean_provider_name(name: str) -> str:
    value=normalize_ws(name).strip(" ,.;:-")
    value=re.sub(r"^(?:de|del|la|las|los|empresa|sociedad)\s+", "", value, flags=re.I)
    return value.strip(" ,.;:-")


def provider_signature(name: str) -> str:
    base=re.sub(LEGAL_SUFFIX," ",clean_provider_name(name),flags=re.I)
    tokens=[t for t in normalize_name(base).split() if t not in CONNECTORS and t not in LEGAL_TOKENS]
    return " ".join(tokens)


def _display_rank(name: str) -> tuple[int,int,int,str]:
    norm=normalize_name(name)
    suspicious=int(norm.startswith(("DE ","DEL ","LA ","EMPRESA ")))
    conjunctions=len(re.findall(r"\b(?:y|e)\b",name,re.I))
    return suspicious,conjunctions,len(name),name


def clean_entity_resolution() -> dict:
    documents=read_jsonl(table_path("documents"))
    organizations_old=read_jsonl(table_path("organizations"))
    providers_old=read_jsonl(table_path("providers"))
    persons=read_jsonl(table_path("persons"))
    relationships_old=read_jsonl(table_path("relationships"))
    enrichment=read_jsonl(table_path("finding_enrichment"))

    old_org_by_doc={x.get("source_document_id"):x for x in organizations_old if x.get("source_document_id")}
    orgs={}; org_by_doc={}
    for doc in documents:
        did=doc.get("document_id","")
        old=old_org_by_doc.get(did,{})
        name=infer_organization(doc,old.get("name",""))
        if not name:
            continue
        norm=normalize_name(name); oid=stable_id("ENT",norm)
        region=normalize_region(doc.get("region",""),doc.get("unit_cgr",""),doc.get("title",""))
        orgs[oid]=Organization(oid,name,norm,classify_org_type(name),region,"","",did,0.92).to_dict()
        org_by_doc[did]=oid

    provider_map={}; provider_candidates={}; provider_meta={}
    for row in providers_old:
        old_id=row.get("provider_id","")
        mapped=[]
        for piece in _split_compound_provider(row.get("name","")):
            clean=clean_provider_name(piece)
            signature=provider_signature(clean)
            if len(signature)<3:
                continue
            pid=stable_id("ENT","PROVIDER",signature)
            mapped.append(pid)
            provider_candidates.setdefault(pid,[]).append(clean)
            provider_meta.setdefault(pid,row)
        provider_map[old_id]=sorted(set(mapped))

    providers={}
    for pid,candidates in provider_candidates.items():
        name=min(candidates,key=_display_rank)
        meta=provider_meta[pid]
        providers[pid]=Provider(pid,name,normalize_name(name),meta.get("provider_type","PRIVATE_LEGAL_ENTITY"),meta.get("rut","") or "",meta.get("region","") or "",meta.get("source_document_id","") or "",max(float(meta.get("confidence") or 0.7),0.85)).to_dict()

    cleaned_enrichment=[]
    for row in enrichment:
        item=dict(row); did=item.get("document_id","")
        oid=org_by_doc.get(did,""); org=orgs.get(oid,{})
        item["organization_id"]=oid; item["organization_name"]=org.get("name",""); item["organization_type"]=org.get("organization_type","")
        if org.get("region"):
            item["region"]=org.get("region")
        new_provider_ids=[]
        for old_id in item.get("provider_ids") or []:
            new_provider_ids.extend(provider_map.get(old_id,[]))
        new_provider_ids=sorted(set(new_provider_ids))
        item["provider_ids"]=new_provider_ids
        item["provider_names"]=[providers[x]["name"] for x in new_provider_ids if x in providers]
        cleaned_enrichment.append(item)

    relationships={}
    for rel in relationships_old:
        did=rel.get("document_id",""); source=org_by_doc.get(did,rel.get("source_entity_id","")); targets=provider_map.get(rel.get("target_entity_id",""))
        if targets is None:
            targets=[rel.get("target_entity_id","")]
        for target in targets:
            if not source or not target:
                continue
            rel_type=rel.get("relationship_type","")
            rid=stable_id("REL",source,target,rel_type,rel.get("finding_id",""))
            relationships[rid]=Relationship(rid,source,target,rel_type,did,rel.get("event_id","") or "",rel.get("finding_id","") or "",rel.get("evidence_id","") or "",rel.get("source_url","") or "",float(rel.get("confidence") or 0.5)).to_dict()

    entities={}
    for oid,row in orgs.items():
        entities[oid]=Entity(oid,"PUBLIC_ORGANIZATION",row["name"],row["normalized_name"],row.get("rut","") or "",row.get("region","") or "",row.get("source_document_id","") or "",row.get("confidence",0.9)).to_dict()
    for pid,row in providers.items():
        entities[pid]=Entity(pid,"PROVIDER",row["name"],row["normalized_name"],row.get("rut","") or "",row.get("region","") or "",row.get("source_document_id","") or "",row.get("confidence",0.85)).to_dict()
    for person in persons:
        pid=person.get("person_id")
        if pid:
            entities[pid]=Entity(pid,"PERSON",person.get("name","") or "",person.get("normalized_name","") or "",person.get("rut","") or "","",person.get("source_document_id","") or "",person.get("confidence",0.5)).to_dict()

    replace_jsonl("organizations",orgs.values(),"organization_id")
    replace_jsonl("providers",providers.values(),"provider_id")
    replace_jsonl("relationships",relationships.values(),"relationship_id")
    replace_jsonl("finding_enrichment",cleaned_enrichment,"finding_id")
    replace_jsonl("entities",entities.values(),"entity_id")
    return {"organizations":len(orgs),"providers":len(providers),"relationships":len(relationships),"resolved_documents":len(org_by_doc),"provider_aliases_collapsed":max(0,len(providers_old)-len(providers))}
