"""Presentation adapter for scan-level situational awareness."""

from app.models.situation import SituationProfile


class SituationFeature:
    """Render situational guidance without participating in stock scoring."""

    name = "situation"

    def summarize(self, profile: SituationProfile) -> tuple[str, ...]:
        """Return concise user-facing summary lines."""
        lines = (
            f"Environment: {profile.market_regime.value}",
            f"Bias: {profile.trading_bias.value}",
            f"Aggression: {profile.aggression.value}",
            f"Risk: {profile.risk_environment.value}",
            f"Position sizing: {profile.position_sizing_guidance.value}",
        )
        if profile.breadth_profile:
            lines += (
                f"Breadth: {profile.breadth_profile.breadth_state.value} "
                f"({profile.breadth_profile.score:.1f})",
            )
        if profile.cpr_environment != "Unavailable":
            lines += (
                f"CPR: {profile.cpr_environment} "
                f"({profile.cpr_breakout_participation:.0f}% breakout-ready)",
            )
        return lines
