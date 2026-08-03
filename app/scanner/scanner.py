"""Momentum scanner application service."""

from collections.abc import Iterable, Mapping

from app.core.constants import DEFAULT_BENCHMARK
from app.core.logging import get_logger
from app.data.benchmark import BenchmarkSnapshot, build_benchmark_snapshot
from app.data.facts import build_facts
from app.data.indicators import add_indicators
from app.data.loader import DataLoader
from app.data.universe import load_symbols
from app.engine.market import MarketEngine
from app.engine.scorer import Scorer
from app.engine.sector import SectorEngine
from app.engine.stock import StockEngine
from app.features.relative_strength import assign_relative_strength_percentiles
from app.models.stock_result import StockResult

logger = get_logger(__name__)


class Scanner:
    """Coordinate data retrieval, fact derivation, scoring, and ranking."""

    def __init__(
        self,
        loader: DataLoader,
        scorer: Scorer,
        benchmark_symbol: str,
        market_engine: MarketEngine | None = None,
        sector_engine: SectorEngine | None = None,
        stock_engine: StockEngine | None = None,
    ) -> None:
        """Initialize the scanner with explicit, replaceable collaborators."""
        self._loader = loader
        self._scorer = scorer
        self._benchmark_symbol = benchmark_symbol
        self._market_engine = market_engine or MarketEngine(loader)
        self._sector_engine = sector_engine or SectorEngine()
        self._stock_engine = stock_engine or StockEngine()

    def scan(
        self,
        symbols: Iterable[str],
        sector_by_symbol: Mapping[str, str] | None = None,
    ) -> list[StockResult]:
        """Scan symbols independently and return successful results by score."""
        universe = load_symbols(symbols)
        if not universe:
            raise ValueError("At least one symbol is required")

        benchmark = self._load_benchmark()
        frames = {}
        for symbol in universe:
            try:
                frames[symbol] = add_indicators(self._loader.load(symbol))
            except (ValueError, RuntimeError) as exc:
                logger.warning("Skipping %s: %s", symbol, exc)
        market_profile = self._market_engine.analyze(frames)
        sector_analysis = self._sector_engine.analyze(frames, benchmark, sector_by_symbol)
        results: list[StockResult] = []
        for symbol, frame in frames.items():
            try:
                sector_name = sector_analysis.symbol_sectors.get(symbol, "Unclassified")
                sector_profile = sector_analysis.sectors.get(sector_name)
                stock_profile = self._stock_engine.analyze(symbol, frame)
                facts = build_facts(
                    symbol,
                    frame,
                    benchmark,
                    market_profile,
                    sector_profile,
                    sector_name,
                    stock_profile,
                )
                results.append(self._scorer.score(facts))
            except (ValueError, RuntimeError) as exc:
                logger.warning("Skipping %s: %s", symbol, exc)

        results = assign_relative_strength_percentiles(results)
        results = [self._scorer.score(result.facts) for result in results]
        results.sort(key=lambda result: (-result.final_score, result.symbol))
        return [result.model_copy(update={"rank": rank}) for rank, result in enumerate(results, 1)]

    def _load_benchmark(self) -> BenchmarkSnapshot:
        """Load the configured benchmark, falling back to NIFTY 50 when necessary."""
        failures: list[str] = []
        for symbol in dict.fromkeys((self._benchmark_symbol, DEFAULT_BENCHMARK)):
            try:
                frame = add_indicators(self._loader.load(symbol))
                return build_benchmark_snapshot(symbol, frame)
            except (ValueError, RuntimeError) as exc:
                failures.append(f"{symbol}: {exc}")
                logger.warning("Benchmark %s unavailable: %s", symbol, exc)
        raise RuntimeError(f"No benchmark data available ({'; '.join(failures)})")
