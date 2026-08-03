"""Central Pivot Range Intelligence scoring adapter."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class CPRFeature(ScoringFeature):
    """Expose the precomputed CPR profile to aggregate scoring."""

    name = "cpr"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return CPR opportunity score, confidence, state, and evidence."""
        return FeatureResult(
            name=self.name,
            score=facts.cpr_score,
            confidence=facts.cpr_profile.confidence,
            state=facts.cpr_profile.cpr_state.value,
            reasons=facts.cpr_profile.reasons,
        )
