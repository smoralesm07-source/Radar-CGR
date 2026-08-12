from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .models import stable_id
from .storage import upsert_jsonl
from .utils import normalize_ws

SOURCE_URL = "https://www.contraloria.cl/web/cgr/semaforo-municipal"
INDICATORS = [
    ("DIP_ALCALDE", "DIP Alcalde(sa)"),
    ("OTRAS_DIP", "Otras DIPs"),
    ("INFORMES_CONTABLES", "Informes Contables"),
    ("PAGO_OBLIGACIONES_ANTERIORES", "Pago de Obligaciones de Años Anteriores"),
    ("PERCEPCION_INGRESOS_ANTERIORES", "Percepción de Ingresos de Años Anteriores"),
    ("SALDO_INICIAL_CAJA", "Actualización Presupuestaria del Saldo Inicial de Caja"),
    ("PERSONAL_TRANSPARENCIA", "Actualización Personal en Transparencia"),
    ("ROYALTY_SUBDERE", "Reporta gastos Royalty a SUBDERE"),
]


def _status(code: str, raw: str) -> str:
    x = normalize_ws(raw).lower()
    if not x:
        return "UNKNOWN"
    if "no aplica" in x:
        return "NA"
    if code == "DIP_ALCALDE":
        if "oportunamente" in x: return "GREEN"
        if "extempor" in x: return "YELLOW"
        if "no ha presentado" in x: return "RED"
    if code == "OTRAS_DIP":
        if "no tiene" in x or "menos de 20" in x: return "GREEN"
        if "entre 20 y 30" in x: return "YELLOW"
        if "más de 30" in x or "mas de 30" in x: return "RED"
    if code == "INFORMES_CONTABLES":
        if x.startswith("100%") or "100% todos" in x: return "GREEN"
        if "entre 99%" in x or "99% a 50%" in x: return "YELLOW"
        if "menos del 50%" in x: return "RED"
    if code == "PAGO_OBLIGACIONES_ANTERIORES":
        if "totalidad" in x: return "GREEN"
        if "entre el 51%" in x or "51% a 99%" in x: return "YELLOW"
        if "menos del 50%" in x: return "RED"
        if "monto superior" in x: return "OTHER"
    if code == "PERCEPCION_INGRESOS_ANTERIORES":
        if "totalidad" in x: return "GREEN"
        if "entre el 51%" in x or "51% a 99%" in x: return "YELLOW"
        if "menos del 50%" in x: return "RED"
        if "monto superior" in x: return "OTHER"
    if code == "SALDO_INICIAL_CAJA":
        if "ha actualizado correctamente" in x: return "GREEN"
        if "no ha actualizado correctamente" in x: return "RED"
    if code == "PERSONAL_TRANSPARENCIA":
        if "cumple con la obligación" in x or "cumple con la obligacion" in x: return "GREEN"
        if "cumplimiento parcial" in x: return "YELLOW"
        if "incumplimiento" in x: return "RED"
    if code == "ROYALTY_SUBDERE":
        if "no recibió" in x or "no recibio" in x: return "NA"
        if "uno de los dos fondos" in x: return "YELLOW"
        if "no ha informado" in x: return "RED"
        if "ha informado" in x: return "GREEN"
    return "OTHER"


def _header_dates(table) -> list[str]:
    dates=[]
    for th in table.find_all("th"):
        text=normalize_ws(th.get_text(" ",strip=True))
        m=re.search(r"\((\d{2}/\d{2})\)",text)
        if m: dates.append(m.group(1))
    # Algunas tablas duplican encabezados visuales/ocultos; tomamos las primeras 8 fechas útiles.
    compact=[]
    for d in dates:
        if len(compact)<8: compact.append(d)
    return compact


def parse_semaforo(html: str, retrieved_at: str | None = None, source_url: str = SOURCE_URL) -> list[dict]:
    retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot_date = retrieved_at[:10]
    soup=BeautifulSoup(html,"lxml")
    best=None
    for table in soup.find_all("table"):
        rows=table.find_all("tr")
        if best is None or len(rows)>len(best.find_all("tr")): best=table
    if best is None: return []
    dates=_header_dates(best)
    out=[]
    for tr in best.find_all("tr"):
        cells=[normalize_ws(td.get_text(" ",strip=True)) for td in tr.find_all("td")]
        if len(cells)<10: continue
        commune,region=cells[0],cells[1]
        values=cells[2:10]
        if not commune or not region: continue
        for idx,((code,label),raw) in enumerate(zip(INDICATORS,values)):
            as_of=dates[idx] if idx<len(dates) else ""
            row={
                "snapshot_id": stable_id("SEM",snapshot_date,commune,code),
                "snapshot_date": snapshot_date,
                "commune": commune,
                "region": region,
                "indicator_code": code,
                "indicator_label": label,
                "indicator_as_of_ddmm": as_of,
                "status": _status(code,raw),
                "raw_value": raw,
                "source_url": source_url,
                "retrieved_at": retrieved_at,
            }
            out.append(row)
    return out


def persist_semaforo(rows: list[dict]) -> dict:
    inserted,updated=upsert_jsonl("municipal_control_snapshots",rows,"snapshot_id")
    municipalities=len({(x.get("commune"),x.get("region")) for x in rows})
    statuses={}
    for row in rows: statuses[row["status"]]=statuses.get(row["status"],0)+1
    return {"rows":len(rows),"municipalities":municipalities,"inserted":inserted,"updated":updated,"statuses":statuses,"complete_expected_345":municipalities>=345}
