"""Typed explainable decision output models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DecisionAction(StrEnum):
    """Permitted scanner dispositions without execution semantics."""

    BUY = "BUY"
    WATCHLIST = "WATCHLIST"
    AVOID = "AVOID"


class DecisionGrade(StrEnum):
    """Aggregate trade-quality grades."""

    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    REJECT = "Reject"


class WeightedDecisionComponent(BaseModel):
    """Auditable contribution from one existing intelligence profile."""

    model_config = ConfigDict(frozen=True)

    weight: float = Field(gt=0, lt=1)
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=100)


class DecisionProfile(BaseModel):
    """One adaptive, explainable scanner decision."""

    model_config = ConfigDict(frozen=True)

    decision_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    grade: DecisionGrade
    action: DecisionAction
    reasons: tuple[str, ...] = Field(min_length=1)
    warnings: tuple[str, ...]
    weight_breakdown: dict[str, WeightedDecisionComponent] = Field(min_length=7, max_length=7)
