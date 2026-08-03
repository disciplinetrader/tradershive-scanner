"""Sector leadership and rotation scoring feature."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class SectorFeature(ScoringFeature):
    """Expose inherited sector quality and rotation to stock scoring."""

    name = "sector"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return sector score, coverage confidence, rotation state, and reasons."""
        return FeatureResult(
            name=self.name,
            score=facts.sector_score,
            confidence=facts.sector_confidence,
            state=facts.sector_rotation.value,
            reasons=facts.sector_reasons,
        )
