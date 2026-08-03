"""Deterministic 1,000-stock benchmark for Volume Intelligence."""

from time import perf_counter

import numpy as np
import pandas as pd

from app.engine.volume import VolumeEngine

STOCK_COUNT = 1_000
CEILING_SECONDS = 5.0


def build_frame() -> pd.DataFrame:
    """Build realistic OHLCV history without network access."""
    rows = 320
    close = np.linspace(100.0, 180.0, rows) + np.sin(np.arange(rows) / 7) * 1.5
    volume = np.linspace(800_000, 1_200_000, rows)
    volume[-5:] *= np.array([0.75, 0.70, 0.65, 0.60, 1.50])
    return pd.DataFrame(
        {
            "Open": close * 0.998,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": volume,
        },
        index=pd.bdate_range("2024-01-01", periods=rows, tz="UTC"),
    )


def main() -> int:
    """Print throughput and pass/fail against the five-second ceiling."""
    engine = VolumeEngine()
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
        f"state={example.volume_state.value}, confidence={example.confidence:.0%}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
