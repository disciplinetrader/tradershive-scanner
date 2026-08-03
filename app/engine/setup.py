"""Objective swing-setup detection and scoring engine."""

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
import pandas as pd

from app.data.indicators import add_indicators
from app.models.setup import (
    ContractionDetail,
    SetupCandidate,
    SetupFacts,
    SetupProfile,
    SetupType,
)
from app.models.stock import StockGrade, StockProfile


def _bounded(value: float) -> float:
    """Clamp a score to the public zero-to-100 range."""
    return max(0.0, min(100.0, value))


def _make_candidate(**values: object) -> SetupCandidate:
    """Construct a candidate from already bounded internal calculations."""
    return SetupCandidate.model_construct(**values)


@dataclass(frozen=True, slots=True)
class _Context:
    """Internal shared measurements used by individual detectors."""

    frame: pd.DataFrame
    close: float
    base: pd.DataFrame
    base_high: float
    base_low: float
    depth: float
    location: float
    dry_up: float
    contractions: tuple[ContractionDetail, ...]
    tight_closes: int
    range_ratio: float
    inside_day: bool
    nr7: bool
    first_pullback: bool
    uptrend: bool
    distribution: int
    flag_impulse: float
    flag_depth: float
    flag_volume: float
    holds_ema: bool
    rs_strong: bool
    overhead: float


class SetupEngine:
    """Detect and score price-volume structures without issuing decisions."""

    BASE_LENGTH = 20

    def analyze(
        self,
        symbol: str,
        frame: pd.DataFrame,
        stock_profile: StockProfile | None = None,
    ) -> SetupProfile:
        """Return the strongest observed setup and its complete evidence."""
        enriched = (
            frame if {"EMA20", "EMA50", "ATR14"}.issubset(frame.columns) else add_indicators(frame)
        )
        context, confidence = self._context(symbol, enriched)
        candidates = self._candidates(context, stock_profile)
        best = max(candidates, key=lambda candidate: (candidate.score, candidate.detected))
        detected_best = (
            best
            if best.detected
            else _make_candidate(
                setup_type=SetupType.NONE,
                detected=False,
                score=best.score,
                reasons=("No setup satisfies the objective detection thresholds",),
            )
        )
        structure = self._structure_score(context)
        compression = self._compression_score(context)
        volume = _bounded((1.25 - context.dry_up) / 0.75 * 100)
        location = _bounded(context.location * 100)
        pattern = detected_best.score
        overall = _bounded(
            0.35 * pattern + 0.25 * structure + 0.15 * compression + 0.15 * volume + 0.10 * location
        )
        if detected_best.setup_type == SetupType.NONE:
            overall = min(overall, 49.0)
        pivot = context.base_high
        if detected_best.setup_type == SetupType.VCP and context.contractions:
            pivot = context.contractions[-1].high
        invalidation = self._invalidation(context, detected_best.setup_type)
        breakout_distance = max(0.0, pivot / context.close - 1)
        overhead = max(0.0, float(enriched["High"].iloc[-120:].max()) / pivot - 1)
        facts = SetupFacts.model_construct(
            setup_type=detected_best.setup_type,
            setup_score=round(overall, 2),
            setup_confidence=round(confidence, 2),
            pivot_price=round(pivot, 4),
            invalidation_price=round(invalidation, 4),
            base_high=round(context.base_high, 4),
            base_low=round(context.base_low, 4),
            base_depth_percent=round(context.depth * 100, 2),
            base_length_days=len(context.base),
            contraction_count=len(context.contractions),
            latest_contraction_percent=round(
                context.contractions[-1].depth_percent if context.contractions else 0, 2
            ),
            prior_contraction_percent=round(
                context.contractions[-2].depth_percent if len(context.contractions) > 1 else 0, 2
            ),
            contractions=context.contractions,
            volume_dry_up_ratio=round(context.dry_up, 4),
            breakout_distance_percent=round(breakout_distance * 100, 2),
            overhead_resistance_percent=round(overhead * 100, 2),
            first_pullback_detected=context.first_pullback,
            inside_day=context.inside_day,
            nr7=context.nr7,
            tight_closes_count=context.tight_closes,
            range_contraction_ratio=round(context.range_ratio, 4),
        )
        reasons = detected_best.reasons + self._quality_reasons(context, confidence)
        return SetupProfile.model_construct(
            score=round(overall, 2),
            confidence=round(confidence, 2),
            grade=self._grade(overall),
            pattern_score=round(pattern, 2),
            structure_score=round(structure, 2),
            compression_score=round(compression, 2),
            volume_score=round(volume, 2),
            location_score=round(location, 2),
            best_setup_type=detected_best.setup_type,
            reasons=tuple(dict.fromkeys(reasons)),
            facts=facts,
            candidates=candidates,
        )

    def _context(self, symbol: str, frame: pd.DataFrame) -> tuple[_Context, float]:
        """Validate recent history and calculate reusable setup measurements."""
        required = {"Open", "High", "Low", "Close", "Volume", "EMA20", "EMA50", "ATR14"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Indicator frame is missing columns: {sorted(missing)}")
        if len(frame) < 120:
            raise ValueError(f"{symbol} requires at least 120 sessions for setup intelligence")
        recent = frame.iloc[-60:]
        ohlc_values = recent[["Open", "High", "Low", "Close"]].to_numpy(dtype=float)
        finite_ohlc = pd.Series(np.isfinite(ohlc_values).all(axis=1), index=recent.index)
        required_values = recent[list(required)].to_numpy(dtype=float)
        completeness = float(np.count_nonzero(np.isfinite(required_values)) / required_values.size)
        if not bool(finite_ohlc.all()):
            recent = recent.loc[finite_ohlc]
        if len(recent) < 30:
            raise ValueError(f"{symbol} has insufficient valid recent bars")
        base = recent.iloc[-self.BASE_LENGTH :]
        close = float(base["Close"].iloc[-1])
        base_high = float(base["High"].max())
        base_low = float(base["Low"].min())
        depth = (base_high - base_low) / base_high
        location = (close - base_low) / max(base_high - base_low, close * 0.001)
        volume = recent["Volume"].astype(float)
        recent_volume = float(volume.iloc[-10:].mean())
        prior_volume = float(volume.iloc[-40:-10].mean())
        dry_up = (
            recent_volume / prior_volume if prior_volume > 0 and np.isfinite(recent_volume) else 1.0
        )
        ranges = (recent["High"] - recent["Low"]).astype(float)
        prior_range = float(ranges.iloc[-40:-20].mean())
        range_ratio = float(ranges.iloc[-10:].mean()) / prior_range if prior_range > 0 else 1.0
        close_changes = base["Close"].pct_change().abs()
        tight_closes = int((close_changes <= 0.005).sum())
        latest = recent.iloc[-1]
        previous = recent.iloc[-2]
        inside = bool(latest["High"] < previous["High"] and latest["Low"] > previous["Low"])
        nr7 = bool(ranges.iloc[-1] <= ranges.iloc[-7:].min())
        contractions = self._contractions(recent.iloc[-30:])
        ema20 = float(latest["EMA20"])
        ema50 = float(latest["EMA50"])
        prior_advance = close / float(recent["Close"].iloc[-60]) - 1
        uptrend = bool(close >= ema20 >= ema50 and prior_advance >= 0.08)
        close_values = recent["Close"].to_numpy(dtype=float)
        high_values = recent["High"].to_numpy(dtype=float)
        low_values = recent["Low"].to_numpy(dtype=float)
        volume_values = recent["Volume"].to_numpy(dtype=float)
        ema20_values = recent["EMA20"].to_numpy(dtype=float)
        first_pullback = self._first_pullback(
            close_values, high_values, low_values, volume_values, ema20_values
        )
        returns = np.divide(close_values[1:], close_values[:-1]) - 1
        volume_baseline = float(np.nanmean(volume_values[:-10]))
        distribution = int(np.sum((returns < -0.02) & (volume_values[1:] > volume_baseline * 1.3)))
        prior_close = close_values[-31:-10]
        flag_high = high_values[-10:]
        flag_low = low_values[-10:]
        flag_impulse = float(prior_close[-1] / prior_close[0] - 1)
        flag_depth = float((np.max(flag_high) - np.min(flag_low)) / np.max(flag_high))
        recent_flag_volume = volume_values[-10:]
        flag_volume = (
            float(np.nanmean(recent_flag_volume) / np.nanmean(volume_values[-31:-10]))
            if np.isfinite(recent_flag_volume).any()
            else 1.0
        )
        holds_ema = close >= ema20 * 0.98
        rs_strong = float(latest["Return100D"]) > 0
        overhead = max(0.0, float(np.max(high_values)) / base_high - 1)
        confidence = min(1.0, len(frame) / 252) * completeness
        return (
            _Context(
                frame=recent,
                close=close,
                base=base,
                base_high=base_high,
                base_low=base_low,
                depth=depth,
                location=location,
                dry_up=dry_up,
                contractions=contractions,
                tight_closes=tight_closes,
                range_ratio=range_ratio,
                inside_day=inside,
                nr7=nr7,
                first_pullback=first_pullback,
                uptrend=uptrend,
                distribution=distribution,
                flag_impulse=flag_impulse,
                flag_depth=flag_depth,
                flag_volume=flag_volume,
                holds_ema=holds_ema,
                rs_strong=rs_strong,
                overhead=overhead,
            ),
            confidence,
        )

    @staticmethod
    def _contractions(frame: pd.DataFrame) -> tuple[ContractionDetail, ...]:
        """Measure three chronological contraction segments in the latest base."""
        details: list[ContractionDetail] = []
        segment_size = len(frame) // 3
        segments = (
            frame.iloc[:segment_size],
            frame.iloc[segment_size : segment_size * 2],
            frame.iloc[segment_size * 2 :],
        )
        for sequence, segment in enumerate(segments, 1):
            high = float(segment["High"].max())
            low = float(segment["Low"].min())
            depth = (high - low) / high * 100
            if depth >= 1.0:
                details.append(
                    ContractionDetail.model_construct(
                        sequence=sequence,
                        depth_percent=round(depth, 2),
                        high=round(high, 4),
                        low=round(low, 4),
                        sessions=len(segment),
                    )
                )
        return tuple(details)

    @staticmethod
    def _first_pullback(
        close: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        volume: np.ndarray,
        ema20: np.ndarray,
    ) -> bool:
        """Detect the first controlled retracement after recent range expansion."""
        expansion = (high[1:] - low[1:]) / close[:-1]
        impulse = close[1:] / close[:-1] - 1
        events = np.flatnonzero((expansion >= 0.05) & (impulse >= 0.035)) + 1
        if len(events) == 0:
            return False
        event_position = int(events[-1])
        bars_after = len(close) - event_position - 1
        if not 2 <= bars_after <= 12:
            return False
        drawdown = float(np.min(low[event_position + 1 :]) / high[event_position] - 1)
        event_volume = float(volume[event_position])
        pullback_volume = float(np.nanmean(volume[event_position + 1 :]))
        return bool(
            -0.12 <= drawdown <= -0.01
            and pullback_volume < event_volume
            and close[-1] >= ema20[-1] * 0.98
        )

    def _candidates(
        self, context: _Context, stock_profile: StockProfile | None
    ) -> tuple[SetupCandidate, ...]:
        """Evaluate all requested setup types independently."""
        depths = [item.depth_percent for item in context.contractions]
        decreasing = len(depths) >= 2 and all(
            current <= previous * 1.15 for previous, current in pairwise(depths)
        )
        distribution = context.distribution
        vcp_detected = bool(
            context.uptrend
            and 2 <= len(depths) <= 5
            and decreasing
            and context.depth <= 0.25
            and context.range_ratio <= 0.85
            and context.dry_up <= 1.05
            and context.location >= 0.65
            and distribution <= 2
            and context.close >= float(context.frame["EMA50"].iloc[-1]) * 0.98
        )
        vcp_score = _bounded(
            20 * context.uptrend
            + 20 * decreasing
            + 15 * (len(depths) >= 2)
            + 15 * (context.depth <= 0.25)
            + 15 * (context.dry_up <= 1.05)
            + 15 * (context.location >= 0.65)
            - 10 * distribution
        )
        tight_detected = bool(
            context.depth <= 0.12
            and context.range_ratio <= 0.75
            and context.tight_closes >= 8
            and context.dry_up <= 1.0
            and context.location >= 0.65
        )
        tight_score = _bounded(
            25 * (context.depth <= 0.12)
            + 20 * (context.range_ratio <= 0.75)
            + 20 * (context.tight_closes >= 8)
            + 15 * (context.dry_up <= 1.0)
            + 20 * (context.location >= 0.65)
        )
        tolerance = max(context.base_high * 0.012, 1e-9)
        high_touches = int(((context.base_high - context.base["High"]).abs() <= tolerance).sum())
        low_touches = int(((context.base["Low"] - context.base_low).abs() <= tolerance).sum())
        darvas_detected = bool(
            high_touches >= 2
            and low_touches >= 2
            and context.depth <= 0.18
            and context.location >= 0.70
        )
        darvas_score = _bounded(
            25 * (high_touches >= 2)
            + 25 * (low_touches >= 2)
            + 25 * (context.depth <= 0.18)
            + 25 * (context.location >= 0.70)
        )
        impulse = context.flag_impulse
        flag_depth = context.flag_depth
        flag_volume = context.flag_volume
        holds_ema = context.holds_ema
        flag_detected = bool(
            impulse >= 0.12 and flag_depth <= 0.12 and flag_volume <= 0.9 and holds_ema
        )
        flag_score = _bounded(
            35 * (impulse >= 0.12)
            + 25 * (flag_depth <= 0.12)
            + 20 * (flag_volume <= 0.9)
            + 20 * holds_ema
        )
        pullback_score = _bounded(100 if context.first_pullback else 20 * holds_ema)
        inside_score = 100.0 if context.inside_day else 0.0
        nr7_score = 100.0 if context.nr7 else 0.0
        stock_strong = stock_profile is None or stock_profile.score >= 65
        rs_strong = context.rs_strong
        breakout_distance = max(0.0, context.base_high / context.close - 1)
        overhead = context.overhead
        breakout_detected = bool(
            breakout_distance <= 0.03
            and context.depth <= 0.20
            and context.dry_up <= 1.05
            and overhead <= 0.08
            and stock_strong
            and rs_strong
        )
        breakout_score = _bounded(
            20 * (breakout_distance <= 0.03)
            + 20 * (context.depth <= 0.20)
            + 15 * (context.dry_up <= 1.05)
            + 15 * (overhead <= 0.08)
            + 15 * stock_strong
            + 15 * rs_strong
        )
        return (
            _make_candidate(
                setup_type=SetupType.VCP,
                detected=vcp_detected,
                score=vcp_score,
                reasons=(
                    (
                        "Decreasing contraction sequence"
                        if decreasing
                        else "Contractions are not decreasing"
                    ),
                    (
                        "Volume controlled through the base"
                        if context.dry_up <= 1.05
                        else "Volume remains elevated"
                    ),
                ),
            ),
            _make_candidate(
                setup_type=SetupType.TIGHT_BASE,
                detected=tight_detected,
                score=tight_score,
                reasons=(
                    f"{context.tight_closes} tight closes in the base",
                    f"Base depth is {context.depth * 100:.1f}%",
                ),
            ),
            _make_candidate(
                setup_type=SetupType.DARVAS_BOX,
                detected=darvas_detected,
                score=darvas_score,
                reasons=(
                    f"{high_touches} upper-boundary tests",
                    f"{low_touches} lower-boundary tests",
                ),
            ),
            _make_candidate(
                setup_type=SetupType.BULL_FLAG,
                detected=flag_detected,
                score=flag_score,
                reasons=(
                    f"Prior impulse was {impulse * 100:.1f}%",
                    f"Flag volume ratio is {flag_volume:.2f}",
                ),
            ),
            _make_candidate(
                setup_type=SetupType.FIRST_PULLBACK,
                detected=context.first_pullback,
                score=pullback_score,
                reasons=(
                    ("Controlled first pullback after range expansion",)
                    if context.first_pullback
                    else ("No qualifying recent range expansion and pullback",)
                ),
            ),
            _make_candidate(
                setup_type=SetupType.INSIDE_DAY,
                detected=context.inside_day,
                score=inside_score,
                reasons=(
                    ("Latest session is contained within the prior range",)
                    if context.inside_day
                    else ("Latest session is not an inside day",)
                ),
            ),
            _make_candidate(
                setup_type=SetupType.NR7,
                detected=context.nr7,
                score=nr7_score,
                reasons=(
                    ("Latest session has the narrowest range in seven sessions",)
                    if context.nr7
                    else ("Latest range is not NR7",)
                ),
            ),
            _make_candidate(
                setup_type=SetupType.BREAKOUT_READY,
                detected=breakout_detected,
                score=breakout_score,
                reasons=(
                    f"Price is {breakout_distance * 100:.1f}% below pivot",
                    (
                        "Stock and multi-horizon momentum remain strong"
                        if stock_strong and rs_strong
                        else "Stock or momentum profile is not strong"
                    ),
                ),
            ),
        )

    @staticmethod
    def _structure_score(context: _Context) -> float:
        """Score base depth, trend, and price location."""
        return _bounded(35 * (context.depth <= 0.20) + 25 * context.uptrend + 40 * context.location)

    @staticmethod
    def _compression_score(context: _Context) -> float:
        """Score range contraction, tight closes, and contraction progression."""
        decreasing = len(context.contractions) >= 2 and all(
            current.depth_percent <= previous.depth_percent * 1.15
            for previous, current in pairwise(context.contractions)
        )
        return _bounded(
            40 * (1 - min(context.range_ratio, 1))
            + 35 * min(1.0, context.tight_closes / 10)
            + 25 * decreasing
        )

    @staticmethod
    def _invalidation(context: _Context, setup_type: SetupType) -> float:
        """Set an objective structural invalidation below relevant support."""
        if setup_type == SetupType.FIRST_PULLBACK:
            return float(context.frame["Low"].iloc[-10:].min())
        if setup_type in {SetupType.INSIDE_DAY, SetupType.NR7}:
            return float(context.frame["Low"].iloc[-2:].min())
        return context.base_low

    @staticmethod
    def _grade(score: float) -> StockGrade:
        """Translate overall setup quality into standard grades."""
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
    def _quality_reasons(context: _Context, confidence: float) -> tuple[str, ...]:
        """Add concise shared quality or rejection evidence."""
        reasons: list[str] = []
        if context.depth > 0.30 or context.range_ratio > 1.1:
            reasons.append("Wide and loose structure rejected")
        if context.dry_up <= 0.8:
            reasons.append("Volume dried up during consolidation")
        if confidence < 1.0:
            reasons.append("Missing recent data reduces confidence")
        return tuple(reasons)
