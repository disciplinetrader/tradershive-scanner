"""Unit tests for every built-in scoring module."""

from app.features.breadth import BreadthFeature
from app.features.market import MarketFeature
from app.features.momentum import MomentumFeature
from app.features.relative_strength import RelativeStrengthFeature
from app.features.risk import RiskFeature
from app.features.sector import SectorFeature
from app.features.setup import SetupFeature
from app.features.stock import StockFeature
from app.features.trend import TrendFeature
from app.features.volatility import VolatilityFeature
from app.features.volume import VolumeFeature
from app.models.facts import Facts
from app.models.market import MarketRegime


def test_all_bullish_features_return_valid_explainable_scores(bullish_facts: Facts) -> None:
    """Every feature should emit normalized scores, confidence, and reasons."""
    features = [
        MarketFeature(),
        BreadthFeature(),
        SectorFeature(),
        StockFeature(),
        SetupFeature(),
        RiskFeature(),
        TrendFeature(),
        RelativeStrengthFeature(),
        MomentumFeature(),
        VolumeFeature(),
        VolatilityFeature(),
    ]
    for feature in features:
        result = feature.evaluate(bullish_facts)
        assert result.name == feature.name
        assert 0 <= result.score <= 100
        assert 0 <= result.confidence <= 1
        assert result.reasons


def test_bullish_facts_score_highly(bullish_facts: Facts) -> None:
    """Strong trend, momentum, participation, and regime should score well."""
    assert MarketFeature().evaluate(bullish_facts).score == 100
    assert BreadthFeature().evaluate(bullish_facts).score == bullish_facts.breadth_score
    assert SectorFeature().evaluate(bullish_facts).score == 95
    assert StockFeature().evaluate(bullish_facts).score == 94
    assert SetupFeature().evaluate(bullish_facts).score == bullish_facts.setup_score
    assert RiskFeature().evaluate(bullish_facts).score == bullish_facts.risk_score
    assert TrendFeature().evaluate(bullish_facts).score == 100
    assert RelativeStrengthFeature().evaluate(bullish_facts).score >= 80
    assert MomentumFeature().evaluate(bullish_facts).score >= 90
    assert VolatilityFeature().evaluate(bullish_facts).score == 100


def test_bearish_changes_reduce_scores(bullish_facts: Facts) -> None:
    """Adverse inputs lower dependent scores without recalculating stored profiles."""
    bearish = bullish_facts.model_copy(
        update={
            "close": 70,
            "market_trend": False,
            "market_score": 20,
            "market_state": MarketRegime.BEAR,
            "market_reasons": ("Decliners exceed advancers",),
            "ema_alignment": False,
            "near_52_week_high": False,
            "distance_from_high": 0.33,
            "return_63d": -0.15,
            "rs5": -0.03,
            "rs10": -0.04,
            "rs20": -0.05,
            "rs50": -0.10,
            "rs100": -0.12,
            "rs150": -0.15,
            "rs250": -0.20,
            "relative_strength_score": 10,
            "relative_strength_percentile": 10,
            "daily_return": -0.04,
            "volume_ratio": 1.8,
        }
    )
    assert MarketFeature().evaluate(bearish).score == 20
    assert TrendFeature().evaluate(bearish).score == 0
    assert RelativeStrengthFeature().evaluate(bearish).score < 50
    assert MomentumFeature().evaluate(bearish).score < 50
    assert VolumeFeature().evaluate(bearish) == VolumeFeature().evaluate(bullish_facts)


def test_extreme_volatility_is_penalized(bullish_facts: Facts) -> None:
    """Highly unstable candidates should receive lower risk scores."""
    unstable = bullish_facts.model_copy(update={"annualized_volatility": 1.2, "atr14": 12})
    assert VolatilityFeature().evaluate(unstable).score < 50
