"""Deterministic 1,000-stock benchmark for the Setup Intelligence Engine."""

from time import perf_counter

import numpy as np
import pandas as pd

from app.data.indicators import add_indicators
from app.engine.setup import SetupEngine

STOCK_COUNT = 1_000
CEILING_SECONDS = 5.0


def build_frame() -> pd.DataFrame:
    """Build an enriched breakout-ready history without network access."""
    rows = 320
    index = pd.bdate_range("2024-01-01", periods=rows, tz="UTC")
    close = np.linspace(100.0, 170.0, rows)
    close[-20:] = 169.0 + np.sin(np.arange(20)) * 0.35 + np.linspace(-0.4, 0.4, 20)
    ranges = np.full(rows, 0.02)
    ranges[-20:] = 0.012
    volume = np.linspace(900_000, 700_000, rows)
    volume[-20:] = np.linspace(600_000, 350_000, 20)
    return add_indicators(
        pd.DataFrame(
            {
                "Open": close * 0.999,
                "High": close * (1 + ranges / 2),
                "Low": close * (1 - ranges / 2),
                "Close": close,
                "Volume": volume,
            },
            index=index,
        )
    )


def main() -> int:
    """Run the benchmark and print throughput against the five-second ceiling."""
    frame = build_frame()
    engine = SetupEngine()
    started = perf_counter()
    profiles = [engine.analyze(f"BENCH{index:04d}.NS", frame) for index in range(STOCK_COUNT)]
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
        f"type={example.best_setup_type.value}, score={example.score:.2f}, "
        f"confidence={example.confidence:.2f}, grade={example.grade.value}, "
        f"pivot={example.facts.pivot_price:.2f}, "
        f"invalidation={example.facts.invalidation_price:.2f}, "
        f"breakout_distance={example.facts.breakout_distance_percent:.2f}%"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
