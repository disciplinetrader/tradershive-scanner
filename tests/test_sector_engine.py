"""Unit, integration, and performance tests for Sector Intelligence."""

from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
import pytest

from app.data.benchmark import build_benchmark_snapshot
from app.data.indicators import add_indicators
from app.data.sectors import (
    SUPPORTED_SECTORS,
    SectorDefinition,
    SectorRegistry,
    load_sector_assignments,
)
from app.engine.sector import SectorEngine
from app.models.sector import SectorFacts, SectorRotation
from tests.test_scanner_report import build_test_scanner


def _trend_frame(frame: pd.DataFrame, end_multiplier: float) -> pd.DataFrame:
    """Return history with deterministic relative performance ending at a multiplier."""
    result = frame.copy()
    multiplier = np.linspace(1.0, end_multiplier, len(result))
    result.loc[:, "Close"] = result["Close"] * multiplier
    result.loc[:, "Open"] = result["Close"] * 0.999
    result.loc[:, "High"] = result["Close"] * 1.01
    result.loc[:, "Low"] = result["Close"] * 0.99
    return add_indicators(result)


def _sector_facts(**updates: float | int | str) -> SectorFacts:
    """Create representative sector facts with targeted overrides."""
    values: dict[str, float | int | str] = {
        "name": "Defence",
        "member_count": 20,
        "return_5d": 0.04,
        "return_10d": 0.06,
        "return_20d": 0.08,
        "return_50d": 0.15,
        "return_100d": 0.25,
        "return_150d": 0.35,
        "return_250d": 0.50,
        "relative_strength_vs_nifty": 0.20,
        "average_member_relative_strength": 90,
        "percentage_above_ema20": 90,
        "percentage_above_ema50": 92,
        "percentage_above_ema200": 85,
        "new_high_percentage": 20,
        "new_low_percentage": 0,
        "average_volume_ratio": 1.5,
        "momentum_score": 85,
    }
    values.update(updates)
    return SectorFacts(**values)


def test_registry_supports_required_sectors_and_overrides() -> None:
    """All required sectors should be available through normalized assignments."""
    registry = SectorRegistry()
    assert registry.names == SUPPORTED_SECTORS
    assert registry.assignments({"HAL": "Defence", "TCS.NS": "IT"}) == {
        "HAL.NS": "Defence",
        "TCS.NS": "IT",
    }


def test_registry_rejects_duplicate_membership() -> None:
    """A stock cannot silently contribute to multiple sector aggregates."""
    definitions = (
        SectorDefinition(name="Banking", members=frozenset({"SBIN"})),
        SectorDefinition(name="PSU", members=frozenset({"SBIN"})),
    )
    with pytest.raises(ValueError, match="multiple sectors"):
        SectorRegistry(definitions)


def test_sector_assignments_load_from_json(tmp_path: Path) -> None:
    """CLI membership files should validate and normalize symbols."""
    path = tmp_path / "sectors.json"
    path.write_text('{"HAL":"Defence","TCS.NS":"IT"}', encoding="utf-8")
    assert load_sector_assignments(path) == {"HAL.NS": "Defence", "TCS.NS": "IT"}


def test_sector_engine_ranks_leaders_and_calculates_all_facts(
    rising_frame: pd.DataFrame,
) -> None:
    """Multi-horizon returns, breadth, member RS, and rankings should be complete."""
    benchmark_frame = add_indicators(rising_frame)
    benchmark = build_benchmark_snapshot("^NSEI", benchmark_frame)
    frames: dict[str, pd.DataFrame] = {}
    assignments: dict[str, str] = {}
    for sector, multiplier in (("Defence", 2.0), ("Banking", 1.4), ("IT", 1.0), ("Chemical", 0.7)):
        for member in range(5):
            symbol = f"{sector[:3].upper()}{member}.NS"
            frames[symbol] = _trend_frame(rising_frame, multiplier)
            assignments[symbol] = sector

    analysis = SectorEngine().analyze(frames, benchmark, assignments)
    defence = analysis.sectors["Defence"]

    assert defence.rank == 1
    assert defence.percentile == 99
    assert defence.rotation == SectorRotation.LEADING
    assert defence.facts.member_count == 5
    assert defence.facts.return_5d > 0
    assert defence.facts.return_250d > benchmark.returns[250]
    assert defence.facts.relative_strength_vs_nifty > 0
    assert defence.facts.average_member_relative_strength > 50
    assert defence.facts.percentage_above_ema50 == 100
    assert defence.facts.average_volume_ratio > 1
    assert "Broad participation" in defence.reasons


@pytest.mark.parametrize(
    ("facts", "percentile", "expected"),
    [
        (_sector_facts(), 90, SectorRotation.LEADING),
        (
            _sector_facts(
                return_5d=0.15,
                return_10d=0.16,
                return_20d=0.18,
                return_100d=0.05,
                return_150d=0.04,
                return_250d=0.03,
            ),
            60,
            SectorRotation.IMPROVING,
        ),
        (
            _sector_facts(return_5d=-0.05, return_10d=-0.04, return_20d=-0.03),
            60,
            SectorRotation.WEAKENING,
        ),
        (
            _sector_facts(
                return_5d=-0.05,
                return_10d=-0.06,
                return_20d=-0.08,
                return_100d=-0.10,
                return_150d=-0.15,
                return_250d=-0.20,
            ),
            10,
            SectorRotation.LAGGING,
        ),
    ],
)
def test_rotation_states_are_reachable(
    facts: SectorFacts,
    percentile: float,
    expected: SectorRotation,
    rising_frame: pd.DataFrame,
) -> None:
    """Every requested sector rotation state should have explicit conditions."""
    benchmark = build_benchmark_snapshot("^NSEI", add_indicators(rising_frame))
    assert SectorEngine._rotation(facts, benchmark, percentile) == expected


def test_scanner_inherits_sector_profile(rising_frame: pd.DataFrame) -> None:
    """Every classified stock should expose its ranked sector facts and feature."""
    scanner = build_test_scanner(rising_frame)
    results = scanner.scan(
        ["STRONG", "WEAK"],
        {"STRONG": "Defence", "WEAK": "IT"},
    )
    by_symbol = {result.symbol: result for result in results}
    assert by_symbol["STRONG.NS"].facts.sector_name == "Defence"
    assert by_symbol["STRONG.NS"].facts.sector_rank >= 1
    assert by_symbol["STRONG.NS"].features["sector"].state in SectorRotation
    assert by_symbol["WEAK.NS"].facts.sector_name == "IT"


def test_sector_engine_profiles_one_thousand_members_within_budget(
    rising_frame: pd.DataFrame,
) -> None:
    """Sector aggregation should scale beyond a practical NSE stock universe."""
    enriched = add_indicators(rising_frame)
    benchmark = build_benchmark_snapshot("^NSEI", enriched)
    frames = {f"S{index}.NS": enriched for index in range(1_000)}
    assignments = {
        symbol: SUPPORTED_SECTORS[index % len(SUPPORTED_SECTORS)]
        for index, symbol in enumerate(frames)
    }
    started = perf_counter()
    analysis = SectorEngine().analyze(frames, benchmark, assignments)
    elapsed = perf_counter() - started
    assert len(analysis.sectors) == len(SUPPORTED_SECTORS)
    assert sum(profile.facts.member_count for profile in analysis.sectors.values()) == 1_000
    assert elapsed < 5
