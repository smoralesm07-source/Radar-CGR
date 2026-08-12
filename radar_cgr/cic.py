from __future__ import annotations

import re

from .models import stable_id
from .storage import upsert_jsonl
from .utils import normalize_ws

ORDINALS={
    "primer":1,"primero":1,"segundo":2,"tercer":3,"tercero":3,"cuarto":4,"quinto":5,
    "sexto":6,"séptimo":7,"septimo":7,"octavo":8,"noveno":9,"décimo":10,"decimo":10,
    "undécimo":11,"undecimo":11,"duodécimo":12,"duodecimo":12,"decimotercer":13,"decimotercero":13,
}
DATASETS={
    "SIAPER":["siaper","sistema de información y control de personal"],
    "SII":["servicio de impuestos internos","declaraciones de renta"],
    "SICOGEN":["sicogen","sistema de contabilidad general de la nación"],
    "SISREC":["sisrec","sistema de rendición electrónica de cuentas"],
    "MINISTERIO_PUBLICO":["ministerio público","fiscalía nacional"],
    "TRANSPARENCIA":["portal de transparencia"],
    "REGISTRO_DEUDORES_ALIMENTOS":["registro nacional de deudores","deudores de pensiones"],
    "MIGRACIONES":["policía de investigaciones","pdi","salieron del país","movimientos migratorios"],
}


def _number(title:str,text:str)->int|None:
    corpus=f"{title} {text}"
    m=re.search(r"\bCIC\s*(?:N[°ºo.]?\s*)?(\d{1,2})\b",corpus,re.I)
    if m:return int(m.group(1))
    low=corpus.lower()
    for word,n in ORDINALS.items():
        if re.search(rf"\b{re.escape(word)}\s+consolidado de información circularizada\b",low):return n
    return None


def _datasets(text:str)->list[str]:
    low=(text or "").lower();out=[]
    for code,terms in DATASETS.items():
        if any(term in low for term in terms):out.append(code)
    return out


def extract_cic_articles(articles:list[dict])->list[dict]:
    rows=[]
    for art in articles:
        if art.get("error"):continue
        title=normalize_ws(art.get("title","") or "");text=normalize_ws(art.get("text_excerpt","") or "")
        corpus=f"{title} {text}".lower()
        if "consolidado de información circularizada" not in corpus and not re.search(r"\bCIC\b",title,re.I):continue
        num=_number(title,text)
        if not num:continue
        url=art.get("url","")
        rows.append({
            "cic_id":stable_id("CIC",num),
            "cic_number":num,
            "published_date_raw":art.get("date","") or "",
            "title":title,
            "datasets_detected":_datasets(text),
            "source_url":url,
            "content_hash":art.get("content_hash","") or "",
            "text_excerpt":text[:5000],
            "source_system":"CGR",
        })
    dedup={x["cic_id"]:x for x in rows}
    return sorted(dedup.values(),key=lambda x:x["cic_number"])


def persist_cic(rows:list[dict])->dict:
    inserted,updated=upsert_jsonl("cic_catalog",rows,"cic_id")
    nums=sorted({x.get("cic_number") for x in rows if x.get("cic_number")})
    return {"rows":len(rows),"inserted":inserted,"updated":updated,"numbers":nums,"max_number":max(nums) if nums else 0}
