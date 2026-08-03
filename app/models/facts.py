"""Immutable calculated facts consumed by scoring features."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.market import MarketRegime
from app.models.relative_strength import RelativeStrengthProfile


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
    market_score: float = Field(ge=0, le=100)
    market_confidence: float = Field(ge=0, le=1)
    market_state: MarketRegime
    market_reasons: tuple[str, ...] = Field(min_length=1)
    ema_alignment: bool
    near_52_week_high: bool
    distance_from_high: float = Field(ge=0)
    gap_percent: float
    daily_return: float
    return_63d: float
    benchmark_return_63d: float
    rs5: float
    rs10: float
    rs20: float
    rs50: float
    rs100: float
    rs150: float
    rs250: float
    relative_strength_score: float = Field(ge=0, le=100)
    relative_strength_percentile: float = Field(default=0, ge=0, le=100)
    rs_profile: RelativeStrengthProfile
    annualized_volatility: float = Field(ge=0)
    history_days: int = Field(ge=1)
