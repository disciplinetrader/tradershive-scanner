"""Deterministic coverage for Scanner v1.1 intelligence extensions."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.core.v11_config import (
    AdvancedSetupThresholds,
    DecisionGates,
    ScannerProfileConfig,
    ScannerProfileName,
    VolumeEventThresholds,
)
from app.data.benchmark import BenchmarkSnapshot
from app.data.indicators import add_indicators
from app.engine.advanced_market import AdvancedMarketEngine
from app.engine.industry import IndustryGroupEngine
from app.engine.setup import SetupEngine
from app.engine.volume import VolumeEngine
from app.models.market import MarketBreadth, MarketProfile, MarketRegime, MarketVolatility
from app.models.sector import SectorFacts, SectorProfile, SectorRotation
from app.models.setup import ListingMetadata, SetupType
from app.models.volume import VolumeSignature


def v11_frame() -> pd.DataFrame:
    """Return a strong advance followed by a controlled 30-session base."""
    rows = 320
    close = np.linspace(70, 150, rows)
    close[-30:] = 148 + np.sin(np.arange(30) / 3) * 1.2
    volume = np.linspace(1_200_000, 700_000, rows)
    volume[-30:] = np.linspace(650_000, 350_000, 30)
    return add_indicators(
        pd.DataFrame(
            {
                "Open": close * 0.999,
                "High": close * 1.01,
                "Low": close * 0.99,
                "Close": close,
                "Volume": volume,
            },
            index=pd.bdate_range("2024-01-01", periods=rows, tz="UTC"),
        )
    )


def test_typed_v11_configuration_validates() -> None:
    """Every new policy family exposes validated defaults."""
    assert AdvancedSetupThresholds().flat_base_max_days == 45
    assert VolumeEventThresholds().pocket_pivot_lookback == 10
    assert DecisionGates().minimum_r == 2
    assert ScannerProfileConfig(name=ScannerProfileName.IPO_LEADER).name.value == "IPO Leader"


def test_setup_profile_contains_all_advanced_candidates() -> None:
    """All twelve advanced structures participate in best-setup comparison."""
    profile = SetupEngine().analyze("LEADER.NS", v11_frame())
    assert len(profile.advanced_setup_candidates) == 12
    assert {item.setup_type for item in profile.advanced_setup_candidates} == {
        SetupType.IPO_BASE,
        SetupType.FLAT_BASE,
        SetupType.CUP_WITH_HANDLE,
        SetupType.DOUBLE_BOTTOM,
        SetupType.HIGH_TIGHT_FLAG,
        SetupType.THREE_WEEKS_TIGHT,
        SetupType.WYCKOFF_SPRING,
        SetupType.SHAKEOUT_PLUS_THREE,
        SetupType.FAILED_BREAKOUT,
        SetupType.BREAKOUT_RETEST,
        SetupType.STAGE_2_FIRST_BASE,
        SetupType.EARNINGS_GAP_CONSOLIDATION,
    }
    assert profile.catalyst_quality_score < 50
    assert "catalyst" in " ".join(profile.reasons).lower()


def test_volume_profile_contains_advanced_signature() -> None:
    """Advanced volume events and ratings are serialized compatibly."""
    profile = VolumeEngine().analyze("LEADER.NS", v11_frame())
    assert isinstance(profile.volume_signature, VolumeSignature)
    assert profile.up_down_volume_ratio >= 0
    assert 0 <= profile.hidden_accumulation_score <= 100
    assert 0 <= profile.volume_event_confidence <= 1


def test_industry_ranking_and_missing_mapping() -> None:
    """Mapped groups rank while missing mappings remain explicitly unclassified."""
    strong = v11_frame()
    weak = strong.copy()
    weak["Close"] = weak["Close"].iloc[::-1].to_numpy()
    benchmark = BenchmarkSnapshot(
        "^NSEI", True, {5: 0, 10: 0, 20: 0.01, 50: 0.02, 100: 0.03, 150: 0.04, 250: 0.05}, 0.02
    )
    result = IndustryGroupEngine().analyze(
        {"A.NS": strong, "B.NS": strong, "C.NS": weak},
        benchmark,
        {"A.NS": "Defence Electronics", "B.NS": "Defence Electronics"},
        {"A.NS": "Defence", "B.NS": "Defence"},
    )
    assert result.groups["Defence Electronics"].rank == 1
    assert result.groups["Defence Electronics"].score >= 70
    assert result.symbol_groups["C.NS"] == "Unclassified"
    missing = IndustryGroupEngine().analyze({"C.NS": weak}, benchmark, None)
    assert missing.warnings and missing.symbol_groups["C.NS"] == "Unclassified"


def _market_profile() -> MarketProfile:
    """Return a minimal profile suitable for advanced market-state tests."""
    return MarketProfile.model_construct(
        score=60,
        confidence=1,
        state=MarketRegime.BULL,
        reasons=("Test market",),
        indexes={},
        breadth=MarketBreadth.model_construct(
            universe_size=10,
            advancers=6,
            decliners=4,
            unchanged=0,
            advance_decline_ratio=1.5,
            percentage_above_ema20=60,
            percentage_above_ema50=60,
            percentage_above_ema200=60,
            new_highs=1,
            new_lows=0,
        ),
        volatility=MarketVolatility.model_construct(india_vix=15, atr_expansion=0, gap_frequency=0),
    )


def _rally_frame(
    ftd_day: int | None, sessions_after_low: int, undercut: bool = False
) -> pd.DataFrame:
    """Create one decline, rally attempt, and optional FTD without later false lows."""
    close = np.full(41 + sessions_after_low, 110.0)
    close[40] = 100.0
    close[41:] = 100.5 + np.arange(sessions_after_low) * 0.05
    volume = np.full(len(close), 1_000.0)
    if ftd_day is not None:
        position = 40 + ftd_day - 1
        close[position] = close[position - 1] * 1.02
        close[position + 1 :] = close[position] + np.arange(len(close) - position - 1) * 0.05
        volume[position] = 1_500
    if undercut:
        close[-1] = 99.0
    return pd.DataFrame({"Close": close, "Low": close, "Volume": volume})


@pytest.mark.parametrize("day", [4, 7])
def test_follow_through_persists_after_eligible_session(day: int) -> None:
    """A valid historical FTD remains active after the latest eligibility day."""
    profile = AdvancedMarketEngine().enhance(_market_profile(), {"nifty_50": _rally_frame(day, 15)})
    assert profile.follow_through_day
    assert not profile.failed_follow_through


def test_follow_through_failure_and_undercut_invalidation() -> None:
    """Window expiry fails only without FTD; undercut explicitly invalidates an FTD."""
    failed = AdvancedMarketEngine().enhance(_market_profile(), {"nifty_50": _rally_frame(None, 15)})
    invalidated = AdvancedMarketEngine().enhance(
        _market_profile(), {"nifty_50": _rally_frame(4, 15, undercut=True)}
    )
    pre_ftd_undercut = AdvancedMarketEngine().enhance(
        _market_profile(), {"nifty_50": _rally_frame(None, 3, undercut=True)}
    )
    assert failed.failed_follow_through and not failed.follow_through_day
    assert not invalidated.follow_through_day
    assert not pre_ftd_undercut.follow_through_day


def test_follow_through_is_invalidated_by_intraday_rally_low_undercut() -> None:
    """An intraday undercut invalidates the FTD even when the index closes above the low."""
    frame = _rally_frame(4, 15)
    frame.iloc[-1, frame.columns.get_loc("Low")] = 99
    profile = AdvancedMarketEngine().enhance(_market_profile(), {"nifty_50": frame})
    assert not profile.follow_through_day


def test_distribution_first_observation_has_no_wraparound_comparison() -> None:
    """The distribution window's first row never compares with its final volume."""
    frame = _rally_frame(None, 30)
    frame.iloc[-25, frame.columns.get_loc("Close")] *= 0.99
    frame.iloc[-26, frame.columns.get_loc("Volume")] = 2_000
    frame.iloc[-25, frame.columns.get_loc("Volume")] = 1_000
    frame.iloc[-1, frame.columns.get_loc("Volume")] = 500
    profile = AdvancedMarketEngine().enhance(_market_profile(), {"nifty_50": frame})
    assert profile.active_distribution_days == 0


def test_listing_and_earnings_inputs_are_authoritative() -> None:
    """IPO and earnings setups require matching metadata rather than window inference."""
    frame = v11_frame().copy()
    listing = ListingMetadata(
        listing_date=frame.index[0].date(), ipo_open_price=float(frame["Open"].iloc[0])
    )
    valid = SetupEngine().analyze("IPO.NS", frame, listing_metadata=listing)
    missing = SetupEngine().analyze("IPO.NS", frame)
    truncated = SetupEngine().analyze(
        "IPO.NS",
        frame,
        listing_metadata=ListingMetadata(
            listing_date=(frame.index[0] - pd.Timedelta(days=30)).date(),
            ipo_open_price=50,
        ),
    )
    assert valid.facts.ipo_open_price == listing.ipo_open_price
    assert (
        missing.facts.ipo_open_price is None and not missing.advanced_setup_candidates[0].detected
    )
    assert truncated.facts.ipo_open_price is None

    gap_position = len(frame) - 15
    frame.iloc[gap_position, frame.columns.get_loc("Open")] = (
        frame["Close"].iloc[gap_position - 1] * 1.10
    )
    gap_open = frame["Open"].iloc[gap_position]
    frame.iloc[gap_position:, frame.columns.get_loc("Close")] = gap_open
    frame.iloc[gap_position:, frame.columns.get_loc("High")] = gap_open * 1.01
    frame.iloc[gap_position:, frame.columns.get_loc("Low")] = gap_open * 0.99
    event = frame.index[gap_position]
    matched = SetupEngine().analyze("EARN.NS", frame, earnings_dates=(event,), avwap_alignment=True)
    unrelated = SetupEngine().analyze(
        "EARN.NS", frame, earnings_dates=(event - pd.Timedelta(days=30),), avwap_alignment=True
    )
    missing_avwap = SetupEngine().analyze("EARN.NS", frame, earnings_dates=(event,))
    earnings_type = SetupType.EARNINGS_GAP_CONSOLIDATION

    def by_type(profile):
        return next(
            item for item in profile.advanced_setup_candidates if item.setup_type == earnings_type
        )

    assert by_type(matched).detected
    assert not by_type(unrelated).detected
    assert not by_type(missing_avwap).detected


def test_breakout_retest_uses_non_overlapping_windows() -> None:
    """A completed pivot, later breakout, and final retest are detected chronologically."""
    frame = v11_frame().copy()
    frame.iloc[-60:-30, frame.columns.get_loc("High")] = 100
    frame.iloc[-60:-30, frame.columns.get_loc("Low")] = 94
    frame.iloc[-30:-10, frame.columns.get_loc("High")] = 105
    frame.iloc[-10:, frame.columns.get_loc("Low")] = 99.5
    frame.iloc[-1, frame.columns.get_loc("Close")] = 101
    valid = SetupEngine().analyze("RETEST.NS", frame)
    candidate = next(
        item
        for item in valid.advanced_setup_candidates
        if item.setup_type == SetupType.BREAKOUT_RETEST
    )
    invalid_frame = frame.copy()
    invalid_frame.iloc[-30:-10, invalid_frame.columns.get_loc("High")] = 99
    invalid = SetupEngine().analyze("NO.NS", invalid_frame)
    invalid_candidate = next(
        item
        for item in invalid.advanced_setup_candidates
        if item.setup_type == SetupType.BREAKOUT_RETEST
    )
    assert candidate.detected and not invalid_candidate.detected


def test_named_scanner_profiles_have_distinct_enforced_policies() -> None:
    """Named profiles resolve to materially different setup and risk gates."""
    breakout = ScannerProfileConfig(name=ScannerProfileName.MOMENTUM_BREAKOUT)
    ipo = ScannerProfileConfig(name=ScannerProfileName.IPO_LEADER)
    conservative = ScannerProfileConfig(name=ScannerProfileName.CONSERVATIVE_SWING)
    assert ipo.eligible_setups != breakout.eligible_setups
    assert conservative.minimum_risk_score > breakout.minimum_risk_score
    assert conservative.allowed_market_regimes != ipo.allowed_market_regimes


def test_industry_metrics_use_member_and_parent_outputs() -> None:
    """Complete inputs produce real metrics; absent inputs remain missing and reduce confidence."""
    frame = v11_frame()
    benchmark = BenchmarkSnapshot(
        "^NSEI", True, {5: 0, 10: 0, 20: 0, 50: 0, 100: 0, 150: 0, 250: 0}, 0
    )
    sector_facts = SectorFacts.model_construct(
        name="Defence",
        member_count=2,
        return_100d=0.10,
    )
    sector = SectorProfile.model_construct(
        score=80,
        confidence=1,
        rank=1,
        percentile=99,
        rotation=SectorRotation.LEADING,
        reasons=("Leading",),
        facts=sector_facts,
    )
    outputs = {
        symbol: SimpleNamespace(
            facts=SimpleNamespace(setup_score=80, setup_grade="A+"),
            decision_profile=SimpleNamespace(action=SimpleNamespace(value="BUY")),
        )
        for symbol in ("A.NS", "B.NS")
    }
    complete = (
        IndustryGroupEngine()
        .analyze(
            {"A.NS": frame, "B.NS": frame},
            benchmark,
            {"A.NS": "Electronics", "B.NS": "Electronics"},
            {"A.NS": "Defence", "B.NS": "Defence"},
            {"Defence": sector},
            outputs,
        )
        .groups["Electronics"]
    )
    incomplete = (
        IndustryGroupEngine()
        .analyze(
            {"A.NS": frame, "B.NS": frame},
            benchmark,
            {"A.NS": "Electronics", "B.NS": "Electronics"},
            {"A.NS": "Defence", "B.NS": "Defence"},
        )
        .groups["Electronics"]
    )
    assert complete.facts.relative_return_sector is not None
    assert complete.facts.average_setup_score == 80
    assert complete.facts.buy_candidates == 2 and complete.confidence == 1
    assert incomplete.facts.relative_return_sector is None
    assert incomplete.facts.average_setup_score is None and incomplete.confidence < 1


def test_advanced_setup_selection_is_atomic() -> None:
    """An advanced winner supplies every score and structural field as one candidate."""
    profile = SetupEngine().analyze("ATOMIC.NS", v11_frame())
    winner = next(
        item
        for item in profile.advanced_setup_candidates
        if item.detected and item.setup_type == profile.best_setup_type
    )
    assert profile.score == winner.score
    assert profile.confidence == winner.confidence
    assert profile.grade == winner.grade
    assert profile.pattern_score == winner.pattern_score
    assert profile.structure_score == winner.structure_score
    assert profile.compression_score == winner.compression_score
    assert profile.volume_score == winner.volume_score
    assert profile.location_score == winner.location_score
    assert profile.facts.pivot_price == winner.pivot_price
    assert profile.facts.invalidation_price == winner.invalidation_price
    assert profile.facts.base_high == winner.base_high
    assert profile.facts.base_low == winner.base_low
    assert profile.facts.base_length_days == winner.base_length_days
