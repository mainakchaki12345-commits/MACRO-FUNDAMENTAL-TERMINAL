from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from storage import init_db, latest
from ingest import ingest_all_fred

app = FastAPI(title="MacroFX Backend", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

WEIGHTS = {"technicals": .10, "sentiment": .08, "cot": .12, "seasonality": .06, "growth": .15, "inflation": .12, "rates": .18, "employment": .10, "central_bank": .09}
FRED_SERIES = {"GDP":"A191RL1Q225SBE","CPI":"CPIAUCSL","PPI":"PPIACO","PCE":"PCEPI","POLICY_RATE":"FEDFUNDS","UNEMPLOYMENT":"UNRATE","CLAIMS":"ICSA","RETAIL":"RSAFS","JOLTS":"JTSJOL","CONFIDENCE":"UMCSENT","NFP":"PAYEMS"}

def empty_driver() -> dict[str, Any]: return {"score": None, "coverage": 0, "observations": []}
def currency_template(currency: str) -> dict[str, Any]: return {"currency":currency,"drivers":{name:empty_driver() for name in WEIGHTS},"score":None,"coverage":0}

async def fred_series(series_id: str, limit: int = 24) -> list[dict[str, Any]]:
    key=os.getenv("FRED_API_KEY")
    if not key:return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r=await client.get("https://api.stlouisfed.org/fred/series/observations",params={"series_id":series_id,"api_key":key,"file_type":"json","sort_order":"desc","limit":str(limit)})
            r.raise_for_status(); data=r.json()
        return [{"date":x["date"],"value":x["value"],"series_id":series_id,"source":"FRED"} for x in data.get("observations",[]) if x.get("value") not in (None,".")]
    except Exception:return []

@app.on_event("startup")
async def startup(): init_db()

@app.get("/")
async def root(): return {"name":"MacroFX Backend","status":"ok","version":"0.2.0","time":datetime.now(timezone.utc).isoformat()}
@app.get("/api/health")
async def health(): return {"status":"ok","fred_configured":bool(os.getenv("FRED_API_KEY"))}
@app.post("/api/ingest/fred")
async def ingest_fred(): return {"status":"ok","inserted":await ingest_all_fred()}
@app.get("/api/history/{series_name}")
async def history(series_name:str,limit:int=24): return {"series":series_name.upper(),"observations":latest(series_name.upper(),min(max(limit,1),500))}
@app.get("/api/pairs/{pair}")
async def pair_snapshot(pair:str):
    pair=pair.upper()
    if len(pair)!=6:return {"error":"pair must look like EURUSD"}
    base,quote=pair[:3],pair[3:]
    return {"pair":f"{base}/{quote}","base":currency_template(base),"quote":currency_template(quote),"score":None,"signal":"INSUFFICIENT_DATA","generated_at":datetime.now(timezone.utc).isoformat()}
@app.get("/api/fred/{series_name}")
async def fred_named(series_name:str):
    sid=FRED_SERIES.get(series_name.upper())
    if not sid:return {"error":"unknown series","available":sorted(FRED_SERIES)}
    return {"series":series_name.upper(),"series_id":sid,"observations":await fred_series(sid)}
@app.get("/api/config")
async def config(): return {"weights":WEIGHTS,"fred_series":FRED_SERIES}
