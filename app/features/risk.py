"""Risk-quality scoring feature."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult
from app.models.risk import RiskGrade


class RiskFeature(ScoringFeature):
    """Expose structural risk quality without issuing a trade decision."""

    name = "risk"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return risk score, confidence, grade, reasons, and warnings."""
        profile = facts.risk_profile
        if profile is None:
            return FeatureResult(
                name=self.name,
                score=0,
                confidence=0,
                state=RiskGrade.REJECT.value,
                reasons=("Risk profile is unavailable",),
            )
        reasons = profile.reasons + profile.warnings
        return FeatureResult(
            name=self.name,
            score=profile.score,
            confidence=profile.confidence,
            state=profile.grade.value,
            reasons=reasons or ("Risk evidence is unavailable",),
        )
