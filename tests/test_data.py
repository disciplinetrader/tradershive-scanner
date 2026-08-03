"""Tests for loading, indicators, facts, benchmarks, and universes."""

from pathlib import Path

import pandas as pd
import pytest

from app.data.benchmark import benchmark_metrics
from app.data.facts import build_facts
from app.data.indicators import add_indicators
from app.data.loader import DataLoader
from app.data.universe import load_symbols, normalize_nse_symbol
from app.providers.base import MarketDataError, MarketDataProvider


class StaticProvider(MarketDataProvider):
    """In-memory market data provider for tests."""

    def __init__(self, frame: pd.DataFrame) -> None:
        """Store the response frame."""
        self.frame = frame

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Return a defensive copy of the fixed response."""
        return self.frame.copy()


def test_indicators_and_facts_capture_requested_metrics(rising_frame: pd.DataFrame) -> None:
    """All requested facts should derive from sufficient OHLCV history."""
    enriched = add_indicators(rising_frame)
    trend, benchmark_return = benchmark_metrics(enriched)
    facts = build_facts("TEST.NS", enriched, trend, benchmark_return)

    assert facts.close > facts.ema20 > facts.ema50 > facts.ema200
    assert facts.ema_alignment is True
    assert facts.market_trend is True
    assert facts.atr14 > 0
    assert facts.high_52_week >= facts.close
    assert facts.low_52_week < facts.close
    assert facts.volume_ratio > 1
    assert facts.history_days == 320


def test_loader_rejects_insufficient_history(rising_frame: pd.DataFrame) -> None:
    """Too-short histories should fail before indicator calculation."""
    loader = DataLoader(StaticProvider(rising_frame.iloc[:100]))
    with pytest.raises(MarketDataError, match="200 required"):
        loader.load("TEST.NS")


def test_loader_rejects_blank_symbols(rising_frame: pd.DataFrame) -> None:
    """Blank tickers should never reach a provider."""
    loader = DataLoader(StaticProvider(rising_frame))
    with pytest.raises(ValueError, match="must not be blank"):
        loader.load(" ")


def test_universe_normalizes_and_deduplicates_symbols() -> None:
    """Universe entries should follow Yahoo NSE conventions in stable order."""
    assert normalize_nse_symbol(" reliance ") == "RELIANCE.NS"
    assert load_symbols(["RELIANCE", "tcs.ns", "RELIANCE", "# ignored", ""]) == [
        "RELIANCE.NS",
        "TCS.NS",
    ]


def test_universe_loads_first_csv_column(tmp_path: Path) -> None:
    """Simple symbol CSV files should load without a heavyweight parser."""
    source = tmp_path / "symbols.csv"
    source.write_text("Symbol\nINFY,Infosys\nHDFCBANK,HDFC Bank\n", encoding="utf-8")
    assert load_symbols(source) == ["INFY.NS", "HDFCBANK.NS"]
