"""Typed multi-horizon relative-strength profile models."""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.constants import RELATIVE_STRENGTH_PERIOD_WEIGHTS


class RelativeStrengthHorizon(BaseModel):
    """Benchmark-relative return and cross-sectional percentile for one horizon."""

    model_config = ConfigDict(frozen=True)

    relative_return: float
    percentile: float = Field(default=0, ge=0, le=100)


class RelativeStrengthProfile(BaseModel):
    """Complete short-, intermediate-, and long-term leadership profile."""

    model_config = ConfigDict(frozen=True)

    rs5: RelativeStrengthHorizon
    rs10: RelativeStrengthHorizon
    rs20: RelativeStrengthHorizon
    rs50: RelativeStrengthHorizon
    rs100: RelativeStrengthHorizon
    rs150: RelativeStrengthHorizon
    rs250: RelativeStrengthHorizon

    def horizons(self) -> Mapping[int, RelativeStrengthHorizon]:
        """Return the profile keyed by trading-session horizon."""
        return {
            5: self.rs5,
            10: self.rs10,
            20: self.rs20,
            50: self.rs50,
            100: self.rs100,
            150: self.rs150,
            250: self.rs250,
        }

    @computed_field
    @property
    def weighted_relative_return(self) -> float:
        """Return the configured long-horizon-weighted excess return."""
        horizons = self.horizons()
        return sum(
            horizons[period].relative_return * weight
            for period, weight in RELATIVE_STRENGTH_PERIOD_WEIGHTS.items()
        )
