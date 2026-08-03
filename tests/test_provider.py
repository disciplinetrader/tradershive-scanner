"""Tests for Yahoo provider response normalization and failures."""

import pandas as pd
import pytest

from app.providers.base import MarketDataError
from app.providers.yahoo import YahooFinanceProvider


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
    with pytest.raises(MarketDataError, match=r"no history for MISSING\.NS"):
        YahooFinanceProvider().history("MISSING.NS", "2y")


def test_yahoo_provider_wraps_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport errors should not leak provider implementation exceptions."""

    def fail(*args: object, **kwargs: object) -> pd.DataFrame:
        """Raise a representative upstream failure."""
        raise OSError("network unavailable")

    monkeypatch.setattr("app.providers.yahoo.yf.download", fail)
    with pytest.raises(MarketDataError, match=r"Yahoo download failed for TEST\.NS"):
        YahooFinanceProvider().history("TEST.NS", "2y")
