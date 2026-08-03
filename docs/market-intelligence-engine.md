# Market Intelligence Engine

The Market Intelligence Engine evaluates market quality rather than emitting a binary bull/bear
flag. It combines index structure, stock participation, and volatility into a zero-to-100 score,
confidence, one of eight regimes, and concise evidence.

## Inputs

The engine uses the existing provider-independent `DataLoader` for NIFTY 50, NIFTY NEXT 50,
NIFTY MIDCAP 150, NIFTY SMALLCAP 250, BANK NIFTY, and India VIX. Secondary-index or VIX failures
reduce confidence but do not prevent analysis when at least one equity benchmark remains valid.

Each equity index contributes EMA20/50/200, 20/50/150/250-session returns, ATR14, relative volume,
distance from its 52-week high, and new-high/new-low status.

## Breadth and volatility

Breadth is calculated from the valid scanned universe and includes advancers, decliners, unchanged
stocks, advance/decline ratio, percentages above EMA20/50/200, and new highs/lows. Volatility uses
India VIX, average index ATR expansion versus its prior 20 sessions, and the frequency of opening
gaps of at least 1% during the latest 20 sessions.

The quality score weights index structure at 45%, breadth at 35%, and volatility at 20%. Confidence
tracks coverage of the five equity indexes, India VIX, and at least 50 breadth constituents.

## Regimes

The supported states are `Healthy Bull`, `Bull`, `Weak Bull`, `Range`, `Weak Bear`, `Bear`,
`Capitulation`, and `Recovery`. Capitulation requires severe volatility, downside breadth, and new
lows. Recovery identifies improving short-term participation while long-term breadth remains below
50%. Remaining states follow documented quality-score bands.

## Usage

```python
engine = MarketEngine(loader)
profile = engine.analyze(symbol_to_ohlcv_frame)
print(profile.state, profile.score, profile.confidence)
```

`MarketFeature` projects the profile's score, confidence, state, and reasons into every scanner
result. The full profile remains available from `MarketEngine` for future decision modules.

Run focused verification with:

```powershell
python -m pytest tests/test_market_engine.py
```

