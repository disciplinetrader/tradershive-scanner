# Risk Intelligence Engine

The Risk Intelligence Engine evaluates structural downside, objective reward, extension,
volatility, liquidity, and capital-aware position sizing. It does not emit BUY or SELL decisions.

`RiskEngine.analyze(facts, account_size=None)` uses the detected setup pivot and invalidation. When
the invalidation is absent, the known base low is the only fallback. Stops are never moved to create
a preferred R multiple. Missing entry, invalid stops, stop distances outside configured limits,
sub-2R reward, and inadequate liquidity produce a `Reject` grade.

Available R is calculated against the nearest objective resistance: the 52-week high or a measured
base objective. If neither exists, reward remains unknown and confidence is reduced. Mechanical 2R
through 5R levels are reference calculations and are not treated as available reward.

Position sizing is reusable through
`RiskEngine.position_size(account_size, risk_percent, entry_price, stop_price)`. Risk percentages
use human units such as `0.25`, quantities are rounded down to whole shares, and invalid inputs fail
explicitly. The scanner does not assume an account size, so its position-size fields remain null.

Run `python scripts/benchmark_risk_engine.py` for the deterministic 1,000-stock performance gate.
