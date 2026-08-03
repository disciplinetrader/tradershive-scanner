# Setup Intelligence Engine

The Setup Intelligence Engine detects objective swing-trading structures without producing BUY or
SELL decisions. It evaluates VCP, Tight Base, Darvas Box, Bull Flag, First Pullback, Inside Day,
NR7, and Breakout Ready independently, then selects the strongest qualifying observation.

`SetupEngine.analyze(symbol, frame, stock_profile)` returns an immutable `SetupProfile`. Shared
facts include base boundaries and depth, contraction measurements, volume dry-up, pivot and
invalidation levels, breakout distance, overhead resistance, tight closes, and range compression.
Every profile retains all eight `SetupCandidate` results for auditing.

The overall score weights pattern evidence at 35%, structure at 25%, compression and volume at 15%
each, and location at 10%. Grades follow the common TradersHIVE thresholds: A+ (90+), A (80+), B
(65+), C (50+), and D. A profile with no qualifying setup is capped below 50. Missing recent data
reduces confidence; wide, loose structures, deep bases, distribution, elevated volume, and weak
moving-average location prevent high-quality classifications.

Scanner facts and API responses expose the complete profile plus setup score, grade, type, pivot,
invalidation, and breakout distance. The CLI and Excel report surface the same headline fields.
Run `python scripts/benchmark_setup_engine.py` for the deterministic 1,000-stock performance gate.
