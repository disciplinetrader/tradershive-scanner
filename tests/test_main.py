"""Tests for application construction and health behavior."""

from pathlib import Path

from fastapi.routing import APIRoute

from app.core.config import Settings
from app.data.universe import UniverseResolver
from main import HealthResponse, _report_destination, cli, create_app


def test_health_endpoint_reports_version() -> None:
    """The service should expose a cheap readiness-compatible endpoint."""
    settings = Settings(environment="test", app_version="9.9.9")
    application = create_app(settings)
    route = next(
        route
        for route in application.routes
        if isinstance(route, APIRoute) and route.path == "/health"
    )
    response = route.endpoint()
    assert response == HealthResponse(status="ok", version="9.9.9")


def test_official_universe_resolver_parses_and_caches_symbols(tmp_path: Path) -> None:
    """Named production universes use the official Symbol column and local cache."""

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return (
                b"Company Name,Industry,Symbol\nBharat Electronics,Defence,BEL\nHAL,Defence,HAL\n"
            )

    resolver = UniverseResolver(tmp_path, 3600, opener=lambda *args, **kwargs: Response())
    assert resolver.resolve("nifty50") == ["BEL.NS", "HAL.NS"]
    assert (tmp_path / "nifty50.csv").is_file()


def test_custom_universe_uses_existing_file_loader(tmp_path: Path) -> None:
    """Custom files retain normalization, comments, headers, and de-duplication behavior."""
    universe = tmp_path / "symbols.csv"
    universe.write_text("Symbol\nBEL\nHAL.NS\nBEL\n", encoding="utf-8")
    resolver = UniverseResolver(tmp_path / "cache", 3600)
    assert resolver.resolve("custom", universe) == ["BEL.NS", "HAL.NS"]


def test_cli_without_symbols_resolves_configured_universe(monkeypatch, tmp_path: Path) -> None:
    """The production no-argument command resolves its configured universe automatically."""
    observed: list[list[str]] = []

    class Resolver:
        def __init__(self, *args: object) -> None:
            pass

        @staticmethod
        def resolve(name: str, custom_file: Path | None) -> list[str]:
            assert name == "nifty100" and custom_file is None
            return ["BEL.NS", "HAL.NS"]

    class Scanner:
        @staticmethod
        def scan(symbols: list[str], *args: object) -> list[object]:
            observed.append(symbols)
            return []

    settings = Settings(
        environment="test",
        default_universe="nifty100",
        report_directory=tmp_path,
    )
    monkeypatch.setattr("main.get_settings", lambda: settings)
    monkeypatch.setattr("main.UniverseResolver", Resolver)
    monkeypatch.setattr("main.build_scanner", lambda configured: Scanner())
    assert cli([]) == 0
    assert observed == [["BEL.NS", "HAL.NS"]]


def test_cli_explicit_symbols_bypass_default_universe(monkeypatch) -> None:
    """Existing positional-symbol commands continue to scan only those symbols."""
    observed: list[list[str]] = []

    class Scanner:
        @staticmethod
        def scan(symbols: list[str], *args: object) -> list[object]:
            observed.append(symbols)
            return []

    monkeypatch.setattr("main.get_settings", lambda: Settings(environment="test"))
    monkeypatch.setattr("main.build_scanner", lambda configured: Scanner())
    assert cli(["BEL.NS", "HAL.NS"]) == 0
    assert observed == [["BEL.NS", "HAL.NS"]]


def test_default_universe_uses_configured_report_destination(tmp_path: Path) -> None:
    """Only the no-symbol production path automatically creates its configured workbook."""
    settings = Settings(
        environment="test",
        report_directory=tmp_path,
        default_report_filename="closing-scan.xlsx",
    )
    assert _report_destination(None, True, settings) == tmp_path / "closing-scan.xlsx"
    assert _report_destination(None, False, settings) is None
    assert _report_destination(Path("manual.xlsx"), False, settings) == Path("manual.xlsx")
