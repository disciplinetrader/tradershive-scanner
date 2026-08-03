"""Advanced institutional semantics derived from existing volume facts."""

import pandas as pd

from app.core.v11_config import DEFAULT_VOLUME_EVENT_THRESHOLDS, VolumeEventThresholds
from app.models.volume import VolumeProfile, VolumeSignature


class AdvancedVolumeEngine:
    """Classify advanced events without duplicating VolumeEngine calculations."""

    def __init__(self, thresholds: VolumeEventThresholds = DEFAULT_VOLUME_EVENT_THRESHOLDS) -> None:
        self._thresholds = thresholds

    def enhance(self, profile: VolumeProfile, frame: pd.DataFrame) -> VolumeProfile:
        """Translate existing volume facts into institutional event evidence."""
        facts = profile.facts
        pocket = facts.pocket_pivot_volume and not facts.high_volume_reversal
        supporting = facts.low_volume_pullback and facts.buying_pressure >= facts.selling_pressure
        stalling = facts.volume_churn and facts.average_volume_trend > 0
        churning = facts.volume_churn
        climax_top = facts.volume_climax and facts.high_volume_reversal
        selling_climax = (
            facts.volume_climax
            and facts.selling_pressure > facts.buying_pressure
            and not facts.high_volume_reversal
        )
        hidden_accumulation = facts.buying_pressure
        hidden_distribution = facts.selling_pressure
        ratio = facts.up_volume_percent / max(facts.down_volume_percent, 0.01)
        dry_sequence = facts.volume_contraction_sequence >= 2
        demand = facts.volume_expansion_percent >= 30 and facts.buying_pressure > 55
        supply = facts.volume_expansion_percent >= 30 and facts.selling_pressure > 55
        signature = self._signature(
            profile,
            hidden_accumulation,
            hidden_distribution,
            dry_sequence,
            climax_top or selling_climax,
            demand,
            supply,
        )
        rating = (
            "A"
            if hidden_accumulation >= 75
            else "B" if hidden_accumulation >= 60 else "D" if hidden_distribution >= 65 else "C"
        )
        reasons = list(profile.reasons)
        for detected, text in (
            (pocket, "Pocket Pivot volume"),
            (supporting, "Supporting action at trend support"),
            (stalling, "Institutional stalling day"),
            (churning, "High-volume churning"),
            (climax_top, "Potential climax top"),
            (selling_climax, "Potential selling climax"),
        ):
            if detected:
                reasons.append(text)
        return profile.model_copy(
            update={
                "pocket_pivot": pocket,
                "supporting_action": supporting,
                "stalling_day": stalling,
                "churning_day": churning,
                "climax_top": climax_top,
                "selling_climax": selling_climax,
                "hidden_accumulation_score": round(hidden_accumulation, 2),
                "hidden_distribution_score": round(hidden_distribution, 2),
                "up_down_volume_ratio": round(ratio, 3),
                "accumulation_distribution_rating": rating,
                "volume_signature": signature,
                "volume_event_confidence": min(1.0, facts.history_days / 50),
                "dry_up_sequence": dry_sequence,
                "demand_expansion": demand,
                "supply_expansion": supply,
                "reasons": tuple(dict.fromkeys(reasons)),
            }
        )

    @staticmethod
    def _signature(
        profile: VolumeProfile,
        accumulation: float,
        distribution: float,
        dry: bool,
        climactic: bool,
        demand: bool,
        supply: bool,
    ) -> VolumeSignature:
        if climactic:
            return VolumeSignature.CLIMACTIC
        if accumulation >= 70 and distribution >= 60:
            return VolumeSignature.CONFLICTED
        if accumulation >= 75:
            return VolumeSignature.PROFESSIONAL_ACCUMULATION
        if demand:
            return VolumeSignature.HEALTHY_DEMAND
        if dry:
            return VolumeSignature.CONSTRUCTIVE_DRY_UP
        if distribution >= 65 or supply:
            return VolumeSignature.DISTRIBUTION
        if profile.score < 40:
            return VolumeSignature.WEAK_DEMAND
        return VolumeSignature.NEUTRAL
