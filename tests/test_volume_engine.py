"""Deterministic tests for institutional Volume Intelligence."""

from time import perf_counter

import numpy as np
import pandas as pd
import pytest

from app.engine.volume import VolumeEngine
from app.features.volume import VolumeFeature
from app.models.volume import VolumeState
from tests.test_scanner_report import build_test_scanner


def _frame(rows: int = 80) -> pd.DataFrame:
    """Build stable normalized OHLCV history suitable for event mutation."""
    close = np.linspace(100.0, 110.0, rows)
    volume = np.full(rows, 1_000_000.0)
    return pd.DataFrame(
        {
            "Open": close * 0.998,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": volume,
        },
        index=pd.bdate_range("2025-01-01", periods=rows, tz="UTC"),
    )


def test_detects_volume_dry_up() -> None:
    """A sustained contraction should be identified and rewarded."""
    frame = _frame()
    frame.loc[frame.index[-5:], "Volume"] = 300_000
    profile = VolumeEngine().analyze("DRY.NS", frame)
    assert profile.facts.volume_dry_up_percent >= 65
    assert profile.dryup_score == 100
    assert "Volume Dry-Up before breakout" in profile.reasons


def test_detects_healthy_expansion() -> None:
    """A constructive high-volume advance should register expansion."""
    frame = _frame()
    frame.loc[frame.index[-1], "Volume"] = 1_800_000
    profile = VolumeEngine().analyze("EXPAND.NS", frame)
    assert profile.facts.volume_expansion_percent >= 75
    assert "Healthy expansion" in profile.reasons


def test_detects_volume_climax() -> None:
    """Extreme volume and range expansion should classify as climactic."""
    frame = _frame()
    last = frame.index[-1]
    frame.loc[last, ["High", "Low", "Volume"]] = [125, 95, 4_000_000]
    profile = VolumeEngine().analyze("CLIMAX.NS", frame)
    assert profile.facts.volume_climax
    assert profile.volume_state == VolumeState.CLIMACTIC
    assert "Volume climax may signal exhaustion" in profile.warnings


def test_detects_high_volume_churn() -> None:
    """High volume without price progress should flag institutional churn."""
    frame = _frame()
    frame.loc[frame.index[-1], "Close"] = frame.iloc[-2]["Close"]
    frame.loc[frame.index[-1], "Volume"] = 2_000_000
    profile = VolumeEngine().analyze("CHURN.NS", frame)
    assert profile.facts.volume_churn
    assert "High-volume churn without price progress" in profile.warnings


def test_detects_pocket_pivot_volume() -> None:
    """An up session exceeding all recent down-volume sessions is a pocket pivot."""
    frame = _frame()
    frame.loc[frame.index[-10:-1], "Volume"] = 900_000
    frame.loc[frame.index[-5], "Close"] = frame.iloc[-6]["Close"] * 0.99
    frame.loc[frame.index[-1], "Volume"] = 1_400_000
    profile = VolumeEngine().analyze("POCKET.NS", frame)
    assert profile.facts.pocket_pivot_volume
    assert any("Pocket pivot" in reason for reason in profile.reasons)


def test_classifies_professional_accumulation() -> None:
    """Persistent higher-volume advances should classify as accumulation."""
    frame = _frame()
    close = 100 * np.cumprod(np.full(len(frame), 1.008))
    frame.loc[:, "Close"] = close
    frame.loc[:, "Open"] = close * 0.995
    frame.loc[:, "High"] = close * 1.01
    frame.loc[:, "Low"] = close * 0.99
    frame.loc[:, "Volume"] = np.linspace(500_000, 1_500_000, len(frame))
    profile = VolumeEngine().analyze("ACCUM.NS", frame)
    assert profile.volume_state == VolumeState.PROFESSIONAL_ACCUMULATION
    assert profile.accumulation_score > profile.distribution_score


def test_classifies_professional_distribution() -> None:
    """Persistent higher-volume declines should classify as distribution."""
    frame = _frame()
    close = 150 * np.cumprod(np.full(len(frame), 0.992))
    frame.loc[:, "Close"] = close
    frame.loc[:, "Open"] = close * 1.005
    frame.loc[:, "High"] = close * 1.01
    frame.loc[:, "Low"] = close * 0.99
    frame.loc[:, "Volume"] = np.linspace(500_000, 1_500_000, len(frame))
    profile = VolumeEngine().analyze("DIST.NS", frame)
    assert profile.volume_state == VolumeState.PROFESSIONAL_DISTRIBUTION
    assert profile.distribution_score > profile.accumulation_score


def test_missing_data_degrades_confidence_and_invalid_data_fails() -> None:
    """Partial valid history lowers confidence while unusable history is rejected."""
    frame = _frame(20)
    frame.loc[frame.index[:2], "Volume"] = np.nan
    profile = VolumeEngine().analyze("PARTIAL.NS", frame)
    assert profile.confidence < 0.5
    assert "Limited history reduces volume confidence" in profile.warnings
    with pytest.raises(ValueError, match="at least 10"):
        VolumeEngine().analyze("SHORT.NS", frame.iloc[:8])


def test_scanner_and_feature_expose_volume_profile(rising_frame: pd.DataFrame) -> None:
    """Scanner facts, API model, and feature output share one volume profile."""
    result = build_test_scanner(rising_frame).scan(["STRONG"])[0]
    feature = VolumeFeature().evaluate(result.facts)
    assert result.facts.volume_profile.facts.symbol == result.symbol
    assert result.facts.volume_score == feature.score
    assert result.facts.volume_grade.value in {"A+", "A", "B", "C", "D"}
    assert feature.state == result.facts.volume_profile.volume_state.value


def test_profiles_one_thousand_stocks_within_budget() -> None:
    """Volume analysis should remain within the commercial scan budget."""
    engine = VolumeEngine()
    frame = _frame()
    started = perf_counter()
    profiles = [engine.analyze(f"S{index}.NS", frame) for index in range(1_000)]
    assert len(profiles) == 1_000
    # Coverage tracing adds material overhead; the dedicated benchmark enforces five seconds.
    assert perf_counter() - started < 7
