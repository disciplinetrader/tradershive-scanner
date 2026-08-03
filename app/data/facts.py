"""Facts engine converting indicator frames into validated domain facts."""

import math

import pandas as pd

from app.core.constants import RELATIVE_STRENGTH_HORIZONS
from app.data.benchmark import BenchmarkSnapshot
from app.models.facts import Facts
from app.models.market import MarketProfile, MarketRegime
from app.models.relative_strength import RelativeStrengthHorizon, RelativeStrengthProfile


def build_facts(
    symbol: str,
    frame: pd.DataFrame,
    benchmark: BenchmarkSnapshot,
    market_profile: MarketProfile | None = None,
) -> Facts:
    """Build immutable facts from the latest complete indicator row."""
    required = {
        "Open",
        "Close",
        "Volume",
        "EMA20",
        "EMA50",
        "EMA200",
        "ATR14",
        "High52W",
        "Low52W",
        "AverageVolume",
        "DailyReturn",
        "Return63D",
        "AnnualizedVolatility",
    }
    required.update(f"Return{period}D" for period in RELATIVE_STRENGTH_HORIZONS)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Indicator frame is missing columns: {sorted(missing)}")
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]
    if latest[list(required)].isna().any():
        raise ValueError(f"{symbol} has insufficient history for complete facts")

    close = float(latest["Close"])
    high_52_week = float(latest["High52W"])
    average_volume = float(latest["AverageVolume"])
    distance_from_high = max(0.0, (high_52_week - close) / high_52_week)
    previous_close = float(previous["Close"])
    gap_percent = (float(latest["Open"]) / previous_close - 1.0) if previous_close else 0.0
    volume_ratio = float(latest["Volume"]) / average_volume if average_volume else 0.0
    numbers = [close, high_52_week, average_volume, volume_ratio, gap_percent]
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError(f"{symbol} produced non-finite facts")

    ema20 = float(latest["EMA20"])
    ema50 = float(latest["EMA50"])
    ema200 = float(latest["EMA200"])
    relative_returns = {
        period: float(latest[f"Return{period}D"]) - benchmark.returns[period]
        for period in RELATIVE_STRENGTH_HORIZONS
    }
    rs_profile = RelativeStrengthProfile(
        **{
            f"rs{period}": RelativeStrengthHorizon(relative_return=relative_returns[period])
            for period in RELATIVE_STRENGTH_HORIZONS
        }
    )
    market_score = (
        market_profile.score if market_profile else (100.0 if benchmark.market_trend else 20.0)
    )
    market_confidence = market_profile.confidence if market_profile else 0.5
    market_state = (
        market_profile.state
        if market_profile
        else (MarketRegime.BULL if benchmark.market_trend else MarketRegime.BEAR)
    )
    market_reasons = (
        market_profile.reasons
        if market_profile
        else ("Market profile unavailable; using primary benchmark trend",)
    )
    return Facts(
        symbol=symbol.upper(),
        close=close,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        atr14=float(latest["ATR14"]),
        high_52_week=high_52_week,
        low_52_week=float(latest["Low52W"]),
        average_volume=average_volume,
        volume_ratio=volume_ratio,
        market_trend=benchmark.market_trend,
        market_score=market_score,
        market_confidence=market_confidence,
        market_state=market_state,
        market_reasons=market_reasons,
        ema_alignment=close > ema20 > ema50 > ema200,
        near_52_week_high=distance_from_high <= 0.10,
        distance_from_high=distance_from_high,
        gap_percent=gap_percent,
        daily_return=float(latest["DailyReturn"]),
        return_63d=float(latest["Return63D"]),
        benchmark_return_63d=benchmark.return_63d,
        rs5=relative_returns[5],
        rs10=relative_returns[10],
        rs20=relative_returns[20],
        rs50=relative_returns[50],
        rs100=relative_returns[100],
        rs150=relative_returns[150],
        rs250=relative_returns[250],
        relative_strength_score=50,
        rs_profile=rs_profile,
        annualized_volatility=float(latest["AnnualizedVolatility"]),
        history_days=len(frame),
    )
