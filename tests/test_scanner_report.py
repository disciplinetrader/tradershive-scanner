"""Integration-style tests for orchestration and Excel reporting."""

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from app.core.constants import FEATURE_WEIGHTS
from app.data.loader import DataLoader
from app.engine.registry import FeatureRegistry
from app.engine.scorer import Scorer
from app.features.breadth import BreadthFeature
from app.features.cpr import CPRFeature
from app.features.market import MarketFeature
from app.features.momentum import MomentumFeature
from app.features.relative_strength import RelativeStrengthFeature
from app.features.risk import RiskFeature
from app.features.sector import SectorFeature
from app.features.setup import SetupFeature
from app.features.stock import StockFeature
from app.features.trend import TrendFeature
from app.features.volatility import VolatilityFeature
from app.features.volume import VolumeFeature
from app.providers.base import MarketDataProvider
from app.reports.excel import generate_excel_report
from app.scanner.scanner import Scanner


class SymbolProvider(MarketDataProvider):
    """Return deterministic frames with symbol-specific strength."""

    def __init__(self, frame: pd.DataFrame) -> None:
        """Store baseline history."""
        self._frame = frame

    def history(self, symbol: str, period: str) -> pd.DataFrame:
        """Return weaker history for the designated WEAK ticker."""
        frame = self._frame.copy()
        if symbol == "WEAK.NS":
            frame.loc[:, "Close"] = frame["Close"].iloc[::-1].to_numpy()
            frame.loc[:, "Open"] = frame["Close"]
            frame.loc[:, "High"] = frame["Close"] * 1.01
            frame.loc[:, "Low"] = frame["Close"] * 0.99
        return frame


def build_test_scanner(frame: pd.DataFrame) -> Scanner:
    """Construct the complete scanner with an in-memory provider."""
    registry = FeatureRegistry(
        [
            MarketFeature(),
            BreadthFeature(),
            CPRFeature(),
            SectorFeature(),
            StockFeature(),
            SetupFeature(),
            RiskFeature(),
            TrendFeature(),
            RelativeStrengthFeature(),
            MomentumFeature(),
            VolumeFeature(),
            VolatilityFeature(),
        ]
    )
    return Scanner(DataLoader(SymbolProvider(frame)), Scorer(registry, FEATURE_WEIGHTS), "^NSEI")


def test_scanner_ranks_results_and_report_contains_expected_columns(
    rising_frame: pd.DataFrame, tmp_path: Path
) -> None:
    """The full pipeline should rank stocks and export its supporting evidence."""
    results = build_test_scanner(rising_frame).scan(["WEAK", "STRONG"])
    assert [result.rank for result in results] == [1, 2]
    assert results[0].symbol == "STRONG.NS"
    assert results[0].final_score > results[1].final_score

    report = generate_excel_report(results, tmp_path / "scanner.xlsx")
    workbook = load_workbook(report)
    sheet = workbook["Momentum Scanner"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[:3] == ["Rank", "Symbol", "Score"]
    assert headers[:42] == [
        "Rank",
        "Symbol",
        "Score",
        "Decision Score",
        "Action",
        "Trade Grade",
        "Decision Confidence",
        "Decision Reasons",
        "Stock Grade",
        "Stock Score",
        "Breadth Grade",
        "Breadth Score",
        "Breadth State",
        "Breadth Confidence",
        "CPR Grade",
        "CPR Score",
        "CPR State",
        "CPR Breakout %",
        "CPR Trend %",
        "CPR Range %",
        "Volume Grade",
        "Volume Score",
        "Volume State",
        "Volume Confidence",
        "Volume Reasons",
        "Setup Type",
        "Setup Grade",
        "Setup Score",
        "Pivot Price",
        "Invalidation Price",
        "Breakout Distance %",
        "Risk Grade",
        "Risk Score",
        "Entry Price",
        "Stop Price",
        "Available R",
        "RS",
        "Percentile",
        "Sector",
        "Sector Rank",
        "Sector Rotation",
        "Sector Score",
    ]
    assert headers[-1] == "Reasons"
    assert sheet.max_row == 3
    assert results[0].facts.relative_strength_percentile == 99
    assert results[1].facts.relative_strength_percentile == 0
