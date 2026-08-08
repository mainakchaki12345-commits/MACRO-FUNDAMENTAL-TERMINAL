from __future__ import annotations
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from storage import init_db, latest
from ingest import ingest_all_fred
from engine import DriverResult, weighted_score, pair_score, DRIVER_WEIGHTS
from sources import FRED_CSV, WORLD_BANK_COUNTRIES, WORLD_BANK_INDICATORS

app=FastAPI(title="MacroFX Backend",version="0.6.0")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])
SUPPORTED_CURRENCIES=sorted(WORLD_BANK_COUNTRIES)

def level_score(value, neutral=0.0, scale=20.0, higher_is_better=True):
    if value is None: return DriverResult(None,0.0,"missing observation")
    delta=value-neutral
    if not higher_is_better: delta=-delta
    return DriverResult(round(max(-100,min(100,delta*scale)),2),1.0)

def latest_rows(series, n=2): return latest(series,n)
def wb_rows(currency, name, n=2): return latest(f"{name}_{currency}",n)

def yoy_from_index(series, periods=13):
    rows=latest(series,periods)
    if len(rows)<periods or rows[periods-1]["value"] in (None,0): return DriverResult(None,0.0,"insufficient YoY history")
    current=rows[0]["value"]; prior=rows[periods-1]["value"]
    yoy=(current-prior)/abs(prior)*100
    return level_score(yoy,2.0,20.0,False)

def currency_snapshot(currency):
    currency=currency.upper()
    d={name:DriverResult(None,0.0,"no free source connected yet") for name in DRIVER_WEIGHTS}
    if currency=="USD":
        g=latest_rows("GDP",1)
        d["growth"]=level_score(g[0]["value"],0.0,12.0,True) if g else DriverResult(None,0.0,"missing GDP")
        d["inflation"]=yoy_from_index("CPI")
        r=latest_rows("POLICY_RATE",1)
        d["rates"]=level_score(r[0]["value"],3.0,18.0,True) if r else DriverResult(None,0.0,"missing policy rate")
        u=latest_rows("UNEMPLOYMENT",1); c=latest_rows("CLAIMS",2); n=latest_rows("NFP",2)
        parts=[]
        if u: parts.append(level_score(u[0]["value"],5.0,15.0,False))
        if len(c)>=2: parts.append(momentum(c,False))
        if len(n)>=2: parts.append(momentum(n,True))
        if parts: d["employment"]=DriverResult(round(sum(x.score for x in parts)/len(parts),2),round(len(parts)/3,2),"FRED unemployment/claims/NFP composite")
    elif currency in SUPPORTED_CURRENCIES:
        g=wb_rows(currency,"WB_GDP_GROWTH",1); inf=wb_rows(currency,"WB_INFLATION",1); u=wb_rows(currency,"WB_UNEMPLOYMENT",1)
        d["growth"]=level_score(g[0]["value"],0.0,12.0,True) if g else DriverResult(None,0.0,"missing World Bank GDP growth")
        d["inflation"]=level_score(inf[0]["value"],2.0,20.0,False) if inf else DriverResult(None,0.0,"missing World Bank inflation")
        d["employment"]=level_score(u[0]["value"],5.0,15.0,False) if u else DriverResult(None,0.0,"missing World Bank unemployment")
        if currency=="EUR":
            rate=latest_rows("POLICY_RATE_EUR",1); e_inf=latest_rows("INFLATION_EUR",1)
            if rate: d["rates"]=level_score(rate[0]["value"],3.0,18.0,True)
            if e_inf: d["inflation"]=level_score(e_inf[0]["value"],2.0,20.0,False)
    score,coverage=weighted_score(d)
    return {"currency":currency,"score":score,"coverage":coverage,"drivers":{k:{"score":v.score,"coverage":v.coverage,"reason":v.reason} for k,v in d.items()}}

def momentum(rows,higher_is_better=True,scale=20.0):
    if len(rows)<2:return DriverResult(None,0.0,"insufficient history")
    cur,prev=rows[0]["value"],rows[1]["value"]
    if prev in (None,0):return DriverResult(None,0.0,"invalid previous value")
    change=(cur-prev)/abs(prev)*100
    if not higher_is_better:change=-change
    return DriverResult(round(max(-100,min(100,change*scale)),2),1.0)

@app.on_event("startup")
async def startup():
    init_db()
    try: await ingest_all_fred()
    except Exception: pass

@app.get("/")
async def root(): return {"name":"MacroFX Backend","status":"ok","version":"0.6.0","data_mode":"free_fred_world_bank_ecb_eurostat","supported_currencies":SUPPORTED_CURRENCIES,"time":datetime.now(timezone.utc).isoformat()}
@app.get("/api/health")
async def health(): return {"status":"ok","data_mode":"free_fred_world_bank_ecb_eurostat","supported_currencies":SUPPORTED_CURRENCIES,"stored_usd_series":len([s for s in FRED_CSV if latest(s,1)])}
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
    base,quote=pair[:3],pair[3:]; b,q=currency_snapshot(base),currency_snapshot(quote)
    score,cov,signal=pair_score(b["score"],q["score"],b["coverage"],q["coverage"])
    return {"pair":f"{base}/{quote}","score":score,"coverage":cov,"signal":signal,"base":b,"quote":q,"generated_at":datetime.now(timezone.utc).isoformat()}
@app.get("/api/fred/{series_name}")
async def fred_named(series_name:str):
    key=series_name.upper()
    if key not in FRED_CSV:return {"error":"unknown series","available":sorted(FRED_CSV)}
    return {"series":key,"series_id":FRED_CSV[key],"stored":latest(key,24)}
@app.get("/api/config")
async def config(): return {"weights":DRIVER_WEIGHTS,"fred_series":FRED_CSV,"world_bank_indicators":WORLD_BANK_INDICATORS,"supported_currencies":SUPPORTED_CURRENCIES,"official_eur_sources":["ECB","Eurostat"],"free_data":True}
