"""Typed cross-sectional market breadth intelligence models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.stock import StockGrade


class BreadthState(StrEnum):
    """Participation regimes from broad demand to market-wide distress."""

    BROAD_PARTICIPATION = "Broad Participation"
    HEALTHY_PARTICIPATION = "Healthy Participation"
    NEUTRAL = "Neutral"
    WEAK_PARTICIPATION = "Weak Participation"
    NARROW_LEADERSHIP = "Narrow Leadership"
    DISTRIBUTION = "Distribution"
    CAPITULATION = "Capitulation"


class BreadthTrend(StrEnum):
    """Direction of the rolling advance/decline line."""

    EXPANDING = "Expanding"
    STABLE = "Stable"
    NARROWING = "Narrowing"


class BreadthFacts(BaseModel):
    """Current and longitudinal participation measurements for one universe."""

    model_config = ConfigDict(frozen=True)

    universe_size: int = Field(ge=0)
    valid_symbols: int = Field(ge=0)
    advance_decline_line: float
    advance_decline_ratio: float = Field(ge=0)
    advance_decline_volume: float = Field(ge=0)
    up_volume_percent: float = Field(ge=0, le=100)
    down_volume_percent: float = Field(ge=0, le=100)
    new_highs: int = Field(ge=0)
    new_lows: int = Field(ge=0)
    new_high_low_ratio: float = Field(ge=0)
    percentage_above_ema20: float = Field(ge=0, le=100)
    percentage_above_ema50: float = Field(ge=0, le=100)
    percentage_above_ema100: float = Field(ge=0, le=100)
    percentage_above_ema200: float = Field(ge=0, le=100)
    percentage_above_52_week_high_breakout: float = Field(ge=0, le=100)
    percentage_making_higher_highs: float = Field(ge=0, le=100)
    percentage_making_higher_lows: float = Field(ge=0, le=100)
    distribution_days: int = Field(ge=0)
    follow_through_day: bool
    market_participation_score: float = Field(ge=0, le=100)
    breadth_momentum: float = Field(ge=-100, le=100)
    breadth_trend: BreadthTrend
    breadth_thrust: bool
    history_days: int = Field(ge=0)


class BreadthProfile(BaseModel):
    """Explainable institutional breadth assessment shared by a scan."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    grade: StockGrade
    breadth_state: BreadthState
    participation_score: float = Field(ge=0, le=100)
    trend_score: float = Field(ge=0, le=100)
    momentum_score: float = Field(ge=0, le=100)
    thrust_score: float = Field(ge=0, le=100)
    distribution_score: float = Field(ge=0, le=100)
    reasons: tuple[str, ...] = Field(min_length=1)
    warnings: tuple[str, ...]
    facts: BreadthFacts
