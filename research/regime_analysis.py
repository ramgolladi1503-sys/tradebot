from __future__ import annotations

from pathlib import Path
from typing import Any

from research.setup_expectancy import (
    _metric_table,
    _safe_float,
    _write_report,
    calculate_expectancy,
    load_trade_quality_rows,
)


def build_regime_analysis(
    *,
    suggestions_path: Path | None = None,
    trade_log_path: Path | None = None,
    trade_updates_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    rows = load_trade_quality_rows(
        suggestions_path=suggestions_path,
        trade_log_path=trade_log_path,
        trade_updates_path=trade_updates_path,
    )
    evaluated = [row for row in rows if _safe_float(row.get("realized_pnl")) is not None]
    report = {
        "source_trade_count": int(len(rows)),
        "evaluated_trade_count": int(len(evaluated)),
        **calculate_expectancy(evaluated),
        "performance_by_regime": _metric_table(evaluated, "regime", label="regime"),
        "performance_by_strategy": _metric_table(evaluated, "strategy", label="strategy"),
        "notes": [],
    }
    if any(str(row.get("regime") or "").strip().upper() == "UNKNOWN" for row in rows):
        report["notes"].append("missing_regime_tags_defaulted_to_UNKNOWN")
    if not evaluated:
        report["notes"].append("no_realized_trade_rows")
    _write_report(output_path, report)
    return report
