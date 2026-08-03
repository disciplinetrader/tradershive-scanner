"""Breadth Intelligence scoring adapter."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class BreadthFeature(ScoringFeature):
    """Expose the shared precomputed breadth profile to stock scoring."""

    name = "breadth"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return breadth quality, confidence, state, and explanations."""
        return FeatureResult(
            name=self.name,
            score=facts.breadth_score,
            confidence=facts.breadth_profile.confidence,
            state=facts.breadth_profile.breadth_state.value,
            reasons=facts.breadth_profile.reasons,
        )
