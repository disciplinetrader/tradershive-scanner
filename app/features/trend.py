"""Price trend quality scoring."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class TrendFeature(ScoringFeature):
    """Score moving-average structure and proximity to yearly highs."""

    name = "trend"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Evaluate price position and EMA alignment."""
        score = 0.0
        reasons: list[str] = []
        if facts.close > facts.ema20:
            score += 20
            reasons.append("Price is above EMA20")
        else:
            reasons.append("Price is below EMA20")
        if facts.close > facts.ema50:
            score += 20
            reasons.append("Price is above EMA50")
        if facts.close > facts.ema200:
            score += 25
            reasons.append("Price is above EMA200")
        if facts.ema_alignment:
            score += 25
            reasons.append("EMA20, EMA50, and EMA200 are bullishly aligned")
        if facts.near_52_week_high:
            score += 10
            reasons.append("Price is within 10% of its 52-week high")
        else:
            reasons.append(f"Price is {facts.distance_from_high:.1%} below its 52-week high")
        return FeatureResult(name=self.name, score=score, confidence=1, reasons=tuple(reasons))
