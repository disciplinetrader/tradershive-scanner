"""Atomic time-bounded disk cache for canonical OHLCV frames."""

import hashlib
import os
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pandas as pd

from app.data.schema import normalize_ohlcv
from app.providers.base import MarketDataError


class MarketDataCache:
    """Store normalized market data as portable CSV files with expiration."""

    def __init__(
        self,
        directory: Path,
        ttl: timedelta,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Configure a cache directory and strictly positive lifetime."""
        if ttl.total_seconds() <= 0:
            raise ValueError("Cache TTL must be positive")
        self._directory = directory
        self._ttl_seconds = ttl.total_seconds()
        self._clock = clock
        self._lock = threading.RLock()

    def _path(self, namespace: str, symbol: str, period: str) -> Path:
        """Return a filesystem-safe, collision-resistant cache path."""
        identity = f"{namespace}\0{symbol}\0{period}".encode()
        digest = hashlib.sha256(identity).hexdigest()
        return self._directory / f"{digest}.csv"

    def get(self, namespace: str, symbol: str, period: str) -> pd.DataFrame | None:
        """Return a fresh cached frame or None after any recoverable cache fault."""
        path = self._path(namespace, symbol, period)
        with self._lock:
            try:
                age_seconds = max(0.0, self._clock() - path.stat().st_mtime)
                if age_seconds > self._ttl_seconds:
                    return None
                frame = pd.read_csv(path, index_col="Date", parse_dates=["Date"])
                return normalize_ohlcv(frame, symbol)
            except (OSError, ValueError, MarketDataError, pd.errors.ParserError):
                return None

    def put(self, namespace: str, symbol: str, period: str, frame: pd.DataFrame) -> None:
        """Atomically persist a normalized frame without exposing partial writes."""
        path = self._path(namespace, symbol, period)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            try:
                frame.to_csv(temporary, index_label="Date")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
