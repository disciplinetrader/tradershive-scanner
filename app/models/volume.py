"""Typed institutional volume-intelligence models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.stock import StockGrade


class VolumeState(StrEnum):
    """Observable participation states inferred from price and volume."""

    PROFESSIONAL_ACCUMULATION = "Professional Accumulation"
    PROFESSIONAL_DISTRIBUTION = "Professional Distribution"
    HEALTHY = "Healthy"
    NEUTRAL = "Neutral"
    WEAK = "Weak"
    CLIMACTIC = "Climactic"


class VolumeFacts(BaseModel):
    """Point-in-time volume, pressure, and event measurements."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    relative_volume_5: float = Field(ge=0)
    relative_volume_10: float = Field(ge=0)
    relative_volume_20: float = Field(ge=0)
    relative_volume_50: float = Field(ge=0)
    volume_dry_up_percent: float = Field(ge=0, le=100)
    volume_expansion_percent: float
    volume_climax: bool
    volume_churn: bool
    high_volume_reversal: bool
    low_volume_pullback: bool
    pocket_pivot_volume: bool
    volume_contraction_sequence: int = Field(ge=0)
    average_volume_trend: float
    up_volume_percent: float = Field(ge=0, le=100)
    down_volume_percent: float = Field(ge=0, le=100)
    accumulation_days: int = Field(ge=0)
    distribution_days: int = Field(ge=0)
    buying_pressure: float = Field(ge=0, le=100)
    selling_pressure: float = Field(ge=0, le=100)
    volume_momentum: float
    history_days: int = Field(ge=1)


class VolumeProfile(BaseModel):
    """Explainable assessment of institutional participation quality."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    grade: StockGrade
    volume_state: VolumeState
    accumulation_score: float = Field(ge=0, le=100)
    distribution_score: float = Field(ge=0, le=100)
    dryup_score: float = Field(ge=0, le=100)
    expansion_score: float = Field(ge=0, le=100)
    quality_score: float = Field(ge=0, le=100)
    reasons: tuple[str, ...] = Field(min_length=1)
    warnings: tuple[str, ...]
    facts: VolumeFacts
