from __future__ import annotations
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from storage import init_db, latest
from ingest import ingest_all_fred
from engine import DriverResult, weighted_score, pair_score, DRIVER_WEIGHTS
from sources import FRED_CSV

app=FastAPI(title="MacroFX Backend",version="0.4.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])

def momentum(series,higher_is_better=True):
    rows=latest(series,2)
    if len(rows)<2:return DriverResult(None,0.0,"insufficient history")
    cur,prev=rows[0]["value"],rows[1]["value"]
    if prev in (None,0):return DriverResult(None,0.0,"invalid previous value")
    change=(cur-prev)/abs(prev)*100
    if not higher_is_better: change=-change
    return DriverResult(round(max(-100,min(100,change*20)),2),1.0)

def currency_snapshot(currency):
    currency=currency.upper()
    d={name:DriverResult(None,0.0,"currency adapter not connected") for name in DRIVER_WEIGHTS}
    if currency=="USD":
        d["rates"]=momentum("POLICY_RATE")
        d["growth"]=DriverResult(None,0.0,"growth composite pending release normalization")
        d["inflation"]=DriverResult(None,0.0,"inflation-policy regime pending")
        d["employment"]=DriverResult(None,0.0,"employment composite pending release normalization")
    score,coverage=weighted_score(d)
    return {"currency":currency,"score":score,"coverage":coverage,"drivers":{k:{"score":v.score,"coverage":v.coverage,"reason":v.reason} for k,v in d.items()}}

@app.on_event("startup")
async def startup():
    init_db()
    try: await ingest_all_fred()
    except Exception: pass

@app.get("/")
async def root(): return {"name":"MacroFX Backend","status":"ok","version":"0.4.0","data_mode":"public_keyless_fred","time":datetime.now(timezone.utc).isoformat()}

@app.get("/api/health")
async def health(): return {"status":"ok","data_mode":"public_keyless_fred","stored_usd_series":len([s for s in FRED_CSV if latest(s,1)])}
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
    key=series_name.upper()
    if key not in FRED_CSV:return {"error":"unknown series","available":sorted(FRED_CSV)}
    return {"series":key,"series_id":FRED_CSV[key],"stored":latest(key,24)}
@app.get("/api/config")
async def config(): return {"weights":DRIVER_WEIGHTS,"fred_series":FRED_CSV,"fred_api_key_required":False}
