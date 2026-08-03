# Decision Intelligence Engine

The Decision Intelligence Engine combines existing Market, Sector, Relative Strength, Stock,
Setup, and Risk profiles. It does not calculate indicators or rerun subordinate engines.

Each market regime selects a validated `DecisionWeights` configuration from `app/core/config.py`.
Bull regimes distribute influence across leadership and stock quality. Range markets increase
market, setup, and risk influence. Bear and capitulation regimes emphasize market and sector
conditions, making otherwise strong isolated stocks less actionable. Every configuration sums to
one and can be replaced when constructing `DecisionEngine`.

The weighted score is independent from confidence. Confidence is the similarly weighted coverage
of the six input profiles, so missing intelligence cannot appear as conviction. Hard gates then
map the assessment to `BUY`, `WATCHLIST`, or `AVOID`: hostile regimes, weak structure, lagging
sectors, and rejected risk prevent BUY regardless of the aggregate score.

Scanner output retains the legacy feature score for compatibility but ranks by decision score.
API, CLI, and Excel output expose the action, trade grade, confidence, reasons, warnings, and full
weight breakdown. Run `python scripts/benchmark_decision_engine.py` for the 1,000-stock benchmark.
