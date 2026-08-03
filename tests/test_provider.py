"""Tests for Yahoo provider response normalization and failures."""

import pandas as pd
import pytest

from app.providers.base import MarketDataError
from app.providers.yahoo import RetryPolicy, YahooFinanceProvider


def test_yahoo_provider_normalizes_multi_index(
    monkeypatch: pytest.MonkeyPatch, rising_frame: pd.DataFrame
) -> None:
    """Single-ticker yfinance multi-index output should become canonical OHLCV."""
    response = rising_frame.copy()
    response.columns = pd.MultiIndex.from_product([response.columns, ["TEST.NS"]])
    monkeypatch.setattr("app.providers.yahoo.yf.download", lambda *args, **kwargs: response)

    result = YahooFinanceProvider().history("TEST.NS", "2y")

    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(result.index, pd.DatetimeIndex)
    assert result.index.tz is not None


def test_yahoo_provider_rejects_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty upstream responses should carry symbol-specific context."""
    monkeypatch.setattr("app.providers.yahoo.yf.download", lambda *args, **kwargs: pd.DataFrame())
    provider = YahooFinanceProvider(RetryPolicy(attempts=1))
    with pytest.raises(MarketDataError, match=r"failed for MISSING\.NS after 1 attempts"):
        provider.history("MISSING.NS", "2y")


def test_yahoo_provider_wraps_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport errors should not leak provider implementation exceptions."""

    def fail(*args: object, **kwargs: object) -> pd.DataFrame:
        """Raise a representative upstream failure."""
        raise OSError("network unavailable")

    monkeypatch.setattr("app.providers.yahoo.yf.download", fail)
    provider = YahooFinanceProvider(RetryPolicy(attempts=1))
    with pytest.raises(MarketDataError, match=r"Yahoo download failed for TEST\.NS"):
        provider.history("TEST.NS", "2y")


def test_yahoo_provider_retries_with_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch, rising_frame: pd.DataFrame
) -> None:
    """Transient errors should retry with deterministic exponentially increasing delays."""
    calls = 0
    delays: list[float] = []

    def flaky_download(*args: object, **kwargs: object) -> pd.DataFrame:
        """Fail twice before returning valid data."""
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("temporary outage")
        return rising_frame

    monkeypatch.setattr("app.providers.yahoo.yf.download", flaky_download)
    provider = YahooFinanceProvider(
        RetryPolicy(
            attempts=3,
            initial_delay_seconds=0.25,
            maximum_delay_seconds=2,
            jitter_ratio=0,
        ),
        sleeper=delays.append,
    )

    result = provider.history("TEST.NS", "2y")

    assert len(result) == len(rising_frame)
    assert calls == 3
    assert delays == [0.25, 0.5]


def test_retry_policy_rejects_invalid_values() -> None:
    """Unsafe retry configurations should fail during startup."""
    with pytest.raises(ValueError, match="at least one"):
        RetryPolicy(attempts=0)
    with pytest.raises(ValueError, match="must not be negative"):
        RetryPolicy(initial_delay_seconds=-1)
    with pytest.raises(ValueError, match="between zero and one"):
        RetryPolicy(jitter_ratio=2)
