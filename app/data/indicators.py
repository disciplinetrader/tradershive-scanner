"""Vectorized technical indicator calculation."""

import numpy as np
import pandas as pd
import pandas_ta as ta

from app.core.constants import TRADING_DAYS_PER_YEAR


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with all columns required by the facts engine."""
    result = frame.copy()
    close = result["Close"].astype(float)
    for period in (20, 50, 200):
        result[f"EMA{period}"] = ta.ema(close, length=period)

    result["ATR14"] = ta.atr(
        result["High"].astype(float),
        result["Low"].astype(float),
        close,
        length=14,
    )
    result["High52W"] = result["High"].rolling(TRADING_DAYS_PER_YEAR).max()
    result["Low52W"] = result["Low"].rolling(TRADING_DAYS_PER_YEAR).min()
    result["AverageVolume"] = result["Volume"].rolling(20).mean()
    result["DailyReturn"] = close.pct_change()
    result["Return63D"] = close.pct_change(63)
    result["AnnualizedVolatility"] = result["DailyReturn"].rolling(20).std(ddof=1) * np.sqrt(
        TRADING_DAYS_PER_YEAR
    )
    return result
