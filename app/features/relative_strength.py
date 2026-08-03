"""Benchmark-relative performance scoring."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class RelativeStrengthFeature(ScoringFeature):
    """Score 63-session excess return versus the configured benchmark."""

    name = "relative_strength"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Map excess return to a bounded zero-to-100 score."""
        excess_return = facts.return_63d - facts.benchmark_return_63d
        score = min(100.0, max(0.0, 50.0 + excess_return * 250.0))
        direction = "outperformed" if excess_return >= 0 else "underperformed"
        return FeatureResult(
            name=self.name,
            score=round(score, 2),
            confidence=min(1.0, facts.history_days / 252),
            reasons=(f"Stock {direction} benchmark by {abs(excess_return):.1%} over 63 sessions",),
        )
