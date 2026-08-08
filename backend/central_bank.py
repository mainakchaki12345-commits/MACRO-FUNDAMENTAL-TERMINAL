from __future__ import annotations
import re
from datetime import datetime, timezone
import httpx

URL = "https://www.global-rates.com/en/interest-rates/central-banks/"
MAP = {
    "USD": "American Central Bank", "EUR": "European Central Bank", "GBP": "British Central Bank",
    "JPY": "Japanese Central Bank", "CHF": "Swiss Central Bank", "CAD": "Canadian Central Bank",
    "AUD": "Australian Central Bank", "NZD": "New Zealand Central Bank",
}

async def policy_rates() -> dict[str, dict]:
    """Free public fallback table. Values are labeled as an external reference, not an official API."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent":"MacroFX/1.0"}) as client:
        r = await client.get(URL)
        r.raise_for_status()
        html = r.text
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    out={}
    for c,name in MAP.items():
        # Current rate appears close to the bank name in the public overview table.
        m=re.search(re.escape(name)+r".*?(\d+(?:\.\d+)?)\s*%\s*(?:[^0-9]{0,80}(\d{2}-\d{2}-\d{4}))?", text, re.I)
        if m:
            out[c]={"currency":c,"rate":float(m.group(1)),"date":m.group(2),"source":"Global-Rates public central-bank overview","source_url":URL}
    return out

async def policy_rate(currency:str) -> dict:
    data=await policy_rates()
    return data.get(currency.upper(),{"currency":currency.upper(),"rate":None,"source":"Global-Rates public central-bank overview"})

# High-level event windows are intentionally informational. Exact meeting calendars should be
# added from each central bank's official calendar when available; no forecast is invented here.
CENTRAL_BANK_NAMES = {
    "USD":"Federal Reserve", "EUR":"European Central Bank", "GBP":"Bank of England",
    "JPY":"Bank of Japan", "CHF":"Swiss National Bank", "CAD":"Bank of Canada",
    "AUD":"Reserve Bank of Australia", "NZD":"Reserve Bank of New Zealand",
}
