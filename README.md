# TradersHIVE Scanner

TradersHIVE Scanner is an explainable momentum scanner for equities listed on India's
National Stock Exchange. It downloads adjusted daily OHLCV data, derives technical facts,
scores six independent dimensions, ranks candidates, and exports analyst-friendly Excel output.

## Architecture

The domain is isolated from external services. `app/providers/` contains replaceable market-data
adapters; `app/data/` validates bars and calculates facts; `app/features/` contains deterministic
scoring rules; `app/engine/` aggregates scores; and `app/scanner/` coordinates the workflow.
Pydantic models form validated boundaries between those layers.

Detailed normalization, retry, cache, and provider-extension behavior is documented in
[`docs/data-engine.md`](docs/data-engine.md).

## Setup

Python 3.12 is required. Create and activate a virtual environment, then install the application
and development dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Optional environment variables include `BENCHMARK_SYMBOL` (default `^NSEI`), `HISTORY_PERIOD`
(default `2y`), `LOG_LEVEL`, `REPORT_DIRECTORY`, `MARKET_DATA_CACHE_DIRECTORY`, and
`MARKET_DATA_CACHE_TTL_SECONDS`. Copy these into a local `.env` file when needed; never commit
credentials.

## Run

Start the API with `uvicorn main:app --reload`, then call:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/scan `
  -ContentType application/json -Body '{"symbols":["RELIANCE","TCS"]}'
```

Run the CLI and create a report with:

```powershell
python main.py RELIANCE TCS INFY --output reports/momentum.xlsx
```

Symbols without a suffix are normalized to Yahoo's `.NS` convention. The broad-market benchmark
is downloaded once per scan. Individual symbols with invalid or insufficient history are logged
and skipped so one bad ticker does not abort the universe.

## Quality

```powershell
python -m black --check .
python -m ruff check .
python -m pytest
python scripts/benchmark_data_engine.py
```

Scanner scores are screening signals, not investment advice. Yahoo Finance availability and data
quality should be monitored before operational or commercial use.
