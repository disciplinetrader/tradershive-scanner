"""Shared deterministic fixtures for scanner tests."""

from collections.abc import Iterator

import numpy as np
import pandas as pd
import pytest

from app.models.facts import Facts


@pytest.fixture
def rising_frame() -> pd.DataFrame:
    """Return 320 realistic sessions with a stable upward trend."""
    rows = 320
    index = pd.bdate_range("2024-01-01", periods=rows, tz="UTC")
    close = np.linspace(100.0, 180.0, rows) + np.sin(np.arange(rows) / 7) * 1.5
    open_price = close * (1 + np.sin(np.arange(rows)) * 0.002)
    volume = np.linspace(800_000, 1_200_000, rows)
    volume[-1] = 2_000_000
    return pd.DataFrame(
        {
            "Open": open_price,
            "High": np.maximum(open_price, close) * 1.01,
            "Low": np.minimum(open_price, close) * 0.99,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )


@pytest.fixture
def bullish_facts() -> Facts:
    """Return complete facts representing a liquid bullish stock."""
    return Facts(
        symbol="TEST.NS",
        close=100,
        ema20=95,
        ema50=90,
        ema200=80,
        atr14=3,
        high_52_week=105,
        low_52_week=55,
        average_volume=1_000_000,
        volume_ratio=2,
        market_trend=True,
        ema_alignment=True,
        near_52_week_high=True,
        distance_from_high=0.0476,
        gap_percent=0.01,
        daily_return=0.02,
        return_63d=0.20,
        benchmark_return_63d=0.08,
        annualized_volatility=0.30,
        history_days=320,
    )


@pytest.fixture
def feature_names() -> Iterator[str]:
    """Yield canonical feature names for aggregation assertions."""
    yield from (
        "market",
        "trend",
        "relative_strength",
        "momentum",
        "volume",
        "volatility",
    )
