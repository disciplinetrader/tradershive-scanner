"""Typed sector intelligence facts, ranking, and rotation models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SectorRotation(StrEnum):
    """Cross-sectional sector rotation states."""

    IMPROVING = "Improving"
    LEADING = "Leading"
    WEAKENING = "Weakening"
    LAGGING = "Lagging"


class SectorFacts(BaseModel):
    """Aggregated performance, participation, and liquidity for one sector."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    member_count: int = Field(ge=1)
    return_5d: float
    return_10d: float
    return_20d: float
    return_50d: float
    return_100d: float
    return_150d: float
    return_250d: float
    relative_strength_vs_nifty: float
    average_member_relative_strength: float = Field(ge=0, le=99)
    percentage_above_ema20: float = Field(ge=0, le=100)
    percentage_above_ema50: float = Field(ge=0, le=100)
    percentage_above_ema200: float = Field(ge=0, le=100)
    new_high_percentage: float = Field(ge=0, le=100)
    new_low_percentage: float = Field(ge=0, le=100)
    average_volume_ratio: float = Field(ge=0)
    momentum_score: float = Field(ge=0, le=100)


class SectorProfile(BaseModel):
    """Ranked and explainable sector assessment."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    rank: int = Field(ge=1)
    percentile: float = Field(ge=0, le=99)
    rotation: SectorRotation
    reasons: tuple[str, ...] = Field(min_length=1)
    facts: SectorFacts


class SectorAnalysis(BaseModel):
    """All ranked sectors plus normalized symbol assignments."""

    model_config = ConfigDict(frozen=True)

    sectors: dict[str, SectorProfile]
    symbol_sectors: dict[str, str]
