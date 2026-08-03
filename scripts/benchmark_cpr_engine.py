"""Deterministic 1,000-stock benchmark for CPR Intelligence."""

from time import perf_counter

import numpy as np
import pandas as pd

from app.engine.cpr import CPREngine

STOCK_COUNT = 1_000
CEILING_SECONDS = 5.0


def build_frame() -> pd.DataFrame:
    """Build realistic normalized daily history without network access."""
    rows = 320
    close = np.linspace(100.0, 180.0, rows) + np.sin(np.arange(rows) / 9)
    return pd.DataFrame(
        {
            "Open": close * 0.998,
            "High": close * 1.012,
            "Low": close * 0.988,
            "Close": close,
            "Volume": np.linspace(800_000, 1_200_000, rows),
        },
        index=pd.bdate_range("2024-01-01", periods=rows, tz="UTC"),
    )


def main() -> int:
    """Print throughput and pass/fail against the five-second ceiling."""
    engine = CPREngine()
    frame = build_frame()
    started = perf_counter()
    profiles = [engine.analyze(f"BENCH{index:04d}.NS", frame) for index in range(STOCK_COUNT)]
    elapsed = perf_counter() - started
    passed = len(profiles) == STOCK_COUNT and elapsed < CEILING_SECONDS
    print(f"Stocks: {len(profiles)}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {STOCK_COUNT / elapsed:.1f}")
    print(f"5-second ceiling: {'PASS' if passed else 'FAIL'}")
    example = profiles[0]
    print(
        f"Example: score={example.score:.2f}, grade={example.grade.value}, "
        f"state={example.cpr_state.value}, breakout={example.breakout_probability:.1f}%"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
