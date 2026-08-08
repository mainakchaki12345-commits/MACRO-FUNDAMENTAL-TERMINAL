from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MacroFX Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEIGHTS = {
    "technicals": 0.10,
    "sentiment": 0.08,
    "cot": 0.12,
    "seasonality": 0.06,
    "growth": 0.15,
    "inflation": 0.12,
    "rates": 0.18,
    "employment": 0.10,
    "central_bank": 0.09,
}

FRED_SERIES = {
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


def empty_driver() -> dict[str, Any]:
    return {"score": None, "coverage": 0, "observations": []}


def currency_template(currency: str) -> dict[str, Any]:
    return {
        "currency": currency,
        "drivers": {name: empty_driver() for name in WEIGHTS},
        "score": None,
        "coverage": 0,
    }


async def fred_series(series_id: str, limit: int = 24) -> list[dict[str, Any]]:
    key = os.getenv("FRED_API_KEY")
    if not key:
        return []
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": str(limit),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        return [
            {
                "date": item["date"],
                "value": item["value"],
                "series_id": series_id,
                "source": "FRED",
            }
            for item in data.get("observations", [])
            if item.get("value") not in (None, ".")
        ]
    except Exception:
        return []


@app.get("/")
async def root():
    return {"name": "MacroFX Backend", "status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/health")
async def health():
    return {"status": "ok", "fred_configured": bool(os.getenv("FRED_API_KEY"))}


@app.get("/api/pairs/{pair}")
async def pair_snapshot(pair: str):
    pair = pair.upper()
    if len(pair) not in (6,):
        return {"error": "pair must look like EURUSD"}
    base, quote = pair[:3], pair[3:]
    return {
        "pair": f"{base}/{quote}",
        "base": currency_template(base),
        "quote": currency_template(quote),
        "score": None,
        "signal": "INSUFFICIENT_DATA",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/fred/{series_name}")
async def fred_named(series_name: str):
    series_id = FRED_SERIES.get(series_name.upper())
    if not series_id:
        return {"error": "unknown series", "available": sorted(FRED_SERIES)}
    return {
        "series": series_name.upper(),
        "series_id": series_id,
        "observations": await fred_series(series_id),
    }


@app.get("/api/config")
async def config():
    return {"weights": WEIGHTS, "fred_series": FRED_SERIES}
