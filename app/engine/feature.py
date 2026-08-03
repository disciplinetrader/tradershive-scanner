"""Feature scoring contract."""

from abc import ABC, abstractmethod

from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class ScoringFeature(ABC):
    """A deterministic, explainable scoring component."""

    name: str

    @abstractmethod
    def evaluate(self, facts: Facts) -> FeatureResult:
        """Evaluate one set of facts and return a normalized score."""
