"""Typed historical validation configuration, ledger, and report models."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntryModel(StrEnum):
    """Supported objective entry assumptions."""

    NEXT_OPEN = "Next-session open"
    NEXT_CLOSE = "Next-session close"
    PIVOT_TRIGGER = "Pivot-trigger entry"
    RISK_PROFILE = "RiskProfile entry"


class AmbiguityPolicy(StrEnum):
    """EOD policy when stop and target coexist in one candle."""

    STOP_FIRST = "Stop first"
    TARGET_FIRST = "Target first"
    FLAG_ONLY = "Flag only"


class TradeOutcome(StrEnum):
    """Historical candidate disposition."""

    WIN = "Win"
    LOSS = "Loss"
    FLAT = "Flat"
    NOT_TRIGGERED = "Not triggered"
    INVALID = "Invalid"
    INCOMPLETE = "Incomplete"


class ValidationConfig(BaseModel):
    """Fixed, auditable assumptions for one historical validation run."""

    model_config = ConfigDict(frozen=True)

    entry_model: EntryModel = EntryModel.NEXT_OPEN
    target_r: int = Field(default=3, ge=2, le=5)
    maximum_holding_sessions: int = Field(default=20)
    ambiguity_policy: AmbiguityPolicy = AmbiguityPolicy.STOP_FIRST
    top_n_values: tuple[int, ...] = (5, 10, 20)
    minimum_warmup_sessions: int = Field(default=260, ge=1)
    universe_as_of: date | None = None
    include_actions: tuple[str, ...] = ("BUY", "WATCHLIST")

    @model_validator(mode="after")
    def validate_options(self) -> "ValidationConfig":
        """Restrict holding periods and comparison cutoffs to supported values."""
        if self.maximum_holding_sessions not in {5, 10, 20, 40}:
            raise ValueError("maximum_holding_sessions must be 5, 10, 20, or 40")
        if not self.top_n_values or any(value <= 0 for value in self.top_n_values):
            raise ValueError("top_n_values must contain positive integers")
        return self


class HistoricalCandidate(BaseModel):
    """Point-in-time scanner output retained without future market data."""

    model_config = ConfigDict(frozen=True)

    scan_date: date
    symbol: str = Field(min_length=1)
    rank: int = Field(ge=1)
    decision_score: float = Field(ge=0, le=100)
    grade: str
    action: str
    setup_type: str
    market_regime: str
    sector: str
    rs_percentile: float = Field(ge=0, le=100)
    volume_state: str
    cpr_state: str
    avwap_state: str
    risk_grade: str
    pivot_price: float | None = Field(default=None, gt=0)
    risk_entry_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    advanced_setup_type: str = "None"
    volume_signature: str = "Neutral"
    pocket_pivot: bool = False
    hidden_accumulation_score: float = 0
    failed_breakout: bool = False
    market_pressure_score: float = 0
    risk_on_state: str = "Neutral"
    follow_through_state: str = "None"
    sector_rotation: str = "Neutral"
    industry_group: str = "Unclassified"
    industry_group_rotation: str = "Neutral"
    scanner_profile: str = "Momentum Breakout"
    ipo_age_sessions: int = 0
    stage_2_first_base: bool = False
    breakout_retest: bool = False


class HistoricalTrade(BaseModel):
    """Forward outcome calculated from bars strictly after a scan date."""

    model_config = ConfigDict(frozen=True)

    candidate: HistoricalCandidate
    entry_date: date | None = None
    entry_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    initial_risk: float | None = Field(default=None, gt=0)
    maximum_favorable_excursion: float = 0
    maximum_adverse_excursion: float = 0
    mfe_r: float = 0
    mae_r: float = 0
    highest_r_reached: float = 0
    target_2r_hit: bool = False
    target_3r_hit: bool = False
    target_4r_hit: bool = False
    target_5r_hit: bool = False
    stop_hit: bool = False
    exit_date: date | None = None
    exit_price: float | None = Field(default=None, gt=0)
    realized_r: float = 0
    holding_sessions: int = Field(default=0, ge=0)
    outcome: TradeOutcome
    ambiguity_flag: bool = False


class ValidationMetrics(BaseModel):
    """Aggregate predictive-value and trade-path statistics."""

    model_config = ConfigDict(frozen=True)

    number_of_scans: int = Field(ge=0)
    number_of_candidates: int = Field(ge=0)
    number_of_triggered_trades: int = Field(ge=0)
    win_rate: float = 0
    loss_rate: float = 0
    average_realized_r: float = 0
    median_realized_r: float = 0
    expectancy: float = 0
    profit_factor: float | None = None
    average_winner_r: float = 0
    average_loser_r: float = 0
    maximum_drawdown_r: float = 0
    longest_losing_streak: int = 0
    average_holding_period: float = 0
    target_2r_hit_rate: float = 0
    target_3r_hit_rate: float = 0
    target_4r_hit_rate: float = 0
    target_5r_hit_rate: float = 0
    average_mfe: float = 0
    average_mae: float = 0
    exposure: float = 0
    turnover: float = 0


class ValidationBreakdown(BaseModel):
    """Metrics grouped by a named scanner dimension."""

    model_config = ConfigDict(frozen=True)
    dimension: str
    groups: dict[str, ValidationMetrics]


class FeatureAnalysis(BaseModel):
    """Predictive evidence for one feature/value cohort."""

    model_config = ConfigDict(frozen=True)
    sample_size: int
    trigger_rate: float
    prevalence: float = 0
    metrics: ValidationMetrics
    win_rate_confidence_interval: tuple[float, float] | None = None


class DataQualitySummary(BaseModel):
    """Auditable limitations in the historical dataset and replay."""

    model_config = ConfigDict(frozen=True)
    score: float = Field(ge=0, le=100)
    missing_symbols: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class WalkForwardPeriod(BaseModel):
    """One explicitly separated in-sample/out-of-sample window."""

    model_config = ConfigDict(frozen=True)
    in_sample_start: date
    in_sample_end: date
    out_of_sample_start: date
    out_of_sample_end: date
    in_sample_metrics: ValidationMetrics
    out_of_sample_metrics: ValidationMetrics


class WalkForwardReport(BaseModel):
    """Fixed-weight rolling walk-forward results."""

    model_config = ConfigDict(frozen=True)
    periods: tuple[WalkForwardPeriod, ...] = ()
    warnings: tuple[str, ...] = ()


class ValidationReport(BaseModel):
    """Complete historical validation result and trade ledger."""

    model_config = ConfigDict(frozen=True)
    config: ValidationConfig
    metrics: ValidationMetrics
    breakdowns: dict[str, ValidationBreakdown]
    top_n_comparison: dict[str, ValidationMetrics]
    trades: tuple[HistoricalTrade, ...]
    walk_forward: WalkForwardReport | None = None
    data_quality: DataQualitySummary
    feature_analysis: dict[str, FeatureAnalysis] = Field(default_factory=dict)
