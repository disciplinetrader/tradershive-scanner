"""Stable domain and scoring constants."""

from types import MappingProxyType

TRADING_DAYS_PER_YEAR = 252
MINIMUM_HISTORY_DAYS = 200
INDICATOR_WARMUP_DAYS = 260
DEFAULT_BENCHMARK = "^NSEI"
NSE_SUFFIX = ".NS"
MARKET_BENCHMARKS = MappingProxyType(
    {
        "nifty_50": "^NSEI",
        "nifty_next_50": "^NSMIDCP",
        "nifty_midcap_150": "NIFTYMIDCAP150.NS",
        "nifty_smallcap_250": "NIFTYSMLCAP250.NS",
        "bank_nifty": "^NSEBANK",
        "india_vix": "^INDIAVIX",
    }
)
FEATURE_WEIGHTS = MappingProxyType(
    {
        "market": 0.10,
        "sector": 0.15,
        "stock": 0.15,
        "setup": 0.15,
        "trend": 0.12,
        "relative_strength": 0.12,
        "momentum": 0.09,
        "volume": 0.07,
        "volatility": 0.05,
    }
)
RELATIVE_STRENGTH_PERIOD_WEIGHTS = MappingProxyType(
    {
        20: 0.10,
        50: 0.20,
        150: 0.30,
        250: 0.40,
    }
)
RELATIVE_STRENGTH_HORIZONS = (5, 10, 20, 50, 100, 150, 250)
