from __future__ import annotations

import csv
import io
from typing import Any
import httpx

FRED_CSV = {
    "GDP":"A191RL1Q225SBE", "CPI":"CPIAUCSL", "PPI":"PPIACO", "PCE":"PCEPI",
    "POLICY_RATE":"FEDFUNDS", "UNEMPLOYMENT":"UNRATE", "CLAIMS":"ICSA",
    "RETAIL":"RSAFS", "JOLTS":"JTSJOL", "CONFIDENCE":"UMCSENT", "NFP":"PAYEMS",
}

async def fred_csv(series_id: str, limit: int = 120) -> list[dict[str, Any]]:
    url=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r=await client.get(url); r.raise_for_status()
    result=[]
    for row in csv.DictReader(io.StringIO(r.text)):
        value=row.get(series_id)
        if value in (None,".",""): continue
        try: result.append({"date":row["observation_date"],"value":float(value)})
        except (KeyError,ValueError): pass
    return list(reversed(result))[-limit:]

async def public_fred_snapshot(limit:int=120):
    out={}
    for name,sid in FRED_CSV.items():
        try: out[name]=await fred_csv(sid,limit)
        except Exception as e: out[name]={"error":str(e)}
    return out

async def ecb_reference_rates() -> list[dict[str, Any]]:
    url="https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    params={"format":"csvdata","lastNObservations":"30"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r=await client.get(url,params=params); r.raise_for_status()
        result=[]
        for row in csv.DictReader(io.StringIO(r.text)):
            value=row.get("OBS_VALUE")
            if value: result.append({"date":row.get("TIME_PERIOD"),"value":float(value),"source":"ECB","series":"EURUSD_REFERENCE"})
        return result
    except Exception:
        return []
