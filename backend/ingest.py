from __future__ import annotations
from typing import Any
from sources import FRED_CSV, fred_csv
from storage import init_db, upsert_observations

SERIES_META: dict[str, dict[str, str]] = {
    "GDP":{"country":"US","currency":"USD","unit":"percent","frequency":"quarterly"},
    "CPI":{"country":"US","currency":"USD","unit":"index","frequency":"monthly"},
    "PPI":{"country":"US","currency":"USD","unit":"index","frequency":"monthly"},
    "PCE":{"country":"US","currency":"USD","unit":"index","frequency":"monthly"},
    "POLICY_RATE":{"country":"US","currency":"USD","unit":"percent","frequency":"daily"},
    "UNEMPLOYMENT":{"country":"US","currency":"USD","unit":"percent","frequency":"monthly"},
    "CLAIMS":{"country":"US","currency":"USD","unit":"claims","frequency":"weekly"},
    "RETAIL":{"country":"US","currency":"USD","unit":"index","frequency":"monthly"},
    "JOLTS":{"country":"US","currency":"USD","unit":"thousands","frequency":"monthly"},
    "CONFIDENCE":{"country":"US","currency":"USD","unit":"index","frequency":"monthly"},
    "NFP":{"country":"US","currency":"USD","unit":"thousands","frequency":"monthly"},
}

async def ingest_fred_series(name: str, limit: int = 120) -> int:
    key=name.upper()
    if key not in FRED_CSV: raise ValueError(f"Unknown FRED series: {name}")
    observations=await fred_csv(FRED_CSV[key],limit)
    meta=SERIES_META[key]; rows:list[dict[str,Any]]=[]
    for i,o in enumerate(observations):
        previous=observations[i-1]["value"] if i else None
        rows.append({"source":"FRED","series":key,"country":meta["country"],"currency":meta["currency"],"timestamp":o["date"],"value":o["value"],"unit":meta["unit"],"frequency":meta["frequency"],"release_timestamp":None,"previous_value":previous,"revision":0,"url":f"https://fred.stlouisfed.org/series/{FRED_CSV[key]}"})
    return upsert_observations(rows)

async def ingest_all_fred() -> dict[str,int]:
    init_db(); result={}
    for name in FRED_CSV:
        try: result[name]=await ingest_fred_series(name)
        except Exception: result[name]=0
    return result
