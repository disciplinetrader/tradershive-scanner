"""Institutional cross-sectional market breadth analysis."""

from collections.abc import Mapping

import numpy as np
import pandas as pd

from app.data.indicators import add_indicators
from app.models.breadth import BreadthFacts, BreadthProfile, BreadthState, BreadthTrend
from app.models.stock import StockGrade


def _bounded(value: float) -> float:
    """Clamp a public score to zero through 100."""
    return max(0.0, min(100.0, value))


class BreadthEngine:
    """Measure participation across a universe rather than index direction."""

    LOOKBACK = 50

    def analyze(self, frames: Mapping[str, pd.DataFrame]) -> BreadthProfile:
        """Build one breadth profile from normalized or enriched universe frames."""
        facts = self.calculate_facts(frames)
        participation = facts.market_participation_score
        trend = {
            BreadthTrend.EXPANDING: 85.0,
            BreadthTrend.STABLE: 55.0,
            BreadthTrend.NARROWING: 25.0,
        }[facts.breadth_trend]
        momentum = _bounded(50 + facts.breadth_momentum)
        thrust = 100.0 if facts.breadth_thrust else _bounded(momentum * 0.65)
        distribution = _bounded(
            facts.distribution_days * 14
            + max(0.0, facts.down_volume_percent - 50) * 1.2
            + facts.new_lows * 100 / max(1, facts.valid_symbols)
        )
        score = _bounded(
            0.40 * participation
            + 0.22 * trend
            + 0.18 * momentum
            + 0.10 * thrust
            + 0.10 * (100 - distribution)
        )
        state = self._state(facts, score, distribution)
        confidence = min(1.0, facts.valid_symbols / 50) * min(1.0, facts.history_days / 50)
        return BreadthProfile(
            score=round(score, 2),
            confidence=round(confidence, 2),
            grade=self._grade(score),
            breadth_state=state,
            participation_score=round(participation, 2),
            trend_score=round(trend, 2),
            momentum_score=round(momentum, 2),
            thrust_score=round(thrust, 2),
            distribution_score=round(distribution, 2),
            reasons=self._reasons(facts, state),
            warnings=self._warnings(facts, confidence),
            facts=facts,
        )

    def calculate_facts(self, frames: Mapping[str, pd.DataFrame]) -> BreadthFacts:
        """Calculate breadth time series and the latest cross-sectional snapshot."""
        histories: list[dict[str, np.ndarray]] = []
        requested_size = len(frames)
        for frame in frames.values():
            try:
                enriched = frame if "EMA100" in frame.columns else add_indicators(frame)
                required = {
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                    "EMA20",
                    "EMA50",
                    "EMA100",
                    "EMA200",
                    "High52W",
                }
                if required.difference(enriched.columns) or len(enriched) < 2:
                    continue
                recent = enriched.iloc[-min(self.LOOKBACK + 1, len(enriched)) :]
                if recent[list(required)].replace([np.inf, -np.inf], np.nan).isna().any().any():
                    continue
                histories.append({name: recent[name].to_numpy(dtype=float) for name in required})
            except (KeyError, ValueError, IndexError):
                continue
        if not histories:
            raise ValueError("Breadth analysis requires at least one valid symbol")

        common = min(len(history["Close"]) for history in histories)
        closes = np.stack([history["Close"][-common:] for history in histories])
        highs = np.stack([history["High"][-common:] for history in histories])
        lows = np.stack([history["Low"][-common:] for history in histories])
        volumes = np.stack([history["Volume"][-common:] for history in histories])
        returns = closes[:, 1:] / closes[:, :-1] - 1
        advances = np.sum(returns > 0, axis=0)
        declines = np.sum(returns < 0, axis=0)
        ad_net = advances - declines
        ad_line = np.cumsum(ad_net)
        latest_returns = returns[:, -1]
        latest_advancers = int(advances[-1])
        latest_decliners = int(declines[-1])
        up_volume = float(np.sum(volumes[:, -1][latest_returns > 0]))
        down_volume = float(np.sum(volumes[:, -1][latest_returns < 0]))
        directional_volume = up_volume + down_volume
        up_percent = up_volume / directional_volume * 100 if directional_volume else 0.0
        down_percent = down_volume / directional_volume * 100 if directional_volume else 0.0
        latest_close = closes[:, -1]
        latest_high = highs[:, -1]
        latest_low = lows[:, -1]
        ema20 = np.array([history["EMA20"][-1] for history in histories])
        ema50 = np.array([history["EMA50"][-1] for history in histories])
        ema100 = np.array([history["EMA100"][-1] for history in histories])
        ema200 = np.array([history["EMA200"][-1] for history in histories])
        highs52 = np.array([history["High52W"][-1] for history in histories])
        size = len(histories)

        def percentage(mask: np.ndarray) -> float:
            return float(np.mean(mask) * 100)

        new_high_mask = latest_high >= highs52
        prior_lows = np.min(lows[:, :-1], axis=1)
        new_low_mask = latest_low <= prior_lows
        higher_highs = latest_high > highs[:, -2]
        higher_lows = latest_low > lows[:, -2]
        above = tuple(percentage(latest_close > ema) for ema in (ema20, ema50, ema100, ema200))
        current_advance_share = latest_advancers / max(1, latest_advancers + latest_decliners) * 100
        participation = _bounded(
            0.15 * current_advance_share
            + 0.15 * up_percent
            + 0.20 * above[0]
            + 0.20 * above[1]
            + 0.10 * above[2]
            + 0.15 * above[3]
            + 0.05 * percentage(higher_lows)
        )
        breadth_momentum = self._momentum(ad_net, size)
        breadth_trend = self._trend(ad_line, size)
        recent_share = advances / np.maximum(1, advances + declines) * 100
        breadth_thrust = bool(
            len(recent_share) >= 10
            and float(np.mean(recent_share[-5:])) >= 70
            and float(np.mean(recent_share[-5:]) - np.mean(recent_share[-10:-5])) >= 15
        )
        distribution_mask = (recent_share <= 40) & (
            np.sum(volumes[:, 1:] * (returns < 0), axis=0)
            > np.sum(volumes[:, 1:] * (returns > 0), axis=0)
        )
        distribution_days = int(np.sum(distribution_mask[-25:]))
        median_returns = np.median(returns, axis=0)
        volume_shares = np.sum(volumes[:, 1:] * (returns > 0), axis=0) / np.maximum(
            1, np.sum(volumes[:, 1:], axis=0)
        )
        follow_through = bool(
            np.any(
                (median_returns[-10:] >= 0.0125)
                & (recent_share[-10:] >= 60)
                & (volume_shares[-10:] >= 0.60)
            )
        )
        new_highs = int(np.sum(new_high_mask))
        new_lows = int(np.sum(new_low_mask))
        return BreadthFacts(
            universe_size=requested_size,
            valid_symbols=size,
            advance_decline_line=float(ad_line[-1]),
            advance_decline_ratio=(
                latest_advancers / latest_decliners if latest_decliners else float(latest_advancers)
            ),
            advance_decline_volume=up_volume / down_volume if down_volume else up_volume,
            up_volume_percent=up_percent,
            down_volume_percent=down_percent,
            new_highs=new_highs,
            new_lows=new_lows,
            new_high_low_ratio=new_highs / new_lows if new_lows else float(new_highs),
            percentage_above_ema20=above[0],
            percentage_above_ema50=above[1],
            percentage_above_ema100=above[2],
            percentage_above_ema200=above[3],
            percentage_above_52_week_high_breakout=percentage(new_high_mask),
            percentage_making_higher_highs=percentage(higher_highs),
            percentage_making_higher_lows=percentage(higher_lows),
            distribution_days=distribution_days,
            follow_through_day=follow_through,
            market_participation_score=participation,
            breadth_momentum=breadth_momentum,
            breadth_trend=breadth_trend,
            breadth_thrust=breadth_thrust,
            history_days=common - 1,
        )

    @staticmethod
    def _momentum(ad_net: np.ndarray, universe_size: int) -> float:
        """Compare five-session breadth impulse with the preceding baseline."""
        recent = float(np.mean(ad_net[-5:]))
        prior = float(np.mean(ad_net[-20:-5])) if len(ad_net) >= 20 else 0.0
        return max(-100.0, min(100.0, (recent - prior) / max(1, universe_size) * 100))

    @staticmethod
    def _trend(ad_line: np.ndarray, universe_size: int) -> BreadthTrend:
        """Classify the normalized ten-session slope of the A/D line."""
        if len(ad_line) < 10:
            return BreadthTrend.STABLE
        slope = float(ad_line[-1] - ad_line[-10]) / max(1, universe_size * 9)
        if slope >= 0.10:
            return BreadthTrend.EXPANDING
        if slope <= -0.10:
            return BreadthTrend.NARROWING
        return BreadthTrend.STABLE

    @staticmethod
    def _state(facts: BreadthFacts, score: float, distribution: float) -> BreadthState:
        """Classify breadth using participation, damage, and concentration."""
        decline_share = facts.down_volume_percent
        new_low_share = facts.new_lows / max(1, facts.valid_symbols) * 100
        if decline_share >= 85 and new_low_share >= 20:
            return BreadthState.CAPITULATION
        if distribution >= 65:
            return BreadthState.DISTRIBUTION
        if facts.percentage_above_ema200 >= 65 and facts.percentage_above_ema50 >= 75:
            return BreadthState.BROAD_PARTICIPATION
        if facts.percentage_above_ema200 >= 55 and score >= 65:
            return BreadthState.HEALTHY_PARTICIPATION
        if facts.percentage_above_ema200 >= 55 and facts.percentage_above_ema20 < 40:
            return BreadthState.NARROW_LEADERSHIP
        if score < 40:
            return BreadthState.WEAK_PARTICIPATION
        return BreadthState.NEUTRAL

    @staticmethod
    def _grade(score: float) -> StockGrade:
        """Map breadth quality to the shared commercial grade scale."""
        if score >= 90:
            return StockGrade.A_PLUS
        if score >= 80:
            return StockGrade.A
        if score >= 65:
            return StockGrade.B
        if score >= 50:
            return StockGrade.C
        return StockGrade.D

    @staticmethod
    def _reasons(facts: BreadthFacts, state: BreadthState) -> tuple[str, ...]:
        """Generate concrete participation explanations."""
        reasons = [f"{facts.percentage_above_ema50:.0f}% of stocks above EMA50"]
        if state == BreadthState.BROAD_PARTICIPATION:
            reasons.append("Broad participation")
        elif state == BreadthState.HEALTHY_PARTICIPATION:
            reasons.append("Healthy advance")
        elif state in {BreadthState.WEAK_PARTICIPATION, BreadthState.NARROW_LEADERSHIP}:
            reasons.append("Participation narrowing")
        elif state == BreadthState.DISTRIBUTION:
            reasons.append("Distribution increasing")
        elif state == BreadthState.CAPITULATION:
            reasons.append("Market-wide selling indicates capitulation")
        if facts.breadth_thrust:
            reasons.append("Breadth thrust signals leadership expanding")
        if facts.follow_through_day:
            reasons.append("Follow-through day confirms institutional demand")
        return tuple(reasons)

    @staticmethod
    def _warnings(facts: BreadthFacts, confidence: float) -> tuple[str, ...]:
        """Expose deteriorating participation and data-coverage limitations."""
        warnings: list[str] = []
        if facts.distribution_days >= 4:
            warnings.append("Distribution days are clustering")
        if facts.new_lows > facts.new_highs:
            warnings.append("New lows exceed new highs")
        if facts.breadth_trend == BreadthTrend.NARROWING:
            warnings.append("Advance/decline trend is narrowing")
        if confidence < 1:
            warnings.append("Limited universe coverage reduces breadth confidence")
        return tuple(warnings)
