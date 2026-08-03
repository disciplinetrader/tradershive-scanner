# Historical Validation Engine

The validation subsystem measures whether archived TradersHIVE rankings and decisions preceded
favorable price outcomes. It does not optimize weights or recalculate scoring rules.

## Look-ahead prevention

`HistoricalReplayService` creates a new scanner for every scan date and supplies copies of OHLCV
frames truncated at that date. Forward bars are passed only to `ForwardOutcomeEvaluator`, after
the scanner has produced immutable `HistoricalCandidate` snapshots. Duplicate scan dates are
rejected. Point-in-time universe mappings should be supplied through `universe_by_date`; otherwise
the report records survivorship-bias risk.

## Entry and exit assumptions

Configure next-session open, next-session close, pivot-trigger, or the objective RiskProfile entry.
Trigger entries occur only if a later daily high reaches the trigger. Stops come from the historical
RiskProfile snapshot. Targets support 2R through 5R and time exits support 5, 10, 20, or 40 sessions.

Daily candles cannot reveal whether a stop or target traded first. The default conservative policy
records the stop first and flags the ambiguity. Target-first and flag-only policies are available
for sensitivity analysis; none invent intraday sequencing.

## Interpreting results

Expectancy is average realized R per triggered trade. Profit factor divides gross winning R by
gross losing R. Maximum drawdown is the largest peak-to-trough decline in the sequential R curve;
it is not a portfolio simulation. Compare score buckets and Top-N cohorts to determine whether
higher scanner ranks show monotonic predictive value.

Historical results can be distorted by current-constituent universes, omitted delisted stocks,
corporate-action errors, missing sector history, or insufficient warm-up. Review the data-quality
score and warnings before drawing conclusions.

Generate outputs from a validated JSON ledger:

```powershell
python -m app.validation trade-ledger.json --output validation-output
```
