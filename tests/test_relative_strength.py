"""Unit, integration, and performance tests for relative strength."""

from time import perf_counter

import pandas as pd

from app.core.constants import FEATURE_WEIGHTS
from app.data.loader import DataLoader
from app.engine.registry import FeatureRegistry
from app.engine.scorer import Scorer
from app.features.breadth import BreadthFeature
from app.features.market import MarketFeature
from app.features.momentum import MomentumFeature
from app.features.relative_strength import (
    RelativeStrengthFeature,
    assign_relative_strength_percentiles,
)
from app.features.risk import RiskFeature
from app.features.sector import SectorFeature
from app.features.setup import SetupFeature
from app.features.stock import StockFeature
from app.features.trend import TrendFeature
from app.features.volatility import VolatilityFeature
from app.features.volume import VolumeFeature
from app.models.facts import Facts
from app.models.relative_strength import RelativeStrengthHorizon, RelativeStrengthProfile
from app.models.stock_result import StockResult
from app.providers.base import MarketDataError, MarketDataProvider
from app.scanner.scanner import Scanner


def _stock_result(facts: Facts, strength: float) -> StockResult:
    """Build a minimal aggregate result for percentile tests."""
    profile = RelativeStrengthProfile(
        **{
            f"rs{period}": RelativeStrengthHorizon(relative_return=strength)
            for period in (5, 10, 20, 50, 100, 150, 250)
        }
    )
    updated = facts.model_copy(
        update={
            "rs5": strength,
            "rs10": strength,
            "rs20": strength,
            "rs50": strength,
            "rs100": strength,
            "rs150": strength,
            "rs250": strength,
            "rs_profile": profile,
        }
    )
    return StockResult(symbol=updated.symbol, final_score=50, features={}, facts=updated)


def test_relative_strength_feature_uses_weighted_engine_score(bullish_facts: Facts) -> None:
    """The feature should expose facts-engine RS rather than recalculate RSI-like momentum."""
    result = RelativeStrengthFeature().evaluate(bullish_facts)
    assert result.score == 90
    assert result.confidence == 1
    assert "Top 3% over 250 sessions" in result.reasons
    assert "Strong intermediate-term leadership" in result.reasons
    assert "Short-term momentum improving" in result.reasons


def test_percentiles_rank_universe_and_average_ties(bullish_facts: Facts) -> None:
    """Cross-sectional rankings should span zero to 100 and give ties equal ratings."""
    scores = [97.0, 42.0, 91.0, 91.0]
    symbols = ["HAL.NS", "BEL.NS", "SBIN.NS", "TIE.NS"]
    candidates = [
        _stock_result(
            bullish_facts.model_copy(update={"symbol": symbol}),
            score,
        )
        for symbol, score in zip(symbols, scores, strict=True)
    ]

    ranked = assign_relative_strength_percentiles(candidates)
    percentiles = {result.symbol: result.facts.relative_strength_percentile for result in ranked}

    assert percentiles == {"HAL.NS": 99.0, "BEL.NS": 0.0, "SBIN.NS": 49.5, "TIE.NS": 49.5}


def test_single_stock_receives_full_percentile(bullish_facts: Facts) -> None:
    """A one-stock universe should have a defined, maximal percentile."""
    result = assign_relative_strength_percentiles([_stock_result(bullish_facts, 0.05)])
    assert result[0].facts.relative_strength_percentile == 100


def test_percentiles_are_stable_across_market_regimes(bullish_facts: Facts) -> None:
    """Uniformly stronger or weaker markets should preserve relative leadership scores."""
    baseline = [
        _stock_result(bullish_facts.model_copy(update={"symbol": f"B{index}.NS"}), strength)
        for index, strength in enumerate((-0.10, 0.00, 0.10))
    ]
    bullish_regime = [
        _stock_result(bullish_facts.model_copy(update={"symbol": f"R{index}.NS"}), strength)
        for index, strength in enumerate((0.20, 0.30, 0.40))
    ]

    baseline_scores = [
        result.facts.relative_strength_score
        for result in assign_relative_strength_percentiles(baseline)
    ]
    regime_scores = [
        result.facts.relative_strength_score
        for result in assign_relative_strength_percentiles(bullish_regime)
    ]

    assert baseline_scores == regime_scores == [0, 49.5, 99]


def test_percentile_benchmark_handles_ten_thousand_results(
    bullish_facts: Facts,
) -> None:
    """Universe ranking should remain practical for a full Indian equity universe."""
    candidates = [
        _stock_result(
            bullish_facts.model_copy(update={"symbol": f"S{index}.NS"}),
            (index % 101) / 100,
        )
        for index in range(10_000)
    ]
    started = perf_counter()
    ranked = assign_relative_strength_percentiles(candidates)
    elapsed = perf_counter() - started
    assert len(ranked) == 10_000
    assert elapsed < 5


class FallbackProvider(MarketDataProvider):
    """Fail a configured index while serving NIFTY and equity histories."""

    def __init__(self, frame: pd.DataFrame) -> None:
        """Store deterministic history and requested symbols."""
        self._frame = frame
        self.requested: list[str] = []

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Reject the custom benchmark and return stock-specific performance."""
        self.requested.append(symbol)
        if symbol == "^CUSTOM":
            raise MarketDataError("custom index unavailable")
        frame = self._frame.copy()
        if symbol == "LEADER.NS":
            growth = pd.Series(range(len(frame)), index=frame.index) / len(frame)
            frame.loc[:, "Close"] = frame["Close"] * (1 + growth)
            frame.loc[:, "Open"] = frame["Close"]
            frame.loc[:, "High"] = frame["Close"] * 1.01
            frame.loc[:, "Low"] = frame["Close"] * 0.99
        return frame


def _production_scorer() -> Scorer:
    """Construct the standard scorer for integration testing."""
    registry = FeatureRegistry(
        [
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
    )
    return Scorer(registry, FEATURE_WEIGHTS)


def test_scanner_falls_back_to_nifty_and_assigns_percentiles(
    rising_frame: pd.DataFrame,
) -> None:
    """An unavailable configured benchmark should fall back to NIFTY 50."""
    provider = FallbackProvider(rising_frame)
    scanner = Scanner(DataLoader(provider), _production_scorer(), "^CUSTOM")

    results = scanner.scan(["LEADER", "BASE"])

    assert provider.requested[:2] == ["^CUSTOM", "^NSEI"]
    by_symbol = {result.symbol: result for result in results}
    assert by_symbol["LEADER.NS"].facts.relative_strength_score > 50
    assert by_symbol["LEADER.NS"].facts.relative_strength_percentile == 99
    assert by_symbol["LEADER.NS"].features["relative_strength"].score == 99
    assert by_symbol["BASE.NS"].facts.relative_strength_percentile == 0
    assert by_symbol["BASE.NS"].features["relative_strength"].score == 0
