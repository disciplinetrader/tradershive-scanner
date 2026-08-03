"""FastAPI and command-line entry points for TradersHIVE Scanner."""

import argparse
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings, get_settings
from app.core.constants import FEATURE_WEIGHTS
from app.core.logging import configure_logging
from app.data.cache import MarketDataCache
from app.data.loader import DataLoader
from app.engine.registry import FeatureRegistry
from app.engine.scorer import Scorer
from app.features.market import MarketFeature
from app.features.momentum import MomentumFeature
from app.features.relative_strength import RelativeStrengthFeature
from app.features.trend import TrendFeature
from app.features.volatility import VolatilityFeature
from app.features.volume import VolumeFeature
from app.models.stock_result import StockResult
from app.providers.yahoo import YahooFinanceProvider
from app.reports.excel import generate_excel_report
from app.scanner.scanner import Scanner


class ScanRequest(BaseModel):
    """Validated API request containing NSE ticker symbols."""

    model_config = ConfigDict(extra="forbid")

    symbols: list[str] = Field(min_length=1, max_length=500)


class HealthResponse(BaseModel):
    """Service health response."""

    status: str
    version: str


def build_scorer() -> Scorer:
    """Construct the production feature registry and scorer."""
    registry = FeatureRegistry(
        [
            MarketFeature(),
            TrendFeature(),
            RelativeStrengthFeature(),
            MomentumFeature(),
            VolumeFeature(),
            VolatilityFeature(),
        ]
    )
    return Scorer(registry, FEATURE_WEIGHTS)


def build_scanner(settings: Settings | None = None) -> Scanner:
    """Construct a scanner wired to the production Yahoo provider."""
    resolved_settings = settings or get_settings()
    provider = YahooFinanceProvider()
    cache = MarketDataCache(
        resolved_settings.market_data_cache_directory,
        timedelta(seconds=resolved_settings.market_data_cache_ttl_seconds),
    )
    loader = DataLoader(provider, resolved_settings.history_period, cache)
    return Scanner(loader, build_scorer(), resolved_settings.benchmark_symbol)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the HTTP application."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Explainable momentum scanning for Indian equities.",
    )

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Report process health and application version."""
        return HealthResponse(status="ok", version=resolved_settings.app_version)

    @application.post("/scan", response_model=list[StockResult])
    def scan(request: ScanRequest) -> list[StockResult]:
        """Download, score, and rank the requested NSE symbols."""
        try:
            return build_scanner(resolved_settings).scan(request.symbols)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return application


app = create_app()


def cli(arguments: Sequence[str] | None = None) -> int:
    """Run a scan from the command line and optionally generate Excel."""
    parser = argparse.ArgumentParser(description="Scan Indian equities for momentum")
    parser.add_argument("symbols", nargs="+", help="NSE symbols such as RELIANCE or TCS")
    parser.add_argument("--output", type=Path, help="Optional output .xlsx path")
    parsed = parser.parse_args(arguments)
    results = build_scanner().scan(parsed.symbols)
    for result in results:
        print(
            f"{result.rank:>3} {result.symbol:<20} {result.final_score:>6.2f} "
            f"RS {result.features['relative_strength'].score:>6.2f} "
            f"Pctl {result.facts.relative_strength_percentile:>6.2f}"
        )
    if parsed.output:
        report = generate_excel_report(results, parsed.output)
        print(f"Report written to {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
