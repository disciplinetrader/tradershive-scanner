"""Yahoo Finance market data adapter."""

import pandas as pd
import yfinance as yf

from app.providers.base import MarketDataError, MarketDataProvider


class YahooFinanceProvider(MarketDataProvider):
    """Download daily OHLCV bars from Yahoo Finance."""

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Fetch and normalize adjusted daily bars for one symbol."""
        try:
            frame = yf.download(
                symbol,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception as exc:
            raise MarketDataError(f"Yahoo download failed for {symbol}: {exc}") from exc
        if frame.empty:
            raise MarketDataError(f"Yahoo returned no history for {symbol}")
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = set(required).difference(frame.columns)
        if missing:
            raise MarketDataError(f"Yahoo response for {symbol} lacks {sorted(missing)}")
        normalized = frame.loc[:, required].copy()
        normalized.index = pd.to_datetime(normalized.index, utc=True)
        return normalized.dropna(subset=required).sort_index()
