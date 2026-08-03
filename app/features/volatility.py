"""Risk-adjusted volatility scoring."""

from app.engine.feature import ScoringFeature
from app.models.facts import Facts
from app.models.feature_result import FeatureResult


class VolatilityFeature(ScoringFeature):
    """Prefer tradable movement without rewarding extreme instability."""

    name = "volatility"

    def evaluate(self, facts: Facts) -> FeatureResult:
        """Score annualized volatility and ATR as a percentage of price."""
        volatility = facts.annualized_volatility
        atr_percent = facts.atr14 / facts.close
        if 0.15 <= volatility <= 0.45 and atr_percent <= 0.05:
            score = 100.0
            reason = "Volatility is in the preferred momentum range"
        elif volatility < 0.15:
            score = max(30.0, volatility / 0.15 * 80.0)
            reason = "Volatility may be too low for strong momentum"
        else:
            excess = max(volatility - 0.45, atr_percent - 0.05)
            score = max(0.0, 100.0 - excess * 180.0)
            reason = "Volatility is elevated and increases execution risk"
        return FeatureResult(
            name=self.name,
            score=round(score, 2),
            confidence=1,
            reasons=(reason, f"ATR is {atr_percent:.1%} of price"),
        )
