"""Anchored VWAP scoring adapter."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class AVWAPFeature(ScoringFeature):
    """Expose precomputed AVWAP intelligence to aggregate scoring."""

    name = "avwap"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return AVWAP score and evidence."""
        return FeatureResult(
            name=self.name,
            score=facts.avwap_score,
            confidence=facts.avwap_profile.confidence,
            state=facts.avwap_profile.state.value,
            reasons=facts.avwap_profile.reasons,
        )
