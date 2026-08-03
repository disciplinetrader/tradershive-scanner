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
        "RS",
        "Percentile",
        "Trend",
        "Volume",
        "Market",
        "Momentum",
        "Volatility",
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
            result.features["relative_strength"].score,
            result.facts.relative_strength_percentile,
            result.features["trend"].score,
            result.features["volume"].score,
            result.features["market"].score,
            result.features["momentum"].score,
            result.features["volatility"].score,
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
    for row in sheet.iter_rows(min_row=2, min_col=3, max_col=10):
        for cell in row:
            cell.number_format = "0.00"
    workbook.save(temporary)
    temporary.replace(destination)
    return destination
