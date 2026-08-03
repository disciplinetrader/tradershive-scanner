"""Structural downside, reward-to-risk, and position-sizing engine."""

import math

from app.models.facts import Facts
from app.models.risk import PositionSize, RiskFacts, RiskGrade, RiskProfile
from app.models.setup import SetupType


def _bounded(value: float) -> float:
    """Clamp a quality or risk score to zero through 100."""
    return max(0.0, min(100.0, value))


class RiskEngine:
    """Evaluate risk quality without emitting an execution decision."""

    def __init__(
        self,
        minimum_stop_percent: float = 0.005,
        maximum_stop_percent: float = 0.15,
        minimum_daily_turnover: float = 10_000_000,
    ) -> None:
        """Configure structural stop and liquidity rejection boundaries."""
        if not 0 < minimum_stop_percent < maximum_stop_percent < 1:
            raise ValueError("Stop limits must satisfy 0 < minimum < maximum < 1")
        if minimum_daily_turnover <= 0:
            raise ValueError("Minimum daily turnover must be positive")
        self._minimum_stop_percent = minimum_stop_percent
        self._maximum_stop_percent = maximum_stop_percent
        self._minimum_daily_turnover = minimum_daily_turnover

    def analyze(self, facts: Facts, account_size: float | None = None) -> RiskProfile:
        """Calculate risk quality from existing market, stock, and setup facts."""
        warnings: list[str] = []
        entry = self._entry(facts)
        stop = self._stop(facts)
        valid_structure = entry is not None and stop is not None and stop < entry
        if entry is None:
            warnings.append("No valid setup entry is available")
        if stop is None:
            warnings.append("No structural invalidation or base low is available")
        elif entry is not None and stop >= entry:
            warnings.append("Stop is above or equal to entry")

        risk_per_share = entry - stop if valid_structure else None
        stop_percent = risk_per_share / entry if risk_per_share and entry else None
        stop_atr = risk_per_share / facts.atr14 if risk_per_share and facts.atr14 > 0 else None
        if stop_percent is not None and stop_percent < self._minimum_stop_percent:
            warnings.append("Stop distance is unrealistically tight")
            valid_structure = False
        if stop_percent is not None and stop_percent > self._maximum_stop_percent:
            warnings.append("Stop distance exceeds configured maximum")
            valid_structure = False

        resistance = self._nearest_resistance(facts, entry)
        available_reward = (
            resistance - entry if resistance and entry and resistance > entry else None
        )
        available_reward_percent = available_reward / entry if available_reward and entry else None
        available_r = (
            available_reward / risk_per_share if available_reward and risk_per_share else None
        )
        if resistance is None:
            warnings.append("Nearest resistance is unavailable; reward confidence reduced")
        elif available_r is not None and available_r < 2:
            warnings.append("Available reward is below 2R")

        stop_quality = self._stop_quality(stop_percent, stop_atr)
        volatility_quality = self._volatility_quality(facts, entry)
        liquidity_quality = self._liquidity_quality(facts, entry)
        reward_quality, reward_reason = self._reward_quality(available_r)
        extension_quality = self._extension_quality(facts, entry)
        if liquidity_quality < 30:
            warnings.append("Liquidity is inadequate")

        rejected = (
            not valid_structure
            or liquidity_quality < 30
            or (available_r is not None and available_r < 2)
        )
        score = _bounded(
            0.25 * stop_quality
            + 0.20 * volatility_quality
            + 0.15 * liquidity_quality
            + 0.30 * reward_quality
            + 0.10 * extension_quality
        )
        if rejected:
            score = min(score, 39.0)
        confidence = (
            facts.setup_profile.confidence
            + facts.stock_profile.confidence
            + facts.market_confidence
        ) / 3
        if resistance is None:
            confidence *= 0.70
        if entry is None or stop is None:
            confidence *= 0.50
        confidence = _bounded(confidence * 100) / 100

        targets = self._targets(entry, risk_per_share)
        sizes = self._sizes(account_size, entry, stop)
        extension20 = (entry / facts.ema20 - 1) * 100 if entry else 0.0
        extension50 = (entry / facts.ema50 - 1) * 100 if entry else 0.0
        gap_risk = abs(facts.gap_percent) * 100
        overnight_risk = _bounded(
            gap_risk * 12.5 + min(facts.stock_profile.facts.average_gap * 2_000, 50)
        )
        facts_model = RiskFacts(
            entry_price=entry,
            stop_price=stop,
            stop_distance=risk_per_share,
            stop_distance_percent=stop_percent * 100 if stop_percent is not None else None,
            stop_distance_atr=stop_atr,
            risk_per_share=risk_per_share,
            target_2r=targets[0],
            target_3r=targets[1],
            target_4r=targets[2],
            target_5r=targets[3],
            nearest_resistance=resistance,
            available_reward_percent=(
                available_reward_percent * 100 if available_reward_percent is not None else None
            ),
            available_r_multiple=available_r,
            position_size_for_0_25_percent_risk=sizes[0],
            position_size_for_0_50_percent_risk=sizes[1],
            position_size_for_1_00_percent_risk=sizes[2],
            portfolio_heat_contribution=(sizes[2].actual_risk_percent if sizes[2] else 0),
            extension_from_ema20_percent=extension20,
            extension_from_ema50_percent=extension50,
            gap_risk_percent=gap_risk,
            overnight_risk_score=overnight_risk,
            liquidity_risk_score=100 - liquidity_quality,
            volatility_risk_score=100 - volatility_quality,
            structure_risk_score=100 - stop_quality,
        )
        reasons = self._reasons(
            stop_percent,
            stop_atr,
            reward_reason,
            liquidity_quality,
            extension20,
        )
        return RiskProfile(
            score=round(score, 2),
            confidence=round(confidence, 2),
            grade=RiskGrade.REJECT if rejected else self._grade(score),
            stop_quality_score=round(stop_quality, 2),
            volatility_score=round(volatility_quality, 2),
            liquidity_score=round(liquidity_quality, 2),
            reward_score=round(reward_quality, 2),
            extension_score=round(extension_quality, 2),
            reasons=reasons,
            warnings=tuple(dict.fromkeys(warnings)),
            facts=facts_model,
        )

    @staticmethod
    def position_size(
        account_size: float,
        risk_percent: float,
        entry_price: float,
        stop_price: float,
    ) -> PositionSize:
        """Return integer-share sizing for a percentage risk budget."""
        values = (account_size, risk_percent, entry_price, stop_price)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Position-sizing inputs must be finite")
        if account_size <= 0 or not 0 < risk_percent <= 100:
            raise ValueError("Account size and risk percent must be positive")
        risk_per_share = entry_price - stop_price
        if entry_price <= 0 or stop_price <= 0 or risk_per_share <= 0:
            raise ValueError("Entry must be positive and greater than stop")
        risk_amount = account_size * risk_percent / 100
        quantity = max(0, math.floor(risk_amount / risk_per_share))
        position_value = quantity * entry_price
        actual_risk = quantity * risk_per_share / account_size * 100
        return PositionSize(
            account_size=account_size,
            risk_percent=risk_percent,
            risk_amount=round(risk_amount, 2),
            quantity=quantity,
            position_value=round(position_value, 2),
            actual_risk_percent=round(actual_risk, 4),
        )

    @staticmethod
    def _entry(facts: Facts) -> float | None:
        """Use only a valid pivot or a demonstrably triggered setup close."""
        pivot = facts.setup_profile.facts.pivot_price
        if pivot is not None and math.isfinite(pivot) and pivot > 0:
            return pivot
        setup = facts.setup_profile.facts
        if setup.setup_type != SetupType.NONE and facts.close >= setup.base_high:
            return facts.close
        return None

    @staticmethod
    def _stop(facts: Facts) -> float | None:
        """Use setup invalidation, otherwise the nearest known structural low."""
        setup = facts.setup_profile.facts
        candidates = (setup.invalidation_price, setup.base_low)
        return next(
            (
                value
                for value in candidates
                if value is not None and math.isfinite(value) and value > 0
            ),
            None,
        )

    @staticmethod
    def _nearest_resistance(facts: Facts, entry: float | None) -> float | None:
        """Return the nearest objective resistance or measured base objective."""
        if entry is None:
            return None
        setup = facts.setup_profile.facts
        levels: list[float] = []
        if facts.high_52_week > entry * 1.005:
            levels.append(facts.high_52_week)
        measured = setup.base_high + (setup.base_high - setup.base_low)
        if measured > entry * 1.005:
            levels.append(measured)
        return min(levels) if levels else None

    @staticmethod
    def _targets(
        entry: float | None, risk_per_share: float | None
    ) -> tuple[float | None, float | None, float | None, float | None]:
        """Calculate mechanical R reference levels only for valid risk."""
        if entry is None or risk_per_share is None or risk_per_share <= 0:
            return None, None, None, None
        return tuple(round(entry + multiple * risk_per_share, 4) for multiple in (2, 3, 4, 5))

    def _sizes(
        self,
        account_size: float | None,
        entry: float | None,
        stop: float | None,
    ) -> tuple[PositionSize | None, PositionSize | None, PositionSize | None]:
        """Calculate standard sizing examples only when capital is supplied."""
        if account_size is None or entry is None or stop is None or stop >= entry:
            return None, None, None
        return tuple(
            self.position_size(account_size, risk, entry, stop) for risk in (0.25, 0.50, 1.0)
        )

    @staticmethod
    def _stop_quality(stop_percent: float | None, stop_atr: float | None) -> float:
        """Score realistic structural distance and ATR context."""
        if stop_percent is None or stop_atr is None:
            return 0
        percent_quality = (
            100 if 0.02 <= stop_percent <= 0.08 else 60 if 0.01 <= stop_percent <= 0.12 else 20
        )
        atr_quality = 100 if 1 <= stop_atr <= 3 else 60 if 0.5 <= stop_atr <= 5 else 20
        return (percent_quality + atr_quality) / 2

    @staticmethod
    def _volatility_quality(facts: Facts, entry: float | None) -> float:
        """Score ATR as a percentage of intended entry."""
        if entry is None:
            return 0
        atr_percent = facts.atr14 / entry
        if atr_percent <= 0.03:
            return 100
        if atr_percent <= 0.05:
            return 75
        if atr_percent <= 0.08:
            return 40
        return 10

    def _liquidity_quality(self, facts: Facts, entry: float | None) -> float:
        """Score average rupee turnover against tradability thresholds."""
        turnover = facts.average_volume * (entry or facts.close)
        if turnover >= 200_000_000:
            return 100
        if turnover >= 50_000_000:
            return 75
        if turnover >= self._minimum_daily_turnover:
            return 45
        return 10

    @staticmethod
    def _reward_quality(available_r: float | None) -> tuple[float, str]:
        """Map true available R to explicit reward-quality bands."""
        if available_r is None:
            return 25, "Available reward cannot be established objectively"
        if available_r < 2:
            return 0, "Available reward is below 2R"
        if available_r < 3:
            return 45, "Available reward is weak at 2R to below 3R"
        if available_r < 4:
            return 65, "Available reward is acceptable at 3R to below 4R"
        if available_r < 5:
            return 85, "Available reward is strong at 4R to below 5R"
        return 100, "Available reward is excellent at 5R or above"

    @staticmethod
    def _extension_quality(facts: Facts, entry: float | None) -> float:
        """Penalize entries extended above short and intermediate trend support."""
        if entry is None:
            return 0
        extension20 = entry / facts.ema20 - 1
        extension50 = entry / facts.ema50 - 1
        return _bounded(
            100 - max(0.0, extension20 - 0.05) * 500 - max(0.0, extension50 - 0.12) * 250
        )

    @staticmethod
    def _grade(score: float) -> RiskGrade:
        """Translate acceptable risk quality into a stable grade."""
        if score >= 90:
            return RiskGrade.A_PLUS
        if score >= 80:
            return RiskGrade.A
        if score >= 65:
            return RiskGrade.B
        if score >= 50:
            return RiskGrade.C
        return RiskGrade.D

    @staticmethod
    def _reasons(
        stop_percent: float | None,
        stop_atr: float | None,
        reward_reason: str,
        liquidity_quality: float,
        extension20: float,
    ) -> tuple[str, ...]:
        """Generate concise evidence for the risk assessment."""
        reasons = [reward_reason]
        if stop_percent is not None and stop_atr is not None:
            reasons.append(
                f"Structural stop is {stop_percent * 100:.1f}% or {stop_atr:.1f} ATR from entry"
            )
        reasons.append("Liquidity is adequate" if liquidity_quality >= 45 else "Liquidity is poor")
        if extension20 > 8:
            reasons.append(f"Entry is extended {extension20:.1f}% above EMA20")
        else:
            reasons.append("Entry is not materially extended above EMA20")
        return tuple(reasons)
