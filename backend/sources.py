from __future__ import annotations

import csv
import io
from typing import Any
import httpx

# FRED graph CSV endpoints are public and do not require a FRED API key.
FRED_CSV = {
    "GDP": "A191RL1Q225SBE",
    "CPI": "CPIAUCSL",
    "PPI": "PPIACO",
    "PCE": "PCEPI",
    "POLICY_RATE": "FEDFUNDS",
    "UNEMPLOYMENT": "UNRATE",
    "CLAIMS": "ICSA",
    "RETAIL": "RSAFS",
    "JOLTS": "JTSJOL",
    "CONFIDENCE": "UMCSENT",
    "NFP": "PAYEMS",
}

# World Bank provides free, keyless historical macro observations.
# Annual frequency is intentionally preserved; the UI can show frequency/source.
WORLD_BANK_COUNTRIES = {
    "USD": "USA", "EUR": "EMU", "GBP": "GBR", "JPY": "JPN",
    "CHF": "CHE", "CAD": "CAN", "AUD": "AUS", "NZD": "NZL",
}
WORLD_BANK_INDICATORS = {
    "WB_GDP_GROWTH": "NY.GDP.MKTP.KD.ZG",
    "WB_INFLATION": "FP.CPI.TOTL.ZG",
    "WB_UNEMPLOYMENT": "SL.UEM.TOTL.ZS",
}

async def _get(url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r

async def fred_csv(series_id: str, limit: int = 120) -> list[dict[str, Any]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = await _get(url)
    result = []
    for row in csv.DictReader(io.StringIO(r.text)):
        value = row.get(series_id)
        if value in (None, ".", ""):
            continue
        try:
            result.append({"date": row["observation_date"], "value": float(value)})
        except (KeyError, ValueError):
            continue
    return list(reversed(result))[-limit:]

async def world_bank_indicator(currency: str, indicator: str, limit: int = 30) -> list[dict[str, Any]]:
    country = WORLD_BANK_COUNTRIES[currency.upper()]
    indicator_id = WORLD_BANK_INDICATORS[indicator]
    url = f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator_id}"
    r = await _get(url, {"format": "json", "per_page": limit})
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    result = []
    for row in payload[1]:
        value = row.get("value")
        if value is None:
            continue
        result.append({
            "date": str(row.get("date")),
            "value": float(value),
            "source": "World Bank",
            "series": indicator,
            "currency": currency.upper(),
            "country": country,
            "frequency": "annual",
        })
    return list(reversed(result))

async def ecb_reference_rates() -> list[dict[str, Any]]:
    # ECB reference rate: USD per EUR. This is a market/reference series,
    # not the ECB policy rate; it is useful for price/FX context only.
    url = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    r = await _get(url, {"format": "csvdata", "lastNObservations": "120"})
    result = []
    for row in csv.DictReader(io.StringIO(r.text)):
        value = row.get("OBS_VALUE")
        if not value:
            continue
        try:
            result.append({
                "date": row.get("TIME_PERIOD"),
                "value": float(value),
                "source": "ECB",
                "series": "EURUSD_REFERENCE",
                "currency": "EUR",
                "frequency": "daily",
            })
        except (TypeError, ValueError):
            continue
    return result

async def public_fred_snapshot(limit: int = 120):
    out = {}
    for name, sid in FRED_CSV.items():
        try:
            out[name] = await fred_csv(sid, limit)
        except Exception as e:
            out[name] = {"error": str(e)}
    return out
