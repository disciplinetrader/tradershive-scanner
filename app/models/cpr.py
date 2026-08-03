"""Typed multi-timeframe Central Pivot Range intelligence models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.stock import StockGrade


class CPRTimeframe(StrEnum):
    """Supported CPR aggregation periods."""

    DAILY = "Daily"
    WEEKLY = "Weekly"
    MONTHLY = "Monthly"


class CPRWidthState(StrEnum):
    """CPR width classifications based on historical percentile."""

    EXTREMELY_NARROW = "Extremely Narrow"
    NARROW = "Narrow"
    NORMAL = "Normal"
    WIDE = "Wide"
    EXTREMELY_WIDE = "Extremely Wide"


class CPRState(StrEnum):
    """Aggregate CPR structures relevant to swing trading."""

    EXTREMELY_NARROW = "Extremely Narrow"
    NARROW = "Narrow"
    NORMAL = "Normal"
    WIDE = "Wide"
    EXTREMELY_WIDE = "Extremely Wide"
    VIRGIN = "Virgin"
    TRENDING = "Trending"
    BALANCED = "Balanced"


class CPRRelationship(StrEnum):
    """Current CPR position relative to its preceding range."""

    OVERLAPPING_HIGHER = "Overlapping Higher"
    OVERLAPPING_LOWER = "Overlapping Lower"
    INSIDE_VALUE = "Inside Value"
    OUTSIDE_VALUE = "Outside Value"
    HIGHER_VALUE = "Higher Value"
    LOWER_VALUE = "Lower Value"
    UNCHANGED = "Unchanged"


class CPRPriceLocation(StrEnum):
    """Latest price position relative to a CPR band."""

    ABOVE = "Above"
    INSIDE = "Inside"
    BELOW = "Below"


class TimeframeCPR(BaseModel):
    """Complete CPR structure for one timeframe."""

    model_config = ConfigDict(frozen=True)

    timeframe: CPRTimeframe
    pivot: float = Field(gt=0)
    tc: float = Field(gt=0)
    bc: float = Field(gt=0)
    width: float = Field(ge=0)
    width_percentile: float = Field(ge=0, le=100)
    width_state: CPRWidthState
    virgin_cpr: bool
    narrow_cpr: bool
    wide_cpr: bool
    overlapping_higher: bool
    overlapping_lower: bool
    inside_value: bool
    outside_value: bool
    higher_value: bool
    lower_value: bool
    trend_cpr: bool
    distance_from_cpr: float
    price_location: CPRPriceLocation
    breakout_distance: float = Field(ge=0)
    relationship_to_previous_cpr: CPRRelationship


class CPRFacts(BaseModel):
    """Daily, weekly, and monthly CPR structures for one symbol."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    close: float = Field(gt=0)
    daily: TimeframeCPR
    weekly: TimeframeCPR
    monthly: TimeframeCPR
    price_above_all_cprs: bool
    price_below_all_cprs: bool
    aligned_higher_value: bool
    aligned_lower_value: bool
    history_days: int = Field(ge=1)


class CPRProfile(BaseModel):
    """Explainable multi-timeframe CPR opportunity assessment."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    grade: StockGrade
    cpr_state: CPRState
    breakout_probability: float = Field(ge=0, le=100)
    trend_probability: float = Field(ge=0, le=100)
    range_probability: float = Field(ge=0, le=100)
    reasons: tuple[str, ...] = Field(min_length=1)
    warnings: tuple[str, ...]
    facts: CPRFacts
