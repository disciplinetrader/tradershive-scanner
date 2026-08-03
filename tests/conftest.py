"""Shared deterministic fixtures for scanner tests."""

from collections.abc import Iterator

import numpy as np
import pandas as pd
import pytest

from app.engine.setup import SetupEngine
from app.models.facts import Facts
from app.models.market import MarketRegime
from app.models.relative_strength import RelativeStrengthHorizon, RelativeStrengthProfile
from app.models.sector import SectorRotation
from app.models.stock import StockFacts, StockGrade, StockProfile


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
def bullish_facts(rising_frame: pd.DataFrame) -> Facts:
    """Return complete facts representing a liquid bullish stock."""
    stock_facts = StockFacts(
        symbol="TEST.NS",
        close=100,
        ema20=95,
        ema50=90,
        ema100=87,
        ema150=84,
        ema200=80,
        ema_alignment=True,
        distance_above_ema20=0.0526,
        distance_above_ema50=0.1111,
        distance_above_ema200=0.25,
        return_20d=0.08,
        return_50d=0.15,
        return_100d=0.25,
        return_150d=0.35,
        return_250d=0.50,
        atr14=3,
        atr_expansion=0.05,
        average_daily_range=0.025,
        distance_from_52_week_high=0.05,
        distance_from_52_week_low=0.82,
        higher_highs=16,
        higher_lows=16,
        lower_highs=3,
        lower_lows=3,
        gap_percent=0.01,
        average_gap=0.004,
        relative_volume=2,
        average_volume=1_000_000,
        volume_expansion=True,
        volume_contraction=False,
        new_high=False,
        new_low=False,
        inside_day=False,
        outside_day=False,
        nr7=False,
        history_days=320,
    )
    stock_profile = StockProfile(
        score=94,
        confidence=1,
        grade=StockGrade.A_PLUS,
        trend_score=95,
        momentum_score=93,
        participation_score=100,
        health_score=85,
        reasons=("Perfect EMA alignment", "Strong trend persistence", "Strong participation"),
        facts=stock_facts,
    )
    setup_profile = SetupEngine().analyze("TEST.NS", rising_frame, stock_profile)
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
        market_score=100,
        market_confidence=1,
        market_state=MarketRegime.HEALTHY_BULL,
        market_reasons=("Strong breadth", "Low VIX", "Indexes above EMA200"),
        sector_name="Defence",
        sector_rank=1,
        sector_percentile=99,
        sector_score=95,
        sector_confidence=1,
        sector_rotation=SectorRotation.LEADING,
        sector_reasons=("Highest RS over 100 days", "Broad participation"),
        stock_score=stock_profile.score,
        stock_grade=stock_profile.grade,
        stock_profile=stock_profile,
        setup_score=setup_profile.score,
        setup_grade=setup_profile.grade,
        setup_type=setup_profile.best_setup_type,
        setup_profile=setup_profile,
        pivot_price=setup_profile.facts.pivot_price,
        invalidation_price=setup_profile.facts.invalidation_price,
        breakout_distance_percent=setup_profile.facts.breakout_distance_percent,
        ema_alignment=True,
        near_52_week_high=True,
        distance_from_high=0.0476,
        gap_percent=0.01,
        daily_return=0.02,
        return_63d=0.20,
        benchmark_return_63d=0.08,
        rs5=0.03,
        rs10=0.04,
        rs20=0.05,
        rs50=0.10,
        rs100=0.12,
        rs150=0.15,
        rs250=0.20,
        relative_strength_score=90,
        relative_strength_percentile=90,
        rs_profile=RelativeStrengthProfile(
            rs5=RelativeStrengthHorizon(relative_return=0.03, percentile=95),
            rs10=RelativeStrengthHorizon(relative_return=0.04, percentile=90),
            rs20=RelativeStrengthHorizon(relative_return=0.05, percentile=70),
            rs50=RelativeStrengthHorizon(relative_return=0.10, percentile=82),
            rs100=RelativeStrengthHorizon(relative_return=0.12, percentile=86),
            rs150=RelativeStrengthHorizon(relative_return=0.15, percentile=91),
            rs250=RelativeStrengthHorizon(relative_return=0.20, percentile=97),
        ),
        annualized_volatility=0.30,
        history_days=320,
    )


@pytest.fixture
def feature_names() -> Iterator[str]:
    """Yield canonical feature names for aggregation assertions."""
    yield from (
        "market",
        "sector",
        "stock",
        "setup",
        "trend",
        "relative_strength",
        "momentum",
        "volume",
        "volatility",
    )
