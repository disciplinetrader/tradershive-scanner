"""Adaptive explainable decision aggregation over existing intelligence profiles."""

from collections.abc import Mapping

from app.core.config import DEFAULT_DECISION_WEIGHTS, DecisionWeights
from app.core.v11_config import DEFAULT_DECISION_GATES, DecisionGates, ScannerProfileConfig
from app.models.avwap import AVWAPProfile, AVWAPState
from app.models.breadth import BreadthProfile, BreadthState
from app.models.cpr import CPRProfile
from app.models.decision import (
    DecisionAction,
    DecisionGrade,
    DecisionProfile,
    WeightedDecisionComponent,
)
from app.models.industry import IndustryGroupProfile, IndustryRotation
from app.models.market import MarketProfile, MarketRegime
from app.models.relative_strength import RelativeStrengthProfile
from app.models.risk import RiskGrade, RiskProfile
from app.models.sector import SectorProfile, SectorRotation
from app.models.setup import SetupProfile, SetupType
from app.models.stock import StockProfile
from app.models.volume import VolumeProfile, VolumeSignature


def np_mean(values: list[float]) -> float:
    """Return a dependency-free arithmetic mean for decision subscores."""
    return sum(values) / len(values) if values else 0.0


class DecisionEngine:
    """Combine existing engine profiles using market-regime-adaptive weights."""

    def __init__(
        self,
        regime_weights: Mapping[MarketRegime, DecisionWeights] | None = None,
        gates: DecisionGates = DEFAULT_DECISION_GATES,
    ) -> None:
        """Initialize with a complete, externally tunable regime configuration."""
        self._weights = dict(regime_weights or DEFAULT_DECISION_WEIGHTS)
        if set(self._weights) != set(MarketRegime):
            raise ValueError("Decision weights must cover every market regime")
        self._gates = gates

    def evaluate(
        self,
        market: MarketProfile | None,
        sector: SectorProfile | None,
        relative_strength: RelativeStrengthProfile | None,
        stock: StockProfile | None,
        setup: SetupProfile | None,
        risk: RiskProfile | None,
        breadth: BreadthProfile | None = None,
        cpr: CPRProfile | None = None,
        avwap: AVWAPProfile | None = None,
        industry: IndustryGroupProfile | None = None,
        volume: VolumeProfile | None = None,
        scanner_profile: ScannerProfileConfig | None = None,
    ) -> DecisionProfile:
        """Return one decision without recalculating subordinate intelligence."""
        regime = market.state if market else MarketRegime.RANGE
        weights = self._weights[regime]
        rs_score = self._relative_strength_score(relative_strength)
        observations: dict[str, tuple[float, float]] = {
            "market": (market.score, market.confidence) if market else (0, 0),
            "breadth": (breadth.score, breadth.confidence) if breadth else (0, 0),
            "cpr": (cpr.score, cpr.confidence) if cpr else (0, 0),
            "sector": (sector.score, sector.confidence) if sector else (0, 0),
            "relative_strength": (rs_score, 1.0) if relative_strength else (0, 0),
            "stock": (stock.score, stock.confidence) if stock else (0, 0),
            "setup": (setup.score, setup.confidence) if setup else (0, 0),
            "risk": (risk.score, risk.confidence) if risk else (0, 0),
        }
        configured = weights.model_dump()
        breakdown = {
            name: WeightedDecisionComponent(
                weight=configured[name],
                score=score,
                confidence=confidence,
                contribution=round(score * configured[name], 2),
            )
            for name, (score, confidence) in observations.items()
        }
        decision_score = sum(item.contribution for item in breakdown.values())
        confidence = sum(item.confidence * item.weight for item in breakdown.values())
        action = self._action(
            decision_score, confidence, regime, sector, stock, setup, risk, breadth, cpr, avwap
        )
        hard_warnings: list[str] = []
        profile_config = scanner_profile or ScannerProfileConfig()
        if market and market.market_pressure_score > self._gates.maximum_market_pressure:
            action = DecisionAction.AVOID
            hard_warnings.append("Hard gate: market pressure exceeds configured maximum")
        if setup and setup.failure_risk_score > self._gates.maximum_failure_risk:
            action = DecisionAction.AVOID
            hard_warnings.append("Hard gate: failed-breakout risk is excessive")
        if volume and volume.volume_signature == VolumeSignature.DISTRIBUTION:
            action = DecisionAction.AVOID
            hard_warnings.append("Hard gate: institutional distribution")
        if (
            industry
            and industry.rotation == IndustryRotation.LAGGING
            and sector
            and sector.rotation == SectorRotation.LAGGING
        ):
            action = DecisionAction.AVOID
            hard_warnings.append("Hard gate: sector and industry are both lagging")
        if (
            action == DecisionAction.BUY
            and risk
            and (risk.facts.available_r_multiple or 0) < self._gates.minimum_r
        ):
            action = DecisionAction.WATCHLIST
            hard_warnings.append("BUY gate: insufficient available R")
        if (
            action == DecisionAction.BUY
            and profile_config.eligible_setups
            and setup
            and setup.best_setup_type.value not in profile_config.eligible_setups
        ):
            action = DecisionAction.WATCHLIST
            hard_warnings.append("BUY gate: setup is not eligible for selected scanner profile")
        minimum_decision_score = max(
            self._gates.minimum_buy_score, profile_config.minimum_decision_score
        )
        if action == DecisionAction.BUY and decision_score < minimum_decision_score:
            action = DecisionAction.WATCHLIST
            hard_warnings.append("BUY gate: decision score is below scanner-profile minimum")
        if action == DecisionAction.BUY and confidence < self._gates.minimum_confidence:
            action = DecisionAction.WATCHLIST
            hard_warnings.append("BUY gate: confidence is below configured minimum")
        rs_percentile = relative_strength.rs250.percentile if relative_strength else 0.0
        minimum_rs = max(self._gates.minimum_rs, profile_config.minimum_rs)
        if action == DecisionAction.BUY and rs_percentile < minimum_rs:
            action = DecisionAction.WATCHLIST
            hard_warnings.append("BUY gate: Relative Strength is below scanner-profile minimum")
        if action == DecisionAction.BUY and regime not in profile_config.allowed_market_regimes:
            action = DecisionAction.WATCHLIST
            hard_warnings.append("BUY gate: market regime is ineligible for scanner profile")
        if (
            action == DecisionAction.BUY
            and sector
            and sector.percentile
            < max(
                profile_config.minimum_sector_percentile,
                profile_config.minimum_leadership_percentile,
            )
        ):
            action = DecisionAction.WATCHLIST
            hard_warnings.append("BUY gate: sector leadership is below scanner-profile minimum")
        if action == DecisionAction.BUY and industry:
            if industry.confidence < 0.75:
                action = DecisionAction.WATCHLIST
                hard_warnings.append("BUY gate: industry leadership data is incomplete")
            elif industry.percentile < max(
                profile_config.minimum_industry_percentile,
                profile_config.minimum_leadership_percentile,
            ):
                action = DecisionAction.WATCHLIST
                hard_warnings.append(
                    "BUY gate: industry leadership is below scanner-profile minimum"
                )
        if action == DecisionAction.BUY and risk and risk.score < profile_config.minimum_risk_score:
            action = DecisionAction.WATCHLIST
            hard_warnings.append("BUY gate: risk score is below scanner-profile minimum")
        reasons, warnings = self._explain(
            market,
            sector,
            relative_strength,
            stock,
            setup,
            risk,
            breadth,
            cpr,
            avwap,
            observations,
        )
        context_score = market.score if market else 0
        leadership_score = np_mean(
            [sector.score if sector else 0, industry.score if industry else 50]
        )
        institutional_score = np_mean(
            [volume.score if volume else 50, avwap.score if avwap else 50]
        )
        timing_score = np_mean([setup.score if setup else 0, cpr.score if cpr else 50])
        return DecisionProfile(
            decision_score=round(decision_score, 2),
            confidence=round(confidence, 2),
            grade=(
                DecisionGrade.REJECT
                if action == DecisionAction.AVOID
                else self._grade(decision_score)
            ),
            action=action,
            reasons=reasons,
            warnings=tuple(dict.fromkeys((*hard_warnings, *warnings))),
            weight_breakdown=breakdown,
            context_score=round(context_score, 2),
            leadership_score=round(leadership_score, 2),
            institutional_score=round(institutional_score, 2),
            timing_score=round(timing_score, 2),
            setup_score=setup.score if setup else 0,
            risk_score=risk.score if risk else 0,
            decision_confidence=round(confidence, 2),
            scanner_profile=profile_config.name.value,
        )

    @staticmethod
    def _relative_strength_score(profile: RelativeStrengthProfile | None) -> float:
        """Aggregate existing intermediate and long-horizon percentiles."""
        if profile is None:
            return 0
        horizons = profile.horizons()
        return (
            horizons[20].percentile * 0.10
            + horizons[50].percentile * 0.20
            + horizons[150].percentile * 0.30
            + horizons[250].percentile * 0.40
        )

    @staticmethod
    def _action(
        score: float,
        confidence: float,
        regime: MarketRegime,
        sector: SectorProfile | None,
        stock: StockProfile | None,
        setup: SetupProfile | None,
        risk: RiskProfile | None,
        breadth: BreadthProfile | None,
        cpr: CPRProfile | None,
        avwap: AVWAPProfile | None,
    ) -> DecisionAction:
        """Apply transparent action gates after adaptive score calculation."""
        hostile_market = regime in {
            MarketRegime.WEAK_BEAR,
            MarketRegime.BEAR,
            MarketRegime.CAPITULATION,
        }
        weak_sector = sector is not None and (
            sector.rotation == SectorRotation.LAGGING and sector.score < 40
        )
        weak_setup = setup is None or setup.score < 40 or setup.best_setup_type == SetupType.NONE
        poor_risk = risk is None or risk.grade == RiskGrade.REJECT or risk.score < 45
        poor_breadth = breadth is not None and (
            breadth.score < 30
            or breadth.breadth_state in {BreadthState.DISTRIBUTION, BreadthState.CAPITULATION}
        )
        poor_cpr = cpr is not None and cpr.score < 25 and cpr.range_probability >= 75
        poor_avwap = avwap is not None and avwap.state == AVWAPState.STRONG_RESISTANCE
        if (
            hostile_market
            or weak_sector
            or weak_setup
            or poor_risk
            or poor_breadth
            or poor_cpr
            or poor_avwap
            or score < 50
        ):
            return DecisionAction.AVOID
        buy_regime = regime in {
            MarketRegime.HEALTHY_BULL,
            MarketRegime.BULL,
            MarketRegime.WEAK_BULL,
            MarketRegime.RECOVERY,
        }
        if (
            buy_regime
            and score >= 80
            and confidence >= 0.75
            and setup.score >= 70
            and risk.score >= 65
        ):
            return DecisionAction.BUY
        if stock is not None and stock.score >= 60:
            return DecisionAction.WATCHLIST
        return DecisionAction.AVOID

    @staticmethod
    def _grade(score: float) -> DecisionGrade:
        """Translate decision score into a stable trade-quality grade."""
        if score >= 90:
            return DecisionGrade.A_PLUS
        if score >= 80:
            return DecisionGrade.A
        if score >= 65:
            return DecisionGrade.B
        if score >= 50:
            return DecisionGrade.C
        return DecisionGrade.D

    @classmethod
    def _explain(
        cls,
        market: MarketProfile | None,
        sector: SectorProfile | None,
        relative_strength: RelativeStrengthProfile | None,
        stock: StockProfile | None,
        setup: SetupProfile | None,
        risk: RiskProfile | None,
        breadth: BreadthProfile | None,
        cpr: CPRProfile | None,
        avwap: AVWAPProfile | None,
        observations: Mapping[str, tuple[float, float]],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Generate concise reasons and warnings from existing profile evidence."""
        reasons: list[str] = []
        warnings: list[str] = []
        if market:
            reasons.append(f"{market.state.value} market")
        if breadth:
            reasons.append(f"{breadth.breadth_state.value} breadth")
            warnings.extend(breadth.warnings)
        if cpr:
            reasons.append(
                f"{cpr.cpr_state.value} CPR with "
                f"{cpr.breakout_probability:.0f}% breakout probability"
            )
            warnings.extend(cpr.warnings)
        if avwap:
            reasons.append(f"{avwap.state.value} at anchored institutional cost basis")
            warnings.extend(avwap.warnings)
        if sector:
            reasons.append(f"{sector.rotation.value} {sector.facts.name} sector")
        if relative_strength:
            percentile = cls._relative_strength_score(relative_strength)
            reasons.append(f"Top {max(1, round(100 - percentile))}% Relative Strength")
        if stock:
            if stock.facts.ema_alignment:
                reasons.append("Perfect EMA alignment")
            reasons.append(f"{stock.grade.value} stock quality")
        if setup:
            reasons.append(f"{setup.grade.value} {setup.best_setup_type.value} setup")
        if risk:
            available_r = risk.facts.available_r_multiple
            if available_r is not None:
                reasons.append(f"{available_r:.1f}R available")
            if risk.volatility_score >= 80:
                reasons.append("Low volatility risk")
            warnings.extend(risk.warnings)
            extension = risk.facts.extension_from_ema20_percent
            if extension > 5:
                warnings.append(f"Extended {extension:.1f}% above EMA20")
        missing = [name for name, (_, confidence) in observations.items() if confidence == 0]
        if missing:
            warnings.append(f"Missing intelligence: {', '.join(missing)}")
        if market is None:
            warnings.append("Market regime unavailable; Range weights applied")
        return tuple(reasons or ("No positive intelligence evidence is available",)), tuple(
            dict.fromkeys(warnings)
        )
