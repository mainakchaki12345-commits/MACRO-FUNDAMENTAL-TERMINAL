from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DRIVER_WEIGHTS = {
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

@dataclass
class DriverResult:
    score: Optional[float]
    coverage: float
    reason: str = ""


def clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def normalize_change(current: Optional[float], previous: Optional[float],
                     higher_is_better: bool = True) -> DriverResult:
    if current is None or previous is None:
        return DriverResult(None, 0.0, "missing observation")
    if previous == 0:
        return DriverResult(None, 0.0, "previous value is zero")
    change = (current - previous) / abs(previous) * 100.0
    if not higher_is_better:
        change = -change
    # 5% relative movement maps to a full 100-point driver score.
    return DriverResult(clamp(change * 20.0), 1.0)


def weighted_score(drivers: dict[str, DriverResult]) -> tuple[Optional[float], float]:
    weighted = 0.0
    used_weight = 0.0
    total_weight = sum(DRIVER_WEIGHTS.values())
    for name, weight in DRIVER_WEIGHTS.items():
        result = drivers.get(name)
        if result and result.score is not None and result.coverage > 0:
            weighted += result.score * weight * result.coverage
            used_weight += weight * result.coverage
    if used_weight == 0:
        return None, 0.0
    score = weighted / used_weight
    return round(clamp(score), 2), round(used_weight / total_weight, 3)


def pair_score(base: Optional[float], quote: Optional[float],
               base_coverage: float, quote_coverage: float) -> tuple[Optional[float], float, str]:
    if base is None or quote is None:
        return None, min(base_coverage, quote_coverage), "INSUFFICIENT_DATA"
    score = clamp(base - quote)
    if score >= 60:
        signal = "STRONG_BULLISH"
    elif score >= 20:
        signal = "BULLISH"
    elif score <= -60:
        signal = "STRONG_BEARISH"
    elif score <= -20:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"
    return round(score, 2), min(base_coverage, quote_coverage), signal
