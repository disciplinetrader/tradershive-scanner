"""Advanced market-cycle and pressure interpretation."""

from collections.abc import Mapping

import numpy as np
import pandas as pd

from app.core.v11_config import (
    DEFAULT_FOLLOW_THROUGH_RULES,
    DEFAULT_MARKET_PRESSURE_RULES,
    FollowThroughRules,
    MarketPressureRules,
)
from app.models.market import MarketFacts, MarketProfile, RiskOnState


class AdvancedMarketEngine:
    """Enrich a market profile using only already-available index histories."""

    def __init__(
        self,
        follow: FollowThroughRules = DEFAULT_FOLLOW_THROUGH_RULES,
        pressure: MarketPressureRules = DEFAULT_MARKET_PRESSURE_RULES,
    ) -> None:
        self._follow = follow
        self._pressure = pressure

    def enhance(self, profile: MarketProfile, frames: Mapping[str, pd.DataFrame]) -> MarketProfile:
        """Add rally, distribution, pressure, risk posture, and divergence facts."""
        primary = frames["nifty_50"] if "nifty_50" in frames else next(iter(frames.values()))
        close = primary["Close"].to_numpy(float)
        low = primary["Low"].to_numpy(float) if "Low" in primary else close
        volume = primary["Volume"].to_numpy(float)
        returns = np.zeros(len(close))
        returns[1:] = close[1:] / close[:-1] - 1
        recent_low_pos = self._rally_low(close, low)
        rally = recent_low_pos is not None
        rally_day = len(close) - recent_low_pos if recent_low_pos is not None else 0
        ftd_position = self._follow_through_position(close, volume, returns, recent_low_pos)
        undercut = bool(
            recent_low_pos is not None and np.min(low[recent_low_pos + 1 :]) < low[recent_low_pos]
        )
        ftd = ftd_position is not None and not undercut
        window = self._pressure.distribution_window
        start = max(1, len(close) - window)
        positions = (
            np.flatnonzero(
                (returns[start:] <= -self._pressure.distribution_decline)
                & (volume[start:] >= volume[start - 1 : -1])
            )
            + start
        )
        active = 0
        aged = 0
        for absolute_value in positions:
            absolute = int(absolute_value)
            if len(close) - absolute > window or close[-1] >= close[absolute] * (
                1 + self._pressure.age_out_advance
            ):
                aged += 1
            else:
                active += 1
        breadth = profile.breadth.percentage_above_ema50
        vix = profile.volatility.india_vix or 18
        bearish = sum(not item.above_ema200 for item in profile.indexes.values())
        pressure = float(
            np.clip(
                active * 10 + (100 - breadth) * 0.35 + bearish * 8 + max(0, vix - 18) * 2, 0, 100
            )
        )
        risk = self._risk_state(pressure, breadth)
        divergence = self._divergence(profile.indexes)
        expansion = breadth >= 70 and profile.breadth.percentage_above_ema20 >= breadth
        contraction = breadth < 45 or bool(divergence)
        transition = "Improving" if ftd else "Deteriorating" if pressure >= 65 else "Stable"
        return profile.model_copy(
            update={
                "rally_attempt": rally,
                "rally_attempt_day": rally_day if rally else 0,
                "follow_through_day": ftd,
                "failed_follow_through": bool(
                    rally and not undercut and rally_day > self._follow.latest_day and not ftd
                ),
                "active_distribution_days": active,
                "aged_out_distribution_days": aged,
                "distribution_pressure": min(100.0, active / 6 * 100),
                "market_pressure_score": round(pressure, 2),
                "risk_on_state": risk,
                "leadership_expansion": expansion,
                "leadership_contraction": contraction,
                "regime_transition": transition,
                "index_divergence": divergence,
            }
        )

    def _rally_low(self, close: np.ndarray, low: np.ndarray) -> int | None:
        """Return the latest qualifying, non-undercut rally-attempt low."""
        start = max(1, len(close) - 60)
        for position in range(len(close) - 2, start - 1, -1):
            prior = close[max(0, position - 30) : position + 1]
            decline = np.max(prior) / low[position] - 1
            if decline < self._follow.decline_threshold:
                continue
            if low[position] > np.min(low[max(0, position - 30) : position + 1]):
                continue
            if close[position + 1] <= close[position]:
                continue
            if np.min(low[position + 1 :]) < low[position]:
                continue
            return position
        return None

    def _follow_through_position(
        self,
        close: np.ndarray,
        volume: np.ndarray,
        returns: np.ndarray,
        rally_low: int | None,
    ) -> int | None:
        """Find a qualifying FTD anywhere in the current rally's eligible window."""
        if rally_low is None:
            return None
        first = rally_low + self._follow.earliest_day - 1
        last = min(len(close) - 1, rally_low + self._follow.latest_day - 1)
        for position in range(first, last + 1):
            if (
                returns[position] >= self._follow.minimum_gain
                and volume[position] > volume[position - 1]
            ):
                return position
        return None

    @staticmethod
    def _risk_state(pressure: float, breadth: float) -> RiskOnState:
        if pressure <= 20 and breadth >= 75:
            return RiskOnState.STRONG_RISK_ON
        if pressure <= 40 and breadth >= 55:
            return RiskOnState.RISK_ON
        if pressure >= 80:
            return RiskOnState.STRONG_RISK_OFF
        if pressure >= 60:
            return RiskOnState.RISK_OFF
        return RiskOnState.NEUTRAL

    @staticmethod
    def _divergence(indexes: Mapping[str, MarketFacts]) -> tuple[str, ...]:
        reasons = []
        nifty = indexes.get("nifty_50")
        small = indexes.get("nifty_smallcap_250")
        bank = indexes.get("bank_nifty")
        if nifty and small and nifty.return_20d > 0 > small.return_20d:
            reasons.append("Large caps rising while small caps weaken")
        if nifty and bank and nifty.return_20d - bank.return_20d > 0.05:
            reasons.append("Bank Nifty materially lags NIFTY 50")
        positive = sum(item.return_20d > 0 for item in indexes.values())
        if nifty and nifty.return_20d > 0 and positive <= max(1, len(indexes) // 2):
            reasons.append("Narrow index-led advance")
        return tuple(reasons)
