"""Extensible sector definitions and symbol assignment utilities."""

import json
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.data.universe import normalize_nse_symbol

SUPPORTED_SECTORS: tuple[str, ...] = (
    "Banking",
    "Financial Services",
    "IT",
    "Pharma",
    "Auto",
    "FMCG",
    "Energy",
    "Oil & Gas",
    "Metal",
    "Realty",
    "Infrastructure",
    "Capital Goods",
    "Defence",
    "PSU",
    "Chemical",
    "Consumption",
)


class SectorDefinition(BaseModel):
    """Named sector and its explicitly managed member symbols."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    members: frozenset[str] = frozenset()


class SectorRegistry:
    """Validate sector definitions and resolve normalized stock assignments."""

    def __init__(self, definitions: tuple[SectorDefinition, ...] | None = None) -> None:
        """Initialize with all supported sectors or caller-supplied definitions."""
        self._definitions = definitions or tuple(
            SectorDefinition(name=name) for name in SUPPORTED_SECTORS
        )
        names = [definition.name for definition in self._definitions]
        if len(names) != len(set(names)):
            raise ValueError("Sector names must be unique")
        assignments: dict[str, str] = {}
        for definition in self._definitions:
            for member in definition.members:
                symbol = normalize_nse_symbol(member)
                if symbol in assignments:
                    raise ValueError(f"{symbol} belongs to multiple sectors")
                assignments[symbol] = definition.name
        self._assignments = assignments

    @property
    def names(self) -> tuple[str, ...]:
        """Return configured sector names in stable order."""
        return tuple(definition.name for definition in self._definitions)

    def assignments(self, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
        """Return registry assignments combined with validated scan-time overrides."""
        resolved = dict(self._assignments)
        for raw_symbol, sector in (overrides or {}).items():
            if sector not in self.names:
                raise ValueError(f"Unsupported sector {sector!r}")
            resolved[normalize_nse_symbol(raw_symbol)] = sector
        return resolved


def load_sector_assignments(path: Path) -> dict[str, str]:
    """Load a JSON object mapping stock symbols to supported sector names."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load sector map {path}: {exc}") from exc
    if not isinstance(payload, dict) or not all(
        isinstance(symbol, str) and isinstance(sector, str) for symbol, sector in payload.items()
    ):
        raise ValueError("Sector map must be a JSON object of string symbols to string sectors")
    return SectorRegistry().assignments(payload)
