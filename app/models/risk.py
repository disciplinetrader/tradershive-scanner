"""Typed risk-quality, reward, and position-sizing models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RiskGrade(StrEnum):
    """Risk quality bands, ordered from best to structurally unacceptable."""

    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    REJECT = "Reject"


class PositionSize(BaseModel):
    """Capital-aware integer-share position sizing result."""

    model_config = ConfigDict(frozen=True)

    account_size: float = Field(gt=0)
    risk_percent: float = Field(gt=0, le=100)
    risk_amount: float = Field(ge=0)
    quantity: int = Field(ge=0)
    position_value: float = Field(ge=0)
    actual_risk_percent: float = Field(ge=0, le=100)


class RiskFacts(BaseModel):
    """Calculated downside, reward, sizing, extension, and trading risks."""

    model_config = ConfigDict(frozen=True)

    entry_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    stop_distance: float | None = Field(default=None, gt=0)
    stop_distance_percent: float | None = Field(default=None, gt=0)
    stop_distance_atr: float | None = Field(default=None, gt=0)
    risk_per_share: float | None = Field(default=None, gt=0)
    target_2r: float | None = Field(default=None, gt=0)
    target_3r: float | None = Field(default=None, gt=0)
    target_4r: float | None = Field(default=None, gt=0)
    target_5r: float | None = Field(default=None, gt=0)
    nearest_resistance: float | None = Field(default=None, gt=0)
    available_reward_percent: float | None = Field(default=None, ge=0)
    available_r_multiple: float | None = Field(default=None, ge=0)
    position_size_for_0_25_percent_risk: PositionSize | None = None
    position_size_for_0_50_percent_risk: PositionSize | None = None
    position_size_for_1_00_percent_risk: PositionSize | None = None
    portfolio_heat_contribution: float = Field(ge=0, le=100)
    extension_from_ema20_percent: float
    extension_from_ema50_percent: float
    gap_risk_percent: float = Field(ge=0)
    overnight_risk_score: float = Field(ge=0, le=100)
    liquidity_risk_score: float = Field(ge=0, le=100)
    volatility_risk_score: float = Field(ge=0, le=100)
    structure_risk_score: float = Field(ge=0, le=100)


class RiskProfile(BaseModel):
    """Explainable assessment of structural downside and available reward."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    grade: RiskGrade
    stop_quality_score: float = Field(ge=0, le=100)
    volatility_score: float = Field(ge=0, le=100)
    liquidity_score: float = Field(ge=0, le=100)
    reward_score: float = Field(ge=0, le=100)
    extension_score: float = Field(ge=0, le=100)
    reasons: tuple[str, ...] = Field(min_length=1)
    warnings: tuple[str, ...]
    facts: RiskFacts
