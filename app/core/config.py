"""Environment-backed application configuration."""

from functools import lru_cache
from os import getenv
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.market import MarketRegime

load_dotenv()


class DecisionWeights(BaseModel):
    """Tunable decision weights for one market regime."""

    model_config = ConfigDict(frozen=True)

    market: float = Field(gt=0, lt=1)
    breadth: float = Field(gt=0, lt=1)
    cpr: float = Field(gt=0, lt=1)
    sector: float = Field(gt=0, lt=1)
    relative_strength: float = Field(gt=0, lt=1)
    stock: float = Field(gt=0, lt=1)
    setup: float = Field(gt=0, lt=1)
    risk: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def validate_total(self) -> "DecisionWeights":
        """Require normalized weights so decision scores remain comparable."""
        if abs(sum(self.model_dump().values()) - 1.0) > 1e-9:
            raise ValueError("Decision weights must sum to 1.0")
        return self


DEFAULT_DECISION_WEIGHTS: dict[MarketRegime, DecisionWeights] = {
    MarketRegime.HEALTHY_BULL: DecisionWeights(
        market=0.15,
        breadth=0.10,
        cpr=0.10,
        sector=0.16,
        relative_strength=0.16,
        stock=0.15,
        setup=0.10,
        risk=0.08,
    ),
    MarketRegime.BULL: DecisionWeights(
        market=0.18,
        breadth=0.10,
        cpr=0.10,
        sector=0.14,
        relative_strength=0.14,
        stock=0.15,
        setup=0.11,
        risk=0.08,
    ),
    MarketRegime.WEAK_BULL: DecisionWeights(
        market=0.22,
        breadth=0.12,
        cpr=0.10,
        sector=0.13,
        relative_strength=0.12,
        stock=0.12,
        setup=0.10,
        risk=0.09,
    ),
    MarketRegime.RANGE: DecisionWeights(
        market=0.25,
        breadth=0.15,
        cpr=0.08,
        sector=0.15,
        relative_strength=0.07,
        stock=0.07,
        setup=0.13,
        risk=0.10,
    ),
    MarketRegime.WEAK_BEAR: DecisionWeights(
        market=0.28,
        breadth=0.15,
        cpr=0.07,
        sector=0.18,
        relative_strength=0.07,
        stock=0.07,
        setup=0.08,
        risk=0.10,
    ),
    MarketRegime.BEAR: DecisionWeights(
        market=0.30,
        breadth=0.15,
        cpr=0.06,
        sector=0.18,
        relative_strength=0.07,
        stock=0.07,
        setup=0.07,
        risk=0.10,
    ),
    MarketRegime.CAPITULATION: DecisionWeights(
        market=0.35,
        breadth=0.18,
        cpr=0.06,
        sector=0.18,
        relative_strength=0.05,
        stock=0.05,
        setup=0.05,
        risk=0.08,
    ),
    MarketRegime.RECOVERY: DecisionWeights(
        market=0.22,
        breadth=0.13,
        cpr=0.08,
        sector=0.14,
        relative_strength=0.14,
        stock=0.12,
        setup=0.10,
        risk=0.07,
    ),
}


class Settings(BaseModel):
    """Validated process configuration loaded from environment variables."""

    model_config = ConfigDict(frozen=True)

    app_name: str = "TradersHIVE Scanner"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", pattern=r"^(development|test|production)$")
    log_level: str = "INFO"
    benchmark_symbol: str = "^NSEI"
    history_period: str = "2y"
    request_timeout_seconds: int = Field(default=30, ge=1, le=120)
    report_directory: Path = Path("reports")
    market_data_cache_directory: Path = Path(".cache/market-data")
    market_data_cache_ttl_seconds: int = Field(default=21_600, ge=60, le=604_800)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton settings object for the current process."""
    return Settings(
        environment=getenv("APP_ENV", "development"),
        log_level=getenv("LOG_LEVEL", "INFO").upper(),
        benchmark_symbol=getenv("BENCHMARK_SYMBOL", "^NSEI"),
        history_period=getenv("HISTORY_PERIOD", "2y"),
        request_timeout_seconds=int(getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        report_directory=Path(getenv("REPORT_DIRECTORY", "reports")),
        market_data_cache_directory=Path(
            getenv("MARKET_DATA_CACHE_DIRECTORY", ".cache/market-data")
        ),
        market_data_cache_ttl_seconds=int(getenv("MARKET_DATA_CACHE_TTL_SECONDS", "21600")),
    )
