"""Industry group aggregation and relative-leadership ranking."""

from collections import defaultdict
from collections.abc import Mapping

import numpy as np
import pandas as pd

from app.core.v11_config import DEFAULT_INDUSTRY_GROUP_RULES, IndustryGroupRules
from app.data.benchmark import BenchmarkSnapshot
from app.models.industry import (
    IndustryGroupAnalysis,
    IndustryGroupFacts,
    IndustryGroupProfile,
    IndustryRotation,
)
from app.models.sector import SectorProfile

HORIZONS = (5, 10, 20, 50, 100, 150, 250)


class IndustryGroupEngine:
    """Rank configurable industry groups between sectors and stocks."""

    def __init__(self, rules: IndustryGroupRules = DEFAULT_INDUSTRY_GROUP_RULES) -> None:
        self._rules = rules

    def analyze(
        self,
        frames: Mapping[str, pd.DataFrame],
        benchmark: BenchmarkSnapshot,
        industry_by_symbol: Mapping[str, str] | None,
        sector_by_symbol: Mapping[str, str] | None = None,
        sector_profiles: Mapping[str, SectorProfile] | None = None,
        member_outputs: Mapping[str, object] | None = None,
    ) -> IndustryGroupAnalysis:
        """Aggregate mapped stocks; unmapped stocks remain eligible but unclassified."""
        mapping = {key.upper(): value for key, value in (industry_by_symbol or {}).items()}
        sectors = {key.upper(): value for key, value in (sector_by_symbol or {}).items()}
        members: dict[str, list[tuple[str, pd.DataFrame]]] = defaultdict(list)
        symbol_groups: dict[str, str] = {}
        warnings: list[str] = []
        for symbol, frame in frames.items():
            group = mapping.get(symbol)
            if group:
                members[group].append((symbol, frame))
                symbol_groups[symbol] = group
            else:
                symbol_groups[symbol] = "Unclassified"
        if not industry_by_symbol:
            warnings.append("Industry mappings unavailable; stocks remain eligible")
        relatives = {
            symbol: float(frame.iloc[-1].get("Return100D", 0.0)) - benchmark.returns.get(100, 0.0)
            for symbol, frame in frames.items()
        }
        ordered_relatives = sorted(relatives.values())
        percentiles = {
            symbol: 100.0
            * sum(value >= other for other in ordered_relatives)
            / len(ordered_relatives)
            for symbol, value in relatives.items()
        }
        raw = [
            self._facts(
                name,
                group,
                benchmark,
                sectors,
                sector_profiles or {},
                member_outputs or {},
                percentiles,
            )
            for name, group in members.items()
        ]
        ordered = sorted(raw, key=self._score, reverse=True)
        profiles: dict[str, IndustryGroupProfile] = {}
        count = len(ordered)
        for rank, facts in enumerate(ordered, 1):
            percentile = 100.0 if count == 1 else (count - rank) / (count - 1) * 100
            score = self._score(facts)
            rotation = self._rotation(score, facts.momentum_acceleration)
            group_warnings: list[str] = []
            if facts.member_count < self._rules.minimum_members:
                group_warnings.append(
                    f"Only {facts.member_count} mapped member(s); confidence reduced"
                )
            optional = (
                facts.relative_return_sector,
                facts.average_rs_percentile,
                facts.average_setup_score,
                facts.buy_candidates,
                facts.a_plus_setups,
            )
            availability = sum(value is not None for value in optional) / len(optional)
            if availability < 1:
                group_warnings.append("Member or parent-sector intelligence is incomplete")
            profiles[facts.name] = IndustryGroupProfile(
                rank=rank,
                percentile=round(percentile, 2),
                score=round(score, 2),
                confidence=min(1.0, facts.member_count / self._rules.minimum_members)
                * availability,
                rotation=rotation,
                parent_sector=facts.parent_sector,
                reasons=(
                    f"{facts.leadership_breadth:.0f}% leadership breadth",
                    f"{facts.relative_return_nifty:.1%} relative return vs NIFTY",
                ),
                warnings=tuple(group_warnings),
                facts=facts,
            )
        return IndustryGroupAnalysis(
            groups=profiles, symbol_groups=symbol_groups, warnings=tuple(warnings)
        )

    @staticmethod
    def _facts(
        name: str,
        members: list[tuple[str, pd.DataFrame]],
        benchmark: BenchmarkSnapshot,
        sectors: Mapping[str, str],
        sector_profiles: Mapping[str, SectorProfile],
        member_outputs: Mapping[str, object],
        percentiles: Mapping[str, float],
    ) -> IndustryGroupFacts:
        latest = [frame.iloc[-1] for _, frame in members]
        returns = {
            horizon: float(np.mean([row.get(f"Return{horizon}D", 0.0) for row in latest]))
            for horizon in HORIZONS
        }
        size = len(latest)

        def above(ema: str) -> float:
            return sum(float(row["Close"]) > float(row[ema]) for row in latest) / size * 100

        breadth = above("EMA50")
        parent_values = [sectors.get(symbol, "Unclassified") for symbol, _ in members]
        parent = max(set(parent_values), key=parent_values.count)
        volume_scores = [
            min(
                100.0,
                float(row["Volume"]) / max(float(row.get("AverageVolume", row["Volume"])), 1) * 50,
            )
            for row in latest
        ]
        relative_nifty = returns[100] - benchmark.returns.get(100, 0)
        parent_profile = sector_profiles.get(parent)
        relative_sector = (
            returns[100] - parent_profile.facts.return_100d if parent_profile else None
        )
        rs_values = [percentiles[symbol] for symbol, _ in members if symbol in percentiles]
        outputs = [member_outputs[symbol] for symbol, _ in members if symbol in member_outputs]
        output_facts = [getattr(item, "facts", item) for item in outputs]
        setup_scores = [
            float(value.setup_score)
            for value in output_facts
            if getattr(value, "setup_score", None) is not None
        ]
        decisions = [getattr(item, "decision_profile", None) for item in outputs]
        return IndustryGroupFacts(
            name=name,
            parent_sector=parent,
            member_count=size,
            returns=returns,
            relative_return_nifty=relative_nifty,
            relative_return_sector=relative_sector,
            average_rs_percentile=float(np.mean(rs_values)) if rs_values else None,
            percentage_above_ema20=above("EMA20"),
            percentage_above_ema50=breadth,
            percentage_above_ema200=above("EMA200"),
            new_high_percentage=sum(
                float(row["Close"]) >= float(row.get("High52W", row["Close"])) * 0.98
                for row in latest
            )
            / size
            * 100,
            new_low_percentage=sum(
                float(row["Close"]) <= float(row.get("Low52W", row["Close"])) * 1.02
                for row in latest
            )
            / size
            * 100,
            average_volume_score=float(np.mean(volume_scores)),
            average_setup_score=float(np.mean(setup_scores)) if setup_scores else None,
            buy_candidates=(
                sum(item is not None and item.action.value == "BUY" for item in decisions)
                if outputs
                else None
            ),
            a_plus_setups=(
                sum(getattr(value, "setup_grade", None) == "A+" for value in output_facts)
                if outputs
                else None
            ),
            leadership_breadth=breadth,
            momentum_acceleration=returns[20] - returns[50],
        )

    @staticmethod
    def _score(facts: IndustryGroupFacts) -> float:
        return float(
            np.clip(
                50
                + facts.relative_return_nifty * 150
                + (facts.leadership_breadth - 50) * 0.5
                + facts.momentum_acceleration * 100,
                0,
                100,
            )
        )

    @staticmethod
    def _rotation(score: float, acceleration: float) -> IndustryRotation:
        if score >= 70 and acceleration >= 0:
            return IndustryRotation.LEADING
        if acceleration > 0.02:
            return IndustryRotation.IMPROVING
        if score < 30 and acceleration <= 0:
            return IndustryRotation.LAGGING
        if acceleration < -0.02:
            return IndustryRotation.WEAKENING
        return IndustryRotation.NEUTRAL
