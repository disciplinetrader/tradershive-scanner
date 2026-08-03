"""Canonical OHLCV schema normalization."""

from collections.abc import Hashable

import pandas as pd

from app.providers.base import MarketDataError

OHLCV_COLUMNS: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")


def _flatten_columns(columns: pd.MultiIndex, symbol: str) -> list[Hashable]:
    """Select the MultiIndex level containing canonical field names."""
    required = set(OHLCV_COLUMNS)
    candidates: list[int] = []
    for level in range(columns.nlevels):
        values = {str(value).title() for value in columns.get_level_values(level)}
        if required.issubset(values):
            candidates.append(level)
    if len(candidates) != 1:
        raise MarketDataError(
            f"{symbol} has an ambiguous MultiIndex schema; expected one OHLCV field level"
        )
    return [str(value).title() for value in columns.get_level_values(candidates[0])]


def normalize_ohlcv(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalize arbitrary provider bars to UTC-indexed canonical OHLCV data."""
    if not isinstance(frame, pd.DataFrame):
        raise MarketDataError(f"{symbol} provider response is not a DataFrame")
    if frame.empty:
        raise MarketDataError(f"Provider returned no history for {symbol}")

    normalized = frame.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = _flatten_columns(normalized.columns, symbol)
    else:
        normalized.columns = [str(column).title() for column in normalized.columns]

    if normalized.columns.duplicated().any():
        raise MarketDataError(f"{symbol} contains duplicate OHLCV columns")
    missing = set(OHLCV_COLUMNS).difference(normalized.columns)
    if missing:
        raise MarketDataError(f"{symbol} is missing columns: {sorted(missing)}")

    normalized = normalized.loc[:, list(OHLCV_COLUMNS)]
    normalized.index = pd.to_datetime(normalized.index, utc=True, errors="coerce")
    normalized = normalized[~normalized.index.isna()]
    normalized = normalized[~normalized.index.duplicated(keep="last")].sort_index()
    normalized = normalized.apply(pd.to_numeric, errors="coerce").dropna()
    if normalized.empty:
        raise MarketDataError(f"{symbol} has no valid OHLCV rows after normalization")
    normalized.index.name = "Date"
    return normalized
