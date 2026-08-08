from __future__ import annotations

import csv
import io
from typing import Any
import httpx

# Public FRED graph CSV endpoints require no FRED API key.
# The catalog deliberately uses transparent series IDs and labels so the
# terminal can show exactly which free source feeds each driver.
FRED_CSV = {
    # United States
    "GDP": "A191RL1Q225SBE",
    "CPI": "CPIAUCSL",
    "PPI": "PPIACO",
    "P