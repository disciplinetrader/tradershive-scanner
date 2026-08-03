"""Typed Anchored VWAP intelligence models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.stock import StockGrade


class AVWAPAnchorType(StrEnum):
    """Supported anchor events; custom resolvers may add typed definitions."""

    SWING_HIGH = "Swing High"
    SWING_LOW = "Swing Low"
    HIGH_52_WEEK = "52 Week High"
    LOW_52_WEEK = "52 Week Low"
    BREAKOUT_DAY = "Breakout Day"
    GAP_UP = "Gap Up"
    GAP_DOWN = "Gap Down"
    EARNINGS_GAP = "Earnings Gap"
    IPO_DAY = "IPO Day"
    USER_DEFINED = "User-defined"


class AVWAPState(StrEnum):
    """Institutional cost-basis relationship."""

    STRONG_SUPPORT = "Strong Support"
    SUPPORT = "Support"
    NEUTRAL = "Neutral"
    RESISTANCE = "Resistance"
    STRONG_RESISTANCE = "Strong Resistance"
    RECLAIMED = "Reclaimed"
    LOST = "Lost"


class AVWAPAnchor(BaseModel):
    """A resolved anchor accepted by the calculation engine."""

    model_config = ConfigDict(frozen=True)
    anchor_type: AVWAPAnchorType
    position: int = Field(ge=0)
    timestamp: datetime
    label: str = Field(min_length=1)


class AnchorAVWAPFacts(BaseModel):
    """Calculated behavior around one institutional cost basis."""

    model_config = ConfigDict(frozen=True)
    anchor: AVWAPAnchor
    anchored_vwap: float = Field(gt=0)
    distance_percent: float
    above_avwap: bool
    slope: float
    touch_count: int = Field(ge=0)
    respect_count: int = Field(ge=0)
    cross_count: int = Field(ge=0)
    support_strength: float = Field(ge=0, le=100)
    resistance_strength: float = Field(ge=0, le=100)
    compression_around_avwap: bool
    reclaim_detected: bool
    loss_detected: bool
    state: AVWAPState


class AVWAPFacts(BaseModel):
    """All resolved AVWAP structures for a stock."""

    model_config = ConfigDict(frozen=True)
    symbol: str = Field(min_length=1)
    close: float = Field(gt=0)
    anchors: tuple[AnchorAVWAPFacts, ...]
    history_days: int = Field(ge=1)


class AVWAPProfile(BaseModel):
    """Explainable aggregate Anchored VWAP assessment."""

    model_config = ConfigDict(frozen=True)
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    grade: StockGrade
    state: AVWAPState
    support_score: float = Field(ge=0, le=100)
    resistance_score: float = Field(ge=0, le=100)
    alignment_score: float = Field(ge=0, le=100)
    anchor_summary: dict[str, str]
    reasons: tuple[str, ...] = Field(min_length=1)
    warnings: tuple[str, ...]
    facts: AVWAPFacts
