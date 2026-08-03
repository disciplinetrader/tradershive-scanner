"""Focused tests for canonical schemas and disk-backed loading."""

import os
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.data.cache import MarketDataCache
from app.data.loader import DataLoader
from app.data.schema import OHLCV_COLUMNS, normalize_ohlcv
from app.providers.base import MarketDataError, MarketDataProvider


class CountingProvider(MarketDataProvider):
    """Count calls while returning an intentionally non-canonical frame."""

    def __init__(self, frame: pd.DataFrame) -> None:
        """Store a response frame and initialize the call counter."""
        self.frame = frame
        self.calls = 0

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Return the response and record the provider invocation."""
        self.calls += 1
        return self.frame.copy()


def test_normalizer_handles_reversed_multi_index(rising_frame: pd.DataFrame) -> None:
    """Field names may appear in either yfinance MultiIndex level."""
    frame = rising_frame.copy()
    frame.columns = pd.MultiIndex.from_product([["TEST.NS"], frame.columns])
    frame = frame.iloc[::-1]

    result = normalize_ohlcv(frame, "TEST.NS")

    assert tuple(result.columns) == OHLCV_COLUMNS
    assert result.index.is_monotonic_increasing
    assert str(result.index.tz) == "UTC"


def test_loader_uses_fresh_disk_cache(rising_frame: pd.DataFrame, tmp_path: Path) -> None:
    """Repeated loads should avoid duplicate provider calls and return canonical data."""
    provider = CountingProvider(rising_frame.loc[:, list(reversed(OHLCV_COLUMNS))])
    cache = MarketDataCache(tmp_path / "cache", timedelta(hours=1))
    loader = DataLoader(provider, cache=cache)

    first = loader.load("TEST.NS")
    second = loader.load("TEST.NS")

    assert provider.calls == 1
    assert tuple(first.columns) == OHLCV_COLUMNS
    pd.testing.assert_frame_equal(first, second, check_freq=False)


def test_expired_cache_is_refreshed(rising_frame: pd.DataFrame, tmp_path: Path) -> None:
    """Expired entries should trigger a provider refresh."""
    provider = CountingProvider(rising_frame)
    cache_directory = tmp_path / "cache"
    cache = MarketDataCache(cache_directory, timedelta(seconds=1))
    loader = DataLoader(provider, cache=cache)
    loader.load("TEST.NS")
    cache_file = next(cache_directory.glob("*.csv"))
    os.utime(cache_file, (0, 0))

    loader.load("TEST.NS")

    assert provider.calls == 2


def test_corrupt_cache_recovers_from_provider(rising_frame: pd.DataFrame, tmp_path: Path) -> None:
    """Malformed cache entries should be treated as misses rather than fatal errors."""
    provider = CountingProvider(rising_frame)
    cache_directory = tmp_path / "cache"
    cache = MarketDataCache(cache_directory, timedelta(hours=1))
    loader = DataLoader(provider, cache=cache)
    loader.load("TEST.NS")
    next(cache_directory.glob("*.csv")).write_text("invalid", encoding="utf-8")

    result = loader.load("TEST.NS")

    assert provider.calls == 2
    assert len(result) == len(rising_frame)


def test_invalid_provider_data_is_not_cached(rising_frame: pd.DataFrame, tmp_path: Path) -> None:
    """Data that fails loader invariants must never poison the persistent cache."""
    provider = CountingProvider(rising_frame.iloc[:100])
    cache_directory = tmp_path / "cache"
    loader = DataLoader(
        provider,
        cache=MarketDataCache(cache_directory, timedelta(hours=1)),
    )

    with pytest.raises(MarketDataError, match="200 required"):
        loader.load("TEST.NS")

    assert not list(cache_directory.glob("*.csv"))
