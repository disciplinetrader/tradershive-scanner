"""Typed industry-group leadership intelligence models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IndustryRotation(StrEnum):
    """Industry leadership lifecycle."""

    LEADING = "Leading"
    IMPROVING = "Improving"
    NEUTRAL = "Neutral"
    WEAKENING = "Weakening"
    LAGGING = "Lagging"


class IndustryGroupFacts(BaseModel):
    """Cross-sectional facts for one industry group."""

    model_config = ConfigDict(frozen=True)
    name: str
    parent_sector: str
    member_count: int = Field(ge=1)
    returns: dict[int, float]
    relative_return_nifty: float
    relative_return_sector: float | None = None
    average_rs_percentile: float | None = Field(default=None, ge=0, le=100)
    percentage_above_ema20: float = Field(ge=0, le=100)
    percentage_above_ema50: float = Field(ge=0, le=100)
    percentage_above_ema200: float = Field(ge=0, le=100)
    new_high_percentage: float = Field(ge=0, le=100)
    new_low_percentage: float = Field(ge=0, le=100)
    average_volume_score: float = Field(ge=0, le=100)
    average_setup_score: float | None = Field(default=None, ge=0, le=100)
    buy_candidates: int | None = Field(default=None, ge=0)
    a_plus_setups: int | None = Field(default=None, ge=0)
    leadership_breadth: float = Field(ge=0, le=100)
    momentum_acceleration: float


class IndustryGroupProfile(BaseModel):
    """Ranked explainable industry leadership profile."""

    model_config = ConfigDict(frozen=True)
    rank: int = Field(ge=1)
    percentile: float = Field(ge=0, le=100)
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    rotation: IndustryRotation
    parent_sector: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    facts: IndustryGroupFacts


class IndustryGroupAnalysis(BaseModel):
    """Universe industry profiles and symbol assignments."""

    model_config = ConfigDict(frozen=True)
    groups: dict[str, IndustryGroupProfile]
    symbol_groups: dict[str, str]
    warnings: tuple[str, ...]
