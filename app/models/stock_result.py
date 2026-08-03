"""Ranked scanner output model."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.decision import DecisionProfile
from app.models.facts import Facts
from app.models.feature_result import FeatureResult
from app.models.situation import SituationProfile


class StockResult(BaseModel):
    """Aggregate score and supporting evidence for one scanned stock."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(default=0, ge=0)
    symbol: str = Field(min_length=1)
    final_score: float = Field(ge=0, le=100)
    decision_profile: DecisionProfile | None = None
    situation_profile: SituationProfile | None = None
    features: dict[str, FeatureResult]
    facts: Facts

    @property
    def reasons(self) -> tuple[str, ...]:
        """Flatten all feature explanations in deterministic feature order."""
        return tuple(
            reason
            for feature_name in sorted(self.features)
            for reason in self.features[feature_name].reasons
        )

    @property
    def decision_score(self) -> float:
        """Return the adaptive decision score, falling back for legacy results."""
        return self.decision_profile.decision_score if self.decision_profile else self.final_score
