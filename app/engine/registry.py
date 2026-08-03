"""Validated registry of scoring features."""

from collections.abc import Iterable, Iterator

from app.engine.feature import ScoringFeature


class FeatureRegistry:
    """Ordered collection that prevents duplicate feature names."""

    def __init__(self, features: Iterable[ScoringFeature]) -> None:
        """Build a registry from a non-empty feature iterable."""
        self._features = tuple(features)
        if not self._features:
            raise ValueError("At least one scoring feature is required")
        names = [feature.name for feature in self._features]
        if len(names) != len(set(names)):
            raise ValueError("Feature names must be unique")

    def __iter__(self) -> Iterator[ScoringFeature]:
        """Iterate through features in registration order."""
        return iter(self._features)

    @property
    def names(self) -> tuple[str, ...]:
        """Return registered feature names in execution order."""
        return tuple(feature.name for feature in self._features)
