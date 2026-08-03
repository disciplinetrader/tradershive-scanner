"""Unit, integration, and performance tests for Market Intelligence."""

from time import perf_counter

import pandas as pd
import pytest

from app.core.constants import MARKET_BENCHMARKS
from app.data.indicators import add_indicators
from app.data.loader import DataLoader
from app.engine.market import MarketEngine, calculate_breadth, calculate_market_facts
from app.features.market import MarketFeature
from app.models.facts import Facts
from app.models.market import MarketBreadth, MarketRegime, MarketVolatility
from app.providers.base import MarketDataProvider


class MarketProvider(MarketDataProvider):
    """Serve deterministic benchmark frames and a realistic low India VIX."""

    def __init__(self, frame: pd.DataFrame) -> None:
        """Store baseline market history and requested symbols."""
        self._frame = frame
        self.requested: list[str] = []

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Return bullish index data or a low-volatility VIX series."""
        self.requested.append(symbol)
        frame = self._frame.copy()
        if symbol == MARKET_BENCHMARKS["india_vix"]:
            scale = 12 / float(frame["Close"].iloc[-1])
            for column in ("Open", "High", "Low", "Close"):
                frame.loc[:, column] = frame[column] * scale
        return frame


class PartialMarketProvider(MarketProvider):
    """Serve only NIFTY 50 and India VIX to exercise graceful degradation."""

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Reject optional indexes while preserving core market inputs."""
        if symbol not in {
            MARKET_BENCHMARKS["nifty_50"],
            MARKET_BENCHMARKS["india_vix"],
        }:
            raise RuntimeError("optional benchmark unavailable")
        return super().history(symbol, period)


def _breadth(**updates: float | int) -> MarketBreadth:
    """Build representative breadth with selected overrides."""
    values: dict[str, float | int] = {
        "universe_size": 100,
        "advancers": 60,
        "decliners": 40,
        "unchanged": 0,
        "advance_decline_ratio": 1.5,
        "percentage_above_ema20": 65,
        "percentage_above_ema50": 60,
        "percentage_above_ema200": 55,
        "new_highs": 5,
        "new_lows": 2,
    }
    values.update(updates)
    return MarketBreadth(**values)


def test_market_facts_include_all_required_measures(rising_frame: pd.DataFrame) -> None:
    """An index profile should expose trend, return, range, volume, and breakout facts."""
    facts = calculate_market_facts("nifty_50", "^NSEI", add_indicators(rising_frame))
    assert facts.close > facts.ema20 > facts.ema50 > facts.ema200
    assert facts.return_20d > 0
    assert facts.return_50d > 0
    assert facts.return_150d > 0
    assert facts.return_250d > 0
    assert facts.atr14 > 0
    assert facts.relative_volume > 1
    assert 0 <= facts.distance_from_52_week_high <= 1


def test_breadth_calculates_participation(rising_frame: pd.DataFrame) -> None:
    """Breadth should count direction and moving-average participation."""
    advancing = add_indicators(rising_frame)
    declining = advancing.copy()
    declining.loc[declining.index[-1], "Close"] = declining["Close"].iloc[-2] * 0.98
    breadth = calculate_breadth({"UP.NS": advancing, "DOWN.NS": declining})
    assert breadth.universe_size == 2
    assert breadth.advancers == 1
    assert breadth.decliners == 1
    assert breadth.advance_decline_ratio == 1
    assert 0 <= breadth.percentage_above_ema200 <= 100


@pytest.mark.parametrize(
    ("score", "breadth", "volatility", "expected"),
    [
        (
            85,
            _breadth(),
            MarketVolatility(india_vix=12, atr_expansion=0, gap_frequency=0),
            MarketRegime.HEALTHY_BULL,
        ),
        (
            70,
            _breadth(),
            MarketVolatility(india_vix=16, atr_expansion=0, gap_frequency=0),
            MarketRegime.BULL,
        ),
        (
            60,
            _breadth(),
            MarketVolatility(india_vix=20, atr_expansion=0, gap_frequency=0),
            MarketRegime.WEAK_BULL,
        ),
        (
            50,
            _breadth(),
            MarketVolatility(india_vix=20, atr_expansion=0, gap_frequency=0),
            MarketRegime.RANGE,
        ),
        (
            38,
            _breadth(),
            MarketVolatility(india_vix=24, atr_expansion=0.1, gap_frequency=0.1),
            MarketRegime.WEAK_BEAR,
        ),
        (
            25,
            _breadth(),
            MarketVolatility(india_vix=28, atr_expansion=0.2, gap_frequency=0.2),
            MarketRegime.BEAR,
        ),
        (
            10,
            _breadth(
                advancers=10, decliners=90, advance_decline_ratio=0.11, new_highs=0, new_lows=20
            ),
            MarketVolatility(india_vix=35, atr_expansion=0.5, gap_frequency=0.4),
            MarketRegime.CAPITULATION,
        ),
        (
            55,
            _breadth(
                advancers=70,
                decliners=30,
                advance_decline_ratio=2.33,
                percentage_above_ema20=70,
                percentage_above_ema200=35,
            ),
            MarketVolatility(india_vix=18, atr_expansion=0, gap_frequency=0.1),
            MarketRegime.RECOVERY,
        ),
    ],
)
def test_classifier_supports_every_market_regime(
    score: float,
    breadth: MarketBreadth,
    volatility: MarketVolatility,
    expected: MarketRegime,
) -> None:
    """Every documented regime should be reachable through explicit evidence."""
    assert MarketEngine._classify(score, breadth, volatility) == expected


def test_market_engine_builds_explainable_profile(rising_frame: pd.DataFrame) -> None:
    """The integrated engine should load all benchmarks and explain its assessment."""
    provider = MarketProvider(rising_frame)
    engine = MarketEngine(DataLoader(provider))
    universe = {f"S{index}.NS": add_indicators(rising_frame) for index in range(10)}
    profile = engine.analyze(universe)
    assert set(provider.requested) == set(MARKET_BENCHMARKS.values())
    assert len(profile.indexes) == 5
    assert profile.volatility.india_vix == pytest.approx(12)
    assert profile.state in MarketRegime
    assert 0 <= profile.score <= 100
    assert 0 < profile.confidence <= 1
    assert profile.reasons


def test_market_engine_degrades_confidence_when_optional_indexes_fail(
    rising_frame: pd.DataFrame,
) -> None:
    """Missing secondary benchmarks should lower confidence without preventing a profile."""
    engine = MarketEngine(DataLoader(PartialMarketProvider(rising_frame)))
    profile = engine.analyze({"TEST.NS": add_indicators(rising_frame)})
    assert set(profile.indexes) == {"nifty_50"}
    assert profile.volatility.india_vix == pytest.approx(12)
    assert 0 < profile.confidence < 0.5


def test_market_feature_returns_state_and_profile_evidence(bullish_facts: Facts) -> None:
    """The feature contract should expose score, confidence, state, and reasons."""
    result = MarketFeature().evaluate(bullish_facts)
    assert result.score == 100
    assert result.confidence == 1
    assert result.state == "Healthy Bull"
    assert "Strong breadth" in result.reasons


def test_market_engine_profiles_one_thousand_symbols_within_budget(
    rising_frame: pd.DataFrame,
) -> None:
    """Market breadth evaluation should scale beyond a practical NSE universe."""
    enriched = add_indicators(rising_frame)
    universe = {f"S{index}.NS": enriched for index in range(1_000)}
    engine = MarketEngine(DataLoader(MarketProvider(rising_frame)))
    started = perf_counter()
    profile = engine.analyze(universe)
    elapsed = perf_counter() - started
    assert profile.breadth.universe_size == 1_000
    assert elapsed < 5
