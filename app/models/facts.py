"""Immutable calculated facts consumed by scoring features."""

from pydantic import BaseModel, ConfigDict, Field


class Facts(BaseModel):
    """Point-in-time technical facts for one equity and its benchmark."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    close: float = Field(gt=0)
    ema20: float = Field(gt=0)
    ema50: float = Field(gt=0)
    ema200: float = Field(gt=0)
    atr14: float = Field(ge=0)
    high_52_week: float = Field(gt=0)
    low_52_week: float = Field(gt=0)
    average_volume: float = Field(ge=0)
    volume_ratio: float = Field(ge=0)
    market_trend: bool
    ema_alignment: bool
    near_52_week_high: bool
    distance_from_high: float = Field(ge=0)
    gap_percent: float
    daily_return: float
    return_63d: float
    benchmark_return_63d: float
    annualized_volatility: float = Field(ge=0)
    history_days: int = Field(ge=1)
