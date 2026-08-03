"""Feature scoring result model."""

from pydantic import BaseModel, ConfigDict, Field


class FeatureResult(BaseModel):
    """Normalized output emitted by every scoring feature."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    reasons: tuple[str, ...] = Field(min_length=1)
    state: str | None = None
