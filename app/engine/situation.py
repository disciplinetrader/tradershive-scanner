"""Scan-level situational interpretation of existing intelligence outputs."""

from collections.abc import Sequence

from app.models.breadth import BreadthProfile, BreadthState
from app.models.cpr import CPRProfile, CPRState
from app.models.decision import DecisionAction, DecisionProfile
from app.models.market import MarketProfile, MarketRegime
from app.models.relative_strength import RelativeStrengthProfile
from app.models.risk import RiskGrade, RiskProfile
from app.models.sector import SectorProfile, SectorRotation
from app.models.setup import SetupProfile
from app.models.situation import (
    Aggression,
    MoneyFlow,
    PositionSizingGuidance,
    RecommendedSetup,
    RiskEnvironment,
    SectorLeadership,
    SituationProfile,
    TradingBias,
)
from app.models.stock import StockProfile


class SituationEngine:
    """Interpret scan-wide outputs and recommend an operating posture."""

    def analyze(
        self,
        market: MarketProfile,
        sectors: Sequence[SectorProfile],
        relative_strength: Sequence[RelativeStrengthProfile],
        stocks: Sequence[StockProfile],
        setups: Sequence[SetupProfile],
        risks: Sequence[RiskProfile],
        decisions: Sequence[DecisionProfile],
        breadth: BreadthProfile | None = None,
        cprs: Sequence[CPRProfile] = (),
    ) -> SituationProfile:
        """Return one shared situation without recalculating subordinate work."""
        leadership = self._leadership(sectors)
        risk_environment = self._risk_environment(market, risks)
        money_flow = self._money_flow(market, sectors, decisions, breadth)
        bias, aggression = self._base_posture(market.state)
        warnings: list[str] = []
        cpr_environment, cpr_participation = self._cpr_environment(cprs)
        if market.breadth.percentage_above_ema50 < 40:
            aggression = self._downgrade(aggression)
            warnings.append("Weak breadth requires reduced aggression")
        if breadth and breadth.score < 40:
            aggression = self._downgrade(aggression)
            warnings.append(f"{breadth.breadth_state.value} requires reduced aggression")
        if risk_environment in {RiskEnvironment.HIGH, RiskEnvironment.EXTREME}:
            aggression = self._downgrade(aggression)
            warnings.append(f"{risk_environment.value} risk environment")
        if cprs and cpr_environment == "Range Favored":
            aggression = self._downgrade(aggression)
            warnings.append("CPR structures favor range behavior")
        if market.state in {MarketRegime.BEAR, MarketRegime.CAPITULATION}:
            bias = TradingBias.CASH
            aggression = Aggression.VERY_LOW
        setup_types = self._recommended_setups(market.state, aggression)
        sizing, positions, max_risk = self._operating_limits(aggression, bias)
        reasons = self._reasons(
            market,
            sectors,
            relative_strength,
            stocks,
            setups,
            decisions,
            risk_environment,
            breadth,
            cprs,
        )
        return SituationProfile(
            market_regime=market.state,
            breadth_profile=breadth,
            cpr_environment=cpr_environment,
            cpr_breakout_participation=cpr_participation,
            trading_bias=bias,
            aggression=aggression,
            recommended_setup_types=setup_types,
            market_health=market.score,
            risk_environment=risk_environment,
            sector_leadership=leadership,
            money_flow=money_flow,
            position_sizing_guidance=sizing,
            recommended_maximum_open_positions=positions,
            maximum_risk_per_trade=max_risk,
            expected_holding_period=self._holding_period(market.state),
            reasons=reasons,
            recommended_strategy=self._strategy(bias, setup_types),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _leadership(sectors: Sequence[SectorProfile]) -> SectorLeadership:
        """Summarize existing sector ranks and rotation states."""
        ranked = sorted(sectors, key=lambda profile: (profile.rank, profile.facts.name))
        improving = tuple(
            profile.facts.name for profile in ranked if profile.rotation == SectorRotation.IMPROVING
        )
        weakening = tuple(
            profile.facts.name
            for profile in ranked
            if profile.rotation in {SectorRotation.WEAKENING, SectorRotation.LAGGING}
        )
        return SectorLeadership(
            top_sectors=tuple(profile.facts.name for profile in ranked[:5]),
            bottom_sectors=tuple(profile.facts.name for profile in reversed(ranked[-5:])),
            improving_sectors=improving,
            weakening_sectors=weakening,
        )

    @staticmethod
    def _cpr_environment(cprs: Sequence[CPRProfile]) -> tuple[str, float]:
        """Summarize existing stock-level CPR expansion participation."""
        if not cprs:
            return "Unavailable", 0
        breakout_share = sum(profile.breakout_probability >= 70 for profile in cprs) / len(cprs)
        trending_share = sum(profile.cpr_state == CPRState.TRENDING for profile in cprs) / len(cprs)
        range_share = sum(profile.range_probability >= 65 for profile in cprs) / len(cprs)
        if breakout_share >= 0.50 or trending_share >= 0.50:
            state = "Expansion Favorable"
        elif range_share >= 0.50:
            state = "Range Favored"
        else:
            state = "Mixed"
        return state, round(breakout_share * 100, 2)

    @staticmethod
    def _risk_environment(market: MarketProfile, risks: Sequence[RiskProfile]) -> RiskEnvironment:
        """Interpret existing VIX, ATR expansion, and risk rejection participation."""
        vix = market.volatility.india_vix
        rejected_share = (
            sum(profile.grade == RiskGrade.REJECT for profile in risks) / len(risks) if risks else 0
        )
        if (vix is not None and vix >= 30) or market.volatility.atr_expansion >= 0.40:
            return RiskEnvironment.EXTREME
        if (vix is not None and vix >= 22) or rejected_share >= 0.60:
            return RiskEnvironment.HIGH
        if (vix is not None and vix >= 16) or rejected_share >= 0.35:
            return RiskEnvironment.MEDIUM
        return RiskEnvironment.LOW

    @staticmethod
    def _money_flow(
        market: MarketProfile,
        sectors: Sequence[SectorProfile],
        decisions: Sequence[DecisionProfile],
        breadth: BreadthProfile | None,
    ) -> MoneyFlow:
        """Classify broad risk appetite from existing breadth, rotation, and decisions."""
        if market.state in {MarketRegime.BEAR, MarketRegime.CAPITULATION}:
            return MoneyFlow.RISK_OFF
        if breadth and breadth.breadth_state in {
            BreadthState.WEAK_PARTICIPATION,
            BreadthState.DISTRIBUTION,
            BreadthState.CAPITULATION,
        }:
            return MoneyFlow.RISK_OFF
        if market.breadth.percentage_above_ema50 < 35:
            return MoneyFlow.RISK_OFF
        constructive_sectors = sum(
            profile.rotation in {SectorRotation.LEADING, SectorRotation.IMPROVING}
            for profile in sectors
        )
        buy_share = (
            sum(profile.action == DecisionAction.BUY for profile in decisions) / len(decisions)
            if decisions
            else 0
        )
        if (
            market.state in {MarketRegime.HEALTHY_BULL, MarketRegime.BULL, MarketRegime.RECOVERY}
            and market.breadth.percentage_above_ema50 >= 55
            and (not sectors or constructive_sectors >= len(sectors) / 2)
            and (not decisions or buy_share >= 0.30)
        ):
            return MoneyFlow.RISK_ON
        return MoneyFlow.NEUTRAL

    @staticmethod
    def _base_posture(regime: MarketRegime) -> tuple[TradingBias, Aggression]:
        """Map the Market Engine regime to the initial operating posture."""
        return {
            MarketRegime.HEALTHY_BULL: (TradingBias.LONG_ONLY, Aggression.VERY_HIGH),
            MarketRegime.BULL: (TradingBias.LONG_BIAS, Aggression.HIGH),
            MarketRegime.WEAK_BULL: (TradingBias.LONG_BIAS, Aggression.MEDIUM),
            MarketRegime.RANGE: (TradingBias.NEUTRAL, Aggression.LOW),
            MarketRegime.WEAK_BEAR: (TradingBias.SHORT_BIAS, Aggression.VERY_LOW),
            MarketRegime.BEAR: (TradingBias.CASH, Aggression.VERY_LOW),
            MarketRegime.CAPITULATION: (TradingBias.CASH, Aggression.VERY_LOW),
            MarketRegime.RECOVERY: (TradingBias.LONG_BIAS, Aggression.MEDIUM),
        }[regime]

    @staticmethod
    def _downgrade(aggression: Aggression) -> Aggression:
        """Reduce aggression by one band without going below Very Low."""
        levels = (
            Aggression.VERY_HIGH,
            Aggression.HIGH,
            Aggression.MEDIUM,
            Aggression.LOW,
            Aggression.VERY_LOW,
        )
        return levels[min(levels.index(aggression) + 1, len(levels) - 1)]

    @staticmethod
    def _recommended_setups(
        regime: MarketRegime, aggression: Aggression
    ) -> tuple[RecommendedSetup, ...]:
        """Select setup families consistent with regime and operating aggression."""
        if regime in {MarketRegime.BEAR, MarketRegime.CAPITULATION, MarketRegime.WEAK_BEAR}:
            return (RecommendedSetup.WATCHLIST_ONLY,)
        if aggression in {Aggression.VERY_HIGH, Aggression.HIGH}:
            return (
                RecommendedSetup.VCP,
                RecommendedSetup.BREAKOUT,
                RecommendedSetup.FIRST_PULLBACK,
                RecommendedSetup.DARVAS,
                RecommendedSetup.TIGHT_BASE,
                RecommendedSetup.BULL_FLAG,
            )
        if regime == MarketRegime.RECOVERY:
            return (
                RecommendedSetup.FIRST_PULLBACK,
                RecommendedSetup.TIGHT_BASE,
                RecommendedSetup.DARVAS,
            )
        return (
            RecommendedSetup.TIGHT_BASE,
            RecommendedSetup.DARVAS,
            RecommendedSetup.WATCHLIST_ONLY,
        )

    @staticmethod
    def _operating_limits(
        aggression: Aggression, bias: TradingBias
    ) -> tuple[PositionSizingGuidance, int, float]:
        """Return relative sizing, open-position cap, and percent risk guidance."""
        if bias == TradingBias.CASH:
            return PositionSizingGuidance.MINIMAL, 0, 0
        return {
            Aggression.VERY_HIGH: (PositionSizingGuidance.FULL, 12, 1.0),
            Aggression.HIGH: (PositionSizingGuidance.THREE_QUARTER, 10, 0.75),
            Aggression.MEDIUM: (PositionSizingGuidance.HALF, 7, 0.50),
            Aggression.LOW: (PositionSizingGuidance.QUARTER, 4, 0.25),
            Aggression.VERY_LOW: (PositionSizingGuidance.MINIMAL, 2, 0.10),
        }[aggression]

    @staticmethod
    def _holding_period(regime: MarketRegime) -> str:
        """Return an environment-level expected swing holding window."""
        if regime in {MarketRegime.HEALTHY_BULL, MarketRegime.BULL}:
            return "5-20 sessions"
        if regime in {MarketRegime.WEAK_BULL, MarketRegime.RECOVERY}:
            return "3-10 sessions"
        if regime == MarketRegime.RANGE:
            return "2-7 sessions"
        return "Watchlist only"

    @staticmethod
    def _reasons(
        market: MarketProfile,
        sectors: Sequence[SectorProfile],
        relative_strength: Sequence[RelativeStrengthProfile],
        stocks: Sequence[StockProfile],
        setups: Sequence[SetupProfile],
        decisions: Sequence[DecisionProfile],
        risk_environment: RiskEnvironment,
        breadth: BreadthProfile | None,
        cprs: Sequence[CPRProfile],
    ) -> tuple[str, ...]:
        """Explain the posture using already-calculated evidence."""
        reasons = list(market.reasons[:3])
        if breadth:
            reasons.extend(breadth.reasons[:2])
        if cprs:
            expansion_share = sum(profile.breakout_probability >= 70 for profile in cprs) / len(
                cprs
            )
            reasons.append(f"{expansion_share:.0%} show high-probability CPR expansion")
        improving = sum(profile.rotation == SectorRotation.IMPROVING for profile in sectors)
        leading = sum(profile.rotation == SectorRotation.LEADING for profile in sectors)
        if improving or leading:
            reasons.append(f"{leading} leading and {improving} improving sectors")
        if relative_strength:
            strong_rs = sum(profile.rs250.percentile >= 70 for profile in relative_strength) / len(
                relative_strength
            )
            reasons.append(f"{strong_rs:.0%} show high Relative Strength participation")
        if risk_environment == RiskEnvironment.LOW:
            reasons.append("Low volatility and risk pressure")
        if stocks:
            strong_stocks = sum(profile.score >= 70 for profile in stocks) / len(stocks)
            reasons.append(f"{strong_stocks:.0%} show strong stock quality")
        if setups:
            actionable_setups = sum(profile.score >= 65 for profile in setups) / len(setups)
            reasons.append(f"{actionable_setups:.0%} show actionable setup quality")
        if market.breadth.percentage_above_ema50 >= 60:
            reasons.append("Broad market confirmation")
        if decisions:
            buy_share = sum(profile.action == DecisionAction.BUY for profile in decisions) / len(
                decisions
            )
            reasons.append(f"{buy_share:.0%} of candidates qualify as BUY")
        return tuple(dict.fromkeys(reasons or [f"{market.state.value} market regime"]))

    @staticmethod
    def _strategy(
        bias: TradingBias,
        setup_types: tuple[RecommendedSetup, ...],
    ) -> tuple[str, ...]:
        """Translate posture and setup families into concise operating guidance."""
        if bias == TradingBias.CASH:
            return ("Preserve capital", "Build watchlists", "Avoid new swing exposure")
        if setup_types == (RecommendedSetup.WATCHLIST_ONLY,):
            return ("Build watchlists", "Avoid counter-trend trades")
        strategies = [
            f"Prioritize {setup.value.lower()} setups"
            for setup in setup_types
            if setup != RecommendedSetup.WATCHLIST_ONLY
        ]
        strategies.append("Avoid counter-trend trades")
        return tuple(strategies)
