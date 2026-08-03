"""Momentum scanner application service."""

from collections.abc import Iterable

from app.core.logging import get_logger
from app.data.benchmark import benchmark_metrics
from app.data.facts import build_facts
from app.data.indicators import add_indicators
from app.data.loader import DataLoader
from app.data.universe import load_symbols
from app.engine.scorer import Scorer
from app.models.stock_result import StockResult

logger = get_logger(__name__)


class Scanner:
    """Coordinate data retrieval, fact derivation, scoring, and ranking."""

    def __init__(self, loader: DataLoader, scorer: Scorer, benchmark_symbol: str) -> None:
        """Initialize the scanner with explicit, replaceable collaborators."""
        self._loader = loader
        self._scorer = scorer
        self._benchmark_symbol = benchmark_symbol

    def scan(self, symbols: Iterable[str]) -> list[StockResult]:
        """Scan symbols independently and return successful results by score."""
        universe = load_symbols(symbols)
        if not universe:
            raise ValueError("At least one symbol is required")

        benchmark_frame = add_indicators(self._loader.load(self._benchmark_symbol))
        market_trend, benchmark_return = benchmark_metrics(benchmark_frame)
        results: list[StockResult] = []
        for symbol in universe:
            try:
                frame = add_indicators(self._loader.load(symbol))
                facts = build_facts(symbol, frame, market_trend, benchmark_return)
                results.append(self._scorer.score(facts))
            except (ValueError, RuntimeError) as exc:
                logger.warning("Skipping %s: %s", symbol, exc)

        results.sort(key=lambda result: (-result.final_score, result.symbol))
        return [result.model_copy(update={"rank": rank}) for rank, result in enumerate(results, 1)]
