"""Deterministic performance benchmark for the Stock Intelligence Engine."""

from time import perf_counter

import numpy as np
import pandas as pd

from app.data.indicators import add_indicators
from app.engine.stock import StockEngine

STOCK_COUNT = 1_000
CEILING_SECONDS = 5.0
SESSION_COUNT = 320


def build_frame() -> pd.DataFrame:
    """Build realistic normalized OHLCV history without network access."""
    index = pd.bdate_range("2024-01-01", periods=SESSION_COUNT, tz="UTC")
    close = np.linspace(100.0, 180.0, SESSION_COUNT) + np.sin(np.arange(SESSION_COUNT) / 7) * 1.5
    open_price = close * (1 + np.sin(np.arange(SESSION_COUNT)) * 0.002)
    volume = np.linspace(800_000, 1_200_000, SESSION_COUNT)
    volume[-1] = 2_000_000
    return pd.DataFrame(
        {
            "Open": open_price,
            "High": np.maximum(open_price, close) * 1.01,
            "Low": np.minimum(open_price, close) * 0.99,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )


def main() -> int:
    """Profile 1,000 stocks and report throughput against the performance ceiling."""
    frame = add_indicators(build_frame())
    engine = StockEngine()
    started = perf_counter()
    profiles = [engine.analyze(f"BENCH{index:04d}.NS", frame) for index in range(STOCK_COUNT)]
    elapsed = perf_counter() - started
    throughput = STOCK_COUNT / elapsed
    passed = len(profiles) == STOCK_COUNT and elapsed < CEILING_SECONDS
    print(f"Stocks: {len(profiles)}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {throughput:.1f}")
    print(f"5-second ceiling: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
