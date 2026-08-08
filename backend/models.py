from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

class DriverScore(BaseModel):
    score: Optional[float] = None
    coverage: float = Field(ge=0, le=1)
    reason: str = ""

class CurrencyScore(BaseModel):
    currency: str
    score: Optional[float] = None
    coverage: float = Field(ge=0, le=1)
    drivers: dict[str, DriverScore]

class PairScore(BaseModel):
    pair: str
    score: Optional[float] = None
    coverage: float = Field(ge=0, le=1)
    signal: str
    base: CurrencyScore
    quote: CurrencyScore
