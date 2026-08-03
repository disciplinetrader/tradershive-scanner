"""Intrinsic stock trend, momentum, participation, and health engine."""

import pandas as pd

from app.data.indicators import add_indicators
from app.models.stock import StockFacts, StockGrade, StockProfile


def _bounded(value: float) -> float:
    """Clamp a numeric score to the public zero-to-100 contract."""
    return max(0.0, min(100.0, value))


class StockEngine:
    """Evaluate intrinsic technical quality without detecting chart patterns."""

    STRUCTURE_WINDOW = 20

    def analyze(self, symbol: str, frame: pd.DataFrame) -> StockProfile:
        """Build a complete, deterministic profile from normalized OHLCV history."""
        facts = self.calculate_facts(symbol, frame)
        trend = self._trend_score(facts)
        momentum = self._momentum_score(facts)
        participation = self._participation_score(facts)
        health = self._health_score(facts)
        score = _bounded(0.35 * trend + 0.30 * momentum + 0.20 * participation + 0.15 * health)
        return StockProfile(
            score=round(score, 2),
            confidence=round(min(1.0, facts.history_days / 252), 2),
            grade=self._grade(score),
            trend_score=round(trend, 2),
            momentum_score=round(momentum, 2),
            participation_score=round(participation, 2),
            health_score=round(health, 2),
            reasons=self._reasons(facts, trend, momentum, participation, health),
            facts=facts,
        )

    def calculate_facts(self, symbol: str, frame: pd.DataFrame) -> StockFacts:
        """Derive validated stock measurements from an OHLCV frame."""
        enriched = frame if {"EMA100", "EMA150"}.issubset(frame.columns) else add_indicators(frame)
        required = {
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
            "EMA20",
            "EMA50",
            "EMA100",
            "EMA150",
            "EMA200",
            "ATR14",
            "High52W",
            "Low52W",
            "AverageVolume",
            "Return20D",
            "Return50D",
            "Return100D",
            "Return150D",
            "Return250D",
        }
        missing = required.difference(enriched.columns)
        if missing:
            raise ValueError(f"Indicator frame is missing columns: {sorted(missing)}")
        if len(enriched) < 252:
            raise ValueError(f"{symbol} requires at least 252 sessions for stock intelligence")
        latest = enriched.iloc[-1]
        if latest[list(required)].isna().any():
            raise ValueError(f"{symbol} has insufficient history for stock intelligence")

        close = float(latest["Close"])
        ema = {period: float(latest[f"EMA{period}"]) for period in (20, 50, 100, 150, 200)}
        recent = enriched.iloc[-self.STRUCTURE_WINDOW :]
        previous = enriched.iloc[-2]
        prior_52_week = enriched.iloc[-253:-1]
        ranges = (enriched["High"] - enriched["Low"]).astype(float)
        gaps = (enriched["Open"] / enriched["Close"].shift(1) - 1).abs()
        atr_average = float(enriched["ATR14"].iloc[-21:-1].mean())
        average_volume = float(latest["AverageVolume"])
        relative_volume = float(latest["Volume"]) / average_volume if average_volume else 0.0
        recent_volume = float(enriched["Volume"].iloc[-5:].mean())
        baseline_volume = float(enriched["Volume"].iloc[-25:-5].mean())
        current_range = float(latest["High"] - latest["Low"])
        prior_ranges = ranges.iloc[-7:-1]
        high_52 = float(latest["High52W"])
        low_52 = float(latest["Low52W"])
        return StockFacts(
            symbol=symbol.upper(),
            close=close,
            ema20=ema[20],
            ema50=ema[50],
            ema100=ema[100],
            ema150=ema[150],
            ema200=ema[200],
            ema_alignment=close > ema[20] > ema[50] > ema[100] > ema[150] > ema[200],
            distance_above_ema20=close / ema[20] - 1,
            distance_above_ema50=close / ema[50] - 1,
            distance_above_ema200=close / ema[200] - 1,
            return_20d=float(latest["Return20D"]),
            return_50d=float(latest["Return50D"]),
            return_100d=float(latest["Return100D"]),
            return_150d=float(latest["Return150D"]),
            return_250d=float(latest["Return250D"]),
            atr14=float(latest["ATR14"]),
            atr_expansion=float(latest["ATR14"]) / atr_average - 1 if atr_average else 0.0,
            average_daily_range=float((recent["High"] - recent["Low"]).mean() / close),
            distance_from_52_week_high=max(0.0, high_52 / close - 1),
            distance_from_52_week_low=max(0.0, close / low_52 - 1),
            higher_highs=int((recent["High"].diff() > 0).sum()),
            higher_lows=int((recent["Low"].diff() > 0).sum()),
            lower_highs=int((recent["High"].diff() < 0).sum()),
            lower_lows=int((recent["Low"].diff() < 0).sum()),
            gap_percent=float(latest["Open"] / previous["Close"] - 1),
            average_gap=float(gaps.iloc[-20:].mean()),
            relative_volume=relative_volume,
            average_volume=average_volume,
            volume_expansion=bool(
                relative_volume >= 1.25 or recent_volume >= baseline_volume * 1.15
            ),
            volume_contraction=bool(
                relative_volume <= 0.75 or recent_volume <= baseline_volume * 0.85
            ),
            new_high=bool(float(latest["High"]) >= float(prior_52_week["High"].max())),
            new_low=bool(float(latest["Low"]) <= float(prior_52_week["Low"].min())),
            inside_day=bool(latest["High"] < previous["High"] and latest["Low"] > previous["Low"]),
            outside_day=bool(latest["High"] > previous["High"] and latest["Low"] < previous["Low"]),
            nr7=bool(current_range <= float(prior_ranges.min())),
            history_days=len(enriched),
        )

    @staticmethod
    def _trend_score(facts: StockFacts) -> float:
        """Score EMA structure, position, persistence, and long-term direction."""
        score = 35.0 if facts.ema_alignment else 0.0
        score += 10.0 * (facts.close > facts.ema20)
        score += 10.0 * (facts.close > facts.ema50)
        score += 15.0 * (facts.close > facts.ema200)
        score += 15.0 * facts.higher_highs / 19
        score += 15.0 * facts.higher_lows / 19
        return _bounded(score)

    @staticmethod
    def _momentum_score(facts: StockFacts) -> float:
        """Score positive, persistent returns and proximity to annual highs."""
        returns = (
            facts.return_20d,
            facts.return_50d,
            facts.return_100d,
            facts.return_150d,
            facts.return_250d,
        )
        positive = sum(value > 0 for value in returns) / len(returns) * 40
        magnitude = (
            sum(
                _bounded(value / target * 100)
                for value, target in zip(returns, (0.08, 0.15, 0.25, 0.35, 0.50), strict=True)
            )
            / len(returns)
            * 0.40
        )
        proximity = _bounded(100 - facts.distance_from_52_week_high * 500) * 0.20
        return _bounded(positive + magnitude + proximity)

    @staticmethod
    def _participation_score(facts: StockFacts) -> float:
        """Score current and persistent trading-volume confirmation."""
        relative = _bounded(facts.relative_volume / 1.5 * 100)
        score = 0.65 * relative + 25 * facts.volume_expansion + 10 * (not facts.volume_contraction)
        return _bounded(score)

    @staticmethod
    def _health_score(facts: StockFacts) -> float:
        """Reward controlled volatility and penalize technical damage."""
        atr_percent = facts.atr14 / facts.close
        atr_quality = _bounded(100 - abs(atr_percent - 0.025) * 2_000)
        expansion_quality = _bounded(100 - max(0.0, facts.atr_expansion) * 200)
        gap_quality = _bounded(100 - facts.average_gap * 2_500)
        structure = 100.0 * facts.higher_lows / max(1, facts.higher_lows + facts.lower_lows)
        damage_penalty = 25 * facts.new_low + 10 * (facts.distance_above_ema200 < 0)
        return _bounded(
            0.35 * atr_quality
            + 0.25 * expansion_quality
            + 0.20 * gap_quality
            + 0.20 * structure
            - damage_penalty
        )

    @staticmethod
    def _grade(score: float) -> StockGrade:
        """Translate the overall score into a stable commercial grade."""
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
    def _reasons(
        facts: StockFacts, trend: float, momentum: float, participation: float, health: float
    ) -> tuple[str, ...]:
        """Explain the strongest evidence and material weaknesses."""
        reasons: list[str] = []
        if facts.ema_alignment:
            reasons.append("Perfect EMA alignment")
        elif facts.close < facts.ema200:
            reasons.append("Price is below EMA200")
        if trend >= 75:
            reasons.append("Strong trend persistence")
        if facts.distance_from_52_week_high <= 0.10:
            reasons.append("Near 52 Week High")
        elif facts.new_low:
            reasons.append("New 52 week low signals technical damage")
        if health >= 65:
            reasons.append("Healthy ATR")
        elif facts.atr_expansion > 0.25:
            reasons.append("ATR expansion indicates elevated risk")
        if participation >= 65:
            reasons.append("Strong participation")
        elif facts.volume_contraction:
            reasons.append("Volume participation is contracting")
        if momentum < 40:
            reasons.append("Multi-horizon momentum is weak")
        return tuple(reasons or ("Technical quality is mixed",))
