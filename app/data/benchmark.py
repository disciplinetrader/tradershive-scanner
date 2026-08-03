"""Benchmark trend and multi-horizon return calculations."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import pandas as pd

from app.core.constants import RELATIVE_STRENGTH_HORIZONS


@dataclass(frozen=True, slots=True)
class BenchmarkSnapshot:
    """Point-in-time benchmark regime and trailing returns."""

    symbol: str
    market_trend: bool
    returns: Mapping[int, float]
    return_63d: float

    def __post_init__(self) -> None:
        """Freeze the return mapping after construction."""
        object.__setattr__(self, "returns", MappingProxyType(dict(self.returns)))


def build_benchmark_snapshot(symbol: str, frame: pd.DataFrame) -> BenchmarkSnapshot:
    """Build benchmark trend and matched-period returns from an indicator frame."""
    return_columns = {period: f"Return{period}D" for period in RELATIVE_STRENGTH_HORIZONS}
    required = {"Close", "EMA50", "EMA200", "Return63D", *return_columns.values()}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Benchmark frame is missing indicators: {sorted(missing)}")
    latest = frame.iloc[-1]
    if latest[list(required)].isna().any():
        raise ValueError("Benchmark has insufficient history for relative-strength metrics")
    trend = bool(latest["Close"] > latest["EMA200"] and latest["EMA50"] > latest["EMA200"])
    return BenchmarkSnapshot(
        symbol=symbol,
        market_trend=trend,
        returns={period: float(latest[column]) for period, column in return_columns.items()},
        return_63d=float(latest["Return63D"]),
    )


def benchmark_metrics(frame: pd.DataFrame) -> tuple[bool, float]:
    """Return legacy market-trend and 63-session metrics for compatible consumers."""
    snapshot = build_benchmark_snapshot("benchmark", frame)
    return snapshot.market_trend, snapshot.return_63d
