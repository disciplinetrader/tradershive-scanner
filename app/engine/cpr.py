"""Multi-timeframe Central Pivot Range structure and probability engine."""

import numpy as np
import pandas as pd

from app.models.cpr import (
    CPRFacts,
    CPRPriceLocation,
    CPRProfile,
    CPRRelationship,
    CPRState,
    CPRTimeframe,
    CPRWidthState,
    TimeframeCPR,
)
from app.models.stock import StockGrade


def _bounded(value: float) -> float:
    """Clamp probability and score values to zero through 100."""
    return max(0.0, min(100.0, value))


class CPREngine:
    """Classify daily, weekly, and monthly CPR structure for swing trading."""

    MINIMUM_SESSIONS = 45

    def __init__(self) -> None:
        """Initialize reusable calendar-group boundaries for universe scans."""
        self._group_cache: dict[tuple[str, int, int, int], tuple[np.ndarray, np.ndarray]] = {}

    def analyze(self, symbol: str, frame: pd.DataFrame) -> CPRProfile:
        """Return a complete CPR profile from normalized OHLC history."""
        facts = self.calculate_facts(symbol, frame)
        periods = (facts.daily, facts.weekly, facts.monthly)
        width_expansion = sum(100 - period.width_percentile for period in periods) / 3
        bullish_alignment = sum(
            period.relationship_to_previous_cpr
            in {CPRRelationship.HIGHER_VALUE, CPRRelationship.OVERLAPPING_HIGHER}
            for period in periods
        )
        bearish_alignment = sum(
            period.relationship_to_previous_cpr
            in {CPRRelationship.LOWER_VALUE, CPRRelationship.OVERLAPPING_LOWER}
            for period in periods
        )
        location_alignment = 100 if facts.price_above_all_cprs else 0
        if facts.price_below_all_cprs:
            location_alignment = 15
        elif not facts.price_above_all_cprs:
            location_alignment = 50
        breakout = _bounded(
            0.55 * width_expansion
            + 10 * sum(period.virgin_cpr for period in periods)
            + 0.15 * location_alignment
        )
        trend = _bounded(
            25
            + 18 * max(bullish_alignment, bearish_alignment)
            + 0.20 * location_alignment
            + 8 * sum(period.trend_cpr for period in periods)
        )
        range_probability = _bounded(
            100
            - 0.55 * breakout
            - 0.25 * trend
            + 8
            * sum(
                period.width_state in {CPRWidthState.WIDE, CPRWidthState.EXTREMELY_WIDE}
                for period in periods
            )
        )
        score = _bounded(0.50 * breakout + 0.35 * trend + 0.15 * (100 - range_probability))
        state = self._aggregate_state(facts)
        confidence = min(1.0, facts.history_days / 252)
        return CPRProfile(
            score=round(score, 2),
            confidence=round(confidence, 2),
            grade=self._grade(score),
            cpr_state=state,
            breakout_probability=round(breakout, 2),
            trend_probability=round(trend, 2),
            range_probability=round(range_probability, 2),
            reasons=self._reasons(facts, breakout, trend),
            warnings=self._warnings(facts, confidence),
            facts=facts,
        )

    def calculate_facts(self, symbol: str, frame: pd.DataFrame) -> CPRFacts:
        """Calculate three timeframe CPR bands and their prior relationships."""
        required = {"High", "Low", "Close"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"OHLC frame is missing columns: {sorted(missing)}")
        selected = frame.loc[:, ["High", "Low", "Close"]]
        values = selected.to_numpy(dtype=float)
        valid_rows = np.isfinite(values).all(axis=1)
        clean = selected if valid_rows.all() else selected.loc[valid_rows]
        if len(clean) < self.MINIMUM_SESSIONS:
            raise ValueError(f"{symbol} requires at least {self.MINIMUM_SESSIONS} valid sessions")
        if (clean.to_numpy(dtype=float) <= 0).any():
            raise ValueError(f"{symbol} contains invalid OHLC values")
        daily_periods = clean
        weekly_periods = self._resample(clean, "W-FRI")
        monthly_periods = self._resample(clean, "M")
        if min(len(weekly_periods), len(monthly_periods)) < 3:
            raise ValueError(f"{symbol} has insufficient weekly or monthly CPR history")
        latest = clean.iloc[-1]
        close = float(latest["Close"])
        daily = self._timeframe(CPRTimeframe.DAILY, daily_periods, latest, close)
        weekly = self._timeframe(
            CPRTimeframe.WEEKLY, weekly_periods, weekly_periods.iloc[-1], close
        )
        monthly = self._timeframe(
            CPRTimeframe.MONTHLY, monthly_periods, monthly_periods.iloc[-1], close
        )
        periods = (daily, weekly, monthly)
        return CPRFacts(
            symbol=symbol.upper(),
            close=close,
            daily=daily,
            weekly=weekly,
            monthly=monthly,
            price_above_all_cprs=all(
                period.price_location == CPRPriceLocation.ABOVE for period in periods
            ),
            price_below_all_cprs=all(
                period.price_location == CPRPriceLocation.BELOW for period in periods
            ),
            aligned_higher_value=all(
                period.relationship_to_previous_cpr
                in {CPRRelationship.HIGHER_VALUE, CPRRelationship.OVERLAPPING_HIGHER}
                for period in periods
            ),
            aligned_lower_value=all(
                period.relationship_to_previous_cpr
                in {CPRRelationship.LOWER_VALUE, CPRRelationship.OVERLAPPING_LOWER}
                for period in periods
            ),
            history_days=len(clean),
        )

    def _resample(self, frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
        """Aggregate normalized daily OHLC into a higher timeframe."""
        index_values = frame.index.asi8
        key = (frequency, len(frame), int(index_values[0]), int(index_values[-1]))
        boundaries = self._group_cache.get(key)
        if boundaries is None:
            plain_index = frame.index.tz_localize(None) if frame.index.tz else frame.index
            periods = plain_index.to_period(frequency).asi8
            starts = np.r_[0, np.flatnonzero(periods[1:] != periods[:-1]) + 1]
            ends = np.r_[starts[1:] - 1, len(frame) - 1]
            boundaries = (starts, ends)
            self._group_cache[key] = boundaries
        starts, ends = boundaries
        high = np.maximum.reduceat(frame["High"].to_numpy(dtype=float), starts)
        low = np.minimum.reduceat(frame["Low"].to_numpy(dtype=float), starts)
        close = frame["Close"].to_numpy(dtype=float)[ends]
        return pd.DataFrame(
            {"High": high, "Low": low, "Close": close},
            index=frame.index[ends],
        )

    def _timeframe(
        self,
        timeframe: CPRTimeframe,
        periods: pd.DataFrame,
        observed: pd.Series,
        close: float,
    ) -> TimeframeCPR:
        """Build one timeframe using the prior period's HLC values."""
        current = self._band(periods.iloc[-2])
        previous = self._band(periods.iloc[-3])
        history = periods.iloc[:-1]
        pivots = (history["High"] + history["Low"] + history["Close"]) / 3
        midpoints = (history["High"] + history["Low"]) / 2
        widths = ((2 * pivots - 2 * midpoints).abs() / pivots * 100).to_numpy(dtype=float)
        less = float(np.sum(widths < current[3]))
        equal = float(np.sum(np.isclose(widths, current[3], rtol=1e-9, atol=1e-12)))
        percentile = (less + 0.5 * equal) / len(widths) * 100
        width_state = self._width_state(percentile)
        relationship = self._relationship(current, previous)
        bc, tc = current[1], current[2]
        if close > tc:
            location = CPRPriceLocation.ABOVE
            distance = (close - tc) / current[0] * 100
            breakout_distance = 0.0
        elif close < bc:
            location = CPRPriceLocation.BELOW
            distance = (close - bc) / current[0] * 100
            breakout_distance = (bc - close) / current[0] * 100
        else:
            location = CPRPriceLocation.INSIDE
            distance = 0.0
            breakout_distance = (tc - close) / current[0] * 100
        virgin = bool(float(observed["Low"]) > tc or float(observed["High"]) < bc)
        return TimeframeCPR(
            timeframe=timeframe,
            pivot=current[0],
            bc=bc,
            tc=tc,
            width=current[3],
            width_percentile=percentile,
            width_state=width_state,
            virgin_cpr=virgin,
            narrow_cpr=width_state in {CPRWidthState.EXTREMELY_NARROW, CPRWidthState.NARROW},
            wide_cpr=width_state in {CPRWidthState.WIDE, CPRWidthState.EXTREMELY_WIDE},
            overlapping_higher=relationship == CPRRelationship.OVERLAPPING_HIGHER,
            overlapping_lower=relationship == CPRRelationship.OVERLAPPING_LOWER,
            inside_value=relationship == CPRRelationship.INSIDE_VALUE,
            outside_value=relationship == CPRRelationship.OUTSIDE_VALUE,
            higher_value=relationship == CPRRelationship.HIGHER_VALUE,
            lower_value=relationship == CPRRelationship.LOWER_VALUE,
            trend_cpr=relationship
            in {
                CPRRelationship.HIGHER_VALUE,
                CPRRelationship.LOWER_VALUE,
                CPRRelationship.OVERLAPPING_HIGHER,
                CPRRelationship.OVERLAPPING_LOWER,
            },
            distance_from_cpr=distance,
            price_location=location,
            breakout_distance=max(0.0, breakout_distance),
            relationship_to_previous_cpr=relationship,
        )

    @staticmethod
    def _band(row: pd.Series) -> tuple[float, float, float, float]:
        """Return pivot, lower boundary, upper boundary, and percent width."""
        high, low, close = (float(row[name]) for name in ("High", "Low", "Close"))
        pivot = (high + low + close) / 3
        raw_bc = (high + low) / 2
        raw_tc = 2 * pivot - raw_bc
        bc, tc = sorted((raw_bc, raw_tc))
        return pivot, bc, tc, (tc - bc) / pivot * 100

    @staticmethod
    def _width_state(percentile: float) -> CPRWidthState:
        """Classify CPR width using its own historical distribution."""
        if percentile <= 10:
            return CPRWidthState.EXTREMELY_NARROW
        if percentile <= 30:
            return CPRWidthState.NARROW
        if percentile < 70:
            return CPRWidthState.NORMAL
        if percentile < 90:
            return CPRWidthState.WIDE
        return CPRWidthState.EXTREMELY_WIDE

    @staticmethod
    def _relationship(
        current: tuple[float, float, float, float],
        previous: tuple[float, float, float, float],
    ) -> CPRRelationship:
        """Classify the current band relative to the preceding CPR band."""
        _, bc, tc, _ = current
        _, prior_bc, prior_tc, _ = previous
        if bc > prior_tc:
            return CPRRelationship.HIGHER_VALUE
        if tc < prior_bc:
            return CPRRelationship.LOWER_VALUE
        if bc >= prior_bc and tc <= prior_tc:
            return CPRRelationship.INSIDE_VALUE
        if bc <= prior_bc and tc >= prior_tc:
            return CPRRelationship.OUTSIDE_VALUE
        if current[0] > previous[0]:
            return CPRRelationship.OVERLAPPING_HIGHER
        if current[0] < previous[0]:
            return CPRRelationship.OVERLAPPING_LOWER
        return CPRRelationship.UNCHANGED

    @staticmethod
    def _aggregate_state(facts: CPRFacts) -> CPRState:
        """Select the dominant multi-timeframe CPR state."""
        periods = (facts.daily, facts.weekly, facts.monthly)
        if all(period.virgin_cpr for period in periods):
            return CPRState.VIRGIN
        if facts.aligned_higher_value or facts.aligned_lower_value:
            return CPRState.TRENDING
        width = facts.daily.width_state
        if width == CPRWidthState.EXTREMELY_NARROW:
            return CPRState.EXTREMELY_NARROW
        if width == CPRWidthState.NARROW:
            return CPRState.NARROW
        if width == CPRWidthState.WIDE:
            return CPRState.WIDE
        if width == CPRWidthState.EXTREMELY_WIDE:
            return CPRState.EXTREMELY_WIDE
        if any(period.inside_value or period.outside_value for period in periods):
            return CPRState.BALANCED
        return CPRState.NORMAL

    @staticmethod
    def _grade(score: float) -> StockGrade:
        """Map CPR opportunity quality to the shared grade scale."""
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
    def _reasons(facts: CPRFacts, breakout: float, trend: float) -> tuple[str, ...]:
        """Explain the strongest timeframe and alignment evidence."""
        reasons = [f"Daily CPR {facts.daily.width_state.value.lower()}"]
        if facts.weekly.higher_value or facts.weekly.overlapping_higher:
            reasons.append("Weekly CPR higher value")
        elif facts.weekly.lower_value or facts.weekly.overlapping_lower:
            reasons.append("Weekly CPR lower value")
        if facts.monthly.higher_value or facts.monthly.overlapping_higher:
            reasons.append("Monthly CPR bullish")
        elif facts.monthly.lower_value or facts.monthly.overlapping_lower:
            reasons.append("Monthly CPR bearish")
        if facts.price_above_all_cprs:
            reasons.append("Price above all CPRs")
        elif facts.price_below_all_cprs:
            reasons.append("Price below all CPRs")
        if breakout >= 70:
            reasons.append("High probability expansion")
        if trend >= 75:
            reasons.append("Multi-timeframe CPR trend alignment")
        return tuple(reasons)

    @staticmethod
    def _warnings(facts: CPRFacts, confidence: float) -> tuple[str, ...]:
        """Expose contradictory structures and incomplete historical context."""
        warnings: list[str] = []
        locations = {
            facts.daily.price_location,
            facts.weekly.price_location,
            facts.monthly.price_location,
        }
        if len(locations) > 1:
            warnings.append("Price location is mixed across CPR timeframes")
        if facts.daily.wide_cpr and facts.weekly.wide_cpr:
            warnings.append("Wide daily and weekly CPRs favor range behavior")
        if confidence < 1:
            warnings.append("Limited history reduces CPR confidence")
        return tuple(warnings)
