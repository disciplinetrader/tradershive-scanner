"""Typed intrinsic stock-quality facts and profile models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StockGrade(StrEnum):
    """Commercial quality bands for intrinsic technical strength."""

    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class StockFacts(BaseModel):
    """Point-in-time trend, momentum, participation, and health measurements."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    close: float = Field(gt=0)
    ema20: float = Field(gt=0)
    ema50: float = Field(gt=0)
    ema100: float = Field(gt=0)
    ema150: float = Field(gt=0)
    ema200: float = Field(gt=0)
    ema_alignment: bool
    distance_above_ema20: float
    distance_above_ema50: float
    distance_above_ema200: float
    return_20d: float
    return_50d: float
    return_100d: float
    return_150d: float
    return_250d: float
    atr14: float = Field(ge=0)
    atr_expansion: float
    average_daily_range: float = Field(ge=0)
    distance_from_52_week_high: float = Field(ge=0)
    distance_from_52_week_low: float = Field(ge=0)
    higher_highs: int = Field(ge=0)
    higher_lows: int = Field(ge=0)
    lower_highs: int = Field(ge=0)
    lower_lows: int = Field(ge=0)
    gap_percent: float
    average_gap: float = Field(ge=0)
    relative_volume: float = Field(ge=0)
    average_volume: float = Field(ge=0)
    volume_expansion: bool
    volume_contraction: bool
    new_high: bool
    new_low: bool
    inside_day: bool
    outside_day: bool
    nr7: bool
    history_days: int = Field(ge=1)


class StockProfile(BaseModel):
    """Explainable intrinsic technical-quality assessment for one stock."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    grade: StockGrade
    trend_score: float = Field(ge=0, le=100)
    momentum_score: float = Field(ge=0, le=100)
    participation_score: float = Field(ge=0, le=100)
    health_score: float = Field(ge=0, le=100)
    reasons: tuple[str, ...] = Field(min_length=1)
    facts: StockFacts
