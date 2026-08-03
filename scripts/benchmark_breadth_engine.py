"""Deterministic 1,000-stock benchmark for Breadth Intelligence."""

from time import perf_counter

import numpy as np
import pandas as pd

from app.engine.breadth import BreadthEngine

STOCK_COUNT = 1_000
CEILING_SECONDS = 5.0


def build_frame() -> pd.DataFrame:
    """Build one pre-enriched frame reusable across a synthetic universe."""
    rows = 51
    close = 100 * np.cumprod(np.full(rows, 1.004))
    high = close * 1.01
    return pd.DataFrame(
        {
            "High": high,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.linspace(800_000, 1_200_000, rows),
            "EMA20": close * 0.98,
            "EMA50": close * 0.95,
            "EMA100": close * 0.90,
            "EMA200": close * 0.80,
            "High52W": np.maximum.accumulate(high),
        },
        index=pd.bdate_range("2025-01-01", periods=rows, tz="UTC"),
    )


def main() -> int:
    """Print breadth throughput and pass/fail against the five-second ceiling."""
    frame = build_frame()
    universe = {f"BENCH{index:04d}.NS": frame for index in range(STOCK_COUNT)}
    started = perf_counter()
    profile = BreadthEngine().analyze(universe)
    elapsed = perf_counter() - started
    passed = profile.facts.valid_symbols == STOCK_COUNT and elapsed < CEILING_SECONDS
    print(f"Stocks: {profile.facts.valid_symbols}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {STOCK_COUNT / elapsed:.1f}")
    print(f"5-second ceiling: {'PASS' if passed else 'FAIL'}")
    print(
        f"Example: score={profile.score:.2f}, grade={profile.grade.value}, "
        f"state={profile.breadth_state.value}, confidence={profile.confidence:.0%}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
