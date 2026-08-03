"""Absolute momentum scoring."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class MomentumFeature(ScoringFeature):
    """Score medium-term return while identifying immediate reversals."""

    name = "momentum"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Map 63-session and daily returns to a bounded score."""
        base = 50.0 + facts.return_63d * 200.0
        daily_adjustment = min(10.0, max(-10.0, facts.daily_return * 200.0))
        score = min(100.0, max(0.0, base + daily_adjustment))
        reasons = [f"63-session return is {facts.return_63d:.1%}"]
        if facts.daily_return >= 0:
            reasons.append(f"Latest session gained {facts.daily_return:.1%}")
        else:
            reasons.append(f"Latest session declined {abs(facts.daily_return):.1%}")
        return FeatureResult(
            name=self.name,
            score=round(score, 2),
            confidence=min(1.0, facts.history_days / 252),
            reasons=tuple(reasons),
        )
