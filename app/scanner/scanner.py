"""Momentum scanner application service."""

from collections.abc import Iterable, Mapping

from app.core.constants import DEFAULT_BENCHMARK
from app.core.logging import get_logger
from app.data.benchmark import BenchmarkSnapshot, build_benchmark_snapshot
from app.data.facts import build_facts
from app.data.indicators import add_indicators
from app.data.loader import DataLoader
from app.data.universe import load_symbols
from app.engine.avwap import AVWAPEngine
from app.engine.breadth import BreadthEngine
from app.engine.cpr import CPREngine
from app.engine.decision import DecisionEngine
from app.engine.market import MarketEngine
from app.engine.risk import RiskEngine
from app.engine.scorer import Scorer
from app.engine.sector import SectorEngine
from app.engine.setup import SetupEngine
from app.engine.situation import SituationEngine
from app.engine.stock import StockEngine
from app.engine.volume import VolumeEngine
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
        setup_engine: SetupEngine | None = None,
        risk_engine: RiskEngine | None = None,
        decision_engine: DecisionEngine | None = None,
        situation_engine: SituationEngine | None = None,
        volume_engine: VolumeEngine | None = None,
        breadth_engine: BreadthEngine | None = None,
        cpr_engine: CPREngine | None = None,
        avwap_engine: AVWAPEngine | None = None,
    ) -> None:
        """Initialize the scanner with explicit, replaceable collaborators."""
        self._loader = loader
        self._scorer = scorer
        self._benchmark_symbol = benchmark_symbol
        self._market_engine = market_engine or MarketEngine(loader)
        self._sector_engine = sector_engine or SectorEngine()
        self._stock_engine = stock_engine or StockEngine()
        self._setup_engine = setup_engine or SetupEngine()
        self._risk_engine = risk_engine or RiskEngine()
        self._decision_engine = decision_engine or DecisionEngine()
        self._situation_engine = situation_engine or SituationEngine()
        self._volume_engine = volume_engine or VolumeEngine()
        self._breadth_engine = breadth_engine or BreadthEngine()
        self._cpr_engine = cpr_engine or CPREngine()
        self._avwap_engine = avwap_engine or AVWAPEngine()

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
        breadth_profile = self._breadth_engine.analyze(frames)
        market_profile = self._market_engine.analyze(frames)
        sector_analysis = self._sector_engine.analyze(frames, benchmark, sector_by_symbol)
        results: list[StockResult] = []
        for symbol, frame in frames.items():
            try:
                sector_name = sector_analysis.symbol_sectors.get(symbol, "Unclassified")
                sector_profile = sector_analysis.sectors.get(sector_name)
                stock_profile = self._stock_engine.analyze(symbol, frame)
                setup_profile = self._setup_engine.analyze(symbol, frame, stock_profile)
                volume_profile = self._volume_engine.analyze(symbol, frame)
                cpr_profile = self._cpr_engine.analyze(symbol, frame)
                avwap_profile = self._avwap_engine.analyze(symbol, frame)
                facts = build_facts(
                    symbol,
                    frame,
                    benchmark,
                    market_profile,
                    sector_profile,
                    sector_name,
                    stock_profile,
                    setup_profile,
                    volume_profile,
                    breadth_profile,
                    cpr_profile,
                    avwap_profile,
                )
                risk_profile = self._risk_engine.analyze(facts)
                facts = facts.model_copy(
                    update={
                        "risk_score": risk_profile.score,
                        "risk_grade": risk_profile.grade,
                        "entry_price": risk_profile.facts.entry_price,
                        "stop_price": risk_profile.facts.stop_price,
                        "available_r_multiple": risk_profile.facts.available_r_multiple,
                        "risk_profile": risk_profile,
                    }
                )
                results.append(self._scorer.score(facts))
            except (ValueError, RuntimeError) as exc:
                logger.warning("Skipping %s: %s", symbol, exc)

        results = assign_relative_strength_percentiles(results)
        results = [self._scorer.score(result.facts) for result in results]
        decided_results: list[StockResult] = []
        for result in results:
            sector_profile = sector_analysis.sectors.get(result.facts.sector_name)
            decision = self._decision_engine.evaluate(
                market_profile,
                sector_profile,
                result.facts.rs_profile,
                result.facts.stock_profile,
                result.facts.setup_profile,
                result.facts.risk_profile,
                breadth_profile,
                result.facts.cpr_profile,
                result.facts.avwap_profile,
            )
            decided_results.append(result.model_copy(update={"decision_profile": decision}))
        results = decided_results
        situation = self._situation_engine.analyze(
            market_profile,
            tuple(sector_analysis.sectors.values()),
            tuple(result.facts.rs_profile for result in results),
            tuple(result.facts.stock_profile for result in results),
            tuple(result.facts.setup_profile for result in results),
            tuple(result.facts.risk_profile for result in results if result.facts.risk_profile),
            tuple(result.decision_profile for result in results if result.decision_profile),
            breadth_profile,
            tuple(result.facts.cpr_profile for result in results),
            tuple(result.facts.avwap_profile for result in results),
        )
        results = [result.model_copy(update={"situation_profile": situation}) for result in results]
        results.sort(key=lambda result: (-result.decision_score, result.symbol))
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
