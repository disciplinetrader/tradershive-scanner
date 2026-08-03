"""O'Neil/Minervini-style benchmark-relative strength scoring."""

import math
from collections.abc import Iterable

from app.core.constants import RELATIVE_STRENGTH_HORIZONS
from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult
from app.models.relative_strength import RelativeStrengthHorizon, RelativeStrengthProfile
from app.models.stock_result import StockResult


class RelativeStrengthFeature(ScoringFeature):
    """Score cross-sectional leadership using the universe RS percentile."""

    name = "relative_strength"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return percentile-driven RS with horizon-specific explanations."""
        horizons = facts.rs_profile.horizons()
        strongest_period, strongest = max(
            horizons.items(), key=lambda item: (item[1].percentile, item[0])
        )
        reasons = [self._strongest_horizon_reason(strongest_period, strongest.percentile)]

        intermediate_percentile = sum(horizons[period].percentile for period in (50, 100, 150)) / 3
        if intermediate_percentile >= 75:
            reasons.append("Strong intermediate-term leadership")
        else:
            reasons.append(
                f"Intermediate-term leadership at the {intermediate_percentile:.0f}th percentile"
            )

        short_term_percentile = (horizons[5].percentile + horizons[10].percentile) / 2
        if short_term_percentile > horizons[20].percentile + 5:
            reasons.append("Short-term momentum improving")
        elif short_term_percentile < horizons[20].percentile - 5:
            reasons.append("Short-term momentum losing relative strength")
        else:
            reasons.append("Short-term relative momentum is stable")

        return FeatureResult(
            name=self.name,
            score=facts.relative_strength_percentile,
            confidence=min(1.0, facts.history_days / 251),
            reasons=tuple(reasons),
        )

    @staticmethod
    def _strongest_horizon_reason(period: int, percentile: float) -> str:
        """Describe the profile's strongest cross-sectional horizon."""
        if percentile >= 50:
            top_percent = max(1, math.ceil(100 - percentile))
            return f"Top {top_percent}% over {period} sessions"
        return f"{period}-session leadership is below the universe median"


def _percentiles(values: Iterable[float]) -> dict[float, float]:
    """Calculate zero-to-99 tie-aware O'Neil-style percentiles by unique value."""
    sorted_values = sorted(values)
    if not sorted_values:
        return {}
    if len(sorted_values) == 1:
        return {sorted_values[0]: 100.0}
    positions_by_value: dict[float, list[int]] = {}
    for index, value in enumerate(sorted_values):
        positions_by_value.setdefault(value, []).append(index)
    return {
        value: round((sum(positions) / len(positions)) / (len(sorted_values) - 1) * 99, 2)
        for value, positions in positions_by_value.items()
    }


def assign_relative_strength_percentiles(results: list[StockResult]) -> list[StockResult]:
    """Assign aggregate and per-horizon cross-sectional leadership percentiles."""
    if not results:
        return []
    aggregate_percentiles = _percentiles(
        result.facts.rs_profile.weighted_relative_return for result in results
    )
    horizon_percentiles = {
        period: _percentiles(
            result.facts.rs_profile.horizons()[period].relative_return for result in results
        )
        for period in RELATIVE_STRENGTH_HORIZONS
    }

    ranked: list[StockResult] = []
    for result in results:
        facts = result.facts
        profile_horizons = facts.rs_profile.horizons()
        profile = RelativeStrengthProfile(
            **{
                f"rs{period}": RelativeStrengthHorizon(
                    relative_return=profile_horizons[period].relative_return,
                    percentile=horizon_percentiles[period][
                        profile_horizons[period].relative_return
                    ],
                )
                for period in RELATIVE_STRENGTH_HORIZONS
            }
        )
        percentile = aggregate_percentiles[facts.rs_profile.weighted_relative_return]
        ranked.append(
            result.model_copy(
                update={
                    "facts": facts.model_copy(
                        update={
                            "relative_strength_score": percentile,
                            "relative_strength_percentile": percentile,
                            "rs_profile": profile,
                        }
                    )
                }
            )
        )
    return ranked
