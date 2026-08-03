"""Cross-sectional sector aggregation, ranking, and rotation engine."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.core.constants import RELATIVE_STRENGTH_HORIZONS, RELATIVE_STRENGTH_PERIOD_WEIGHTS
from app.data.benchmark import BenchmarkSnapshot
from app.data.indicators import add_indicators
from app.data.sectors import SectorRegistry
from app.models.sector import SectorAnalysis, SectorFacts, SectorProfile, SectorRotation


@dataclass(frozen=True, slots=True)
class _MemberObservation:
    """Validated technical observation used by sector aggregation."""

    returns: Mapping[int, float]
    weighted_relative_strength: float
    above_ema20: bool
    above_ema50: bool
    above_ema200: bool
    new_high: bool
    new_low: bool
    volume_ratio: float


def _percentiles(values: Iterable[float]) -> dict[float, float]:
    """Return tie-aware cross-sectional percentiles on a zero-to-99 scale."""
    ordered = sorted(values)
    if not ordered:
        return {}
    if len(ordered) == 1:
        return {ordered[0]: 99.0}
    positions: dict[float, list[int]] = {}
    for index, value in enumerate(ordered):
        positions.setdefault(value, []).append(index)
    return {
        value: round(sum(indices) / len(indices) / (len(ordered) - 1) * 99, 2)
        for value, indices in positions.items()
    }


class SectorEngine:
    """Calculate sector leadership, ranking, participation, and rotation."""

    def __init__(self, registry: SectorRegistry | None = None) -> None:
        """Initialize with an extensible sector registry."""
        self._registry = registry or SectorRegistry()

    def analyze(
        self,
        frames: Mapping[str, pd.DataFrame],
        benchmark: BenchmarkSnapshot,
        sector_by_symbol: Mapping[str, str] | None = None,
    ) -> SectorAnalysis:
        """Build ranked profiles for every represented supported sector."""
        assignments = self._registry.assignments(sector_by_symbol)
        observations: dict[str, _MemberObservation] = {}
        for symbol, frame in frames.items():
            if symbol not in assignments:
                continue
            try:
                observations[symbol] = self._observation(frame, benchmark)
            except (KeyError, ValueError, IndexError):
                continue
        if not observations:
            return SectorAnalysis(sectors={}, symbol_sectors=assignments)

        member_percentiles = _percentiles(
            observation.weighted_relative_strength for observation in observations.values()
        )
        grouped: dict[str, list[_MemberObservation]] = {}
        for symbol, observation in observations.items():
            grouped.setdefault(assignments[symbol], []).append(observation)

        facts_by_sector = {
            sector: self._aggregate(sector, members, benchmark, member_percentiles)
            for sector, members in grouped.items()
        }
        sector_rs_percentiles = _percentiles(
            facts.relative_strength_vs_nifty for facts in facts_by_sector.values()
        )
        horizon_percentiles = {
            period: _percentiles(
                getattr(facts, f"return_{period}d") - benchmark.returns[period]
                for facts in facts_by_sector.values()
            )
            for period in RELATIVE_STRENGTH_HORIZONS
        }
        raw_scores = {
            sector: self._score(facts, sector_rs_percentiles[facts.relative_strength_vs_nifty])
            for sector, facts in facts_by_sector.items()
        }
        score_percentiles = _percentiles(raw_scores.values())
        ordered_sectors = sorted(raw_scores, key=lambda sector: (-raw_scores[sector], sector))
        profiles: dict[str, SectorProfile] = {}
        for rank, sector in enumerate(ordered_sectors, 1):
            facts = facts_by_sector[sector]
            percentile = score_percentiles[raw_scores[sector]]
            rotation = self._rotation(facts, benchmark, percentile)
            reasons = self._reasons(facts, benchmark, horizon_percentiles, rank)
            profiles[sector] = SectorProfile(
                score=round(raw_scores[sector], 2),
                confidence=round(min(1.0, facts.member_count / 20), 2),
                rank=rank,
                percentile=percentile,
                rotation=rotation,
                reasons=reasons,
                facts=facts,
            )
        return SectorAnalysis(sectors=profiles, symbol_sectors=assignments)

    @staticmethod
    def _observation(frame: pd.DataFrame, benchmark: BenchmarkSnapshot) -> _MemberObservation:
        """Build one valid member observation from an indicator frame."""
        enriched = frame if "EMA200" in frame.columns else add_indicators(frame)
        latest = enriched.iloc[-1]
        returns = {
            period: float(latest[f"Return{period}D"]) for period in RELATIVE_STRENGTH_HORIZONS
        }
        required = [
            "Close",
            "EMA20",
            "EMA50",
            "EMA200",
            "High52W",
            "Low52W",
            "AverageVolume",
            "Volume",
        ]
        if latest[required].isna().any() or not all(np.isfinite(list(returns.values()))):
            raise ValueError("Incomplete member facts")
        weighted_rs = sum(
            (returns[period] - benchmark.returns[period]) * weight
            for period, weight in RELATIVE_STRENGTH_PERIOD_WEIGHTS.items()
        )
        average_volume = float(latest["AverageVolume"])
        close = float(latest["Close"])
        return _MemberObservation(
            returns=returns,
            weighted_relative_strength=weighted_rs,
            above_ema20=close > float(latest["EMA20"]),
            above_ema50=close > float(latest["EMA50"]),
            above_ema200=close > float(latest["EMA200"]),
            new_high=float(latest["High"]) >= float(enriched["High"].iloc[-253:-1].max()),
            new_low=float(latest["Low"]) <= float(enriched["Low"].iloc[-253:-1].min()),
            volume_ratio=float(latest["Volume"]) / average_volume if average_volume > 0 else 0,
        )

    @staticmethod
    def _aggregate(
        name: str,
        members: list[_MemberObservation],
        benchmark: BenchmarkSnapshot,
        member_percentiles: Mapping[float, float],
    ) -> SectorFacts:
        """Aggregate valid member observations into sector facts."""
        size = len(members)
        returns = {
            period: float(np.mean([member.returns[period] for member in members]))
            for period in RELATIVE_STRENGTH_HORIZONS
        }
        relative_strength = sum(
            (returns[period] - benchmark.returns[period]) * weight
            for period, weight in RELATIVE_STRENGTH_PERIOD_WEIGHTS.items()
        )
        momentum_return = (
            0.20 * returns[5] + 0.25 * returns[10] + 0.30 * returns[20] + 0.25 * returns[50]
        )
        momentum_score = max(0.0, min(100.0, 50.0 + momentum_return * 250))
        return SectorFacts(
            name=name,
            member_count=size,
            return_5d=returns[5],
            return_10d=returns[10],
            return_20d=returns[20],
            return_50d=returns[50],
            return_100d=returns[100],
            return_150d=returns[150],
            return_250d=returns[250],
            relative_strength_vs_nifty=relative_strength,
            average_member_relative_strength=float(
                np.mean(
                    [member_percentiles[member.weighted_relative_strength] for member in members]
                )
            ),
            percentage_above_ema20=sum(member.above_ema20 for member in members) / size * 100,
            percentage_above_ema50=sum(member.above_ema50 for member in members) / size * 100,
            percentage_above_ema200=sum(member.above_ema200 for member in members) / size * 100,
            new_high_percentage=sum(member.new_high for member in members) / size * 100,
            new_low_percentage=sum(member.new_low for member in members) / size * 100,
            average_volume_ratio=float(np.mean([member.volume_ratio for member in members])),
            momentum_score=momentum_score,
        )

    @staticmethod
    def _score(facts: SectorFacts, sector_rs_percentile: float) -> float:
        """Combine leadership, member quality, breadth, and momentum."""
        breadth = (
            facts.percentage_above_ema20
            + facts.percentage_above_ema50
            + facts.percentage_above_ema200
        ) / 3
        breakout_quality = max(
            0.0, min(100.0, 50 + facts.new_high_percentage - facts.new_low_percentage)
        )
        return (
            0.35 * sector_rs_percentile
            + 0.25 * facts.average_member_relative_strength
            + 0.20 * breadth
            + 0.15 * facts.momentum_score
            + 0.05 * breakout_quality
        )

    @staticmethod
    def _rotation(
        facts: SectorFacts, benchmark: BenchmarkSnapshot, percentile: float
    ) -> SectorRotation:
        """Classify leadership direction using short/long relative acceleration."""
        short_relative = np.mean(
            [
                facts.return_5d - benchmark.returns[5],
                facts.return_10d - benchmark.returns[10],
                facts.return_20d - benchmark.returns[20],
            ]
        )
        long_relative = np.mean(
            [
                facts.return_100d - benchmark.returns[100],
                facts.return_150d - benchmark.returns[150],
                facts.return_250d - benchmark.returns[250],
            ]
        )
        acceleration = short_relative - long_relative
        if percentile >= 70 and long_relative > 0 and short_relative >= 0:
            return SectorRotation.LEADING
        if acceleration >= 0.03 and short_relative > 0:
            return SectorRotation.IMPROVING
        if long_relative > 0 and (short_relative < 0 or acceleration <= -0.03):
            return SectorRotation.WEAKENING
        return SectorRotation.LAGGING

    @staticmethod
    def _reasons(
        facts: SectorFacts,
        benchmark: BenchmarkSnapshot,
        horizon_percentiles: Mapping[int, Mapping[float, float]],
        rank: int,
    ) -> tuple[str, ...]:
        """Explain the strongest horizon, participation, and momentum."""
        relative_by_period = {
            period: getattr(facts, f"return_{period}d") - benchmark.returns[period]
            for period in RELATIVE_STRENGTH_HORIZONS
        }
        strongest_period = max(
            RELATIVE_STRENGTH_HORIZONS,
            key=lambda period: horizon_percentiles[period][relative_by_period[period]],
        )
        strongest_percentile = horizon_percentiles[strongest_period][
            relative_by_period[strongest_period]
        ]
        reasons = [
            (
                f"Highest RS over {strongest_period} days"
                if strongest_percentile == 99
                else f"Top {max(1, round(100 - strongest_percentile))}% RS over "
                f"{strongest_period} days"
            ),
            f"{facts.percentage_above_ema50:.0f}% above EMA50",
        ]
        if facts.percentage_above_ema20 >= 65 and facts.percentage_above_ema50 >= 65:
            reasons.append("Broad participation")
        if facts.momentum_score >= 65:
            reasons.append("Strong momentum")
        elif facts.momentum_score < 40:
            reasons.append("Momentum is weak")
        if rank == 1:
            reasons.append("Top-ranked sector in the current universe")
        return tuple(reasons)
