from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .config import BRONZE_DIR, GOLD_DIR, SILVER_DIR
from .models import canonical_json
from .utils import ensure_parent

TABLES=[
    "documents","events","findings","evidence","entities",
    "organizations","providers","persons","relationships",
    "irregularities","penal_hypotheses","finding_enrichment","source_runs"
]
VOLATILE_FIELDS={"retrieved_at"}


def table_path(name:str)->Path: return SILVER_DIR/f"{name}.jsonl"


def read_jsonl(path:Path)->list[dict]:
    if not path.exists(): return []
    rows=[]
    with path.open("r",encoding="utf-8") as fh:
        for line in fh:
            line=line.strip()
            if line: rows.append(json.loads(line))
    return rows


def _semantic(row:dict)->dict:
    return {k:v for k,v in row.items() if k not in VOLATILE_FIELDS}


def _write_rows(path:Path, rows:list[dict], key:str)->None:
    ensure_parent(path)
    with path.open("w",encoding="utf-8") as fh:
        for row in sorted(rows,key=lambda r:str(r.get(key,""))):
            fh.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")


def upsert_jsonl(name:str,rows:Iterable[dict],key:str)->tuple[int,int]:
    path=table_path(name); existing={row.get(key):row for row in read_jsonl(path) if row.get(key)}; inserted=updated=0
    for row in rows:
        k=row.get(key)
        if not k: continue
        previous=existing.get(k)
        if previous is None:
            inserted+=1; existing[k]=row
        elif canonical_json(_semantic(previous))!=canonical_json(_semantic(row)):
            updated+=1; existing[k]=row
        else:
            existing[k]=previous
    _write_rows(path,list(existing.values()),key)
    return inserted,updated


def replace_jsonl(name:str, rows:Iterable[dict], key:str)->tuple[int,int,int]:
    """Reemplazo determinista para tablas derivadas. Retorna insertados, actualizados y eliminados."""
    path=table_path(name)
    previous={row.get(key):row for row in read_jsonl(path) if row.get(key)}
    current={row.get(key):row for row in rows if row.get(key)}
    inserted=sum(k not in previous for k in current)
    updated=sum(k in previous and canonical_json(_semantic(previous[k]))!=canonical_json(_semantic(v)) for k,v in current.items())
    deleted=sum(k not in current for k in previous)
    _write_rows(path,list(current.values()),key)
    return inserted,updated,deleted


def write_snapshot(source_id:str,run_date:str,payload:dict)->Path:
    path=BRONZE_DIR/source_id/run_date/"snapshot.json"; ensure_parent(path); path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); return path


def export_parquet()->dict[str,str]:
    result={}
    try: import pandas as pd
    except Exception: return result
    for name in TABLES:
        src=table_path(name)
        if not src.exists() or src.stat().st_size==0: continue
        rows=read_jsonl(src)
        if not rows: continue
        out=GOLD_DIR/f"{name}.parquet"; out.parent.mkdir(parents=True,exist_ok=True)
        try: pd.DataFrame(rows).to_parquet(out,index=False); result[name]=str(out)
        except Exception: continue
    return result
