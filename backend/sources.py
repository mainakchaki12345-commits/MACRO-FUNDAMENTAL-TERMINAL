from __future__ import annotations

import csv
import io
from typing import Any

import httpx


async def cftc_public() -> list[dict[str, Any]]:
    """Fetch the CFTC public historical futures report when available.

    CFTC publishes public downloadable datasets. The parser is intentionally
    conservative: if the upstream schema changes, return an empty list rather
    than silently producing incorrect positioning numbers.
    """
    urls = [
        "https://www.cftc.gov/files/dea/history/fut_fin_txt_2026.zip",
    ]
    # ZIP parsing is kept out of the first adapter so a schema mismatch cannot
    # contaminate the scoring engine. A dedicated CFTC parser can be added once
    # the exact report contract is selected for each currency future.
    return []


async def ecb_reference_rates() -> list[dict[str, Any]]:
    """Return ECB reference-rate observations if the public endpoint responds."""
    url = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    params = {"format": "csvdata", "lastNObservations": "30"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
        rows = csv.DictReader(io.StringIO(r.text))
        result = []
        for row in rows:
            value = row.get("OBS_VALUE")
            if value:
                result.append({
                    "date": row.get("TIME_PERIOD"),
                    "value": float(value),
                    "source": "ECB",
                    "series": "EURUSD_REFERENCE",
                })
        return result
    except Exception:
        return []
