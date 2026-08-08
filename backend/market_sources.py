from __future__ import annotations

import os, statistics
from datetime import datetime, timezone
from typing import Any
import httpx

CFTC_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Yahoo symbols for the major FX pairs supported by the terminal.
YAHOO_SYMBOLS = {
    "EURUSD":"EURUSD=X", "GBPUSD":"GBPUSD=X", "USDJPY":"JPY=X", "USDCHF":"CHF=X",
    "USDCAD":"CAD=X", "AUDUSD":"AUDUSD=X", "NZDUSD":"NZDUSD=X", "EURGBP":"EURGBP=X",
    "EURJPY":"EURJPY=X", "EURCHF":"EURCHF=X", "EURAUD":"EURAUD=X", "EURCAD":"EURCAD=X",
    "GBPJPY":"GBPJPY=X", "GBPCHF":"GBPCHF=X", "AUDJPY":"AUDJPY=X", "AUDNZD":"AUDNZD=X",
    "NZDJPY":"NZDJPY=X", "CADJPY":"CADJPY=X", "CHFJPY":"CHFJPY=X",
}

# CFTC Legacy futures names are currency futures proxies, not spot FX positions.
COT_MARKETS = {
    "EUR":"EURO FX", "GBP":"BRITISH POUND", "JPY":"JAPANESE YEN", "CHF":"SWISS FRANC",
    "CAD":"CANADIAN DOLLAR", "AUD":"AUSTRALIAN DOLLAR", "NZD":"NEW ZEALAND DOLLAR",
}

PAIR_TO_YAHOO = {k:v for k,v in YAHOO_SYMBOLS.items()}

async def yahoo_chart(pair: str, range_: str = "5y", interval: str = "1d") -> list[dict[str, Any]]:
    pair = pair.upper().replace("/", "")
    symbol = PAIR_TO_YAHOO.get(pair)
    if not symbol:
        raise ValueError(f"unsupported FX pair: {pair}")
    url = YAHOO_URL.format(symbol=symbol)
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers={"User-Agent":"MacroFX/1.0"}) as client:
        r = await client.get(url, params={"range":range_,"interval":interval,"includePrePost":"false"})
        r.raise_for_status()
        payload = r.json()
    result = (payload.get("chart",{}).get("result") or [None])[0]
    if not result: return []
    timestamps = result.get("timestamp") or []
    q = (result.get("indicators",{}).get("quote") or [{}])[0]
    closes = q.get("close") or []
    opens = q.get("open") or []
    highs = q.get("high") or []
    lows = q.get("low") or []
    out=[]
    for i,ts in enumerate(timestamps):
        if i >= len(closes) or closes[i] is None: continue
        out.append({"timestamp":datetime.fromtimestamp(ts,tz=timezone.utc).isoformat(),"value":float(closes[i]),
                    "open": opens[i], "high": highs[i], "low": lows[i]})
    return out

async def yahoo_price(pair: str) -> dict[str, Any]:
    pair=pair.upper().replace("/","")
    rows=await yahoo_chart(pair,"5d","1d")
    if not rows: return {"pair":pair,"price":None,"source":"Yahoo Finance"}
    return {"pair":pair,"price":rows[-1]["value"],"timestamp":rows[-1]["timestamp"],"source":"Yahoo Finance"}

def sma(values:list[float], n:int=21):
    return sum(values[-n:])/n if len(values)>=n else None

def technicals_from_daily_and_hourly(daily:list[dict[str,Any]], hourly:list[dict[str,Any]]) -> dict[str,Any]:
    d=[x["value"] for x in daily if x.get("value") is not None]
    d_sma=sma(d,21)
    # Build 4-hour closes from hourly bars using UTC 4-hour buckets.
    buckets={}
    for x in hourly:
        dt=datetime.fromisoformat(x["timestamp"].replace("Z","+00:00"))
        key=dt.replace(hour=(dt.hour//4)*4,minute=0,second=0,microsecond=0)
        buckets[key]=x["value"]
    h4=[buckets[k] for k in sorted(buckets)]
    h4_sma=sma(h4,21)
    price=d[-1] if d else (h4[-1] if h4 else None)
    parts=[]
    if price is not None and d_sma is not None: parts.append(100.0 if price>d_sma else -100.0)
    if price is not None and h4_sma is not None: parts.append(100.0 if price>h4_sma else -100.0)
    score=round(sum(parts)/len(parts),2) if parts else None
    return {"price":price,"sma21_d1":d_sma,"sma21_h4":h4_sma,"score":score,
            "signal":"BULLISH" if score and score>25 else "BEARISH" if score and score<-25 else "NEUTRAL" if score is not None else "N/A",
            "coverage":round(len(parts)/2,2),"source":"Yahoo Finance"}

async def technicals(pair:str):
    daily=await yahoo_chart(pair,"5y","1d")
    # Yahoo limits hourly history to a shorter window; 2y is safely inside the normal 1h limit.
    hourly=await yahoo_chart(pair,"2y","1h")
    return technicals_from_daily_and_hourly(daily,hourly)

async def seasonality(pair:str, years:int=10):
    rows=await yahoo_chart(pair,"10y","1mo")
    if len(rows)<24: return {"score":None,"coverage":0.0,"reason":"insufficient monthly history","source":"Yahoo Finance"}
    current_month=datetime.now(timezone.utc).month
    # Month return = close of current calendar month / previous month - 1.
    month_returns=[]
    for i in range(1,len(rows)):
        dt=datetime.fromisoformat(rows[i]["timestamp"].replace("Z","+00:00"))
        if dt.month==current_month and rows[i-1].get("value"):
            month_returns.append((rows[i]["value"]-rows[i-1]["value"])/rows[i-1]["value"]*100)
    if not month_returns: return {"score":None,"coverage":0.0,"reason":"no same-month history","source":"Yahoo Finance"}
    avg=sum(month_returns)/len(month_returns)
    # +/-2% average monthly bias maps to +/-100.
    score=max(-100,min(100,avg*50))
    return {"score":round(score,2),"coverage":1.0,"average_month_return_pct":round(avg,3),
            "observations":len(month_returns),"month":current_month,"source":"Yahoo Finance"}

async def cftc_currency(currency:str, limit:int=104):
    currency=currency.upper(); market=COT_MARKETS.get(currency)
    if not market:
        return {"currency":currency,"score":None,"coverage":0.0,"reason":"CFTC currency futures proxy unavailable"}
    # Socrata supports filtering and returns JSON without an API key.
    where=f"upper(commodity_name) like '%{market.upper()}%'"
    params={"$limit":limit,"$where":where,"$order":"report_date_as_yyyy_mm_dd DESC"}
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers={"User-Agent":"MacroFX/1.0"}) as client:
        r=await client.get(CFTC_URL,params=params); r.raise_for_status(); data=r.json()
    if not data: return {"currency":currency,"score":None,"coverage":0.0,"reason":"no CFTC rows"}
    latest=data[0]
    def num(k):
        try:return float(latest.get(k))
        except (TypeError,ValueError):return None
    long_=num("noncomm_positions_long_all"); short=num("noncomm_positions_short_all")
    if long_ is None or short is None:return {"currency":currency,"score":None,"coverage":0.0,"reason":"missing non-commercial positions"}
    net=long_-short
    # Percentile/rank over the available history gives a comparable -100..100 signal.
    nets=[]
    for row in data:
        try:nets.append(float(row.get("noncomm_positions_long_all"))-float(row.get("noncomm_positions_short_all")))
        except (TypeError,ValueError):pass
    if len(nets)>=10:
        rank=sum(1 for x in nets if x<=net)/(len(nets)-1)
        score=(rank*2-1)*100
    else: score=max(-100,min(100,net/max(abs(long_+short),1)*100))
    return {"currency":currency,"market":market,"report_date":latest.get("report_date_as_yyyy_mm_dd"),
            "noncommercial_long":long_,"noncommercial_short":short,"net":net,
            "score":round(score,2),"coverage":1.0,"source":"CFTC Legacy Futures Only"}

async def retail_sentiment(pair:str):
    # Myfxbook's Community Outlook is a free community-retail proxy, but its API requires a free session.
    # Credentials are optional and are kept only in Railway environment variables, never in frontend code.
    email=os.getenv("MYFXBOOK_EMAIL"); password=os.getenv("MYFXBOOK_PASSWORD")
    if not email or not password:
        return {"pair":pair,"score":None,"coverage":0.0,
                "reason":"MYFXBOOK_EMAIL and MYFXBOOK_PASSWORD not configured; no retail source is safely keyless",
                "source":"Myfxbook Community Outlook"}
    base="https://www.myfxbook.com/api"
    async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers={"User-Agent":"MacroFX/1.0"}) as client:
        login=await client.get(f"{base}/login.json",params={"email":email,"password":password})
        login.raise_for_status(); lj=login.json()
        if lj.get("error"): return {"pair":pair,"score":None,"coverage":0.0,"reason":"Myfxbook login failed","source":"Myfxbook Community Outlook"}
        session=lj.get("session")
        data=(await client.get(f"{base}/get-community-outlook.json",params={"session":session})).json()
    symbol=next((x for x in data.get("symbols",[]) if str(x.get("name","")).upper()==pair.upper().replace("/","")),None)
    if not symbol:return {"pair":pair,"score":None,"coverage":0.0,"reason":"pair not in Myfxbook community outlook","source":"Myfxbook Community Outlook"}
    long_pct=float(symbol.get("longPercentage",0)); short_pct=float(symbol.get("shortPercentage",0))
    # Contrarian score: more retail long => bearish; more retail short => bullish.
    score=max(-100,min(100,(short_pct-long_pct)*2))
    return {"pair":pair,"long_pct":long_pct,"short_pct":short_pct,"score":round(score,2),"coverage":1.0,
            "source":"Myfxbook Community Outlook (retail proxy)"}
