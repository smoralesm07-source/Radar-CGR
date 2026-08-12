from __future__ import annotations

import re

from .models import FAUMatch, stable_id
from .storage import read_jsonl, replace_jsonl, table_path

FAU_SOURCE_URL="https://www.contraloria.cl/web/cgr/alerta-posibles-fraudes"

FAU_CATALOG=[
    {
        "pattern_code":"FAU_REMUNERACIONES",
        "pattern_label":"Remuneraciones y pagos a personal",
        "process":"REMUNERATIONS",
        "origin":"CGR_FAU_PUBLIC_THEME",
        "patterns":[r"remuneraci",r"honorarios?",r"bonos?",r"asignaciones?",r"pago[s]? en exceso.{0,80}funcionari"],
    },
    {
        "pattern_code":"FAU_ADQUISICIONES",
        "pattern_label":"Adquisiciones y contratación pública",
        "process":"PROCUREMENT",
        "origin":"CGR_FAU_PUBLIC_THEME",
        "patterns":[r"licitaci",r"trato directo",r"contrataci[oó]n",r"adjudicaci",r"inhabilidad",r"conflicto de inter[eé]s"],
    },
    {
        "pattern_code":"FAU_CUENTAS_CORRIENTES",
        "pattern_label":"Administración de cuentas corrientes y fondos",
        "process":"BANK_ACCOUNTS_AND_FUNDS",
        "origin":"CGR_FAU_PUBLIC_THEME",
        "patterns":[r"cuentas? corrientes?",r"conciliaci[oó]n bancaria",r"transferencias? bancarias?",r"giros?",r"fondos?.{0,80}cuenta"],
    },
    {
        "pattern_code":"FAU_HORAS_JORNADA",
        "pattern_label":"Horas extraordinarias y control de jornada",
        "process":"WORKING_TIME",
        "origin":"CGR_FAU_PUBLIC_THEME",
        "patterns":[r"horas? extraordinarias?",r"control horario",r"jornada laboral",r"marcaci[oó]n",r"control de asistencia"],
    },
    {
        "pattern_code":"FAU_PAGO_PROVEEDORES",
        "pattern_label":"Pagos a proveedores y acreditación de prestaciones",
        "process":"SUPPLIER_PAYMENTS",
        "origin":"CGR_FAU_PUBLIC_THEME",
        "patterns":[r"proveedor",r"facturas?",r"pago[s]? improcedent",r"sobrepago",r"prestaci[oó]n.{0,80}no acredit",r"servicios?.{0,80}no acredit"],
    },
]


def _catalog_rows()->list[dict]:
    return [{k:v for k,v in item.items() if k!="patterns"}|{"source_url":FAU_SOURCE_URL} for item in FAU_CATALOG]


def rebuild_fau_matches()->dict:
    findings=read_jsonl(table_path("findings")); enrichment={x.get("finding_id"):x for x in read_jsonl(table_path("finding_enrichment")) if x.get("finding_id")}; rows=[]
    for finding in findings:
        fid=finding.get("finding_id",""); text=finding.get("description","") or ""; e=enrichment.get(fid,{})
        irregularity_text=" ".join(e.get("irregularity_labels") or [])
        combined=f"{text} {irregularity_text}"
        for item in FAU_CATALOG:
            matched=[]
            for pattern in item["patterns"]:
                m=re.search(pattern,combined,re.I|re.S)
                if m: matched.append(m.group(0)[:120])
            if not matched: continue
            score=min(100,40+len(matched)*14)
            if e.get("cgr_score",0)>=75: score=min(100,score+8)
            rows.append(FAUMatch(
                fau_match_id=stable_id("FAU",fid,item["pattern_code"]),finding_id=fid,document_id=finding.get("document_id","") or "",
                pattern_code=item["pattern_code"],pattern_label=item["pattern_label"],score=score,
                match_basis=sorted(set(matched))[:8],source_url=finding.get("source_url","") or "",origin=item["origin"],
            ).to_dict())
    replace_jsonl("fau_catalog",_catalog_rows(),"pattern_code")
    replace_jsonl("fau_matches",rows,"fau_match_id")
    return {"fau_patterns":len(FAU_CATALOG),"fau_matches":len(rows),"high_matches":sum(x["score"]>=75 for x in rows)}
