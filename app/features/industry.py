"""Industry-group scoring adapter."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class IndustryGroupFeature(ScoringFeature):
    """Expose inherited industry leadership to aggregate scoring."""

    name = "industry_group"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Return a neutral low-confidence result when mapping is unavailable."""
        profile = facts.industry_group_profile
        return FeatureResult(
            name=self.name,
            score=facts.industry_group_score,
            confidence=profile.confidence if profile else 0,
            state=facts.industry_group_rotation.value,
            reasons=(
                profile.reasons
                if profile
                else ("Industry mapping unavailable; stock remains eligible",)
            ),
        )
