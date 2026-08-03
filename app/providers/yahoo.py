"""Retrying Yahoo Finance market data adapter."""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from app.data.schema import normalize_ohlcv
from app.providers.base import MarketDataError, MarketDataProvider


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential-backoff configuration."""

    attempts: int = 3
    initial_delay_seconds: float = 0.5
    maximum_delay_seconds: float = 4.0
    jitter_ratio: float = 0.1

    def __post_init__(self) -> None:
        """Reject invalid retry parameters at construction time."""
        if self.attempts < 1:
            raise ValueError("Retry attempts must be at least one")
        if self.initial_delay_seconds < 0 or self.maximum_delay_seconds < 0:
            raise ValueError("Retry delays must not be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("Retry jitter ratio must be between zero and one")


class YahooFinanceProvider(MarketDataProvider):
    """Download daily OHLCV bars from Yahoo Finance."""

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        """Configure bounded retries with injectable timing for deterministic tests."""
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleeper = sleeper
        self._random_source = random_source

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Fetch adjusted daily bars, retry transient failures, and normalize them."""
        last_error: Exception | None = None
        for attempt in range(1, self._retry_policy.attempts + 1):
            try:
                frame = yf.download(
                    symbol,
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )
                return normalize_ohlcv(frame, symbol)
            except Exception as exc:
                last_error = exc
                if attempt < self._retry_policy.attempts:
                    self._sleeper(self._delay(attempt))
        raise MarketDataError(
            f"Yahoo download failed for {symbol} after {self._retry_policy.attempts} attempts: "
            f"{last_error}"
        ) from last_error

    def _delay(self, attempt: int) -> float:
        """Calculate capped exponential delay with symmetric proportional jitter."""
        policy = self._retry_policy
        base = min(policy.maximum_delay_seconds, policy.initial_delay_seconds * 2 ** (attempt - 1))
        jitter = (self._random_source() * 2 - 1) * policy.jitter_ratio * base
        return max(0.0, base + jitter)
