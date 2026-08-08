from __future__ import annotations
import os
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from storage import init_db, latest
from ingest import ingest_all_fred
from engine import DriverResult, weighted_score, pair_score, DRIVER_WEIGHTS

app=FastAPI(title="MacroFX Backend",version="0.3.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])
FRED_SERIES={"GDP":"A191RL1Q225SBE","CPI":"CPIAUCSL","PPI":"PPIACO","PCE":"PCEPI","POLICY_RATE":"FEDFUNDS","UNEMPLOYMENT":"UNRATE","CLAIMS":"ICSA","RETAIL":"RSAFS","JOLTS":"JTSJOL","CONFIDENCE":"UMCSENT","NFP":"PAYEMS"}

def obs(series):
    rows=latest(series,2)
    if len(rows)<2:return DriverResult(None,0.0,"insufficient history")
    a,b=rows[0]["value"],rows[1]["value"]
    if b in (None,0):return DriverResult(None,0.0,"invalid previous value")
    return DriverResult(round(max(-100,min(100,((a-b)/abs(b))*2000)),2),1.0)

def currency_snapshot(currency):
    d={name:DriverResult(None,0.0,"no currency adapter") for name in DRIVER_WEIGHTS}
    if currency.upper()=="USD":
        d["rates"]=obs("POLICY_RATE")
        d["growth"]=DriverResult(None,0.0,"release-specific composite pending")
        d["inflation"]=DriverResult(None,0.0,"policy-regime interpretation pending")
        d["employment"]=DriverResult(None,0.0,"release-specific composite pending")
    score,coverage=weighted_score(d)
    return {"currency":currency.upper(),"score":score,"coverage":coverage,"drivers":{k:{"score":v.score,"coverage":v.coverage,"reason":v.reason} for k,v in d.items()}}

@app.on_event("startup")
async def startup(): init_db()
@app.get("/")
async def root(): return {"name":"MacroFX Backend","status":"ok","version":"0.3.0","time":datetime.now(timezone.utc).isoformat()}
@app.get("/api/health")
async def health(): return {"status":"ok","fred_configured":bool(os.getenv("FRED_API_KEY"))}
@app.post("/api/ingest/fred")
async def ingest_fred(): return {"status":"ok","inserted":await ingest_all_fred()}
@app.get("/api/history/{series_name}")
async def history(series_name:str,limit:int=24): return {"series":series_name.upper(),"observations":latest(series_name.upper(),min(max(limit,1),500))}
@app.get("/api/currency/{currency}")
async def currency(currency:str): return currency_snapshot(currency)
@app.get("/api/macro/{pair}")
async def macro(pair:str):
    pair=pair.upper().replace("/","")
    if len(pair)!=6:return {"error":"pair must look like EURUSD"}
    base,quote=pair[:3],pair[3:]
    b,q=currency_snapshot(base),currency_snapshot(quote)
    score,cov,signal=pair_score(b["score"],q["score"],b["coverage"],q["coverage"])
    return {"pair":f"{base}/{quote}","score":score,"coverage":cov,"signal":signal,"base":b,"quote":q,"generated_at":datetime.now(timezone.utc).isoformat()}
@app.get("/api/fred/{series_name}")
async def fred_named(series_name:str):
    sid=FRED_SERIES.get(series_name.upper())
    if not sid:return {"error":"unknown series","available":sorted(FRED_SERIES)}
    return {"series":series_name.upper(),"series_id":sid,"stored":latest(series_name.upper(),24)}
@app.get("/api/config")
async def config(): return {"weights":DRIVER_WEIGHTS,"fred_series":FRED_SERIES}
