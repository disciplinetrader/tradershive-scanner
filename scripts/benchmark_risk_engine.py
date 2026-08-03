"""Deterministic 1,000-stock benchmark for the Risk Intelligence Engine."""

from time import perf_counter

import numpy as np
import pandas as pd

from app.data.benchmark import build_benchmark_snapshot
from app.data.facts import build_facts
from app.data.indicators import add_indicators
from app.engine.risk import RiskEngine
from app.engine.setup import SetupEngine
from app.engine.stock import StockEngine

STOCK_COUNT = 1_000
CEILING_SECONDS = 5.0


def build_facts_fixture():
    """Build complete production models from deterministic OHLCV history."""
    rows = 320
    index = pd.bdate_range("2024-01-01", periods=rows, tz="UTC")
    close = np.linspace(100.0, 180.0, rows)
    frame = add_indicators(
        pd.DataFrame(
            {
                "Open": close * 0.999,
                "High": close * 1.01,
                "Low": close * 0.99,
                "Close": close,
                "Volume": np.full(rows, 1_500_000),
            },
            index=index,
        )
    )
    stock = StockEngine().analyze("BENCH.NS", frame)
    setup = SetupEngine().analyze("BENCH.NS", frame, stock)
    benchmark = build_benchmark_snapshot("^NSEI", frame)
    return build_facts(
        "BENCH.NS",
        frame,
        benchmark,
        stock_profile=stock,
        setup_profile=setup,
    )


def main() -> int:
    """Run the benchmark and print throughput against the five-second ceiling."""
    facts = build_facts_fixture()
    engine = RiskEngine()
    started = perf_counter()
    profiles = [engine.analyze(facts) for _ in range(STOCK_COUNT)]
    elapsed = perf_counter() - started
    throughput = STOCK_COUNT / elapsed
    passed = len(profiles) == STOCK_COUNT and elapsed < CEILING_SECONDS
    print(f"Stocks: {len(profiles)}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {throughput:.1f}")
    print(f"5-second ceiling: {'PASS' if passed else 'FAIL'}")
    example = profiles[0]
    print(
        "Example profile: "
        f"grade={example.grade.value}, score={example.score:.2f}, "
        f"entry={example.facts.entry_price}, stop={example.facts.stop_price}, "
        f"available_r={example.facts.available_r_multiple}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
