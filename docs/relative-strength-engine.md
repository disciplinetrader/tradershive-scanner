# Relative Strength Engine

TradersHIVE Relative Strength measures price leadership against a market benchmark. It is not the
Relative Strength Index (RSI) and does not use overbought or oversold oscillators.

## Calculation

For each stock and benchmark, the engine calculates close-to-close returns over 5, 10, 20, 50,
100, 150, and 250 trading sessions. Each stock return is converted to an excess return:

```text
relative return = stock return - benchmark return
```

The complete set is exposed as an `RS Profile`. The default ranking signal is:

```text
(RS20 × 10%) + (RS50 × 20%) + (RS150 × 30%) + (RS250 × 40%)
```

The longer periods intentionally dominate the ranking, consistent with O'Neil/Minervini-style price
leadership. The weighted value is not converted using fixed return thresholds or market-regime
min/max values. It is ranked against the current scan universe.

## Universe percentile

After every valid symbol has calculated its profile, the scanner calculates a cross-sectional
percentile for the weighted signal and for every individual horizon. The weighted percentile is the
final RS score: top 1% is 99, top 5% is approximately 95, and the median is approximately 50.

The weakest result receives 0 and the strongest receives 99. Ties receive the average of
their occupied percentile positions. A one-stock universe receives 100 by definition. The scanner
then recalculates its weighted total so the Relative Strength feature contributes this percentile,
not an absolute-return normalization.

## Benchmark resilience

The scanner first requests the configured `BENCHMARK_SYMBOL`. If that request or its indicator
calculation fails, it retries the benchmark stage with NIFTY 50 (`^NSEI`) through the existing data
loader and provider stack. Scanning stops with a contextual error only if neither benchmark is
available.

At least 251 valid trading sessions are needed to calculate a 250-session return. Symbols without
sufficient complete history are logged and skipped by the scanner.

## Output

`Facts` contains `rs5`, `rs10`, `rs20`, `rs50`, `rs100`, `rs150`, `rs250`,
`relative_strength_score`, `relative_strength_percentile`, and a typed `rs_profile`. Each profile
horizon carries both excess return and universe percentile for future Decision Engine consumers.
The Excel report surfaces the following leading columns:

```text
Rank | Symbol | Score | RS | Percentile | Trend | Volume
```

Run the focused tests with:

```powershell
python -m pytest tests/test_relative_strength.py tests/test_scanner_report.py
```
