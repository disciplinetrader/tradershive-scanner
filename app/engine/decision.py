"""Adaptive explainable decision aggregation over existing intelligence profiles."""

from collections.abc import Mapping

from app.core.config import DEFAULT_DECISION_WEIGHTS, DecisionWeights
from app.models.breadth import BreadthProfile, BreadthState
from app.models.cpr import CPRProfile
from app.models.decision import (
    DecisionAction,
    DecisionGrade,
    DecisionProfile,
    WeightedDecisionComponent,
)
from app.models.market import MarketProfile, MarketRegime
from app.models.relative_strength import RelativeStrengthProfile
from app.models.risk import RiskGrade, RiskProfile
from app.models.sector import SectorProfile, SectorRotation
from app.models.setup import SetupProfile, SetupType
from app.models.stock import StockProfile


class DecisionEngine:
    """Combine existing engine profiles using market-regime-adaptive weights."""

    def __init__(
        self,
        regime_weights: Mapping[MarketRegime, DecisionWeights] | None = None,
    ) -> None:
        """Initialize with a complete, externally tunable regime configuration."""
        self._weights = dict(regime_weights or DEFAULT_DECISION_WEIGHTS)
        if set(self._weights) != set(MarketRegime):
            raise ValueError("Decision weights must cover every market regime")

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
            decision_score, confidence, regime, sector, stock, setup, risk, breadth, cpr
        )
        reasons, warnings = self._explain(
            market,
            sector,
            relative_strength,
            stock,
            setup,
            risk,
            breadth,
            cpr,
            observations,
        )
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
            warnings=warnings,
            weight_breakdown=breakdown,
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
        if (
            hostile_market
            or weak_sector
            or weak_setup
            or poor_risk
            or poor_breadth
            or poor_cpr
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
