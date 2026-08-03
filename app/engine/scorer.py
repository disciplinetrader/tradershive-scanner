"""Confidence-aware weighted feature aggregation."""

from collections.abc import Mapping

from app.engine.registry import FeatureRegistry
from app.models.facts import Facts
from app.models.feature_result import FeatureResult
from app.models.stock_result import StockResult


class Scorer:
    """Run registered features and calculate a normalized weighted score."""

    def __init__(self, registry: FeatureRegistry, weights: Mapping[str, float]) -> None:
        """Validate and store feature weights."""
        if set(registry.names) != set(weights):
            raise ValueError("Weights must exactly match registered feature names")
        if any(weight <= 0 for weight in weights.values()):
            raise ValueError("Feature weights must be positive")
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Feature weights must sum to 1.0, got {total}")
        self._registry = registry
        self._weights = dict(weights)

    def score(self, facts: Facts) -> StockResult:
        """Calculate each feature and aggregate confidence-adjusted scores."""
        results: dict[str, FeatureResult] = {}
        weighted_points = 0.0
        effective_weight = 0.0
        for feature in self._registry:
            result = feature.evaluate(facts)
            results[feature.name] = result
            confidence_weight = self._weights[feature.name] * result.confidence
            weighted_points += result.score * confidence_weight
            effective_weight += confidence_weight
        final_score = weighted_points / effective_weight if effective_weight else 0.0
        return StockResult(
            symbol=facts.symbol,
            final_score=round(final_score, 2),
            features=results,
            facts=facts,
        )
