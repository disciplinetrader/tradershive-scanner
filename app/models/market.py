"""Typed market-intelligence facts and aggregate profile."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MarketRegime(StrEnum):
    """Supported market-quality regimes from strongest to most distressed."""

    HEALTHY_BULL = "Healthy Bull"
    BULL = "Bull"
    WEAK_BULL = "Weak Bull"
    RANGE = "Range"
    WEAK_BEAR = "Weak Bear"
    BEAR = "Bear"
    CAPITULATION = "Capitulation"
    RECOVERY = "Recovery"


class MarketFacts(BaseModel):
    """Point-in-time technical quality facts for one market benchmark."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    close: float = Field(gt=0)
    ema20: float = Field(gt=0)
    ema50: float = Field(gt=0)
    ema200: float = Field(gt=0)
    return_20d: float
    return_50d: float
    return_150d: float
    return_250d: float
    atr14: float = Field(ge=0)
    relative_volume: float = Field(ge=0)
    distance_from_52_week_high: float = Field(ge=0)
    new_high: bool
    new_low: bool
    above_ema20: bool
    above_ema50: bool
    above_ema200: bool


class MarketBreadth(BaseModel):
    """Cross-sectional participation across the scanned stock universe."""

    model_config = ConfigDict(frozen=True)

    universe_size: int = Field(ge=0)
    advancers: int = Field(ge=0)
    decliners: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    advance_decline_ratio: float = Field(ge=0)
    percentage_above_ema20: float = Field(ge=0, le=100)
    percentage_above_ema50: float = Field(ge=0, le=100)
    percentage_above_ema200: float = Field(ge=0, le=100)
    new_highs: int = Field(ge=0)
    new_lows: int = Field(ge=0)


class MarketVolatility(BaseModel):
    """Market-wide volatility and discontinuity measures."""

    model_config = ConfigDict(frozen=True)

    india_vix: float | None = Field(default=None, ge=0)
    atr_expansion: float
    gap_frequency: float = Field(ge=0, le=1)


class MarketProfile(BaseModel):
    """Complete market regime assessment and its supporting evidence."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    state: MarketRegime
    reasons: tuple[str, ...] = Field(min_length=1)
    indexes: dict[str, MarketFacts]
    breadth: MarketBreadth
    volatility: MarketVolatility
