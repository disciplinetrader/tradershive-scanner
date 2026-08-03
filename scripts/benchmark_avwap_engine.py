"""Benchmark AVWAP analysis for a 1,000-stock universe."""

from time import perf_counter

import numpy as np
import pandas as pd

from app.engine.avwap import AVWAPEngine


def main() -> int:
    """Run the deterministic benchmark and report its five-second gate."""
    rows = 320
    close = np.linspace(100, 180, rows)
    frame = pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(rows, 1_000_000.0),
        },
        index=pd.bdate_range("2024-01-01", periods=rows, tz="UTC"),
    )
    engine = AVWAPEngine()
    engine.analyze("WARMUP", frame)
    started = perf_counter()
    for number in range(1_000):
        engine.analyze(f"S{number}.NS", frame)
    elapsed = perf_counter() - started
    passed = elapsed <= 5.0
    print("Stocks: 1000")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {1000 / elapsed:.1f}")
    print(f"5-second ceiling: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
