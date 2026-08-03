"""Benchmark trend and return calculations."""

import pandas as pd


def benchmark_metrics(frame: pd.DataFrame) -> tuple[bool, float]:
    """Return benchmark uptrend status and trailing 63-session return."""
    if "EMA50" not in frame or "EMA200" not in frame or "Return63D" not in frame:
        raise ValueError("Benchmark frame must contain calculated indicators")
    latest = frame.iloc[-1]
    values = latest[["Close", "EMA50", "EMA200", "Return63D"]]
    if values.isna().any():
        raise ValueError("Benchmark has insufficient history for trend metrics")
    trend = bool(latest["Close"] > latest["EMA200"] and latest["EMA50"] > latest["EMA200"])
    return trend, float(latest["Return63D"])
