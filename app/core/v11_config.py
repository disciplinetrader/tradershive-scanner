"""Validated policy configuration for Scanner v1.1 intelligence."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.market import MarketRegime


class AdvancedSetupThresholds(BaseModel):
    """Objective setup limits shared by advanced pattern detectors."""

    model_config = ConfigDict(frozen=True)
    ipo_min_age: int = Field(default=20, ge=10)
    ipo_max_age: int = Field(default=500, ge=20)
    flat_base_min_days: int = 20
    flat_base_max_days: int = 45
    flat_base_max_depth: float = Field(default=0.15, gt=0, lt=1)
    handle_max_depth: float = Field(default=0.12, gt=0, lt=1)
    high_tight_flag_advance: float = Field(default=0.80, gt=0)
    tight_weekly_range: float = Field(default=0.015, gt=0)
    gap_threshold: float = Field(default=0.08, gt=0)
    earnings_event_tolerance_days: int = Field(default=1, ge=0, le=5)
    require_earnings_avwap: bool = True


class VolumeEventThresholds(BaseModel):
    """Volume-event and signature thresholds."""

    model_config = ConfigDict(frozen=True)
    pocket_pivot_lookback: int = Field(default=10, ge=5)
    elevated_volume_ratio: float = Field(default=1.30, gt=1)
    extreme_volume_ratio: float = Field(default=2.50, gt=1)
    weak_close_location: float = Field(default=0.50, ge=0, le=1)
    extension_percent: float = Field(default=0.15, gt=0)


class FollowThroughRules(BaseModel):
    """Objective rally-attempt and follow-through rules."""

    model_config = ConfigDict(frozen=True)
    minimum_gain: float = Field(default=0.0125, gt=0)
    earliest_day: int = Field(default=4, ge=2)
    latest_day: int = Field(default=10, ge=4)
    decline_threshold: float = Field(default=0.08, gt=0)


class MarketPressureRules(BaseModel):
    """Market pressure and distribution aging policy."""

    model_config = ConfigDict(frozen=True)
    distribution_window: int = Field(default=25, ge=10)
    distribution_decline: float = Field(default=0.002, gt=0)
    age_out_advance: float = Field(default=0.06, gt=0)
    extreme_pressure: float = Field(default=80, ge=0, le=100)


class IndustryGroupRules(BaseModel):
    """Industry ranking confidence rules."""

    model_config = ConfigDict(frozen=True)
    minimum_members: int = Field(default=2, ge=1)
    strong_breadth: float = Field(default=70, ge=0, le=100)


class ScannerProfileName(StrEnum):
    """Supported scanner operating profiles."""

    MOMENTUM_BREAKOUT = "Momentum Breakout"
    FIRST_PULLBACK = "First Pullback"
    IPO_LEADER = "IPO Leader"
    TIGHT_BASE = "Tight Base"
    RECOVERY_LEADER = "Recovery Leader"
    CONSERVATIVE_SWING = "Conservative Swing"


class DecisionGates(BaseModel):
    """Post-weighting decision gates."""

    model_config = ConfigDict(frozen=True)
    minimum_buy_score: float = Field(default=80, ge=0, le=100)
    minimum_confidence: float = Field(default=0.75, ge=0, le=1)
    minimum_r: float = Field(default=2, ge=0)
    maximum_failure_risk: float = Field(default=60, ge=0, le=100)
    maximum_market_pressure: float = Field(default=75, ge=0, le=100)
    minimum_rs: float = Field(default=70, ge=0, le=100)


class ScannerProfileConfig(BaseModel):
    """Setup eligibility and thresholds for one scanner profile."""

    model_config = ConfigDict(frozen=True)
    name: ScannerProfileName = ScannerProfileName.MOMENTUM_BREAKOUT
    eligible_setups: tuple[str, ...] = ()
    minimum_rs: float = Field(default=70, ge=0, le=100)
    minimum_leadership_percentile: float = Field(default=50, ge=0, le=100)
    minimum_risk_score: float = Field(default=45, ge=0, le=100)
    minimum_decision_score: float = Field(default=80, ge=0, le=100)
    minimum_sector_percentile: float = Field(default=50, ge=0, le=100)
    minimum_industry_percentile: float = Field(default=50, ge=0, le=100)
    allowed_market_regimes: tuple[MarketRegime, ...] = tuple(MarketRegime)

    @model_validator(mode="before")
    @classmethod
    def apply_named_defaults(cls, data: object) -> object:
        """Populate omitted policy fields from the selected named profile."""
        if not isinstance(data, dict):
            return data
        name = ScannerProfileName(data.get("name", ScannerProfileName.MOMENTUM_BREAKOUT))
        presets: dict[ScannerProfileName, dict[str, object]] = {
            ScannerProfileName.MOMENTUM_BREAKOUT: {
                "eligible_setups": (),
                "minimum_rs": 70,
                "minimum_decision_score": 80,
            },
            ScannerProfileName.FIRST_PULLBACK: {
                "eligible_setups": ("First Pullback", "Breakout Retest"),
                "minimum_rs": 65,
                "minimum_decision_score": 76,
            },
            ScannerProfileName.IPO_LEADER: {
                "eligible_setups": ("IPO Base", "Earnings Gap Consolidation"),
                "minimum_rs": 75,
                "minimum_industry_percentile": 60,
                "minimum_decision_score": 82,
            },
            ScannerProfileName.TIGHT_BASE: {
                "eligible_setups": ("Tight Base", "Flat Base", "Three Weeks Tight", "VCP"),
                "minimum_rs": 70,
                "minimum_decision_score": 78,
            },
            ScannerProfileName.RECOVERY_LEADER: {
                "eligible_setups": ("Wyckoff Spring", "Shakeout Plus Three", "Breakout Retest"),
                "minimum_rs": 60,
                "allowed_market_regimes": (MarketRegime.RECOVERY, MarketRegime.WEAK_BULL),
                "minimum_decision_score": 74,
            },
            ScannerProfileName.CONSERVATIVE_SWING: {
                "eligible_setups": ("VCP", "Tight Base", "Flat Base", "First Pullback"),
                "minimum_rs": 80,
                "minimum_sector_percentile": 70,
                "minimum_industry_percentile": 70,
                "minimum_risk_score": 70,
                "minimum_decision_score": 85,
                "allowed_market_regimes": (MarketRegime.HEALTHY_BULL, MarketRegime.BULL),
            },
        }
        return {**presets[name], **data}


DEFAULT_ADVANCED_SETUP_THRESHOLDS = AdvancedSetupThresholds()
DEFAULT_VOLUME_EVENT_THRESHOLDS = VolumeEventThresholds()
DEFAULT_FOLLOW_THROUGH_RULES = FollowThroughRules()
DEFAULT_MARKET_PRESSURE_RULES = MarketPressureRules()
DEFAULT_INDUSTRY_GROUP_RULES = IndustryGroupRules()
DEFAULT_DECISION_GATES = DecisionGates()
