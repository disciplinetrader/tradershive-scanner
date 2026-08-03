"""Ranked scanner output model."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class StockResult(BaseModel):
    """Aggregate score and supporting evidence for one scanned stock."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(default=0, ge=0)
    symbol: str = Field(min_length=1)
    final_score: float = Field(ge=0, le=100)
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
