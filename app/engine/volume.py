"""Institutional accumulation and distribution analysis from OHLCV history."""

from itertools import pairwise

import numpy as np
import pandas as pd

from app.models.stock import StockGrade
from app.models.volume import VolumeFacts, VolumeProfile, VolumeState


def _bounded(value: float) -> float:
    """Clamp a score to the public zero-to-100 range."""
    return max(0.0, min(100.0, value))


class VolumeEngine:
    """Detect professional participation using price-volume relationships."""

    MINIMUM_SESSIONS = 10
    FULL_CONFIDENCE_SESSIONS = 50

    def analyze(self, symbol: str, frame: pd.DataFrame) -> VolumeProfile:
        """Return a deterministic volume profile from normalized OHLCV data."""
        facts = self.calculate_facts(symbol, frame)
        accumulation = self._accumulation_score(facts)
        distribution = self._distribution_score(facts)
        dryup = _bounded(facts.volume_dry_up_percent * 2.5)
        expansion = _bounded(50 + facts.volume_expansion_percent)
        quality = self._quality_score(facts, accumulation, distribution, dryup, expansion)
        state = self._state(facts, accumulation, distribution, quality)
        confidence = min(1.0, facts.history_days / self.FULL_CONFIDENCE_SESSIONS)
        return VolumeProfile(
            score=round(quality, 2),
            confidence=round(confidence, 2),
            grade=self._grade(quality),
            volume_state=state,
            accumulation_score=round(accumulation, 2),
            distribution_score=round(distribution, 2),
            dryup_score=round(dryup, 2),
            expansion_score=round(expansion, 2),
            quality_score=round(quality, 2),
            reasons=self._reasons(facts, state),
            warnings=self._warnings(facts, confidence),
            facts=facts,
        )

    def calculate_facts(self, symbol: str, frame: pd.DataFrame) -> VolumeFacts:
        """Calculate volume events and participation statistics without indicators."""
        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"OHLCV frame is missing columns: {sorted(missing)}")
        clean = frame.loc[:, sorted(required)].replace([np.inf, -np.inf], np.nan).dropna()
        if len(clean) < self.MINIMUM_SESSIONS:
            raise ValueError(f"{symbol} requires at least {self.MINIMUM_SESSIONS} valid sessions")
        if (clean[["Open", "High", "Low", "Close"]] <= 0).any().any() or (
            clean["Volume"] < 0
        ).any():
            raise ValueError(f"{symbol} contains invalid OHLCV values")

        close = clean["Close"].to_numpy(dtype=float)
        high = clean["High"].to_numpy(dtype=float)
        low = clean["Low"].to_numpy(dtype=float)
        volume = clean["Volume"].to_numpy(dtype=float)
        returns = np.zeros(len(close), dtype=float)
        returns[1:] = close[1:] / close[:-1] - 1
        ranges = (high - low) / close
        current_volume = volume[-1]

        def relative(period: int) -> float:
            baseline = float(np.mean(volume[-min(period, len(volume)) :]))
            return current_volume / baseline if baseline > 0 else 0.0

        baseline20 = (
            float(np.mean(volume[-21:-1])) if len(volume) > 20 else float(np.mean(volume[:-1]))
        )
        recent5 = float(np.mean(volume[-5:]))
        prior20 = volume[-25:-5] if len(volume) >= 25 else volume[:-5]
        prior_average = float(np.mean(prior20)) if len(prior20) else baseline20
        dryup = _bounded((1 - recent5 / prior_average) * 100) if prior_average else 0.0
        expansion = (current_volume / baseline20 - 1) * 100 if baseline20 else 0.0
        average_range = (
            float(np.mean(ranges[-21:-1])) if len(ranges) > 20 else float(np.mean(ranges[:-1]))
        )
        average_abs_return = float(np.mean(np.abs(returns[-21:-1]))) or 0.001
        rel20 = relative(20)
        close_location = (close[-1] - low[-1]) / max(high[-1] - low[-1], 1e-12)
        climax = bool(rel20 >= 2.5 and ranges[-1] >= average_range * 1.5)
        churn = bool(rel20 >= 1.5 and abs(returns[-1]) <= average_abs_return * 0.5)
        reversal = bool(rel20 >= 1.5 and returns[-1] < 0 and close_location <= 0.35)
        pullback = bool(returns[-1] < 0 and rel20 <= 0.8)
        down_volumes = volume[-11:-1][returns[-11:-1] < 0]
        pocket_pivot = bool(
            returns[-1] > 0 and len(down_volumes) and current_volume > float(np.max(down_volumes))
        )
        blocks = [float(np.mean(block)) for block in np.array_split(volume[-20:], 4) if len(block)]
        contraction_sequence = sum(later < earlier for earlier, later in pairwise(blocks))
        older = volume[-50:-10] if len(volume) >= 50 else volume[:-10]
        older_average = float(np.mean(older)) if len(older) else float(np.mean(volume))
        trend = (float(np.mean(volume[-10:])) / older_average - 1) * 100 if older_average else 0.0
        window_volume = volume[-20:]
        window_returns = returns[-20:]
        total_volume = float(np.sum(window_volume))
        up_volume = float(np.sum(window_volume[window_returns > 0]))
        down_volume = float(np.sum(window_volume[window_returns < 0]))
        up_percent = up_volume / total_volume * 100 if total_volume else 0.0
        down_percent = down_volume / total_volume * 100 if total_volume else 0.0
        previous_volume = np.roll(volume, 1)
        accumulation_days = int(
            np.sum((returns[-20:] >= 0.005) & (volume[-20:] > previous_volume[-20:]))
        )
        distribution_days = int(
            np.sum((returns[-20:] <= -0.005) & (volume[-20:] > previous_volume[-20:]))
        )
        intraday_pressure = np.clip((close - low) / np.maximum(high - low, 1e-12), 0, 1)
        pressure_volume = volume[-20:]
        pressure_total = float(np.sum(pressure_volume))
        buying_pressure = (
            float(np.sum(pressure_volume * intraday_pressure[-20:])) / pressure_total * 100
            if pressure_total
            else 0.0
        )
        selling_pressure = 100 - buying_pressure if pressure_total else 0.0
        momentum = (recent5 / baseline20 - 1) * 100 if baseline20 else 0.0
        return VolumeFacts(
            symbol=symbol.upper(),
            relative_volume_5=relative(5),
            relative_volume_10=relative(10),
            relative_volume_20=rel20,
            relative_volume_50=relative(50),
            volume_dry_up_percent=dryup,
            volume_expansion_percent=expansion,
            volume_climax=climax,
            volume_churn=churn,
            high_volume_reversal=reversal,
            low_volume_pullback=pullback,
            pocket_pivot_volume=pocket_pivot,
            volume_contraction_sequence=contraction_sequence,
            average_volume_trend=trend,
            up_volume_percent=up_percent,
            down_volume_percent=down_percent,
            accumulation_days=accumulation_days,
            distribution_days=distribution_days,
            buying_pressure=buying_pressure,
            selling_pressure=selling_pressure,
            volume_momentum=momentum,
            history_days=len(clean),
        )

    @staticmethod
    def _accumulation_score(facts: VolumeFacts) -> float:
        """Score evidence of persistent institutional demand."""
        return _bounded(
            0.45 * facts.up_volume_percent
            + 0.30 * facts.buying_pressure
            + 5 * facts.accumulation_days
            + 10 * facts.pocket_pivot_volume
        )

    @staticmethod
    def _distribution_score(facts: VolumeFacts) -> float:
        """Score evidence of persistent institutional supply."""
        return _bounded(
            0.45 * facts.down_volume_percent
            + 0.30 * facts.selling_pressure
            + 7 * facts.distribution_days
            + 15 * facts.high_volume_reversal
        )

    @staticmethod
    def _quality_score(
        facts: VolumeFacts,
        accumulation: float,
        distribution: float,
        dryup: float,
        expansion: float,
    ) -> float:
        """Combine demand, controlled contraction, and participation quality."""
        score = 35 + 0.35 * accumulation - 0.35 * distribution
        score += 0.12 * dryup + 0.12 * expansion
        score += 3 * facts.volume_contraction_sequence + 8 * facts.low_volume_pullback
        score += 8 * facts.pocket_pivot_volume
        score -= 15 * facts.volume_climax + 10 * facts.volume_churn
        return _bounded(score)

    @staticmethod
    def _state(
        facts: VolumeFacts, accumulation: float, distribution: float, quality: float
    ) -> VolumeState:
        """Classify the dominant volume behavior."""
        if facts.volume_climax:
            return VolumeState.CLIMACTIC
        if distribution >= 65 and distribution > accumulation + 10:
            return VolumeState.PROFESSIONAL_DISTRIBUTION
        if accumulation >= 65 and accumulation > distribution + 10:
            return VolumeState.PROFESSIONAL_ACCUMULATION
        if quality >= 65:
            return VolumeState.HEALTHY
        if quality < 40:
            return VolumeState.WEAK
        return VolumeState.NEUTRAL

    @staticmethod
    def _grade(score: float) -> StockGrade:
        """Map quality score to the repository-wide grade scale."""
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
    def _reasons(facts: VolumeFacts, state: VolumeState) -> tuple[str, ...]:
        """Explain concrete positive and negative price-volume evidence."""
        reasons: list[str] = []
        if facts.volume_dry_up_percent >= 20:
            reasons.append("Volume Dry-Up before breakout")
        if state == VolumeState.PROFESSIONAL_ACCUMULATION:
            reasons.append("Professional accumulation")
        elif state == VolumeState.PROFESSIONAL_DISTRIBUTION:
            reasons.append("Distribution increasing")
        if facts.volume_expansion_percent >= 25 and not facts.high_volume_reversal:
            reasons.append("Healthy expansion")
        if facts.pocket_pivot_volume:
            reasons.append("Pocket pivot volume exceeds recent down-volume sessions")
        if facts.low_volume_pullback:
            reasons.append("Low-volume pullback shows controlled supply")
        if state == VolumeState.WEAK:
            reasons.append("Weak participation")
        return tuple(reasons or ("Volume participation is neutral",))

    @staticmethod
    def _warnings(facts: VolumeFacts, confidence: float) -> tuple[str, ...]:
        """Expose adverse events and incomplete-history limitations."""
        warnings: list[str] = []
        if facts.volume_climax:
            warnings.append("Volume climax may signal exhaustion")
        if facts.volume_churn:
            warnings.append("High-volume churn without price progress")
        if facts.high_volume_reversal:
            warnings.append("High-volume reversal signals institutional selling")
        if confidence < 1:
            warnings.append("Limited history reduces volume confidence")
        return tuple(warnings)
