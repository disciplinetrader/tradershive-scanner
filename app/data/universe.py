"""Indian equity symbol normalization and universe loading."""

from collections.abc import Iterable
from pathlib import Path

from app.core.constants import NSE_SUFFIX


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
