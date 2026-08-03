"""Environment-backed application configuration."""

from functools import lru_cache
from os import getenv
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()


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
    )
