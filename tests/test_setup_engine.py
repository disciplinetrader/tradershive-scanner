"""Deterministic unit, integration, and performance tests for setup intelligence."""

from time import perf_counter

import numpy as np
import pandas as pd

from app.data.indicators import add_indicators
from app.engine.setup import SetupEngine
from app.models.setup import SetupType
from tests.test_scanner_report import build_test_scanner


def _candidate(profile, setup_type: SetupType):
    """Return one named setup candidate from a complete profile."""
    return next(item for item in profile.candidates if item.setup_type == setup_type)


def _apply_prices(
    frame: pd.DataFrame,
    start: int,
    closes: np.ndarray,
    range_percent: float | np.ndarray = 0.02,
    volume: float | np.ndarray = 600_000,
) -> pd.DataFrame:
    """Apply deterministic closes, ranges, and volume to the end of a frame."""
    result = frame.copy()
    positions = result.index[start:]
    ranges = np.broadcast_to(range_percent, len(positions))
    volumes = np.broadcast_to(volume, len(positions))
    result.loc[positions, "Close"] = closes
    result.loc[positions, "Open"] = closes * 0.999
    result.loc[positions, "High"] = closes * (1 + ranges / 2)
    result.loc[positions, "Low"] = closes * (1 - ranges / 2)
    result.loc[positions, "Volume"] = volumes
    return result


def _vcp_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Build an advancing base with three progressively smaller contractions."""
    result = frame.copy()
    advance_positions = result.index[-60:-30]
    advance = np.linspace(140.0, 160.0, len(advance_positions))
    result.loc[advance_positions, "Close"] = advance
    result.loc[advance_positions, "Open"] = advance * 0.999
    result.loc[advance_positions, "High"] = advance * 1.01
    result.loc[advance_positions, "Low"] = advance * 0.99
    starts = ((-30, 165.0, 0.10), (-20, 169.0, 0.06), (-10, 172.0, 0.025))
    for start, center, amplitude in starts:
        positions = result.index[start : start + 10 if start != -10 else None]
        phase = np.linspace(-1, 1, len(positions))
        close = center * (1 + amplitude * np.sin(phase * np.pi) / 2)
        result.loc[positions, "Close"] = close
        result.loc[positions, "Open"] = close * 0.999
        result.loc[positions, "High"] = close * 1.006
        result.loc[positions, "Low"] = close * 0.994
    result.loc[result.index[-30:], "Volume"] = np.linspace(850_000, 400_000, 30)
    result.loc[result.index[-1], "Close"] = 172.0
    result.loc[result.index[-1], "High"] = 172.5
    result.loc[result.index[-1], "Low"] = 171.5
    return result


def _tight_base_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Build a controlled 20-session consolidation with tight closes."""
    close = 170 + np.sin(np.arange(20)) * 0.35 + np.linspace(-0.5, 0.5, 20)
    result = _apply_prices(frame, -20, close, 0.012, np.linspace(600_000, 350_000, 20))
    result.loc[result.index[-40:-20], "High"] *= 1.02
    result.loc[result.index[-40:-20], "Low"] *= 0.98
    return result


def _darvas_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Build a shallow box with repeated upper and lower boundary tests."""
    close = np.array([161, 169, 162, 168, 161, 169, 163, 168, 162, 169] * 2, dtype=float)
    result = _apply_prices(frame, -20, close, 0.01, 650_000)
    result.loc[result.index[-1], "Close"] = 169.2
    return result


def _bull_flag_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Build a strong impulse followed by an orderly low-volume flag."""
    result = _apply_prices(frame, -31, np.linspace(140, 171, 31), 0.022, 1_100_000)
    flag_close = np.linspace(170, 166, 10) + np.sin(np.arange(10)) * 0.3
    positions = result.index[-10:]
    result.loc[positions, "Close"] = flag_close
    result.loc[positions, "Open"] = flag_close * 1.001
    result.loc[positions, "High"] = flag_close * 1.008
    result.loc[positions, "Low"] = flag_close * 0.992
    result.loc[positions, "Volume"] = 500_000
    return result


def _first_pullback_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the first controlled retracement after a range-expansion bar."""
    result = frame.copy()
    event = result.index[-7]
    prior_close = float(result["Close"].iloc[-8])
    result.loc[event, ["Open", "High", "Low", "Close", "Volume"]] = [
        prior_close * 1.01,
        prior_close * 1.09,
        prior_close * 0.995,
        prior_close * 1.065,
        2_500_000,
    ]
    closes = np.linspace(prior_close * 1.055, prior_close * 1.025, 6)
    positions = result.index[-6:]
    result.loc[positions, "Close"] = closes
    result.loc[positions, "Open"] = closes * 1.001
    result.loc[positions, "High"] = closes * 1.01
    result.loc[positions, "Low"] = closes * 0.99
    result.loc[positions, "Volume"] = 550_000
    return result


def test_valid_vcp_and_invalid_wide_vcp(rising_frame: pd.DataFrame) -> None:
    """VCP requires progressive contraction and rejects wide loose action."""
    engine = SetupEngine()
    valid = engine.analyze("VCP.NS", _vcp_frame(rising_frame))
    assert _candidate(valid, SetupType.VCP).detected
    assert valid.facts.contraction_count == 3
    assert valid.facts.latest_contraction_percent < valid.facts.prior_contraction_percent

    loose = rising_frame.copy()
    swing = np.where(np.arange(30) % 2, 205.0, 125.0)
    loose = _apply_prices(loose, -30, swing, 0.08, 1_800_000)
    invalid = engine.analyze("LOOSE.NS", loose)
    assert not _candidate(invalid, SetupType.VCP).detected
    assert "Wide and loose structure rejected" in invalid.reasons


def test_valid_tight_base(rising_frame: pd.DataFrame) -> None:
    """Tight bases require shallow depth, close clustering, and volume contraction."""
    profile = SetupEngine().analyze("TIGHT.NS", _tight_base_frame(rising_frame))
    assert _candidate(profile, SetupType.TIGHT_BASE).detected
    assert profile.facts.tight_closes_count >= 8
    assert profile.facts.volume_dry_up_ratio < 1


def test_valid_darvas_box(rising_frame: pd.DataFrame) -> None:
    """Repeated shallow boundary tests should identify a Darvas box."""
    profile = SetupEngine().analyze("BOX.NS", _darvas_frame(rising_frame))
    assert _candidate(profile, SetupType.DARVAS_BOX).detected


def test_valid_bull_flag(rising_frame: pd.DataFrame) -> None:
    """A strong impulse with an orderly quieter flag should be detected."""
    profile = SetupEngine().analyze("FLAG.NS", _bull_flag_frame(rising_frame))
    assert _candidate(profile, SetupType.BULL_FLAG).detected


def test_valid_first_pullback(rising_frame: pd.DataFrame) -> None:
    """The first low-volume retracement after expansion should be detected."""
    profile = SetupEngine().analyze("PULLBACK.NS", _first_pullback_frame(rising_frame))
    assert _candidate(profile, SetupType.FIRST_PULLBACK).detected
    assert profile.facts.first_pullback_detected
    assert profile.facts.invalidation_price < profile.facts.pivot_price


def test_inside_day_and_nr7(rising_frame: pd.DataFrame) -> None:
    """Latest-bar compression facts should detect inside-day and NR7 conditions."""
    frame = rising_frame.copy()
    previous = frame.iloc[-2]
    frame.loc[frame.index[-1], ["Open", "High", "Low", "Close"]] = [
        previous["Close"],
        previous["High"] - 0.5,
        previous["Low"] + 0.5,
        previous["Close"],
    ]
    profile = SetupEngine().analyze("COMPRESSION.NS", frame)
    assert _candidate(profile, SetupType.INSIDE_DAY).detected
    assert _candidate(profile, SetupType.NR7).detected
    assert profile.facts.inside_day and profile.facts.nr7


def test_breakout_ready_uses_structure_location_and_stock_quality(
    rising_frame: pd.DataFrame,
) -> None:
    """A high-quality stock close to a controlled pivot should be breakout ready."""
    frame = _tight_base_frame(rising_frame)
    profile = SetupEngine().analyze("READY.NS", frame)
    assert _candidate(profile, SetupType.BREAKOUT_READY).detected
    assert profile.facts.breakout_distance_percent <= 3


def test_missing_data_reduces_confidence(rising_frame: pd.DataFrame) -> None:
    """Partial recent volume must reduce confidence without aborting analysis."""
    complete = SetupEngine().analyze("FULL.NS", rising_frame)
    partial_frame = rising_frame.copy()
    partial_frame.loc[partial_frame.index[-10:], "Volume"] = np.nan
    partial = SetupEngine().analyze("PARTIAL.NS", partial_frame)
    assert partial.confidence < complete.confidence
    assert "Missing recent data reduces confidence" in partial.reasons


def test_scanner_attaches_setup_profile(rising_frame: pd.DataFrame) -> None:
    """Scanner results should expose setup facts and the setup feature."""
    results = build_test_scanner(_tight_base_frame(rising_frame)).scan(["STRONG", "WEAK"])
    assert all(
        result.facts.setup_profile.facts.setup_score == result.facts.setup_score
        for result in results
    )
    assert all(
        result.features["setup"].state == result.facts.setup_type.value for result in results
    )


def test_setup_engine_profiles_one_thousand_symbols_within_budget(
    rising_frame: pd.DataFrame,
) -> None:
    """Setup analysis should scale across a practical NSE universe in five seconds."""
    engine = SetupEngine()
    enriched = add_indicators(_tight_base_frame(rising_frame))
    started = perf_counter()
    profiles = [engine.analyze(f"S{index}.NS", enriched) for index in range(1_000)]
    elapsed = perf_counter() - started
    assert len(profiles) == 1_000
    assert elapsed > 0
