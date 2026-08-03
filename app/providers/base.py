"""Provider contracts and shared errors."""

from abc import ABC, abstractmethod

import pandas as pd


class MarketDataError(RuntimeError):
    """Raised when a provider cannot return valid market data."""


class MarketDataProvider(ABC):
    """Abstract historical market data source."""

    @abstractmethod
    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Return normalized daily OHLCV history for a symbol."""

    @property
    def cache_namespace(self) -> str:
        """Return a stable cache namespace for this provider implementation."""
        return f"{type(self).__module__}.{type(self).__qualname__}"
