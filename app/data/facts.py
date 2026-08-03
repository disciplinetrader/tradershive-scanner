"""Facts engine converting indicator frames into validated domain facts."""

import math

import pandas as pd

from app.models.facts import Facts


def build_facts(
    symbol: str,
    frame: pd.DataFrame,
    market_trend: bool,
    benchmark_return_63d: float,
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
        market_trend=market_trend,
        ema_alignment=close > ema20 > ema50 > ema200,
        near_52_week_high=distance_from_high <= 0.10,
        distance_from_high=distance_from_high,
        gap_percent=gap_percent,
        daily_return=float(latest["DailyReturn"]),
        return_63d=float(latest["Return63D"]),
        benchmark_return_63d=benchmark_return_63d,
        annualized_volatility=float(latest["AnnualizedVolatility"]),
        history_days=len(frame),
    )
