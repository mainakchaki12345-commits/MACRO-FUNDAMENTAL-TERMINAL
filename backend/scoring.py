from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from engine import DRIVER_WEIGHTS, clamp, weighted_score, pair_score, DriverResult

@dataclass
class Observation:
    current: Optional[float]
    previous: Optional[float]


def momentum(o: Observation, higher_is_better: bool = True) -> DriverResult:
    if o.current is None or o.previous is None or o.previous == 0:
        return DriverResult(None, 0.0, "missing observation")
    change = (o.current - o.previous) / abs(o.previous) * 100.0
    if not higher_is_better: change = -change
    return DriverResult(clamp(change * 20.0), 1.0)


def combine(results: list[DriverResult]) -> DriverResult:
    usable=[r for r in results if r.score is not None and r.coverage>0]
    if not usable:return DriverResult(None,0.0,"no usable observations")
    score=sum(r.score*r.coverage for r in usable)/sum(r.coverage for r in usable)
    coverage=min(1.0,sum(r.coverage for r in usable)/len(results))
    return DriverResult(round(clamp(score),2),round(coverage,3))


def growth(gdp: Observation, pmi: Observation, retail: Observation, confidence: Observation) -> DriverResult:
    return combine([momentum(gdp), momentum(pmi), momentum(retail), momentum(confidence)])


def inflation(cpi: Observation, ppi: Observation, pce: Observation) -> DriverResult:
    # Inflation is not inherently bullish/bearish. This driver measures acceleration;
    # the interpretation layer can combine it with the central-bank/rate regime.
    return combine([momentum(cpi), momentum(ppi), momentum(pce)])


def employment(nfp: Observation, unemployment: Observation, claims: Observation, adp: Observation, jolts: Observation) -> DriverResult:
    return combine([
        momentum(nfp, True),
        momentum(unemployment, False),
        momentum(claims, False),
        momentum(adp, True),
        momentum(jolts, True),
    ])


def rate_differential(base_rate: Optional[float], quote_rate: Optional[float]) -> DriverResult:
    if base_rate is None or quote_rate is None:
        return DriverResult(None,0.0,"missing policy rate")
    # A 5 percentage-point differential maps to +100/-100.
    return DriverResult(round(clamp((base_rate-quote_rate)*20.0),2),1.0)


def currency_score(drivers: dict[str, DriverResult]):
    return weighted_score(drivers)


def pair_currency_score(base_score: Optional[float], quote_score: Optional[float], base_coverage: float, quote_coverage: float):
    return pair_score(base_score, quote_score, base_coverage, quote_coverage)
