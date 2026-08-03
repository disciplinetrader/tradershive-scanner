"""Tests for application construction and health behavior."""

from fastapi.routing import APIRoute

from app.core.config import Settings
from main import HealthResponse, create_app


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
