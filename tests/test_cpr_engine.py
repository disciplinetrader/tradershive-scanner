"""Deterministic tests for multi-timeframe CPR Intelligence."""

from time import perf_counter

import numpy as np
import pandas as pd
import pytest

from app.engine.cpr import CPREngine
from app.features.cpr import CPRFeature
from app.models.cpr import CPRPriceLocation, CPRRelationship, CPRWidthState
from tests.test_scanner_report import build_test_scanner


def _frame(rows: int = 320) -> pd.DataFrame:
    """Build stable OHLCV history whose final sessions can be controlled."""
    close = np.linspace(90.0, 110.0, rows)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 2,
            "Low": close - 2,
            "Close": close + 1,
            "Volume": np.full(rows, 1_000_000.0),
        },
        index=pd.bdate_range("2024-01-01", periods=rows, tz="UTC"),
    )


def _set_session(frame: pd.DataFrame, offset: int, low: float, high: float, close: float) -> None:
    """Mutate one deterministic session while preserving valid OHLC values."""
    index = frame.index[offset]
    frame.loc[index, ["Open", "Low", "High", "Close"]] = [close, low, high, close]


def test_virgin_daily_cpr() -> None:
    """A session that never touches its prior-day CPR should remain virgin."""
    frame = _frame()
    _set_session(frame, -2, 98, 102, 100)
    _set_session(frame, -1, 108, 112, 110)
    daily = CPREngine().analyze("VIRGIN.NS", frame).facts.daily
    assert daily.virgin_cpr
    assert daily.price_location == CPRPriceLocation.ABOVE


def test_narrow_and_wide_cpr_classification() -> None:
    """Historical width ranking should distinguish compression and broad value."""
    narrow_frame = _frame()
    _set_session(narrow_frame, -2, 98, 102, 100)
    narrow = CPREngine().analyze("NARROW.NS", narrow_frame).facts.daily
    wide_frame = _frame()
    _set_session(wide_frame, -2, 90, 110, 110)
    wide = CPREngine().analyze("WIDE.NS", wide_frame).facts.daily
    assert narrow.width_state in {CPRWidthState.EXTREMELY_NARROW, CPRWidthState.NARROW}
    assert narrow.narrow_cpr
    assert wide.width_state in {CPRWidthState.WIDE, CPRWidthState.EXTREMELY_WIDE}
    assert wide.wide_cpr


def test_bullish_and_bearish_relationships() -> None:
    """Non-overlapping value migration should identify directional CPR structure."""
    bullish = _frame()
    _set_session(bullish, -3, 98, 102, 100)
    _set_session(bullish, -2, 108, 112, 110)
    bullish_daily = CPREngine().analyze("BULL.NS", bullish).facts.daily
    bearish = _frame()
    _set_session(bearish, -3, 108, 112, 110)
    _set_session(bearish, -2, 98, 102, 100)
    bearish_daily = CPREngine().analyze("BEAR.NS", bearish).facts.daily
    assert bullish_daily.relationship_to_previous_cpr == CPRRelationship.HIGHER_VALUE
    assert bearish_daily.relationship_to_previous_cpr == CPRRelationship.LOWER_VALUE


def test_breakout_probability_rewards_narrow_structure() -> None:
    """Compression should provide greater expansion probability than a wide CPR."""
    narrow_frame = _frame()
    _set_session(narrow_frame, -2, 98, 102, 100)
    _set_session(narrow_frame, -1, 105, 109, 108)
    wide_frame = _frame()
    _set_session(wide_frame, -2, 85, 115, 115)
    narrow = CPREngine().analyze("NARROW.NS", narrow_frame)
    wide = CPREngine().analyze("WIDE.NS", wide_frame)
    assert narrow.breakout_probability > wide.breakout_probability
    assert 0 <= narrow.trend_probability <= 100
    assert 0 <= narrow.range_probability <= 100


def test_missing_data_degrades_confidence_and_invalid_history_fails() -> None:
    """Partial history lowers confidence while unusable data fails explicitly."""
    frame = _frame(65)
    profile = CPREngine().analyze("PARTIAL.NS", frame)
    assert profile.confidence < 0.3
    assert "Limited history reduces CPR confidence" in profile.warnings
    with pytest.raises(ValueError, match="at least 45"):
        CPREngine().analyze("SHORT.NS", frame.iloc[:40])


def test_feature_scanner_decision_and_situation_expose_cpr(rising_frame: pd.DataFrame) -> None:
    """CPR must propagate through scoring, API models, Decision, and Situation."""
    result = build_test_scanner(rising_frame).scan(["STRONG"])[0]
    feature = CPRFeature().evaluate(result.facts)
    assert feature.score == result.facts.cpr_score
    assert feature.state == result.facts.cpr_profile.cpr_state.value
    assert "cpr" in result.decision_profile.weight_breakdown
    assert result.situation_profile.cpr_environment != "Unavailable"


def test_cpr_engine_profiles_one_thousand_stocks_within_budget() -> None:
    """Multi-timeframe CPR analysis should meet the commercial scan ceiling."""
    engine = CPREngine()
    frame = _frame()
    started = perf_counter()
    profiles = [engine.analyze(f"S{index}.NS", frame) for index in range(1_000)]
    assert len(profiles) == 1_000
    # Coverage tracing materially affects Pydantic-heavy loops; the benchmark enforces five seconds.
    assert perf_counter() - started < 15
