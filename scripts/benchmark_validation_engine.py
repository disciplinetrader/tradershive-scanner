"""Deterministic benchmark for monthly validation of two years and 250 symbols."""

from datetime import date
from time import perf_counter

import numpy as np
import pandas as pd

from app.validation.engine import ForwardOutcomeEvaluator, ValidationReportBuilder
from app.validation.models import EntryModel, HistoricalCandidate, ValidationConfig


def main() -> int:
    """Evaluate 6,000 candidates against a documented ten-second ceiling."""
    symbols, scan_count = 250, 24
    rows = 504
    index = pd.bdate_range("2023-01-02", periods=rows)
    close = np.linspace(100, 150, rows)
    frame = pd.DataFrame(
        {
            "Open": close,
            "High": close + 3,
            "Low": close - 1,
            "Close": close + 0.5,
            "Volume": 1_000_000,
        },
        index=index,
    )
    evaluator = ForwardOutcomeEvaluator()
    builder = ValidationReportBuilder()
    config = ValidationConfig(entry_model=EntryModel.RISK_PROFILE)
    started = perf_counter()
    trades = []
    for month in range(scan_count):
        scan_date = date(2023 + month // 12, month % 12 + 1, 1)
        future = frame.iloc[month * 15 :]
        for number in range(symbols):
            candidate = HistoricalCandidate(
                scan_date=scan_date,
                symbol=f"S{number}.NS",
                rank=number + 1,
                decision_score=80,
                grade="A",
                action="BUY",
                setup_type="VCP",
                market_regime="Bull",
                sector="IT",
                rs_percentile=80,
                volume_state="Healthy",
                cpr_state="Trending",
                avwap_state="Support",
                risk_grade="A",
                risk_entry_price=101,
                stop_price=99,
            )
            trades.append(evaluator.evaluate(candidate, future, config))
    builder.build(trades, config)
    elapsed = perf_counter() - started
    passed = elapsed <= 10.0
    print(f"Symbols: {symbols}")
    print(f"Scan dates: {scan_count}")
    print(f"Candidates evaluated: {len(trades)}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Candidates per second: {len(trades) / elapsed:.1f}")
    print("Memory notes: shared immutable 504-row fixture; ledger retained in memory")
    print(f"10-second ceiling: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
