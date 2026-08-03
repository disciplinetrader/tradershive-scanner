# Data Engine

The TradersHIVE data engine provides one deterministic boundary between external market-data
services and scanner calculations. Consumers depend on `MarketDataProvider`, never directly on
Yahoo Finance or `yfinance`.

## Data flow

```text
DataLoader -> MarketDataCache -> MarketDataProvider -> normalize_ohlcv -> validation
```

`DataLoader.load(symbol)` checks the optional disk cache, calls its provider on a miss, normalizes
the response again at the application boundary, validates market invariants, stores an atomic cache
entry, and returns a defensive DataFrame. Double normalization is intentional: alternate providers
cannot bypass the canonical contract.

## Canonical schema

Every result has exactly these columns in order:

```text
Open, High, Low, Close, Volume
```

The index is a sorted, unique, UTC `DatetimeIndex` named `Date`. Column matching is
case-insensitive. Invalid dates and incomplete/non-numeric rows are removed. MultiIndex responses
are supported whether the OHLCV field names occupy the first or second level; ambiguous or
multi-symbol responses fail explicitly.

At least 200 valid sessions are required. Prices must be positive and volume must be non-negative.

## Reliability

`YahooFinanceProvider` defaults to three attempts with exponential delays of 0.5 and 1 second,
10% symmetric jitter, and a four-second cap. Retry timing is injectable for deterministic tests.
An exhausted operation raises `MarketDataError` with its symbol, attempt count, and final cause.

The disk cache uses SHA-256 keys derived from provider namespace, symbol, and period. CSV makes
entries portable and inspectable. Writes use a same-directory temporary file followed by atomic
replacement. Cache corruption becomes a miss, never a scanner outage. Production defaults to
`.cache/market-data` with a six-hour TTL, configurable through:

- `MARKET_DATA_CACHE_DIRECTORY`
- `MARKET_DATA_CACHE_TTL_SECONDS` (60 seconds to seven days)

## Extension example

```python
class LicensedProvider(MarketDataProvider):
    def history(self, symbol: str, period: str) -> pd.DataFrame:
        return vendor_client.daily_bars(symbol=symbol, period=period)
```

No loader changes are required. The shared normalizer enforces the same output contract.

## Verification and benchmark

```powershell
python -m pytest tests/test_data.py tests/test_data_engine.py tests/test_provider.py
python scripts/benchmark_data_engine.py
```

The benchmark loads 100 symbols with 320 sessions each twice: a cold provider-backed pass and a
warm disk-cache pass. It uses synthetic deterministic bars so results measure engine overhead rather
than internet latency or Yahoo rate limits. Output is JSON and includes throughput and cache speedup.

