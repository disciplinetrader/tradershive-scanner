"""Institutional volume-intelligence scoring adapter."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class VolumeFeature(ScoringFeature):
    """Expose the precomputed Volume Intelligence profile to aggregation."""

    name = "volume"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return institutional volume quality, confidence, state, and evidence."""
        return FeatureResult(
            name=self.name,
            score=facts.volume_score,
            confidence=facts.volume_profile.confidence,
            state=facts.volume_profile.volume_state.value,
            reasons=facts.volume_profile.reasons,
        )
