"""Validated market history loading service."""

import pandas as pd

from app.core.constants import MINIMUM_HISTORY_DAYS
from app.providers.base import MarketDataError, MarketDataProvider


class DataLoader:
    """Load provider data and enforce scanner input invariants."""

    def __init__(self, provider: MarketDataProvider, period: str = "2y") -> None:
        """Initialize the loader with an injected market data provider."""
        self._provider = provider
        self._period = period

    def load(self, symbol: str) -> pd.DataFrame:
        """Return validated, deduplicated, chronological OHLCV bars."""
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("Symbol must not be blank")
        frame = self._provider.history(normalized_symbol, self._period).copy()
        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required.difference(frame.columns)
        if missing:
            raise MarketDataError(f"{normalized_symbol} is missing columns: {sorted(missing)}")
        frame = frame.loc[:, sorted(required)].sort_index()
        frame = frame[~frame.index.duplicated(keep="last")]
        frame = frame.apply(pd.to_numeric, errors="coerce").dropna()
        if len(frame) < MINIMUM_HISTORY_DAYS:
            raise MarketDataError(
                f"{normalized_symbol} has {len(frame)} rows; {MINIMUM_HISTORY_DAYS} required"
            )
        if (frame[["Open", "High", "Low", "Close"]] <= 0).any().any():
            raise MarketDataError(f"{normalized_symbol} contains non-positive prices")
        if (frame["Volume"] < 0).any():
            raise MarketDataError(f"{normalized_symbol} contains negative volume")
        return frame
