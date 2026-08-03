"""Stable domain and scoring constants."""

from types import MappingProxyType

TRADING_DAYS_PER_YEAR = 252
MINIMUM_HISTORY_DAYS = 200
INDICATOR_WARMUP_DAYS = 260
DEFAULT_BENCHMARK = "^NSEI"
NSE_SUFFIX = ".NS"
FEATURE_WEIGHTS = MappingProxyType(
    {
        "market": 0.10,
        "trend": 0.25,
        "relative_strength": 0.20,
        "momentum": 0.20,
        "volume": 0.15,
        "volatility": 0.10,
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
