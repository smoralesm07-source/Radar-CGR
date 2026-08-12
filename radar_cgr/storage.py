from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .config import BRONZE_DIR, GOLD_DIR, SILVER_DIR
from .models import canonical_json
from .utils import ensure_parent

TABLES = ["documents", "events", "findings", "evidence", "entities", "relationships", "source_runs"]


def table_path(name: str) -> Path:
    return SILVER_DIR / f"{name}.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists(): return []
    rows=[]
    with path.open("r",encoding="utf-8") as fh:
        for line in fh:
            line=line.strip()
            if line: rows.append(json.loads(line))
    return rows


def upsert_jsonl(name: str, rows: Iterable[dict], key: str) -> tuple[int,int]:
    path=table_path(name); ensure_parent(path)
    existing={row.get(key):row for row in read_jsonl(path) if row.get(key)}
    inserted=updated=0
    for row in rows:
        k=row.get(key)
        if not k: continue
        previous=existing.get(k)
        if previous is None: inserted+=1
        elif canonical_json(previous)!=canonical_json(row): updated+=1
        existing[k]=row
    with path.open("w",encoding="utf-8") as fh:
        for row in sorted(existing.values(),key=lambda r:str(r.get(key,""))): fh.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    return inserted,updated


def write_snapshot(source_id: str, run_date: str, payload: dict) -> Path:
    path=BRONZE_DIR/source_id/run_date/"snapshot.json"; ensure_parent(path)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); return path


def export_parquet() -> dict[str,str]:
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
