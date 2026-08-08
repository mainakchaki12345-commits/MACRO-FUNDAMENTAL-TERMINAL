from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from storage import init_db, latest
from ingest import ingest_all_fred
from engine import DriverResult, weighted_score, pair_score, DRIVER_WEIGHTS, clamp
from sources import FRED_CSV, WORLD_BANK_COUNTRIES, WORLD_BANK_INDICATORS
from market_sources import yahoo_price, technicals, seasonality, cftc_currency, retail_sentiment

app=FastAPI(title="MacroFX Backend",version="0.7.0")
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

def momentum(rows,higher_is_better=True,scale=20.0):
    if len(rows)<2:return DriverResult(None,0.0,"insufficient history")
    cur,prev=rows[0]["value"],rows[1]["value"]
    if prev in (None,0):return DriverResult(None,0.0,"invalid previous value")
    change=(cur-prev)/abs(prev)*100
    if not higher_is_better:change=-change
    return DriverResult(round(max(-100,min(100,change*scale)),2),1.0)

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


def differential(a,b):
    if a is None or b is None: return None
    return clamp(a-b)

async def market_snapshot(pair:str):
    # All four feeds are free/public where available. Retail remains optional because Myfxbook
    # requires a free account session; the engine never fabricates retail positioning.
    results=await asyncio.gather(
        yahoo_price(pair), technicals(pair), seasonality(pair), retail_sentiment(pair),
        return_exceptions=True
    )
    def safe(x, fallback): return fallback if isinstance(x,Exception) else x
    price=safe(results[0],{"pair":pair,"price":None,"source":"Yahoo Finance","error":str(results[0]) if isinstance(results[0],Exception) else None})
    tech=safe(results[1],{"score":None,"coverage":0.0,"reason":"market price unavailable"})
    seas=safe(results[2],{"score":None,"coverage":0.0,"reason":"seasonality unavailable"})
    retail=safe(results[3],{"score":None,"coverage":0.0,"reason":"retail source unavailable"})
    return {"price":price,"technicals":tech,"seasonality":seas,"sentiment":retail}

async def cot_pair_snapshot(base:str,quote:str):
    b,q=await asyncio.gather(cftc_currency(base),cftc_currency(quote),return_exceptions=True)
    if isinstance(b,Exception): b={"currency":base,"score":None,"coverage":0.0,"reason":str(b)}
    if isinstance(q,Exception): q={"currency":quote,"score":None,"coverage":0.0,"reason":str(q)}
    score=differential(b.get("score"),q.get("score"))
    cov=min(b.get("coverage",0),q.get("coverage",0))
    return {"base":b,"quote":q,"score":score,"coverage":cov,
            "reason":"CFTC non-commercial futures net-position percentile differential"}

async def full_pair(pair:str):
    pair=pair.upper().replace("/","")
    if len(pair)!=6:return {"error":"pair must look like EURUSD"}
    base,quote=pair[:3],pair[3:]
    b,q=currency_snapshot(base),currency_snapshot(quote)
    market,cot=await asyncio.gather(market_snapshot(f"{base}{quote}"),cot_pair_snapshot(base,quote))

    # Preserve the original macro currency differential while adding the three pair-level
    # market drivers. Each component retains the terminal's declared driver weight.
    pair_drivers={
        "technicals":market["technicals"],
        "sentiment":market["sentiment"],
        "cot":cot,
        "seasonality":market["seasonality"],
    }
    macro_components={k: (b["drivers"].get(k,{}).get("score"), q["drivers"].get(k,{}).get("score"),
                           min(b["drivers"].get(k,{}).get("coverage",0),q["drivers"].get(k,{}).get("coverage",0)))
                      for k in ("growth","inflation","rates","employment")}
    weighted=0.0; used=0.0
    # Macro differential: base minus quote for each currency driver.
    for name,(bs,qs,cov) in macro_components.items():
        if bs is not None and qs is not None and cov>0:
            w=DRIVER_WEIGHTS[name]*cov; weighted += differential(bs,qs)*w; used += w
    for name,obj in pair_drivers.items():
        score=obj.get("score"); cov=obj.get("coverage",0)
        if score is not None and cov>0:
            w=DRIVER_WEIGHTS[name]*cov; weighted += score*w; used += w
    total=sum(DRIVER_WEIGHTS.values())
    score=round(clamp(weighted/used),2) if used else None
    coverage=round(used/total,3)
    if score is None: signal="INSUFFICIENT_DATA"
    elif score>=60: signal="STRONG_BULLISH"
    elif score>=20: signal="BULLISH"
    elif score<=-60: signal="STRONG_BEARISH"
    elif score<=-20: signal="BEARISH"
    else: signal="NEUTRAL"
    return {
        "pair":f"{base}/{quote}","score":score,"coverage":coverage,"signal":signal,
        "base":b,"quote":q,"market":market,"cot":cot,
        "drivers":{
            "technicals":market["technicals"],"sentiment":market["sentiment"],"cot":cot,
            "seasonality":market["seasonality"],
            "growth":{"score":differential(b["drivers"]["growth"]["score"],q["drivers"]["growth"]["score"]),"coverage":macro_components["growth"][2]},
            "inflation":{"score":differential(b["drivers"]["inflation"]["score"],q["drivers"]["inflation"]["score"]),"coverage":macro_components["inflation"][2]},
            "rates":{"score":differential(b["drivers"]["rates"]["score"],q["drivers"]["rates"]["score"]),"coverage":macro_components["rates"][2]},
            "employment":{"score":differential(b["drivers"]["employment"]["score"],q["drivers"]["employment"]["score"]),"coverage":macro_components["employment"][2]},
            "central_bank":{"score":None,"coverage":0.0,"reason":"central-bank event feed not connected yet"},
        },
        "generated_at":datetime.now(timezone.utc).isoformat()
    }

@app.on_event("startup")
async def startup():
    init_db()
    try: await ingest_all_fred()
    except Exception: pass

@app.get("/")
async def root(): return {"name":"MacroFX Backend","status":"ok","version":"0.7.0","data_mode":"free_fred_world_bank_ecb_eurostat_cftc_yahoo","supported_currencies":SUPPORTED_CURRENCIES,"time":datetime.now(timezone.utc).isoformat()}
@app.get("/api/health")
async def health(): return {"status":"ok","data_mode":"free_fred_world_bank_ecb_eurostat_cftc_yahoo","supported_currencies":SUPPORTED_CURRENCIES,"stored_usd_series":len([s for s in FRED_CSV if latest(s,1)])}
@app.post("/api/ingest/fred")
async def ingest_fred(): return {"status":"ok","inserted":await ingest_all_fred()}
@app.get("/api/history/{series_name}")
async def history(series_name:str,limit:int=24): return {"series":series_name.upper(),"observations":latest(series_name.upper(),min(max(limit,1),500))}
@app.get("/api/currency/{currency}")
async def currency(currency:str): return currency_snapshot(currency)
@app.get("/api/market/{pair}")
async def market(pair:str): return await market_snapshot(pair.upper().replace("/",""))
@app.get("/api/cot/{currency}")
async def cot(currency:str): return await cftc_currency(currency.upper())
@app.get("/api/macro/{pair}")
async def macro(pair:str): return await full_pair(pair)
@app.get("/api/fred/{series_name}")
async def fred_named(series_name:str):
    key=series_name.upper()
    if key not in FRED_CSV:return {"error":"unknown series","available":sorted(FRED_CSV)}
    return {"series":key,"series_id":FRED_CSV[key],"stored":latest(key,24)}
@app.get("/api/config")
async def config(): return {"weights":DRIVER_WEIGHTS,"fred_series":FRED_CSV,"world_bank_indicators":WORLD_BANK_INDICATORS,"supported_currencies":SUPPORTED_CURRENCIES,"market_pairs":sorted(PAIR_TO_YAHOO),"free_data":True}
