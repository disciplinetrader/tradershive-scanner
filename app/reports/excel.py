"""Professional Excel output for ranked scanner results."""

from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.models.stock_result import StockResult


def generate_excel_report(results: Sequence[StockResult], destination: Path) -> Path:
    """Write ranked results to an atomic, formatted Excel workbook."""
    if not results:
        raise ValueError("Cannot generate a report without results")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")

    headers = [
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
        "Trend",
        "Volume",
        "Market",
        "Momentum",
        "Volatility",
        "AVWAP Grade",
        "AVWAP Score",
        "AVWAP State",
        "AVWAP Alignment %",
        "Industry Group",
        "Industry Rank",
        "Industry Percentile",
        "Industry Rotation",
        "Advanced Setup Score",
        "Failure Risk Score",
        "Volume Signature",
        "Pocket Pivot",
        "Decision Profile",
        "Reasons",
    ]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Momentum Scanner"
    sheet.append(headers)
    for result in results:
        row: list[int | float | str] = [
            result.rank,
            result.symbol,
            result.final_score,
            result.decision_score,
            result.decision_profile.action.value if result.decision_profile else "",
            result.decision_profile.grade.value if result.decision_profile else "",
            result.decision_profile.confidence if result.decision_profile else 0,
            " | ".join(result.decision_profile.reasons) if result.decision_profile else "",
            result.facts.stock_grade.value,
            result.facts.stock_score,
            result.facts.breadth_grade.value,
            result.facts.breadth_score,
            result.facts.breadth_profile.breadth_state.value,
            result.facts.breadth_profile.confidence,
            result.facts.cpr_profile.grade.value,
            result.facts.cpr_score,
            result.facts.cpr_profile.cpr_state.value,
            result.facts.cpr_profile.breakout_probability,
            result.facts.cpr_profile.trend_probability,
            result.facts.cpr_profile.range_probability,
            result.facts.volume_grade.value,
            result.facts.volume_score,
            result.facts.volume_profile.volume_state.value,
            result.facts.volume_profile.confidence,
            " | ".join(result.facts.volume_profile.reasons),
            result.facts.setup_type.value,
            result.facts.setup_grade.value,
            result.facts.setup_score,
            result.facts.pivot_price,
            result.facts.invalidation_price,
            result.facts.breakout_distance_percent,
            result.facts.risk_grade.value,
            result.facts.risk_score,
            result.facts.entry_price or "",
            result.facts.stop_price or "",
            (
                result.facts.available_r_multiple
                if result.facts.available_r_multiple is not None
                else ""
            ),
            result.features["relative_strength"].score,
            result.facts.relative_strength_percentile,
            result.facts.sector_name,
            result.facts.sector_rank,
            result.facts.sector_rotation.value,
            result.features["sector"].score,
            result.features["trend"].score,
            result.features["volume"].score,
            result.features["market"].score,
            result.features["momentum"].score,
            result.features["volatility"].score,
            result.facts.avwap_profile.grade.value,
            result.facts.avwap_score,
            result.facts.avwap_profile.state.value,
            result.facts.avwap_profile.alignment_score,
            result.facts.industry_group,
            result.facts.industry_group_rank,
            result.facts.industry_group_percentile,
            result.facts.industry_group_rotation.value,
            result.facts.setup_profile.advanced_setup_score,
            result.facts.setup_profile.failure_risk_score,
            result.facts.volume_profile.volume_signature.value,
            str(result.facts.volume_profile.pocket_pivot),
            (
                result.decision_profile.scanner_profile
                if result.decision_profile
                else "Momentum Breakout"
            ),
            " | ".join(result.reasons),
        ]
        sheet.append(row)

    header_fill = PatternFill("solid", fgColor="17365D")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    table = Table(displayName="ScannerResults", ref=sheet.dimensions)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)
    for index, header in enumerate(headers, 1):
        width = 80 if header == "Reasons" else max(12, min(24, len(header) + 2))
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2, min_col=3, max_col=len(headers)):
        for cell in row:
            cell.number_format = "0.00"
    situation = results[0].situation_profile
    if situation:
        summary = workbook.create_sheet("Situation Summary", 0)
        summary.append(["Situation Summary", "Value"])
        summary_rows = (
            ("Market Regime", situation.market_regime.value),
            (
                "Breadth State",
                (
                    situation.breadth_profile.breadth_state.value
                    if situation.breadth_profile
                    else "Unavailable"
                ),
            ),
            (
                "Breadth Score",
                situation.breadth_profile.score if situation.breadth_profile else 0,
            ),
            ("CPR Environment", situation.cpr_environment),
            ("CPR Breakout Participation %", situation.cpr_breakout_participation),
            ("AVWAP Environment", situation.avwap_environment.value),
            ("AVWAP Support Participation %", situation.avwap_support_participation),
            ("Trading Bias", situation.trading_bias.value),
            ("Aggression", situation.aggression.value),
            ("Market Health", situation.market_health),
            ("Risk Environment", situation.risk_environment.value),
            ("Money Flow", situation.money_flow.value),
            ("Position Sizing", situation.position_sizing_guidance.value),
            ("Maximum Open Positions", situation.recommended_maximum_open_positions),
            ("Maximum Risk Per Trade %", situation.maximum_risk_per_trade),
            ("Expected Holding Period", situation.expected_holding_period),
            (
                "Recommended Setups",
                ", ".join(item.value for item in situation.recommended_setup_types),
            ),
            ("Top 5 Sectors", ", ".join(situation.sector_leadership.top_sectors)),
            ("Bottom 5 Sectors", ", ".join(situation.sector_leadership.bottom_sectors)),
            ("Improving Sectors", ", ".join(situation.sector_leadership.improving_sectors)),
            ("Weakening Sectors", ", ".join(situation.sector_leadership.weakening_sectors)),
            ("Reasons", " | ".join(situation.reasons)),
            ("Recommended Strategy", " | ".join(situation.recommended_strategy)),
            ("Warnings", " | ".join(situation.warnings)),
        )
        for row in summary_rows:
            summary.append(row)
        for cell in summary[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = header_fill
        summary.column_dimensions["A"].width = 30
        summary.column_dimensions["B"].width = 100
    workbook.save(temporary)
    temporary.replace(destination)
    return destination
