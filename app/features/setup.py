"""Actionable setup-quality scoring feature."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class SetupFeature(ScoringFeature):
    """Expose setup quality without emitting a trading decision."""

    name = "setup"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return setup score, confidence, type, and objective evidence."""
        return FeatureResult(
            name=self.name,
            score=facts.setup_score,
            confidence=facts.setup_profile.confidence,
            state=facts.setup_type.value,
            reasons=facts.setup_profile.reasons,
        )
