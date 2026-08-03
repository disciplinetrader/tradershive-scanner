"""Extensible, vectorized Anchored VWAP intelligence engine."""

from collections.abc import Iterable, Sequence
from typing import Protocol

import numpy as np
import pandas as pd

from app.models.avwap import (
    AnchorAVWAPFacts,
    AVWAPAnchor,
    AVWAPAnchorType,
    AVWAPFacts,
    AVWAPProfile,
    AVWAPState,
)
from app.models.stock import StockGrade


class AnchorResolver(Protocol):
    """Extension point that discovers anchors without changing engine logic."""

    def resolve(self, frame: pd.DataFrame) -> Iterable[AVWAPAnchor]:
        """Return anchors for a normalized OHLCV frame."""


class MarketEventAnchorResolver:
    """Discover price, gap, breakout, earnings-proxy, and IPO anchors."""

    def resolve(self, frame: pd.DataFrame) -> Iterable[AVWAPAnchor]:
        """Resolve deterministic built-in market-event anchors."""
        size = len(frame)
        start = max(0, size - 252)
        recent = max(0, size - 60)
        high = frame["High"].to_numpy(float)
        low = frame["Low"].to_numpy(float)
        close = frame["Close"].to_numpy(float)
        open_ = frame["Open"].to_numpy(float)
        volume = frame["Volume"].to_numpy(float)
        positions: list[tuple[AVWAPAnchorType, int, str]] = [
            (
                AVWAPAnchorType.SWING_HIGH,
                recent + int(np.argmax(high[recent:])),
                "Swing-high AVWAP",
            ),
            (AVWAPAnchorType.SWING_LOW, recent + int(np.argmin(low[recent:])), "Swing-low AVWAP"),
            (
                AVWAPAnchorType.HIGH_52_WEEK,
                start + int(np.argmax(high[start:])),
                "52-week-high AVWAP",
            ),
            (AVWAPAnchorType.LOW_52_WEEK, start + int(np.argmin(low[start:])), "52-week-low AVWAP"),
            (AVWAPAnchorType.IPO_DAY, 0, "IPO-day AVWAP"),
        ]
        if size > 1:
            gaps = open_[1:] / close[:-1] - 1
            up = np.flatnonzero(gaps >= 0.02)
            down = np.flatnonzero(gaps <= -0.02)
            if up.size:
                positions.append((AVWAPAnchorType.GAP_UP, int(up[-1] + 1), "Gap-up AVWAP"))
            if down.size:
                positions.append((AVWAPAnchorType.GAP_DOWN, int(down[-1] + 1), "Gap-down AVWAP"))
            significant = np.flatnonzero(np.abs(gaps) >= 0.04)
            if significant.size:
                pos = int(significant[np.argmax(volume[significant + 1])] + 1)
                positions.append((AVWAPAnchorType.EARNINGS_GAP, pos, "Earnings-gap AVWAP"))
        breakout = None
        for pos in range(max(20, size - 100), size):
            if close[pos] > np.max(high[pos - 20 : pos]):
                breakout = pos
        if breakout is not None:
            positions.append((AVWAPAnchorType.BREAKOUT_DAY, breakout, "Breakout AVWAP"))
        for anchor_type, position, label in positions:
            timestamp = pd.Timestamp(frame.index[position]).to_pydatetime()
            yield AVWAPAnchor(
                anchor_type=anchor_type, position=position, timestamp=timestamp, label=label
            )


class AVWAPEngine:
    """Evaluate price behavior around independently resolved AVWAP anchors."""

    def __init__(self, resolvers: Sequence[AnchorResolver] | None = None) -> None:
        """Initialize with replaceable anchor resolvers."""
        self._resolvers = tuple((MarketEventAnchorResolver(),) if resolvers is None else resolvers)

    def analyze(
        self,
        symbol: str,
        frame: pd.DataFrame,
        user_anchors: Sequence[AVWAPAnchor] = (),
    ) -> AVWAPProfile:
        """Return multi-anchor institutional support and resistance intelligence."""
        required = {"Open", "High", "Low", "Close", "Volume"}
        if missing := required.difference(frame.columns):
            raise ValueError(f"AVWAP frame is missing columns: {sorted(missing)}")
        if frame.empty or frame[list(required)].dropna().empty:
            raise ValueError("AVWAP requires valid OHLCV history")
        anchors = [anchor for resolver in self._resolvers for anchor in resolver.resolve(frame)]
        anchors.extend(user_anchors)
        unique = {(anchor.anchor_type, anchor.position, anchor.label): anchor for anchor in anchors}
        calculated = tuple(
            self._calculate(frame, anchor)
            for anchor in unique.values()
            if anchor.position < len(frame)
        )
        if not calculated:
            return self._empty(symbol, frame)
        support = float(np.mean([item.support_strength for item in calculated]))
        resistance = float(np.mean([item.resistance_strength for item in calculated]))
        alignment = 100.0 * sum(item.above_avwap for item in calculated) / len(calculated)
        reclaimed = sum(item.reclaim_detected for item in calculated)
        lost = sum(item.loss_detected for item in calculated)
        state = self._state(support, resistance, reclaimed, lost)
        score = float(
            np.clip(0.55 * support + 0.35 * alignment + 0.10 * (100 - resistance), 0, 100)
        )
        confidence = min(1.0, 0.35 + 0.08 * len(calculated) + min(len(frame), 252) / 1000)
        reasons = self._reasons(calculated, state)
        warnings = []
        if len(frame) < 252:
            warnings.append("Less than 252 sessions limits long-horizon anchor confidence")
        if any(item.anchor.anchor_type == AVWAPAnchorType.EARNINGS_GAP for item in calculated):
            warnings.append(
                "Earnings-gap anchor inferred from price and volume; calendar not supplied"
            )
        facts = AVWAPFacts(
            symbol=symbol.upper(),
            close=float(frame["Close"].iloc[-1]),
            anchors=calculated,
            history_days=len(frame),
        )
        return AVWAPProfile(
            score=round(score, 2),
            confidence=round(confidence, 2),
            grade=self._grade(score),
            state=state,
            support_score=round(support, 2),
            resistance_score=round(resistance, 2),
            alignment_score=round(alignment, 2),
            anchor_summary={item.anchor.label: item.state.value for item in calculated},
            reasons=reasons,
            warnings=tuple(warnings),
            facts=facts,
        )

    @staticmethod
    def _calculate(frame: pd.DataFrame, anchor: AVWAPAnchor) -> AnchorAVWAPFacts:
        subset = frame.iloc[anchor.position :]
        high, low, close, volume = (
            subset[name].to_numpy(float) for name in ("High", "Low", "Close", "Volume")
        )
        typical = (high + low + close) / 3
        cumulative_volume = np.cumsum(np.maximum(volume, 0))
        avwap = np.divide(
            np.cumsum(typical * np.maximum(volume, 0)),
            cumulative_volume,
            out=typical.copy(),
            where=cumulative_volume > 0,
        )
        distance = (close / avwap - 1) * 100
        side = distance >= 0
        touches = np.abs(distance) <= 1
        cross_count = int(np.count_nonzero(side[1:] != side[:-1]))
        respect_count = (
            int(np.count_nonzero(touches[:-1] & (side[1:] == side[:-1]))) if len(side) > 1 else 0
        )
        slope_window = min(5, len(avwap) - 1)
        slope = (
            0.0
            if slope_window == 0
            else (avwap[-1] / avwap[-1 - slope_window] - 1) * 100 / slope_window
        )
        reclaim = len(side) > 1 and bool(side[-1] and not side[-2])
        loss = len(side) > 1 and bool(not side[-1] and side[-2])
        behavior = min(30.0, respect_count * 8 + int(touches.sum()) * 2)
        support = float(np.clip((55 if side[-1] else 10) + max(0, slope) * 20 + behavior, 0, 100))
        resistance = float(
            np.clip((55 if not side[-1] else 10) + max(0, -slope) * 20 + behavior, 0, 100)
        )
        state = (
            AVWAPState.RECLAIMED
            if reclaim
            else (
                AVWAPState.LOST
                if loss
                else (
                    AVWAPState.STRONG_SUPPORT
                    if support >= 75
                    else (
                        AVWAPState.SUPPORT
                        if support >= 55
                        else (
                            AVWAPState.STRONG_RESISTANCE
                            if resistance >= 75
                            else AVWAPState.RESISTANCE if resistance >= 55 else AVWAPState.NEUTRAL
                        )
                    )
                )
            )
        )
        return AnchorAVWAPFacts(
            anchor=anchor,
            anchored_vwap=round(float(avwap[-1]), 4),
            distance_percent=round(float(distance[-1]), 2),
            above_avwap=bool(side[-1]),
            slope=round(float(slope), 4),
            touch_count=int(touches.sum()),
            respect_count=respect_count,
            cross_count=cross_count,
            support_strength=round(support, 2),
            resistance_strength=round(resistance, 2),
            compression_around_avwap=bool(np.mean(np.abs(distance[-min(5, len(distance)) :])) <= 1),
            reclaim_detected=reclaim,
            loss_detected=loss,
            state=state,
        )

    @staticmethod
    def _state(support: float, resistance: float, reclaimed: int, lost: int) -> AVWAPState:
        if reclaimed > lost and reclaimed:
            return AVWAPState.RECLAIMED
        if lost > reclaimed and lost:
            return AVWAPState.LOST
        if support >= 75:
            return AVWAPState.STRONG_SUPPORT
        if support >= 55:
            return AVWAPState.SUPPORT
        if resistance >= 75:
            return AVWAPState.STRONG_RESISTANCE
        if resistance >= 55:
            return AVWAPState.RESISTANCE
        return AVWAPState.NEUTRAL

    @staticmethod
    def _reasons(items: tuple[AnchorAVWAPFacts, ...], state: AVWAPState) -> tuple[str, ...]:
        evidence = sorted(items, key=lambda item: item.support_strength, reverse=True)
        reasons = [f"{state.value} across institutional cost-basis anchors"]
        reasons.extend(f"Above {item.anchor.label}" for item in evidence if item.above_avwap)
        return tuple(reasons[:4])

    @staticmethod
    def _grade(score: float) -> StockGrade:
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
    def _empty(symbol: str, frame: pd.DataFrame) -> AVWAPProfile:
        facts = AVWAPFacts(
            symbol=symbol.upper(),
            close=float(frame["Close"].iloc[-1]),
            anchors=(),
            history_days=len(frame),
        )
        return AVWAPProfile(
            score=0,
            confidence=0,
            grade=StockGrade.D,
            state=AVWAPState.NEUTRAL,
            support_score=0,
            resistance_score=0,
            alignment_score=0,
            anchor_summary={},
            reasons=("No valid AVWAP anchors available",),
            warnings=("Anchor data unavailable",),
            facts=facts,
        )
