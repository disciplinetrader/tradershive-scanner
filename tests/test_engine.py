"""Tests for feature registration and aggregate scoring."""

import pytest

from app.core.constants import FEATURE_WEIGHTS
from app.engine.registry import FeatureRegistry
from app.engine.scorer import Scorer
from app.features.breadth import BreadthFeature
from app.features.cpr import CPRFeature
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


def production_registry() -> FeatureRegistry:
    """Construct the standard feature registry for tests."""
    return FeatureRegistry(
        [
            MarketFeature(),
            BreadthFeature(),
            CPRFeature(),
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
    )


def test_scorer_returns_all_features_and_bounded_score(bullish_facts: Facts) -> None:
    """Aggregation should retain evidence and remain normalized."""
    result = Scorer(production_registry(), FEATURE_WEIGHTS).score(bullish_facts)
    assert result.symbol == "TEST.NS"
    assert result.final_score > 85
    assert set(result.features) == set(FEATURE_WEIGHTS)
    assert len(result.reasons) >= len(FEATURE_WEIGHTS)


def test_registry_rejects_duplicate_features() -> None:
    """Ambiguous duplicate output keys should be rejected at startup."""
    with pytest.raises(ValueError, match="unique"):
        FeatureRegistry([MarketFeature(), MarketFeature()])


def test_scorer_requires_exact_normalized_weights() -> None:
    """Missing and non-normalized weights should fail fast."""
    registry = FeatureRegistry([MarketFeature()])
    with pytest.raises(ValueError, match="exactly match"):
        Scorer(registry, {"trend": 1})
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        Scorer(registry, {"market": 0.5})
