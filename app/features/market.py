"""Multi-dimensional market regime scoring feature."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class MarketFeature(ScoringFeature):
    """Expose Market Intelligence quality to the aggregate stock scorer."""

    name = "market"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return market quality score, confidence, state, and profile reasons."""
        return FeatureResult(
            name=self.name,
            score=facts.market_score,
            confidence=facts.market_confidence,
            state=facts.market_state.value,
            reasons=facts.market_reasons,
        )
