"""Objective advanced setup detection layered onto the existing Setup Engine."""

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from app.core.v11_config import DEFAULT_ADVANCED_SETUP_THRESHOLDS, AdvancedSetupThresholds
from app.models.setup import ListingMetadata, SetupCandidate, SetupProfile, SetupType
from app.models.stock import StockGrade


class AdvancedSetupEngine:
    """Enhance a precomputed SetupProfile without duplicating its base measurements."""

    def __init__(
        self, thresholds: AdvancedSetupThresholds = DEFAULT_ADVANCED_SETUP_THRESHOLDS
    ) -> None:
        self._t = thresholds

    def enhance(
        self,
        profile: SetupProfile,
        frame: pd.DataFrame,
        earnings_dates: Sequence[pd.Timestamp] = (),
        avwap_alignment: bool | None = None,
        listing_metadata: ListingMetadata | None = None,
    ) -> SetupProfile:
        """Detect advanced structures and compare them with existing candidates."""
        close = frame["Close"].to_numpy(float)
        high = frame["High"].to_numpy(float)
        low = frame["Low"].to_numpy(float)
        volume = frame["Volume"].to_numpy(float)
        open_ = frame["Open"].to_numpy(float)
        ema50 = frame["EMA50"].to_numpy(float)
        ema200 = frame["EMA200"].to_numpy(float) if "EMA200" in frame else ema50
        candidates, flags, detection_warnings = self._detect(
            frame.index,
            close,
            high,
            low,
            volume,
            open_,
            ema50,
            ema200,
            earnings_dates,
            avwap_alignment,
            listing_metadata,
        )
        candidates = tuple(
            self._complete_candidate(item, profile, high, low) for item in candidates
        )
        legacy = SetupCandidate.model_construct(
            setup_type=profile.best_setup_type,
            detected=profile.best_setup_type != SetupType.NONE,
            score=profile.score,
            confidence=profile.confidence,
            grade=profile.grade,
            pivot_price=profile.facts.pivot_price,
            invalidation_price=profile.facts.invalidation_price,
            base_high=profile.facts.base_high,
            base_low=profile.facts.base_low,
            base_length_days=profile.facts.base_length_days,
            pattern_score=profile.pattern_score,
            structure_score=profile.structure_score,
            compression_score=profile.compression_score,
            volume_score=profile.volume_score,
            location_score=profile.location_score,
            reasons=profile.reasons,
            warnings=profile.warnings,
        )
        selectable = tuple(
            item for item in candidates if item.setup_type != SetupType.FAILED_BREAKOUT
        )
        best = max((legacy, *selectable), key=lambda item: (item.detected, item.score))
        advanced_score = max(item.score for item in selectable)
        failure = next(
            item.score for item in candidates if item.setup_type == SetupType.FAILED_BREAKOUT
        )
        retest = next(
            item.score for item in candidates if item.setup_type == SetupType.BREAKOUT_RETEST
        )
        stage = next(
            item.score for item in candidates if item.setup_type == SetupType.STAGE_2_FIRST_BASE
        )
        facts = profile.facts.model_copy(
            update={
                "setup_type": best.setup_type if best.detected else profile.best_setup_type,
                "setup_score": best.score if best.detected else profile.score,
                "setup_confidence": best.confidence if best.detected else profile.confidence,
                "pivot_price": best.pivot_price if best.detected else profile.facts.pivot_price,
                "invalidation_price": (
                    best.invalidation_price if best.detected else profile.facts.invalidation_price
                ),
                "base_high": best.base_high if best.detected else profile.facts.base_high,
                "base_low": best.base_low if best.detected else profile.facts.base_low,
                "base_depth_percent": (
                    (best.base_high - best.base_low) / best.base_high * 100
                    if best.detected and best.base_high and best.base_low
                    else profile.facts.base_depth_percent
                ),
                "base_length_days": (
                    best.base_length_days if best.detected else profile.facts.base_length_days
                ),
                "breakout_distance_percent": (
                    max(0.0, best.pivot_price / close[-1] - 1) * 100
                    if best.detected and best.pivot_price
                    else profile.facts.breakout_distance_percent
                ),
                "overhead_resistance_percent": (
                    max(0.0, float(np.max(high[-120:])) / best.pivot_price - 1) * 100
                    if best.detected and best.pivot_price
                    else profile.facts.overhead_resistance_percent
                ),
                "ipo_age_sessions": flags.pop("ipo_age_sessions"),
                "ipo_open_price": flags.pop("ipo_open_price"),
                "ipo_high": flags.pop("ipo_high"),
                "ipo_low": flags.pop("ipo_low"),
                "ipo_base_depth_percent": flags.pop("ipo_base_depth_percent"),
                "ipo_base_length": flags.pop("ipo_base_length"),
                "ipo_pivot": flags.pop("ipo_pivot"),
                "ipo_avwap_alignment": avwap_alignment,
                "ipo_base_score": candidates[0].score,
                **flags,
            }
        )
        warnings = tuple(detection_warnings)
        selected = best if best.detected else None
        return profile.model_copy(
            update={
                "best_setup_type": best.setup_type if best.detected else profile.best_setup_type,
                "score": selected.score if selected else profile.score,
                "confidence": selected.confidence if selected else profile.confidence,
                "grade": selected.grade if selected else profile.grade,
                "pattern_score": selected.pattern_score if selected else profile.pattern_score,
                "structure_score": (
                    selected.structure_score if selected else profile.structure_score
                ),
                "compression_score": (
                    selected.compression_score if selected else profile.compression_score
                ),
                "volume_score": selected.volume_score if selected else profile.volume_score,
                "location_score": selected.location_score if selected else profile.location_score,
                "facts": facts,
                "candidates": (*profile.candidates, *candidates),
                "advanced_setup_score": round(advanced_score, 2),
                "base_maturity_score": min(100.0, profile.facts.base_length_days / 45 * 100),
                "failure_risk_score": round(failure, 2),
                "prior_advance_score": round(
                    min(100.0, max(0.0, (close[-20] / close[-60] - 1) * 250)), 2
                ),
                "catalyst_quality_score": 80 if earnings_dates else 20,
                "breakout_retest_score": round(retest, 2),
                "stage_quality_score": round(stage, 2),
                "advanced_setup_candidates": candidates,
                "reasons": tuple(dict.fromkeys((*best.reasons, *profile.reasons, *warnings))),
                "warnings": warnings,
            }
        )

    def _detect(
        self,
        index: pd.Index,
        close: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        volume: np.ndarray,
        open_: np.ndarray,
        ema50: np.ndarray,
        ema200: np.ndarray,
        earnings_dates: Sequence[pd.Timestamp],
        avwap: bool | None,
        listing_metadata: ListingMetadata | None,
    ) -> tuple[tuple[SetupCandidate, ...], dict[str, object], tuple[str, ...]]:
        age = len(close)
        warnings: list[str] = []
        base_high = float(np.max(high[-30:]))
        base_low = float(np.min(low[-30:]))
        depth = (base_high - base_low) / base_high
        dry = float(np.mean(volume[-10:]) / max(np.mean(volume[-30:-10]), 1))
        near = close[-1] >= base_high * 0.95
        prior = close[-20] / close[-60] - 1
        distribution = int(
            np.sum((np.diff(close[-30:]) < 0) & (volume[-29:] > np.mean(volume[-30:]) * 1.3))
        )
        ipo_age = 0
        ipo_open: float | None = None
        ipo_high: float | None = None
        ipo_low: float | None = None
        listing_complete = False
        if listing_metadata is None:
            warnings.append("Authoritative listing metadata unavailable; IPO setup not evaluated")
        else:
            listing = pd.Timestamp(listing_metadata.listing_date)
            normalized_index = pd.DatetimeIndex(index).tz_localize(None).normalize()
            positions = np.flatnonzero(normalized_index >= listing)
            first_delay = (normalized_index[0] - listing).days
            listing_complete = bool(positions.size and positions[0] == 0 and 0 <= first_delay <= 7)
            if listing_complete:
                ipo_age = len(positions)
                ipo_open = listing_metadata.ipo_open_price
                ipo_high = float(np.max(high[positions]))
                ipo_low = float(np.min(low[positions]))
            else:
                warnings.append("Price history does not begin at listing; IPO setup not evaluated")
        ipo = (
            listing_complete
            and ipo_age <= self._t.ipo_max_age
            and ipo_age >= self._t.ipo_min_age
            and close[-1] > open_[0]
            and depth <= 0.30
            and dry <= 1
            and ema50[-1] >= ema50[-10]
        )
        flat = (
            depth <= self._t.flat_base_max_depth
            and near
            and dry <= 1
            and prior > 0.08
            and distribution < 4
        )
        left = int(np.argmax(high[-120:-60]))
        cup_low = float(np.min(low[-80:-15]))
        left_high = float(high[-120:-60][left])
        right = float(np.max(high[-20:]))
        cup_depth = (left_high - cup_low) / left_high
        handle_depth = (float(np.max(high[-15:])) - float(np.min(low[-15:]))) / max(
            float(np.max(high[-15:])), 1
        )
        cup = (
            0.12 <= cup_depth <= 0.40
            and right >= left_high * 0.90
            and handle_depth <= self._t.handle_max_depth
            and np.min(low[-15:]) > (left_high + cup_low) / 2
            and dry < 1
        )
        first_low = int(np.argmin(low[-100:-50]))
        second_low = int(np.argmin(low[-49:-5]))
        l1 = float(low[-100:-50][first_low])
        l2 = float(low[-49:-5][second_low])
        middle = float(np.max(high[-60:-25]))
        double = abs(l2 / l1 - 1) <= 0.05 and middle > l1 * 1.08 and close[-1] >= middle * 0.97
        advance = close[-20] / close[-40] - 1
        htf = advance >= self._t.high_tight_flag_advance and depth <= 0.20 and dry < 0.9
        complete_week_start = age % 5
        weekly = close[complete_week_start:].reshape(-1, 5)[:, -1]
        three = (
            len(weekly) >= 4
            and np.ptp(weekly[-3:]) / max(weekly[-3:]) <= self._t.tight_weekly_range
            and prior > 0.10
        )
        support = float(np.min(low[-25:-5]))
        spring = np.min(low[-5:]) < support * 0.99 and close[-1] > support and close[-1] > open_[-1]
        shake = spring and np.all(np.diff(close[-3:]) >= 0)
        pivot = float(np.max(high[-60:-30]))
        broke = np.max(high[-30:-10]) > pivot
        failed = broke and close[-1] < pivot * 0.99 and close[-1] < (high[-1] + low[-1]) / 2
        retest = (
            broke
            and abs(close[-1] / pivot - 1) <= 0.025
            and np.min(low[-10:]) <= pivot * 1.01
            and close[-1] >= pivot * 0.98
            and dry <= 1
        )
        stage = (
            close[-1] > ema50[-1] > ema200[-1]
            and ema50[-1] > ema50[-20]
            and ema200[-1] >= ema200[-20]
            and depth <= 0.20
        )
        gaps = open_[1:] / close[:-1] - 1
        gap_positions = np.flatnonzero(gaps >= self._t.gap_threshold) + 1
        event_dates = [pd.Timestamp(item).tz_localize(None).normalize() for item in earnings_dates]
        matched_gap = None
        if event_dates and gap_positions.size:
            normalized_dates = pd.DatetimeIndex(index).tz_localize(None).normalize()
            matched_gap = next(
                (
                    int(position)
                    for position in reversed(gap_positions)
                    if position >= age - 30
                    and any(
                        abs((normalized_dates[position] - event).days)
                        <= self._t.earnings_event_tolerance_days
                        for event in event_dates
                    )
                ),
                None,
            )
        if not event_dates:
            warnings.append("Earnings catalyst data unavailable; earnings setup not evaluated")
        elif matched_gap is not None and self._t.require_earnings_avwap and avwap is None:
            warnings.append("Earnings AVWAP evidence unavailable; earnings setup not evaluated")
        earnings = bool(
            matched_gap is not None
            and close[-1] >= open_[matched_gap] * 0.95
            and (avwap is True or not self._t.require_earnings_avwap)
        )
        values: Mapping[SetupType, tuple[bool, float, str]] = {
            SetupType.IPO_BASE: (ipo, 85 if ipo else 25, "Controlled IPO price discovery"),
            SetupType.FLAT_BASE: (flat, 85 if flat else 30, "Tight 20-45 session flat base"),
            SetupType.CUP_WITH_HANDLE: (
                cup,
                90 if cup else 20,
                "Rounded cup with upper-half handle",
            ),
            SetupType.DOUBLE_BOTTOM: (
                double,
                85 if double else 20,
                "Two lows with valid middle pivot",
            ),
            SetupType.HIGH_TIGHT_FLAG: (htf, 95 if htf else 10, "Rare high-tight-flag validation"),
            SetupType.THREE_WEEKS_TIGHT: (
                three,
                85 if three else 20,
                "Three weekly closes tightly grouped",
            ),
            SetupType.WYCKOFF_SPRING: (
                spring,
                80 if spring else 15,
                "Objective support undercut and reclaim",
            ),
            SetupType.SHAKEOUT_PLUS_THREE: (
                shake,
                85 if shake else 15,
                "Shakeout followed by three-session stabilization",
            ),
            SetupType.FAILED_BREAKOUT: (
                failed,
                90 if failed else 0,
                "Breakout failure back inside base",
            ),
            SetupType.BREAKOUT_RETEST: (retest, 85 if retest else 20, "Former pivot retest held"),
            SetupType.STAGE_2_FIRST_BASE: (
                stage,
                85 if stage else 20,
                "Rising EMA50 and EMA200 Stage 2 base",
            ),
            SetupType.EARNINGS_GAP_CONSOLIDATION: (
                earnings,
                90 if earnings else 10,
                (
                    "Earnings gap consolidation"
                    if event_dates
                    else "Catalyst unavailable; earnings setup not asserted"
                ),
            ),
        }
        candidates = tuple(
            SetupCandidate.model_construct(
                setup_type=k,
                detected=bool(v[0]),
                score=v[1],
                confidence=0.0,
                grade=StockGrade.D,
                pivot_price=None,
                invalidation_price=None,
                base_high=None,
                base_low=None,
                base_length_days=None,
                pattern_score=0.0,
                structure_score=0.0,
                compression_score=0.0,
                volume_score=0.0,
                location_score=0.0,
                reasons=(v[2],),
                warnings=(),
            )
            for k, v in values.items()
        )
        return (
            candidates,
            {
                "ipo_age_sessions": ipo_age,
                "ipo_open_price": ipo_open,
                "ipo_high": ipo_high,
                "ipo_low": ipo_low,
                "ipo_base_depth_percent": (
                    (ipo_high - ipo_low) / ipo_high * 100 if ipo_high and ipo_low else 0
                ),
                "ipo_base_length": ipo_age,
                "ipo_pivot": float(np.max(high[-20:])) if listing_complete else None,
                "failed_breakout": bool(failed),
                "breakout_retest": bool(retest),
                "stage_2_first_base": bool(stage),
                "earnings_catalyst_available": bool(event_dates),
            },
            tuple(warnings),
        )

    @staticmethod
    def _complete_candidate(
        candidate: SetupCandidate,
        profile: SetupProfile,
        high: np.ndarray,
        low: np.ndarray,
    ) -> SetupCandidate:
        """Attach one internally consistent score, risk structure, and component set."""
        pivot = (
            float(np.max(high[-60:-30]))
            if candidate.setup_type == SetupType.BREAKOUT_RETEST
            else float(np.max(high[-20:]))
        )
        invalidation = float(np.min(low[-20:]))
        base_window = (
            120
            if candidate.setup_type == SetupType.CUP_WITH_HANDLE
            else 100 if candidate.setup_type == SetupType.DOUBLE_BOTTOM else 30
        )
        base_high = float(np.max(high[-base_window:]))
        base_low = float(np.min(low[-base_window:]))
        score = candidate.score
        grade = (
            StockGrade.A_PLUS
            if score >= 90
            else (
                StockGrade.A
                if score >= 80
                else StockGrade.B if score >= 70 else StockGrade.C if score >= 55 else StockGrade.D
            )
        )
        return candidate.model_copy(
            update={
                "confidence": profile.confidence if candidate.detected else 0.0,
                "grade": grade,
                "pivot_price": pivot if candidate.detected else None,
                "invalidation_price": invalidation if candidate.detected else None,
                "base_high": base_high if candidate.detected else None,
                "base_low": base_low if candidate.detected else None,
                "base_length_days": base_window if candidate.detected else None,
                "pattern_score": score,
                "structure_score": profile.structure_score,
                "compression_score": profile.compression_score,
                "volume_score": profile.volume_score,
                "location_score": profile.location_score,
            }
        )
