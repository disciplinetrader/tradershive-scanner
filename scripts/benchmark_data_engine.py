"""Reproducible cold/warm benchmark for loading a 100-symbol universe."""

import argparse
import json
import tempfile
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from app.data.cache import MarketDataCache
from app.data.loader import DataLoader
from app.providers.base import MarketDataProvider


class SyntheticProvider(MarketDataProvider):
    """Deterministic provider isolating loader and cache overhead from network variance."""

    def __init__(self, rows: int = 320) -> None:
        """Precompute a representative daily OHLCV frame."""
        index = pd.bdate_range("2024-01-01", periods=rows, tz="UTC")
        close = np.linspace(100.0, 160.0, rows)
        self._frame = pd.DataFrame(
            {
                "Open": close * 0.999,
                "High": close * 1.01,
                "Low": close * 0.99,
                "Close": close,
                "Volume": np.linspace(500_000, 1_000_000, rows),
            },
            index=index,
        )

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Return a defensive copy of representative provider data."""
        return self._frame.copy()


def _timed_load(loader: DataLoader, symbols: Sequence[str]) -> float:
    """Return elapsed seconds for loading every supplied symbol."""
    started = perf_counter()
    for symbol in symbols:
        loader.load(symbol)
    return perf_counter() - started


def run_benchmark(cache_directory: Path) -> dict[str, float | int]:
    """Measure cold provider-backed and warm disk-cached loading for 100 symbols."""
    symbols = [f"BENCH{index:03}.NS" for index in range(100)]
    cache = MarketDataCache(cache_directory, timedelta(hours=1))
    loader = DataLoader(SyntheticProvider(), period="2y", cache=cache)
    cold_seconds = _timed_load(loader, symbols)
    warm_seconds = _timed_load(loader, symbols)
    return {
        "symbols": len(symbols),
        "rows_per_symbol": 320,
        "cold_seconds": round(cold_seconds, 6),
        "warm_seconds": round(warm_seconds, 6),
        "warm_symbols_per_second": round(len(symbols) / warm_seconds, 2),
        "cache_speedup": round(cold_seconds / warm_seconds, 2),
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the benchmark and print machine-readable JSON results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-directory", type=Path)
    parsed = parser.parse_args(arguments)
    if parsed.cache_directory:
        results = run_benchmark(parsed.cache_directory)
    else:
        with tempfile.TemporaryDirectory(prefix="tradershive-benchmark-") as directory:
            results = run_benchmark(Path(directory))
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
