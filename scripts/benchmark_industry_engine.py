"""Benchmark industry aggregation for 1,000 stocks."""

from time import perf_counter

from benchmark_setup_engine import build_frame

from app.data.benchmark import BenchmarkSnapshot
from app.engine.industry import IndustryGroupEngine


def main() -> int:
    frame = build_frame()
    frames = {f"S{i}.NS": frame for i in range(1000)}
    mapping = {symbol: f"GROUP{i%50}" for i, symbol in enumerate(frames)}
    benchmark = BenchmarkSnapshot(
        "^NSEI", True, {5: 0, 10: 0, 20: 0.01, 50: 0.02, 100: 0.03, 150: 0.04, 250: 0.05}, 0.02
    )
    started = perf_counter()
    result = IndustryGroupEngine().analyze(frames, benchmark, mapping)
    elapsed = perf_counter() - started
    passed = elapsed <= 5
    print("Stocks: 1000")
    print(f"Industry groups: {len(result.groups)}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {1000/elapsed:.1f}")
    print(f"5-second ceiling: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
