"""Deterministic tests for institutional Breadth Intelligence."""

from time import perf_counter

import numpy as np
import pandas as pd
import pytest

from app.engine.breadth import BreadthEngine
from app.features.breadth import BreadthFeature
from app.models.breadth import BreadthState
from tests.test_scanner_report import build_test_scanner


def _frame(
    returns: np.ndarray,
    *,
    above20: bool = True,
    above50: bool = True,
    above100: bool = True,
    above200: bool = True,
    new_low: bool = False,
    volume: float = 1_000_000,
) -> pd.DataFrame:
    """Build a pre-enriched history with explicitly controlled breadth behavior."""
    close = 100 * np.cumprod(1 + returns)
    low = close * 0.99
    if not new_low:
        low[-1] = max(low[-1], float(np.min(low[:-1])) + 0.01)
    high = close * 1.01
    latest = close[-1]
    rows = len(close)
    return pd.DataFrame(
        {
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": np.full(rows, volume),
            "EMA20": np.full(rows, latest * (0.95 if above20 else 1.05)),
            "EMA50": np.full(rows, latest * (0.90 if above50 else 1.10)),
            "EMA100": np.full(rows, latest * (0.85 if above100 else 1.15)),
            "EMA200": np.full(rows, latest * (0.80 if above200 else 1.20)),
            "High52W": np.maximum.accumulate(high),
        },
        index=pd.bdate_range("2025-01-01", periods=rows, tz="UTC"),
    )


def _universe(size: int, returns: np.ndarray, **kwargs) -> dict[str, pd.DataFrame]:
    """Build a universe of independent frames with identical controlled behavior."""
    return {f"S{index}.NS": _frame(returns, **kwargs) for index in range(size)}


def test_broad_bull_has_broad_participation() -> None:
    """Persistent market-wide advances should confirm broad leadership."""
    profile = BreadthEngine().analyze(_universe(100, np.full(51, 0.006)))
    assert profile.breadth_state == BreadthState.BROAD_PARTICIPATION
    assert profile.facts.percentage_above_ema50 == 100
    assert profile.facts.advance_decline_ratio == 100
    assert "Broad participation" in profile.reasons


def test_weak_breadth_is_detected_without_capitulation() -> None:
    """One broad weak session with damaged EMA structure should flag weak participation."""
    frames = {}
    for index in range(100):
        returns = np.zeros(51)
        returns[-1] = -0.01 if index < 80 else 0.01
        frames[f"S{index}.NS"] = _frame(
            returns,
            above20=index >= 80,
            above50=index >= 80,
            above100=index >= 80,
            above200=index >= 80,
        )
    profile = BreadthEngine().analyze(frames)
    assert profile.breadth_state == BreadthState.WEAK_PARTICIPATION
    assert profile.participation_score < 40
    assert "Participation narrowing" in profile.reasons


def test_narrow_leadership_is_distinguished_from_weak_market() -> None:
    """Strong long-term breadth with weak short-term breadth should be narrow leadership."""
    frames = {}
    for index in range(100):
        frames[f"S{index}.NS"] = _frame(
            np.zeros(51),
            above20=index < 25,
            above50=index < 35,
            above100=index < 60,
            above200=index < 80,
        )
    profile = BreadthEngine().analyze(frames)
    assert profile.breadth_state == BreadthState.NARROW_LEADERSHIP
    assert profile.facts.percentage_above_ema200 == 80
    assert profile.facts.percentage_above_ema20 == 25


def test_distribution_cluster_is_classified() -> None:
    """Repeated broad down-volume sessions should produce distribution."""
    returns = np.zeros(51)
    returns[-8:] = -0.008
    profile = BreadthEngine().analyze(_universe(100, returns))
    assert profile.breadth_state == BreadthState.DISTRIBUTION
    assert profile.facts.distribution_days >= 4
    assert "Distribution increasing" in profile.reasons


def test_capitulation_requires_down_volume_and_new_lows() -> None:
    """Market-wide new lows on down volume should override ordinary distribution."""
    returns = np.full(51, -0.01)
    profile = BreadthEngine().analyze(_universe(100, returns, new_low=True))
    assert profile.breadth_state == BreadthState.CAPITULATION
    assert profile.facts.new_lows == 100
    assert profile.facts.down_volume_percent == 100


def test_follow_through_day_and_breadth_thrust() -> None:
    """A sharp transition from weak to broad demand should identify confirmation."""
    frames = {}
    for index in range(100):
        returns = np.zeros(51)
        returns[-10:-5] = -0.005 if index < 80 else 0.005
        returns[-5:] = 0.015 if index < 80 else -0.002
        frames[f"S{index}.NS"] = _frame(returns, volume=1_500_000 if index < 80 else 500_000)
    profile = BreadthEngine().analyze(frames)
    assert profile.facts.follow_through_day
    assert profile.facts.breadth_thrust
    assert profile.thrust_score == 100


def test_missing_data_reduces_confidence_and_empty_universe_fails() -> None:
    """Coverage gaps must be explicit and fully invalid universes must fail."""
    valid = _frame(np.full(20, 0.002))
    invalid = valid.drop(columns="EMA100")
    profile = BreadthEngine().analyze({"VALID.NS": valid, "INVALID.NS": invalid.iloc[:2]})
    assert profile.confidence < 0.1
    assert "Limited universe coverage reduces breadth confidence" in profile.warnings
    with pytest.raises(ValueError, match="at least one valid symbol"):
        BreadthEngine().analyze({})


def test_feature_scanner_and_api_model_expose_shared_breadth(rising_frame: pd.DataFrame) -> None:
    """Every stock should carry the same precomputed breadth profile."""
    results = build_test_scanner(rising_frame).scan(["STRONG", "WEAK"])
    assert results[0].facts.breadth_profile == results[1].facts.breadth_profile
    feature = BreadthFeature().evaluate(results[0].facts)
    assert feature.score == results[0].facts.breadth_score
    assert feature.state == results[0].facts.breadth_profile.breadth_state.value
    assert "breadth" in results[0].decision_profile.weight_breakdown
    assert results[0].situation_profile.breadth_profile is not None


def test_breadth_engine_profiles_one_thousand_stock_universe_within_budget() -> None:
    """A full commercial universe should remain inside the five-second scan budget."""
    frame = _frame(np.full(51, 0.002))
    frames = {f"S{index}.NS": frame for index in range(1_000)}
    started = perf_counter()
    profile = BreadthEngine().analyze(frames)
    assert profile.facts.valid_symbols == 1_000
    assert perf_counter() - started < 5
