"""Participation and liquidity scoring."""

import math

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class VolumeFeature(ScoringFeature):
    """Reward above-average participation, especially on positive sessions."""

    name = "volume"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Score current volume relative to its 20-session average."""
        score = min(100.0, max(0.0, 35.0 + math.log2(max(facts.volume_ratio, 0.25)) * 35.0))
        if facts.daily_return < 0:
            score = max(0.0, score - 15.0)
        participation = "above" if facts.volume_ratio >= 1 else "below"
        reasons = [f"Volume is {facts.volume_ratio:.2f}x average ({participation} normal)"]
        if facts.daily_return < 0 and facts.volume_ratio > 1:
            reasons.append("Elevated volume occurred on a down session")
        return FeatureResult(
            name=self.name,
            score=round(score, 2),
            confidence=1 if facts.average_volume > 0 else 0,
            reasons=tuple(reasons),
        )
