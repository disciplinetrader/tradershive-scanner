"""Unit, integration, and performance tests for Stock Intelligence."""

from time import perf_counter

import numpy as np
import pandas as pd
import pytest

from app.data.indicators import add_indicators
from app.engine.stock import StockEngine
from app.features.stock import StockFeature
from app.models.stock import StockGrade
from tests.test_scanner_report import build_test_scanner


def _falling_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return deterministic declining history with weakening participation."""
    result = frame.copy()
    close = np.linspace(180.0, 80.0, len(result))
    result.loc[:, "Close"] = close
    result.loc[:, "Open"] = close * 1.002
    result.loc[:, "High"] = close * 1.015
    result.loc[:, "Low"] = close * 0.985
    result.loc[:, "Volume"] = np.linspace(1_200_000, 600_000, len(result))
    return result


def test_stock_engine_calculates_complete_facts_and_scores(rising_frame: pd.DataFrame) -> None:
    """A persistent uptrend should produce complete, bounded intelligence."""
    profile = StockEngine().analyze("HAL.NS", add_indicators(rising_frame))
    facts = profile.facts
    assert facts.symbol == "HAL.NS"
    assert facts.ema20 > facts.ema50 > facts.ema100 > facts.ema150 > facts.ema200
    assert facts.ema_alignment
    assert facts.distance_above_ema20 > 0
    assert facts.return_20d > 0
    assert facts.return_250d > 0
    assert facts.atr14 > 0
    assert facts.average_daily_range > 0
    assert facts.higher_highs + facts.lower_highs <= 19
    assert facts.higher_lows + facts.lower_lows <= 19
    assert facts.relative_volume > 1
    assert profile.score >= 65
    assert profile.grade in {StockGrade.A_PLUS, StockGrade.A, StockGrade.B}
    assert all(
        0 <= score <= 100
        for score in (
            profile.trend_score,
            profile.momentum_score,
            profile.participation_score,
            profile.health_score,
        )
    )


def test_declining_stock_is_lower_quality(rising_frame: pd.DataFrame) -> None:
    """A damaged long-term trend should rank below a persistent leader."""
    engine = StockEngine()
    leader = engine.analyze("LEADER.NS", rising_frame)
    laggard = engine.analyze("LAGGARD.NS", _falling_frame(rising_frame))
    assert leader.score > laggard.score
    assert laggard.grade in {StockGrade.C, StockGrade.D}
    assert "Price is below EMA200" in laggard.reasons


def test_stock_engine_rejects_short_history(rising_frame: pd.DataFrame) -> None:
    """Annual-quality facts must not silently use incomplete history."""
    with pytest.raises(ValueError, match="252 sessions"):
        StockEngine().analyze("SHORT.NS", rising_frame.iloc[-200:])


def test_stock_feature_exposes_profile(bullish_facts) -> None:
    """Feature output should preserve the profile grade and evidence."""
    result = StockFeature().evaluate(bullish_facts)
    assert result.score == bullish_facts.stock_score
    assert result.state == "A+"
    assert result.reasons == bullish_facts.stock_profile.reasons


def test_scanner_attaches_stock_profile(rising_frame: pd.DataFrame) -> None:
    """Every successful scanner result should inherit intrinsic intelligence."""
    results = build_test_scanner(rising_frame).scan(["STRONG", "WEAK"])
    assert all(result.facts.stock_profile.facts.symbol == result.symbol for result in results)
    assert results[0].features["stock"].state == results[0].facts.stock_grade.value
    assert results[0].facts.stock_score > results[1].facts.stock_score


def test_stock_engine_profiles_one_thousand_symbols_within_budget(
    rising_frame: pd.DataFrame,
) -> None:
    """Vectorized analysis should scale beyond a practical NSE universe."""
    engine = StockEngine()
    enriched = add_indicators(rising_frame)
    started = perf_counter()
    profiles = [engine.analyze(f"S{index}.NS", enriched) for index in range(1_000)]
    elapsed = perf_counter() - started
    assert len(profiles) == 1_000
    assert elapsed < 10
