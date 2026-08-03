"""Benchmark the complete v1.1 scanner pipeline for 500 stocks."""

import sys
from pathlib import Path
from time import perf_counter

from benchmark_setup_engine import build_frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.loader import DataLoader
from app.providers.base import MarketDataProvider
from app.scanner.scanner import Scanner
from main import build_scorer


class FixtureProvider(MarketDataProvider):
    """Return deterministic OHLCV for every symbol."""

    def __init__(self, frame):
        self._frame = frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]]

    def history(self, symbol: str, period: str):
        return self._frame.copy()


def main() -> int:
    """Run 500 stocks through data, intelligence, decision, and situation layers."""
    count = 500
    scanner = Scanner(DataLoader(FixtureProvider(build_frame())), build_scorer(), "^NSEI")
    symbols = [f"S{index}.NS" for index in range(count)]
    industries = {symbol: f"GROUP{index % 25}" for index, symbol in enumerate(symbols)}
    started = perf_counter()
    results = scanner.scan(symbols, industry_by_symbol=industries)
    elapsed = perf_counter() - started
    passed = len(results) == count and elapsed <= 60
    print(f"Stocks: {count}")
    print(f"Ranked results: {len(results)}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {count / elapsed:.1f}")
    print(f"60-second ceiling: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
