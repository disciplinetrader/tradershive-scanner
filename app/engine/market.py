"""Multi-index market quality, breadth, and volatility engine."""

from collections.abc import Mapping

import numpy as np
import pandas as pd

from app.core.constants import MARKET_BENCHMARKS
from app.core.logging import get_logger
from app.data.indicators import add_indicators
from app.data.loader import DataLoader
from app.models.market import (
    MarketBreadth,
    MarketFacts,
    MarketProfile,
    MarketRegime,
    MarketVolatility,
)

logger = get_logger(__name__)


def calculate_market_facts(name: str, symbol: str, frame: pd.DataFrame) -> MarketFacts:
    """Derive technical quality facts for one benchmark history."""
    enriched = frame if "EMA200" in frame.columns else add_indicators(frame)
    latest = enriched.iloc[-1]
    required = [
        "Close",
        "EMA20",
        "EMA50",
        "EMA200",
        "Return20D",
        "Return50D",
        "Return150D",
        "Return250D",
        "ATR14",
        "High52W",
        "Low52W",
        "AverageVolume",
        "Volume",
    ]
    if latest[required].isna().any():
        raise ValueError(f"{symbol} has insufficient history for market facts")
    close = float(latest["Close"])
    high_52_week = float(latest["High52W"])
    average_volume = float(latest["AverageVolume"])
    prior_high = float(enriched["High"].iloc[-253:-1].max())
    prior_low = float(enriched["Low"].iloc[-253:-1].min())
    return MarketFacts(
        name=name,
        symbol=symbol,
        close=close,
        ema20=float(latest["EMA20"]),
        ema50=float(latest["EMA50"]),
        ema200=float(latest["EMA200"]),
        return_20d=float(latest["Return20D"]),
        return_50d=float(latest["Return50D"]),
        return_150d=float(latest["Return150D"]),
        return_250d=float(latest["Return250D"]),
        atr14=float(latest["ATR14"]),
        relative_volume=float(latest["Volume"]) / average_volume if average_volume > 0 else 0,
        distance_from_52_week_high=max(0, (high_52_week - close) / high_52_week),
        new_high=bool(float(latest["High"]) >= prior_high),
        new_low=bool(float(latest["Low"]) <= prior_low),
        above_ema20=bool(close > latest["EMA20"]),
        above_ema50=bool(close > latest["EMA50"]),
        above_ema200=bool(close > latest["EMA200"]),
    )


def calculate_breadth(frames: Mapping[str, pd.DataFrame]) -> MarketBreadth:
    """Calculate participation metrics from valid stock histories."""
    observations: list[tuple[bool, bool, bool, bool, bool, bool, bool]] = []
    for frame in frames.values():
        try:
            enriched = frame if "EMA200" in frame.columns else add_indicators(frame)
            latest = enriched.iloc[-1]
            previous = enriched.iloc[-2]
            required = latest[["Close", "EMA20", "EMA50", "EMA200", "High52W", "Low52W"]]
            if required.isna().any():
                continue
            close = float(latest["Close"])
            observations.append(
                (
                    close > float(previous["Close"]),
                    close < float(previous["Close"]),
                    close > float(latest["EMA20"]),
                    close > float(latest["EMA50"]),
                    close > float(latest["EMA200"]),
                    float(latest["High"]) >= float(enriched["High"].iloc[-253:-1].max()),
                    float(latest["Low"]) <= float(enriched["Low"].iloc[-253:-1].min()),
                )
            )
        except (KeyError, ValueError, IndexError):
            continue
    size = len(observations)
    if size == 0:
        return MarketBreadth(
            universe_size=0,
            advancers=0,
            decliners=0,
            unchanged=0,
            advance_decline_ratio=0,
            percentage_above_ema20=0,
            percentage_above_ema50=0,
            percentage_above_ema200=0,
            new_highs=0,
            new_lows=0,
        )
    advancers = sum(observation[0] for observation in observations)
    decliners = sum(observation[1] for observation in observations)
    new_highs = sum(observation[5] for observation in observations)
    new_lows = sum(observation[6] for observation in observations)
    return MarketBreadth(
        universe_size=size,
        advancers=advancers,
        decliners=decliners,
        unchanged=size - advancers - decliners,
        advance_decline_ratio=advancers / decliners if decliners else float(advancers),
        percentage_above_ema20=sum(item[2] for item in observations) / size * 100,
        percentage_above_ema50=sum(item[3] for item in observations) / size * 100,
        percentage_above_ema200=sum(item[4] for item in observations) / size * 100,
        new_highs=new_highs,
        new_lows=new_lows,
    )


class MarketEngine:
    """Build a resilient market profile from indexes, breadth, and volatility."""

    def __init__(self, loader: DataLoader) -> None:
        """Initialize the engine with the existing provider-independent loader."""
        self._loader = loader

    def analyze(self, universe_frames: Mapping[str, pd.DataFrame]) -> MarketProfile:
        """Return the current multi-dimensional market regime profile."""
        index_facts: dict[str, MarketFacts] = {}
        index_frames: dict[str, pd.DataFrame] = {}
        vix_value: float | None = None
        for name, symbol in MARKET_BENCHMARKS.items():
            try:
                frame = add_indicators(self._loader.load(symbol))
                if name == "india_vix":
                    vix_value = float(frame["Close"].iloc[-1])
                else:
                    index_frames[name] = frame
                    index_facts[name] = calculate_market_facts(name, symbol, frame)
            except (ValueError, RuntimeError) as exc:
                logger.warning("Market benchmark %s unavailable: %s", symbol, exc)
        if not index_facts:
            raise RuntimeError("No equity benchmark data available for market analysis")

        breadth = calculate_breadth(universe_frames)
        volatility = self._calculate_volatility(index_frames, vix_value)
        score = self._score(index_facts, breadth, volatility)
        state = self._classify(score, breadth, volatility)
        confidence = self._confidence(index_facts, breadth, vix_value)
        reasons = self._reasons(index_facts, breadth, volatility, state)
        profile = MarketProfile(
            score=round(score, 2),
            confidence=round(confidence, 2),
            state=state,
            reasons=reasons,
            indexes=index_facts,
            breadth=breadth,
            volatility=volatility,
        )
        from app.engine.advanced_market import AdvancedMarketEngine

        return AdvancedMarketEngine().enhance(profile, index_frames)

    @staticmethod
    def _calculate_volatility(
        frames: Mapping[str, pd.DataFrame], vix_value: float | None
    ) -> MarketVolatility:
        """Aggregate ATR expansion and significant opening-gap frequency."""
        atr_expansions: list[float] = []
        gaps: list[float] = []
        for frame in frames.values():
            atr_average = float(frame["ATR14"].iloc[-21:-1].mean())
            if atr_average > 0:
                atr_expansions.append(float(frame["ATR14"].iloc[-1]) / atr_average - 1)
            recent = frame.iloc[-20:]
            gap = (recent["Open"] / frame["Close"].shift(1).loc[recent.index] - 1).abs()
            gaps.extend((gap >= 0.01).dropna().astype(float).tolist())
        return MarketVolatility(
            india_vix=vix_value,
            atr_expansion=float(np.mean(atr_expansions)) if atr_expansions else 0,
            gap_frequency=float(np.mean(gaps)) if gaps else 0,
        )

    @staticmethod
    def _score(
        indexes: Mapping[str, MarketFacts],
        breadth: MarketBreadth,
        volatility: MarketVolatility,
    ) -> float:
        """Combine index quality, participation, and volatility into zero-to-100 quality."""
        index_scores = []
        for facts in indexes.values():
            index_scores.append(
                20 * facts.above_ema20
                + 20 * facts.above_ema50
                + 30 * facts.above_ema200
                + 10 * (facts.return_50d > 0)
                + 10 * (facts.return_150d > 0)
                + 10 * (facts.distance_from_52_week_high <= 0.10)
            )
        index_score = float(np.mean(index_scores))
        directional = breadth.advancers + breadth.decliners
        advance_share = breadth.advancers / directional * 100 if directional else 50
        breadth_score = (
            0.20 * breadth.percentage_above_ema20
            + 0.30 * breadth.percentage_above_ema50
            + 0.35 * breadth.percentage_above_ema200
            + 0.15 * advance_share
        )
        vix_score = MarketEngine._vix_score(volatility.india_vix)
        atr_score = max(0.0, min(100.0, 80.0 - volatility.atr_expansion * 200))
        gap_score = max(0.0, min(100.0, 100.0 - volatility.gap_frequency * 250))
        volatility_score = (vix_score + atr_score + gap_score) / 3
        return max(
            0.0, min(100.0, 0.45 * index_score + 0.35 * breadth_score + 0.20 * volatility_score)
        )

    @staticmethod
    def _vix_score(vix: float | None) -> float:
        """Map India VIX to a monotonic market-quality score."""
        if vix is None:
            return 50
        if vix <= 15:
            return 100
        if vix <= 20:
            return 75
        if vix <= 25:
            return 50
        if vix <= 30:
            return 25
        return 0

    @staticmethod
    def _classify(
        score: float, breadth: MarketBreadth, volatility: MarketVolatility
    ) -> MarketRegime:
        """Classify quality while explicitly detecting capitulation and recovery."""
        directional = breadth.advancers + breadth.decliners
        decline_share = breadth.decliners / directional if directional else 0
        advance_share = breadth.advancers / directional if directional else 0
        if (
            volatility.india_vix is not None
            and volatility.india_vix >= 30
            and decline_share >= 0.75
            and breadth.new_lows > max(2, breadth.new_highs * 3)
        ):
            return MarketRegime.CAPITULATION
        if (
            breadth.percentage_above_ema20 >= 60
            and breadth.percentage_above_ema200 < 50
            and advance_share >= 0.60
            and score >= 40
        ):
            return MarketRegime.RECOVERY
        if score >= 80:
            return MarketRegime.HEALTHY_BULL
        if score >= 67:
            return MarketRegime.BULL
        if score >= 56:
            return MarketRegime.WEAK_BULL
        if score >= 44:
            return MarketRegime.RANGE
        if score >= 33:
            return MarketRegime.WEAK_BEAR
        if score >= 20:
            return MarketRegime.BEAR
        return MarketRegime.CAPITULATION

    @staticmethod
    def _confidence(
        indexes: Mapping[str, MarketFacts], breadth: MarketBreadth, vix: float | None
    ) -> float:
        """Quantify coverage across requested indexes, VIX, and breadth."""
        index_coverage = min(1.0, len(indexes) / 5)
        breadth_coverage = min(1.0, breadth.universe_size / 50)
        return 0.50 * index_coverage + 0.35 * breadth_coverage + 0.15 * (vix is not None)

    @staticmethod
    def _reasons(
        indexes: Mapping[str, MarketFacts],
        breadth: MarketBreadth,
        volatility: MarketVolatility,
        state: MarketRegime,
    ) -> tuple[str, ...]:
        """Generate concise evidence specific to current market conditions."""
        reasons: list[str] = []
        above_200 = sum(facts.above_ema200 for facts in indexes.values())
        if above_200 / len(indexes) >= 0.8:
            reasons.append("Indexes above EMA200")
        else:
            reasons.append(f"{above_200} of {len(indexes)} indexes are above EMA200")
        if breadth.percentage_above_ema50 >= 65 and breadth.advancers > breadth.decliners:
            reasons.extend(("Strong breadth", "Broad participation"))
        elif breadth.advancers < breadth.decliners:
            reasons.append("Decliners exceed advancers")
        else:
            reasons.append("Breadth is mixed")
        if volatility.india_vix is None:
            reasons.append("India VIX unavailable; confidence reduced")
        elif volatility.india_vix <= 15:
            reasons.append("Low VIX")
        elif volatility.india_vix >= 25:
            reasons.append("Elevated India VIX")
        if state == MarketRegime.RECOVERY:
            reasons.append("Short-term participation is recovering ahead of long-term breadth")
        elif state == MarketRegime.CAPITULATION:
            reasons.append("Selling pressure and volatility indicate capitulation")
        return tuple(reasons)
