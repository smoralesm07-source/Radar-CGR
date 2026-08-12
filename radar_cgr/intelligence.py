from __future__ import annotations

import re
from collections import defaultdict

from .models import Entity, Irregularity, Organization, PenalHypothesis, Person, Provider, Relationship, stable_id
from .storage import read_jsonl, replace_jsonl, table_path
from .utils import normalize_name, normalize_ws

REGIONS = {
    "ARICA Y PARINACOTA": "Arica y Parinacota",
    "TARAPACA": "Tarapacá",
    "ANTOFAGASTA": "Antofagasta",
    "ATACAMA": "Atacama",
    "COQUIMBO": "Coquimbo",
    "VALPARAISO": "Valparaíso",
    "METROPOLITANA": "Metropolitana de Santiago",
    "O HIGGINS": "O'Higgins",
    "OHIGGINS": "O'Higgins",
    "LIBERTADOR GENERAL BERNARDO O HIGGINS": "O'Higgins",
    "MAULE": "Maule",
    "NUBLE": "Ñuble",
    "BIO BIO": "Biobío",
    "BIOBIO": "Biobío",
    "ARAUCANIA": "La Araucanía",
    "LOS RIOS": "Los Ríos",
    "LOS LAGOS": "Los Lagos",
    "AYSEN": "Aysén",
    "MAGALLANES": "Magallanes y de la Antártica Chilena",
}

ORG_CANON = {
    "CNR": "Comisión Nacional de Riego",
    "COMISION NACIONAL DE RIEGO": "Comisión Nacional de Riego",
    "INDAP": "Instituto de Desarrollo Agropecuario",
    "INSTITUTO DE DESARROLLO AGROPECUARIO": "Instituto de Desarrollo Agropecuario",
}

IRREGULARITY_RULES = [
    ("PAYMENT_IMPROPER", "Pago improcedente", "FINANCIAL", 76, [r"pagos? improcedent", r"gastos? improcedent"]),
    ("PAYMENT_UNSUPPORTED", "Pago o gasto sin respaldo suficiente", "FINANCIAL", 70, [r"pago.{0,80}sin respaldo", r"gasto.{0,80}sin respaldo", r"respaldos? documentales?.{0,80}insuficient"]),
    ("SERVICE_NOT_PROVEN", "Prestación o servicio no acreditado", "PROCUREMENT", 78, [r"servicios?.{0,80}no (?:fue|fueron|se encuentra[n]?)?\s*acredit", r"no permiten acreditar.{0,80}(?:servicio|prestaci[oó]n)", r"prestaci[oó]n.{0,80}no acredit"]),
    ("PROCUREMENT_IRREGULAR", "Contratación o compra irregular", "PROCUREMENT", 68, [r"irregularidad.{0,60}(?:compra|contrataci[oó]n|licitaci[oó]n)", r"contrataci[oó]n.{0,80}(?:inhabilidad|improcedent|irregular)", r"compras?.{0,80}fuera del portal", r"vicios? esenciales?.{0,80}procedimiento"]),
    ("DIRECT_AWARD", "Uso observado de trato directo", "PROCUREMENT", 58, [r"trato directo"]),
    ("CONFLICT_INTEREST", "Conflicto de interés o inhabilidad", "INTEGRITY", 82, [r"conflicto de inter[eé]s", r"inhabilidad", r"incompatibil", r"c[oó]nyuge.{0,120}funcionari", r"funcionari.{0,120}c[oó]nyuge"]),
    ("RELATED_PARTY", "Vínculo o parte relacionada", "INTEGRITY", 72, [r"v[ií]nculo.{0,80}(?:empresa|proveedor|contrat)", r"lazos? familiares", r"parentesco", r"socio.{0,100}(?:directiv|funcionari)"]),
    ("OVERPAYMENT", "Pago en exceso o sobrepago", "FINANCIAL", 74, [r"pago[s]? en exceso", r"sobrepago", r"pag[oó].{0,50}en exceso"]),
    ("UNRENDERED_FUNDS", "Fondos o saldos sin rendición", "PUBLIC_FUNDS", 70, [r"sin rendir", r"rendici[oó]n.{0,80}(?:pendiente|no acredit|improcedent)", r"fondos?.{0,100}no rendid"]),
    ("PUBLIC_FUNDS_MISUSE", "Uso de fondos para fines distintos", "PUBLIC_FUNDS", 80, [r"fondos?.{0,100}fines? distintos", r"recursos?.{0,100}fines? distintos", r"desv[ií]o.{0,80}fondos?", r"transferencias?.{0,120}cuenta de sueldos"]),
    ("ACCOUNTING_ANOMALY", "Anomalía o integridad contable", "FINANCIAL", 60, [r"no manten[ií]a registrados?.{0,100}contabilidad", r"integridad y razonabilidad.{0,80}informaci[oó]n financiera", r"discrepancias?.{0,100}registros?", r"diferencias?.{0,80}contabl"]),
    ("DOCUMENT_INCONSISTENCY", "Documentación inconsistente o no verificable", "DOCUMENTARY", 62, [r"documentaci[oó]n.{0,100}(?:insuficient|inconsisten|no permite)", r"no figuran en.{0,60}(?:sistema|registros?)", r"discrepancias?.{0,100}antecedentes"]),
    ("BENEFICIARY_INELIGIBLE", "Beneficiario con requisitos observados", "BENEFICIARY", 58, [r"beneficiari.{0,120}(?:no cumpl|sin cumplir|requisit|ineligible)", r"reevaluar.{0,80}beneficiari"]),
    ("CONTROL_FAILURE", "Debilidad o falla de control", "CONTROL", 45, [r"debilidad(?:es)? (?:administrativas?|de control)", r"falta de control", r"no ha realizado acciones de fiscalizaci[oó]n", r"falta de gestiones oportunas", r"p[eé]rdida de trazabilidad"]),
    ("PERSONNEL_IRREGULARITY", "Irregularidad asociada a personal", "PERSONNEL", 58, [r"funcionari.{0,100}(?:irregular|inhabilidad|licencia|remuneraci)", r"honorarios?.{0,100}(?:lazos? familiares|inhabilidad)", r"trabajador.{0,100}simult[aá]neamente"]),
    ("ASSET_CONTROL", "Control irregular de bienes o activos", "ASSETS", 58, [r"bienes? no habidos", r"veh[ií]culos?.{0,80}(?:remate|encargo policial|sin antecedentes)", r"inventario.{0,80}(?:diferencia|faltante)"]),
]

ROLE_PATTERNS = {
    "FUNCIONARIO": r"funcionari[oa]s?",
    "DIRECTIVO": r"directiv[oa]s?",
    "ALCALDE": r"alcald[ea]",
    "GERENTE_GENERAL": r"gerente general",
    "JEFE": r"jef[ea]",
    "ADMINISTRADOR": r"administrador(?:a)?",
    "SERVIDOR_PUBLICO": r"servidor(?:a)?s? p[uú]blic[oa]s?",
    "AUTORIDAD": r"autoridad(?:es)?",
}

COMPANY_TOKEN = r"(?:[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9&'.-]*|de|del|la|las|los|y|e)"
COMPANY_SUFFIX = r"(?:SpA|S\.?A\.?|Ltda\.?|Limitada|E\.?I\.?R\.?L\.?)"
COMPANY_RE = re.compile(rf"\b((?:{COMPANY_TOKEN}\s+){{1,9}}{COMPANY_SUFFIX})\b")
FOUNDATION_RE = re.compile(r"\b((?:Fundaci[oó]n|Corporaci[oó]n)\s+(?:[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9&'.-]*|de|del|la|las|los|y)(?:\s+(?:[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9&'.-]*|de|del|la|las|los|y)){0,7})")
PERSON_RE = re.compile(r"\b(?:don|doña|señor|señora)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})\b")


def normalize_region(*values: str) -> str:
    combined = " ".join(v or "" for v in values)
    norm = normalize_name(combined)
    for key, label in REGIONS.items():
        if key in norm:
            return label
    return ""


def classify_org_type(name: str) -> str:
    n=normalize_name(name)
    if n.startswith("MUNICIPALIDAD"): return "MUNICIPALITY"
    if n.startswith("GOBIERNO REGIONAL") or n.startswith("GORE "): return "REGIONAL_GOVERNMENT"
    if n.startswith("SERVICIO DE SALUD"): return "HEALTH_SERVICE"
    if n.startswith("HOSPITAL"): return "HOSPITAL"
    if n.startswith("UNIVERSIDAD"): return "STATE_UNIVERSITY"
    if "INSTITUTO" in n: return "PUBLIC_INSTITUTE"
    if "COMISION" in n: return "PUBLIC_COMMISSION"
    if "MINISTERIO" in n or "SEREMI" in n: return "CENTRAL_GOVERNMENT"
    return "PUBLIC_ORGANIZATION"


def _canonical_org(name: str) -> str:
    cleaned=normalize_ws(re.sub(r"\s+(?:sobre|respecto|a los pagos|para|durante)\b.*$", "", name or "", flags=re.I)).strip(" ,.;:-")
    norm=normalize_name(cleaned)
    if norm in ORG_CANON: return ORG_CANON[norm]
    if norm.startswith("LA "): cleaned=cleaned[3:]
    if norm.startswith("EL "): cleaned=cleaned[3:]
    return normalize_ws(cleaned)


def extract_public_organization(document: dict, event: dict | None = None) -> str:
    if event and event.get("entity_name"):
        candidate=_canonical_org(event.get("entity_name", ""))
        if 3 <= len(candidate) <= 180:
            return candidate
    text=document.get("raw_text","")
    objective=""
    m=re.search(r"OBJETIVO\s+(.*?)(?:CONCLUSIONES|$)",text,re.I|re.S)
    if m: objective=normalize_ws(m.group(1))
    for pat in [
        r"(?:auditor[ií]a|fiscalizaci[oó]n|investigaci[oó]n|revisi[oó]n)\s+(?:en|a)\s+(?:el|la|los|las)?\s*([^,.;]{3,180})",
        r"\b(Municipalidad de [A-ZÁÉÍÓÚÑa-záéíóúñ -]{3,80})",
        r"\b(Gobierno Regional (?:de|del) [A-ZÁÉÍÓÚÑa-záéíóúñ -]{3,80})",
        r"\b(Servicio de Salud [A-ZÁÉÍÓÚÑa-záéíóúñ -]{3,80})",
        r"\b(Hospital [A-ZÁÉÍÓÚÑa-záéíóúñ -]{3,100})",
        r"\b(Universidad (?:de|del) [A-ZÁÉÍÓÚÑa-záéíóúñ -]{3,100})",
        r"\b(Comisi[oó]n Nacional de Riego)\b",
        r"\b(Instituto de Desarrollo Agropecuario)\b",
    ]:
        m=re.search(pat, objective or text, re.I)
        if m:
            candidate=_canonical_org(m.group(1))
            if 3 <= len(candidate) <= 180: return candidate
    return ""


def extract_providers(text: str) -> list[dict]:
    results={}
    for match in COMPANY_RE.finditer(text or ""):
        name=normalize_ws(match.group(1)).strip(" ,.;:-")
        norm=normalize_name(name)
        if len(norm)<5 or any(x in norm for x in ["CONTRALORIA GENERAL", "SERVICIO DE SALUD", "MUNICIPALIDAD"]): continue
        left=max(0,match.start()-150); right=min(len(text),match.end()+150); context=(text[left:right] or "").lower()
        role="MENTIONED_PROVIDER"
        if re.search(r"pag[oó]|pago[s]?|desembolso",context): role="PAYMENT_RECIPIENT"
        if re.search(r"contrat|licitaci|adjudic",context): role="CONTRACTOR"
        results[norm]={"name":name,"normalized_name":norm,"relationship_type":role,"provider_type":"PRIVATE_LEGAL_ENTITY","confidence":0.92}
    for match in FOUNDATION_RE.finditer(text or ""):
        name=normalize_ws(match.group(1)).strip(" ,.;:-")
        norm=normalize_name(name)
        if len(norm)<8: continue
        left=max(0,match.start()-150); right=min(len(text),match.end()+150); context=(text[left:right] or "").lower()
        if not re.search(r"transfer|convenio|contrat|pago|fundaci[oó]n",context): continue
        role="TRANSFER_RECIPIENT" if "transfer" in context else "MENTIONED_PROVIDER"
        results[norm]={"name":name,"normalized_name":norm,"relationship_type":role,"provider_type":"NONPROFIT_LEGAL_ENTITY","confidence":0.78}
    return sorted(results.values(),key=lambda x:x["normalized_name"])


def extract_persons(text: str) -> list[dict]:
    out={}
    for m in PERSON_RE.finditer(text or ""):
        name=normalize_ws(m.group(1)); norm=normalize_name(name)
        if len(norm)<5: continue
        context=(text[max(0,m.start()-100):min(len(text),m.end()+100)] or "").lower()
        role=""
        for label,pat in ROLE_PATTERNS.items():
            if re.search(pat,context,re.I): role=label; break
        out[norm]={"name":name,"normalized_name":norm,"role":role,"confidence":0.68}
    return sorted(out.values(),key=lambda x:x["normalized_name"])


def detect_roles(text: str) -> list[str]:
    return [label for label,pat in ROLE_PATTERNS.items() if re.search(pat,text or "",re.I|re.S)]


def classify_irregularities(text: str, finding_id: str, document_id: str, evidence_id: str, source_url: str) -> list[Irregularity]:
    rows=[]
    for code,label,family,weight,patterns in IRREGULARITY_RULES:
        if any(re.search(p,text or "",re.I|re.S) for p in patterns):
            rows.append(Irregularity(stable_id("IRR",finding_id,code),finding_id,document_id,code,label,family,weight,evidence_id,source_url))
    return rows


def _relevance(score:int)->str:
    return "HIGH" if score>=75 else "MEDIUM" if score>=50 else "LOW" if score>0 else "NONE"


def assess_penal(text:str, irregularity_codes:set[str], enforcement:list[str], amount:int|None, finding_id:str, document_id:str, evidence_id:str, source_url:str)->list[PenalHypothesis]:
    rows=[]; lower=(text or "").lower(); explicit_mp="CRIMINAL_REFERRAL" in enforcement
    amount_bonus=10 if (amount or 0)>=1_000_000_000 else 7 if (amount or 0)>=100_000_000 else 4 if (amount or 0)>=10_000_000 else 0
    common_limits=["La clasificación es una hipótesis analítica y no acredita dolo ni responsabilidad penal individual."]

    def add(code,label,base,basis:list[str], explicit:bool=False):
        score=min(100,base+amount_bonus+(15 if explicit_mp else 0)+(8 if "REPARO" in enforcement else 0)+(5 if "DISCIPLINARY" in enforcement else 0))
        level="EXPLICIT_CGR_REFERRAL" if explicit_mp else "STRONG_INDICATORS" if score>=70 else "ANALYTICAL_HYPOTHESIS"
        limitations=list(common_limits)
        if not explicit_mp: limitations.append("No consta en este hallazgo una remisión explícita al Ministerio Público.")
        rows.append(PenalHypothesis(stable_id("PNL",finding_id,code),finding_id,document_id,code,label,score,_relevance(score),level,basis,limitations,evidence_id,source_url))

    if irregularity_codes & {"PAYMENT_IMPROPER","PAYMENT_UNSUPPORTED","SERVICE_NOT_PROVEN","OVERPAYMENT","PROCUREMENT_IRREGULAR"}:
        basis=["Uso o contratación de recursos públicos con observaciones CGR"]
        if irregularity_codes & {"PAYMENT_IMPROPER","SERVICE_NOT_PROVEN","OVERPAYMENT"}: basis.append("Pago, sobrepago o prestación no acreditada")
        if "REPARO" in enforcement: basis.append("CGR anuncia o formula reparo")
        add("POTENTIAL_FRAUD_AGAINST_STATE","Posible relevancia para fraude al Fisco",55,basis)

    if "PUBLIC_FUNDS_MISUSE" in irregularity_codes or re.search(r"malvers|desv[ií]o.{0,80}fondos|fondos?.{0,100}fines? distintos",lower,re.I|re.S):
        add("POTENTIAL_MALVERSATION","Posible relevancia para malversación de caudales públicos",62,["Uso o destino de fondos públicos observado como distinto al autorizado"])

    if irregularity_codes & {"CONFLICT_INTEREST","RELATED_PARTY"} and re.search(r"contrat|licitaci|adjudic|proveedor|empresa",lower,re.I|re.S):
        add("POTENTIAL_INCOMPATIBLE_NEGOTIATION","Posible relevancia para negociación incompatible",68,["Contratación o decisión pública asociada a inhabilidad, parentesco o conflicto de interés"])

    if re.search(r"\b(cohecho|soborno|d[aá]diva|coima)\b",lower,re.I):
        add("POTENTIAL_BRIBERY","Posible relevancia para cohecho",78,["El texto CGR contiene una referencia explícita compatible con cohecho/soborno"])

    if re.search(r"falsific|documento[s]? falsos?|facturas? falsas?",lower,re.I):
        add("POTENTIAL_FALSE_DOCUMENT","Posible relevancia penal documental",58,["Documento o antecedente descrito como falso o falsificado"])

    if explicit_mp and not rows:
        add("POTENTIAL_OTHER_PUBLIC_OFFICIAL_OFFENCE","Otra posible relevancia penal asociada al hallazgo",70,["CGR remite expresamente antecedentes al Ministerio Público"],True)
    return rows


def calculate_cgr_score(irregularities:list[Irregularity], enforcement:list[str], amount:int|None)->int:
    base=max([x.cgr_weight for x in irregularities],default=35)
    if (amount or 0)>=1_000_000_000: base+=10
    elif (amount or 0)>=100_000_000: base+=7
    elif (amount or 0)>=10_000_000: base+=4
    if "DISCIPLINARY" in enforcement: base+=6
    if "REPARO" in enforcement: base+=12
    if "CDE_REFERRAL" in enforcement: base+=8
    if "CRIMINAL_REFERRAL" in enforcement: base+=15
    return min(100,base)


def rebuild_intelligence()->dict:
    documents=read_jsonl(table_path("documents")); events=read_jsonl(table_path("events")); findings=read_jsonl(table_path("findings"))
    event_by_doc={x.get("document_id"):x for x in events if x.get("document_id")}
    doc_by_id={x.get("document_id"):x for x in documents if x.get("document_id")}

    organizations={}; providers={}; persons={}; relationships={}; irregularities={}; hypotheses={}; enrichment=[]; generic_entities={}

    org_by_doc={}
    for doc in documents:
        event=event_by_doc.get(doc.get("document_id"),{})
        org_name=extract_public_organization(doc,event)
        region=normalize_region(doc.get("region",""),event.get("region",""),doc.get("unit_cgr",""),doc.get("title",""))
        if not org_name: continue
        norm=normalize_name(org_name); oid=stable_id("ENT",norm); org_by_doc[doc.get("document_id")]=oid
        row=Organization(oid,org_name,norm,classify_org_type(org_name),region,"","",doc.get("document_id",""),0.85)
        organizations[oid]=row.to_dict(); generic_entities[oid]=Entity(oid,"PUBLIC_ORGANIZATION",org_name,norm,"",region,doc.get("document_id",""),0.85).to_dict()

    for finding in findings:
        fid=finding.get("finding_id",""); did=finding.get("document_id",""); text=finding.get("description",""); evidence_id=finding.get("evidence_id",""); source_url=finding.get("source_url","")
        event=event_by_doc.get(did,{}); doc=doc_by_id.get(did,{})
        oid=org_by_doc.get(did,"")
        if not oid:
            org_name=extract_public_organization(doc,event)
            if org_name:
                norm=normalize_name(org_name); oid=stable_id("ENT",norm); region=normalize_region(doc.get("region",""),event.get("region",""),doc.get("unit_cgr",""),doc.get("title",""))
                organizations[oid]=Organization(oid,org_name,norm,classify_org_type(org_name),region,"","",did,0.75).to_dict(); generic_entities[oid]=Entity(oid,"PUBLIC_ORGANIZATION",org_name,norm,"",region,did,0.75).to_dict()
        org=organizations.get(oid,{})
        region=org.get("region") or normalize_region(doc.get("region",""),event.get("region",""),doc.get("unit_cgr",""),doc.get("title",""))

        irr=classify_irregularities(text,fid,did,evidence_id,source_url)
        for x in irr: irregularities[x.irregularity_id]=x.to_dict()
        codes={x.code for x in irr}
        amount=finding.get("amount_clp") if isinstance(finding.get("amount_clp"),(int,float)) else None
        enforcement=list(finding.get("enforcement") or [])
        penal=assess_penal(text,codes,enforcement,int(amount) if amount else None,fid,did,evidence_id,source_url)
        for x in penal: hypotheses[x.hypothesis_id]=x.to_dict()
        cgr_score=calculate_cgr_score(irr,enforcement,int(amount) if amount else None)
        penal_score=max([x.score for x in penal],default=0); penal_relevance=_relevance(penal_score)

        provider_ids=[]; provider_names=[]
        for item in extract_providers(text):
            pid=stable_id("ENT",item["normalized_name"]); provider_ids.append(pid); provider_names.append(item["name"])
            providers[pid]=Provider(pid,item["name"],item["normalized_name"],item["provider_type"],"",region,did,item["confidence"]).to_dict(); generic_entities[pid]=Entity(pid,"PROVIDER",item["name"],item["normalized_name"],"",region,did,item["confidence"]).to_dict()
            if oid:
                rel=Relationship(stable_id("REL",oid,pid,item["relationship_type"],fid),oid,pid,item["relationship_type"],did,finding.get("event_id",""),fid,evidence_id,source_url,item["confidence"])
                relationships[rel.relationship_id]=rel.to_dict()

        person_ids=[]
        for item in extract_persons(text):
            pid=stable_id("ENT",item["normalized_name"]); person_ids.append(pid)
            persons[pid]=Person(pid,item["name"],item["normalized_name"],item["role"],oid,"",did,item["confidence"]).to_dict(); generic_entities[pid]=Entity(pid,"PERSON",item["name"],item["normalized_name"],"",region,did,item["confidence"]).to_dict()
            if oid:
                rel=Relationship(stable_id("REL",oid,pid,"MENTIONED_PERSON",fid),oid,pid,"MENTIONED_PERSON",did,finding.get("event_id",""),fid,evidence_id,source_url,item["confidence"])
                relationships[rel.relationship_id]=rel.to_dict()

        enrichment.append({
            "finding_id":fid,"document_id":did,"event_id":finding.get("event_id",""),"organization_id":oid,
            "organization_name":org.get("name",""),"organization_type":org.get("organization_type",""),"region":region,
            "provider_ids":sorted(set(provider_ids)),"provider_names":sorted(set(provider_names)),"person_ids":sorted(set(person_ids)),"roles_detected":detect_roles(text),
            "irregularity_codes":sorted(codes),"irregularity_labels":sorted({x.label for x in irr}),"cgr_score":cgr_score,
            "penal_score":penal_score,"penal_relevance":penal_relevance,"penal_hypotheses":[x.code for x in penal],
            "aml_score":int(finding.get("aml_score") or 0),"aml_relevance":finding.get("aml_relevance",""),"amount_clp":amount,
            "disciplinary":"DISCIPLINARY" in enforcement,"reparo":"REPARO" in enforcement,"criminal_referral":"CRIMINAL_REFERRAL" in enforcement,"cde_referral":"CDE_REFERRAL" in enforcement,
            "evidence_id":evidence_id,"source_url":source_url,
        })

    replace_jsonl("organizations",organizations.values(),"organization_id"); replace_jsonl("providers",providers.values(),"provider_id"); replace_jsonl("persons",persons.values(),"person_id")
    replace_jsonl("relationships",relationships.values(),"relationship_id"); replace_jsonl("irregularities",irregularities.values(),"irregularity_id"); replace_jsonl("penal_hypotheses",hypotheses.values(),"hypothesis_id")
    replace_jsonl("finding_enrichment",enrichment,"finding_id"); replace_jsonl("entities",generic_entities.values(),"entity_id")
    return {"organizations":len(organizations),"providers":len(providers),"persons":len(persons),"relationships":len(relationships),"irregularities":len(irregularities),"penal_hypotheses":len(hypotheses),"enriched_findings":len(enrichment)}
