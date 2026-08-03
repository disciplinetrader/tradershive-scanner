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


class RiskOnState(StrEnum):
    """Cross-asset market risk posture."""

    STRONG_RISK_ON = "Strong Risk-On"
    RISK_ON = "Risk-On"
    NEUTRAL = "Neutral"
    RISK_OFF = "Risk-Off"
    STRONG_RISK_OFF = "Strong Risk-Off"


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
    rally_attempt: bool = False
    rally_attempt_day: int = 0
    follow_through_day: bool = False
    failed_follow_through: bool = False
    active_distribution_days: int = 0
    aged_out_distribution_days: int = 0
    distribution_pressure: float = Field(default=0, ge=0, le=100)
    market_pressure_score: float = Field(default=0, ge=0, le=100)
    risk_on_state: RiskOnState = RiskOnState.NEUTRAL
    leadership_expansion: bool = False
    leadership_contraction: bool = False
    breakout_attempts: int = 0
    breakout_success_rate: float = 0
    failed_breakout_rate: float = 0
    average_post_breakout_return: float = 0
    average_breakout_mfe: float = 0
    average_breakout_mae: float = 0
    opportunity_count: dict[str, int] = Field(default_factory=dict)
    regime_transition: str = "Stable"
    index_divergence: tuple[str, ...] = ()
