"""Broad-market regime scoring."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class MarketFeature(ScoringFeature):
    """Reward stocks scanned during a supportive benchmark regime."""

    name = "market"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Score the binary benchmark trend fact."""
        if facts.market_trend:
            return FeatureResult(
                name=self.name,
                score=100,
                confidence=1,
                reasons=("Benchmark is above its 200-day EMA with bullish 50/200 alignment",),
            )
        return FeatureResult(
            name=self.name,
            score=20,
            confidence=1,
            reasons=("Benchmark trend is not supportive",),
        )
