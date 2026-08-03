"""Intrinsic stock-quality scoring feature."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class StockFeature(ScoringFeature):
    """Expose the precomputed Stock Intelligence profile to aggregation."""

    name = "stock"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return overall intrinsic quality, confidence, grade, and evidence."""
        return FeatureResult(
            name=self.name,
            score=facts.stock_score,
            confidence=facts.stock_profile.confidence,
            state=facts.stock_grade.value,
            reasons=facts.stock_profile.reasons,
        )
