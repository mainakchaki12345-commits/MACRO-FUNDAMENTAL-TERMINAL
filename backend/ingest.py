from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import FRED_SERIES, fred_series
from storage import init_db, upsert_observations

SERIES_META: dict[str, dict[str, str]] = {
    "GDP": {"country": "US", "currency": "USD", "unit": "percent", "frequency": "quarterly"},
    "CPI": {"country": "US", "currency": "USD", "unit": "index", "frequency": "monthly"},
    "PPI": {"country": "US", "currency": "USD", "unit": "index", "frequency": "monthly"},
    "PCE": {"country": "US", "currency": "USD", "unit": "index", "frequency": "monthly"},
    "POLICY_RATE": {"country": "US", "currency": "USD", "unit": "percent", "frequency": "daily"},
    "UNEMPLOYMENT": {"country": "US", "currency": "USD", "unit": "percent", "frequency": "monthly"},
    "CLAIMS": {"country": "US", "currency": "USD", "unit": "claims", "frequency": "weekly"},
    "RETAIL": {"country": "US", "currency": "USD", "unit": "index", "frequency": "monthly"},
    "JOLTS": {"country": "US", "currency": "USD", "unit": "thousands", "frequency": "monthly"},
    "CONFIDENCE": {"country": "US", "currency": "USD", "unit": "index", "frequency": "monthly"},
    "NFP": {"country": "US", "currency": "USD", "unit": "thousands", "frequency": "monthly"},
}

async def ingest_fred_series(name: str, limit: int = 120) -> int:
    key = name.upper()
    if key not in FRED_SERIES:
        raise ValueError(f"Unknown FRED series: {name}")
    observations = await fred_series(FRED_SERIES[key], limit)
    meta = SERIES_META.get(key, {})
    rows: list[dict[str, Any]] = []
    for i, obs in enumerate(observations):
        try:
            value = float(obs["value"])
        except (TypeError, ValueError):
            continue
        previous = None
        if i + 1 < len(observations):
            try: previous = float(observations[i + 1]["value"])
            except (TypeError, ValueError): pass
        rows.append({
            "source": "FRED", "series": key, "country": meta.get("country"),
            "currency": meta.get("currency"), "timestamp": obs["date"], "value": value,
            "unit": meta.get("unit"), "frequency": meta.get("frequency"),
            "release_timestamp": None, "previous_value": previous, "revision": 0,
            "url": f"https://fred.stlouisfed.org/series/{FRED_SERIES[key]}",
        })
    return upsert_observations(rows)

async def ingest_all_fred() -> dict[str, int]:
    init_db()
    result = {}
    for name in FRED_SERIES:
        result[name] = await ingest_fred_series(name)
    return result
