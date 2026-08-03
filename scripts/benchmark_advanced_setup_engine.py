"""Benchmark 1,000 advanced setup enhancements."""

from time import perf_counter

from benchmark_setup_engine import build_frame

from app.engine.setup import SetupEngine


def main() -> int:
    frame = build_frame()
    engine = SetupEngine()
    started = perf_counter()
    profiles = [engine.analyze(f"S{i}.NS", frame) for i in range(1000)]
    elapsed = perf_counter() - started
    passed = elapsed <= 15
    print("Stocks: 1000")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {1000/elapsed:.1f}")
    print(f"15-second ceiling: {'PASS' if passed else 'FAIL'}")
    return 0 if passed and len(profiles) == 1000 else 1


if __name__ == "__main__":
    raise SystemExit(main())
