"""Command-line report generation for historical validation ledgers."""

import argparse
import json
from pathlib import Path

from app.validation.engine import ValidationReportBuilder
from app.validation.models import HistoricalTrade, ValidationConfig
from app.validation.reports import write_excel_report, write_json_report, write_trade_ledger


def main() -> int:
    """Build validation outputs from an immutable historical trade ledger."""
    parser = argparse.ArgumentParser(description="Build TradersHIVE historical validation reports")
    parser.add_argument("ledger", type=Path, help="JSON array of HistoricalTrade objects")
    parser.add_argument("--output", type=Path, default=Path("validation-output"))
    parsed = parser.parse_args()
    payload = json.loads(parsed.ledger.read_text(encoding="utf-8"))
    trades = tuple(HistoricalTrade.model_validate(item) for item in payload)
    report = ValidationReportBuilder().build(trades, ValidationConfig())
    parsed.output.mkdir(parents=True, exist_ok=True)
    write_json_report(report, parsed.output / "validation-report.json")
    write_excel_report(report, parsed.output / "validation-report.xlsx")
    write_trade_ledger(trades, parsed.output / "trade-ledger.csv")
    print(f"Candidates: {report.metrics.number_of_candidates}")
    print(f"Triggered trades: {report.metrics.number_of_triggered_trades}")
    print(f"Expectancy: {report.metrics.expectancy:.2f}R")
    print(f"Reports: {parsed.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
