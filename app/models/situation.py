"""Typed scan-level situational awareness models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.avwap import AVWAPState
from app.models.breadth import BreadthProfile
from app.models.market import MarketRegime


class TradingBias(StrEnum):
    """Permitted directional operating biases."""

    LONG_ONLY = "Long Only"
    LONG_BIAS = "Long Bias"
    NEUTRAL = "Neutral"
    SHORT_BIAS = "Short Bias"
    CASH = "Cash"


class Aggression(StrEnum):
    """Scanner aggression levels from most to least permissive."""

    VERY_HIGH = "Very High"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    VERY_LOW = "Very Low"


class RecommendedSetup(StrEnum):
    """Setup families appropriate for the current environment."""

    VCP = "VCP"
    BREAKOUT = "Breakout"
    FIRST_PULLBACK = "First Pullback"
    DARVAS = "Darvas"
    TIGHT_BASE = "Tight Base"
    BULL_FLAG = "Bull Flag"
    WATCHLIST_ONLY = "Watchlist Only"


class RiskEnvironment(StrEnum):
    """Scan-level risk conditions."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    EXTREME = "Extreme"


class MoneyFlow(StrEnum):
    """Broad participation and leadership posture."""

    RISK_ON = "Risk ON"
    NEUTRAL = "Neutral"
    RISK_OFF = "Risk OFF"


class PositionSizingGuidance(StrEnum):
    """Relative position-size guidance, never an account-size assumption."""

    FULL = "100%"
    THREE_QUARTER = "75%"
    HALF = "50%"
    QUARTER = "25%"
    MINIMAL = "10%"


class SectorLeadership(BaseModel):
    """Ranked and rotating sectors from the existing Sector Engine."""

    model_config = ConfigDict(frozen=True)

    top_sectors: tuple[str, ...] = Field(max_length=5)
    bottom_sectors: tuple[str, ...] = Field(max_length=5)
    improving_sectors: tuple[str, ...]
    weakening_sectors: tuple[str, ...]


class SituationProfile(BaseModel):
    """Shared operating posture for one complete scanner run."""

    model_config = ConfigDict(frozen=True)

    market_regime: MarketRegime
    breadth_profile: BreadthProfile | None = None
    cpr_environment: str = "Unavailable"
    cpr_breakout_participation: float = Field(default=0, ge=0, le=100)
    avwap_environment: AVWAPState = AVWAPState.NEUTRAL
    avwap_support_participation: float = Field(default=0, ge=0, le=100)
    trading_bias: TradingBias
    aggression: Aggression
    recommended_setup_types: tuple[RecommendedSetup, ...] = Field(min_length=1)
    market_health: float = Field(ge=0, le=100)
    risk_environment: RiskEnvironment
    sector_leadership: SectorLeadership
    money_flow: MoneyFlow
    position_sizing_guidance: PositionSizingGuidance
    recommended_maximum_open_positions: int = Field(ge=0)
    maximum_risk_per_trade: float = Field(ge=0, le=100)
    expected_holding_period: str = Field(min_length=1)
    reasons: tuple[str, ...] = Field(min_length=1)
    recommended_strategy: tuple[str, ...] = Field(min_length=1)
    warnings: tuple[str, ...]
