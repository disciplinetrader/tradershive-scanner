"""Typed swing-setup observations and aggregate profile models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.stock import StockGrade


class SetupType(StrEnum):
    """Objective price-and-volume structures supported in version one."""

    VCP = "VCP"
    TIGHT_BASE = "Tight Base"
    DARVAS_BOX = "Darvas Box"
    BULL_FLAG = "Bull Flag"
    FIRST_PULLBACK = "First Pullback"
    INSIDE_DAY = "Inside Day"
    NR7 = "NR7"
    BREAKOUT_READY = "Breakout Ready"
    NONE = "None"


class ContractionDetail(BaseModel):
    """Measured high-to-low contraction within one chronological segment."""

    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1, le=5)
    depth_percent: float = Field(ge=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    sessions: int = Field(ge=1)


class SetupFacts(BaseModel):
    """Shared objective measurements used by all setup detectors."""

    model_config = ConfigDict(frozen=True)

    setup_type: SetupType
    setup_score: float = Field(ge=0, le=100)
    setup_confidence: float = Field(ge=0, le=1)
    pivot_price: float | None = Field(default=None, gt=0)
    invalidation_price: float | None = Field(default=None, gt=0)
    base_high: float = Field(gt=0)
    base_low: float = Field(gt=0)
    base_depth_percent: float = Field(ge=0)
    base_length_days: int = Field(ge=1)
    contraction_count: int = Field(ge=0, le=5)
    latest_contraction_percent: float = Field(ge=0)
    prior_contraction_percent: float = Field(ge=0)
    contractions: tuple[ContractionDetail, ...]
    volume_dry_up_ratio: float = Field(ge=0)
    breakout_distance_percent: float = Field(ge=0)
    overhead_resistance_percent: float = Field(ge=0)
    first_pullback_detected: bool
    inside_day: bool
    nr7: bool
    tight_closes_count: int = Field(ge=0)
    range_contraction_ratio: float = Field(ge=0)


class SetupCandidate(BaseModel):
    """Score and evidence for one independently evaluated setup type."""

    model_config = ConfigDict(frozen=True)

    setup_type: SetupType
    detected: bool
    score: float = Field(ge=0, le=100)
    reasons: tuple[str, ...] = Field(min_length=1)


class SetupProfile(BaseModel):
    """Best actionable structure with component scores and all candidates."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    grade: StockGrade
    pattern_score: float = Field(ge=0, le=100)
    structure_score: float = Field(ge=0, le=100)
    compression_score: float = Field(ge=0, le=100)
    volume_score: float = Field(ge=0, le=100)
    location_score: float = Field(ge=0, le=100)
    best_setup_type: SetupType
    reasons: tuple[str, ...] = Field(min_length=1)
    facts: SetupFacts
    candidates: tuple[SetupCandidate, ...] = Field(min_length=8, max_length=8)
