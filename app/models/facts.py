"""Immutable calculated facts consumed by scoring features."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.avwap import AVWAPProfile
from app.models.breadth import BreadthProfile
from app.models.cpr import CPRProfile
from app.models.market import MarketRegime
from app.models.relative_strength import RelativeStrengthProfile
from app.models.risk import RiskGrade, RiskProfile
from app.models.sector import SectorRotation
from app.models.setup import SetupProfile, SetupType
from app.models.stock import StockGrade, StockProfile
from app.models.volume import VolumeProfile


class Facts(BaseModel):
    """Point-in-time technical facts for one equity and its benchmark."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    close: float = Field(gt=0)
    ema20: float = Field(gt=0)
    ema50: float = Field(gt=0)
    ema200: float = Field(gt=0)
    atr14: float = Field(ge=0)
    high_52_week: float = Field(gt=0)
    low_52_week: float = Field(gt=0)
    average_volume: float = Field(ge=0)
    volume_ratio: float = Field(ge=0)
    market_trend: bool
    market_score: float = Field(ge=0, le=100)
    market_confidence: float = Field(ge=0, le=1)
    market_state: MarketRegime
    market_reasons: tuple[str, ...] = Field(min_length=1)
    breadth_score: float = Field(ge=0, le=100)
    breadth_grade: StockGrade
    breadth_profile: BreadthProfile
    cpr_score: float = Field(ge=0, le=100)
    cpr_profile: CPRProfile
    avwap_score: float = Field(ge=0, le=100)
    avwap_profile: AVWAPProfile
    sector_name: str = Field(min_length=1)
    sector_rank: int = Field(ge=0)
    sector_percentile: float = Field(ge=0, le=99)
    sector_score: float = Field(ge=0, le=100)
    sector_confidence: float = Field(ge=0, le=1)
    sector_rotation: SectorRotation
    sector_reasons: tuple[str, ...] = Field(min_length=1)
    stock_score: float = Field(ge=0, le=100)
    stock_grade: StockGrade
    stock_profile: StockProfile
    volume_score: float = Field(ge=0, le=100)
    volume_grade: StockGrade
    volume_profile: VolumeProfile
    setup_score: float = Field(ge=0, le=100)
    setup_grade: StockGrade
    setup_type: SetupType
    setup_profile: SetupProfile
    pivot_price: float | None = Field(default=None, gt=0)
    invalidation_price: float | None = Field(default=None, gt=0)
    breakout_distance_percent: float = Field(ge=0)
    risk_score: float = Field(default=0, ge=0, le=100)
    risk_grade: RiskGrade = RiskGrade.REJECT
    entry_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    available_r_multiple: float | None = Field(default=None, ge=0)
    risk_profile: RiskProfile | None = None
    ema_alignment: bool
    near_52_week_high: bool
    distance_from_high: float = Field(ge=0)
    gap_percent: float
    daily_return: float
    return_63d: float
    benchmark_return_63d: float
    rs5: float
    rs10: float
    rs20: float
    rs50: float
    rs100: float
    rs150: float
    rs250: float
    relative_strength_score: float = Field(ge=0, le=100)
    relative_strength_percentile: float = Field(default=0, ge=0, le=100)
    rs_profile: RelativeStrengthProfile
    annualized_volatility: float = Field(ge=0)
    history_days: int = Field(ge=1)
