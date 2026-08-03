"""Indian equity symbol normalization and universe loading."""

import csv
import io
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.request import Request, urlopen

from app.core.constants import NSE_SUFFIX

SUPPORTED_UNIVERSES = ("nifty50", "nifty100", "nifty200", "nifty500", "all", "custom")
NSE_UNIVERSE_URLS = {
    "nifty50": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "nifty100": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty200": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
    "nifty500": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "all": "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
}


class UniverseError(RuntimeError):
    """Raised when a configured production universe cannot be resolved."""


class UniverseResolver:
    """Resolve official NSE constituent universes with a local fallback cache."""

    def __init__(
        self,
        cache_directory: Path,
        ttl_seconds: int,
        timeout_seconds: int = 30,
        clock: Callable[[], float] = time.time,
        opener: Callable[..., object] = urlopen,
    ) -> None:
        """Configure the official-source client and cache policy."""
        self._cache_directory = cache_directory
        self._ttl_seconds = ttl_seconds
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._opener = opener

    def resolve(self, name: str, custom_file: Path | None = None) -> list[str]:
        """Return normalized symbols from a custom file or official NSE CSV."""
        normalized = name.lower()
        if normalized not in SUPPORTED_UNIVERSES:
            raise UniverseError(f"Unsupported universe: {name}")
        if normalized == "custom":
            if custom_file is None:
                raise UniverseError("CUSTOM_UNIVERSE_FILE or --custom-universe-file is required")
            return load_symbols(custom_file)
        cache_path = self._cache_directory / f"{normalized}.csv"
        if self._is_fresh(cache_path):
            return self._parse(cache_path.read_text(encoding="utf-8-sig"), normalized)
        try:
            request = Request(
                NSE_UNIVERSE_URLS[normalized],
                headers={"User-Agent": "Mozilla/5.0 TradersHIVE-Scanner/1.1"},
            )
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = response.read().decode("utf-8-sig")
            symbols = self._parse(payload, normalized)
            self._cache_directory.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(payload, encoding="utf-8")
            return symbols
        except (OSError, UnicodeError, ValueError) as exc:
            if cache_path.is_file():
                return self._parse(cache_path.read_text(encoding="utf-8-sig"), normalized)
            raise UniverseError(f"Unable to load {normalized} universe from NSE: {exc}") from exc

    def _is_fresh(self, path: Path) -> bool:
        """Return whether the cached constituent file remains usable without refresh."""
        return path.is_file() and self._clock() - path.stat().st_mtime <= self._ttl_seconds

    @staticmethod
    def _parse(payload: str, name: str) -> list[str]:
        """Parse the official Symbol column without depending on its column position."""
        rows = csv.DictReader(io.StringIO(payload))
        if not rows.fieldnames:
            raise UniverseError(f"{name} universe CSV has no header")
        symbol_column = next(
            (column for column in rows.fieldnames if column.strip().upper() == "SYMBOL"), None
        )
        if symbol_column is None:
            raise UniverseError(f"{name} universe CSV has no Symbol column")
        symbols = load_symbols(row[symbol_column] for row in rows if row.get(symbol_column))
        if not symbols:
            raise UniverseError(f"{name} universe contains no symbols")
        return symbols


def normalize_nse_symbol(symbol: str) -> str:
    """Normalize a ticker to Yahoo Finance's NSE symbol convention."""
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("Symbol must not be blank")
    return normalized if normalized.endswith(NSE_SUFFIX) else f"{normalized}{NSE_SUFFIX}"


def load_symbols(source: Path | Iterable[str]) -> list[str]:
    """Load unique NSE symbols from a text/CSV-like file or iterable."""
    if isinstance(source, Path):
        if not source.is_file():
            raise FileNotFoundError(f"Universe file does not exist: {source}")
        raw_symbols = [line.split(",", maxsplit=1)[0] for line in source.read_text().splitlines()]
    else:
        raw_symbols = list(source)
    symbols: list[str] = []
    for raw_symbol in raw_symbols:
        stripped = raw_symbol.strip()
        if stripped and not stripped.startswith("#") and stripped.upper() != "SYMBOL":
            symbols.append(normalize_nse_symbol(stripped))
    return list(dict.fromkeys(symbols))
