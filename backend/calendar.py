from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import httpx

URL="https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
PAIR_CURRENCIES={"EURUSD":("EUR","USD"),"GBPUSD":("GBP","USD"),"USDJPY":("USD","JPY"),"USDCHF":("USD","CHF"),"USDCAD":("USD","CAD"),"AUDUSD":("AUD","USD"),"NZDUSD":("NZD","USD"),"EURGBP":("EUR","GBP"),"EURJPY":("EUR","JPY"),"GBPJPY":("GBP","JPY"),"XAUUSD":("USD",)}

def clean(x): return re.sub(r"\s+"," ",(x or "").strip())
def num(x):
    if not x:return None
    s=str(x).replace(",","").replace("%","").strip()
    m=re.search(r"[-+]?\d+(?:\.\d+)?",s)
    try:return float(m.group()) if m else None
    except ValueError:return None

async def weekly_events():
    async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers={"User-Agent":"MacroFX/1.0"}) as client:
        r=await client.get(URL); r.raise_for_status(); raw=r.content
    root=ET.fromstring(raw); out=[]
    for e in root.findall(".//event"):
        row={clean(c.tag).lower():clean(c.text) for c in e}
        country=row.get("country") or row.get("currency") or ""
        actual=row.get("actual"); forecast=row.get("forecast"); previous=row.get("previous")
        av,fv,pv=num(actual),num(forecast),num(previous)
        surprise=None
        if av is not None and fv is not None: surprise=round(av-fv,4)
        out.append({"title":row.get("title",""),"currency":country.upper(),"date":row.get("date",""),"time":row.get("time",""),"impact":row.get("impact",""),"actual":actual or None,"forecast":forecast or None,"previous":previous or None,"actual_numeric":av,"forecast_numeric":fv,"previous_numeric":pv,"surprise":surprise,"source":"ForexFactory weekly calendar feed","source_url":URL})
    return out

async def events_for_pair(pair:str):
    pair=pair.upper().replace("/",""); currencies=PAIR_CURRENCIES.get(pair,(pair[:3],pair[3:]))
    events=await weekly_events()
    filtered=[e for e in events if e["currency"] in currencies]
    return {"pair":pair,"currencies":list(currencies),"events":filtered,"count":len(filtered),"source":"ForexFactory weekly calendar feed","source_url":URL,"generated_at":datetime.now(timezone.utc).isoformat()}
