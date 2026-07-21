#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


STRATEGY_ID = "MEAN_REVERSION_EXTENSION"
SUPPORTED_PNL_MODELS = {
    "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
    "DELTA_PROXY_OPTION",
}
REQUIRED_PHASE4_AUDITS = (
    (
        "phase_4_trade_ledger_audit.json",
        "TRADE_LEDGER_AUDIT_PASSED",
        "TRADE_LEDGER_AUDIT_NOT_PASSED",
    ),
    (
        "phase_4_5_truth_audit.json",
        "PHASE_4_5_TRUTH_AUDIT_PASSED",
        "PHASE_4_5_TRUTH_AUDIT_NOT_PASSED",
    ),
    (
        "phase_4_7_integrity_audit.json",
        "PHASE_4_7_INTEGRITY_AUDIT_PASSED",
        "PHASE_4_7_INTEGRITY_AUDIT_NOT_PASSED",
    ),
    (
        "phase_4_8_selection_quality_audit.json",
        "PHASE_4_8_SELECTION_QUALITY_PASSED",
        "PHASE_4_8_SELECTION_QUALITY_NOT_PASSED",
    ),
    (
        "phase_4_10_accounting_audit.json",
        "PHASE_4_10_ACCOUNTING_PASSED",
        "PHASE_4_10_ACCOUNTING_NOT_PASSED",
    ),
    (
        "phase_4_v2_structural_audit.json",
        "V2_STRUCTURAL_AUDIT_PASSED",
        "V2_STRUCTURAL_AUDIT_NOT_PASSED",
    ),
)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _required_audit_blockers(base_dir: Path) -> list[str]:
    blockers: list[str] = []
    for filename, expected, blocker in REQUIRED_PHASE4_AUDITS:
        report = _load_json(base_dir / filename)
        if not report:
            blockers.append(f"PHASE4_AUDIT_REPORT_MISSING:{filename}")
            continue
        classification = report.get("classification")
        if classification != expected:
            blockers.append(f"{blocker}:{classification or 'MISSING'}")
        blockers.extend(str(value) for value in report.get("blockers", []))
        blockers.extend(
            str(value) for value in report.get("failed_blockers", [])
        )
        blockers.extend(
            str(value) for value in report.get("suspicious_blockers", [])
        )
    return list(dict.fromkeys(blockers))


def _resolve_pnl_model(trades: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    models = {str(trade.get("pnl_model") or "").strip() for trade in trades}
    models.discard("")
    blockers: list[str] = []
    if len(models) > 1:
        blockers.append("MIXED_PNL_MODELS_IN_LEDGER")
        return None, blockers
    if not models:
        # Legacy ledgers used underlying-point gross/net fields. They remain
        # readable, but current generated ledgers always declare the model.
        return "UNDERLYING_INDEX_PROXY_FIXED_HURDLE", blockers
    model = next(iter(models))
    if model not in SUPPORTED_PNL_MODELS:
        blockers.append("UNKNOWN_PNL_MODEL_USED")
        return model, blockers
    return model, blockers


def _pnl_fields(model: str) -> tuple[str, str, str]:
    if model == "DELTA_PROXY_OPTION":
        return (
            "proxy_option_gross_pnl",
            "proxy_option_execution_cost",
            "proxy_option_net_pnl",
        )
    return (
        "underlying_gross_pnl",
        "underlying_execution_cost",
        "underlying_net_pnl_after_index_cost",
    )


def calculate_trade_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "trade_count": 0,
            "pnl_model": None,
            "blockers": [],
            "gross_pnl": 0.0,
            "costs": 0.0,
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "expectancy": 0.0,
            "profit_factor": None,
            "profit_factor_state": "NO_TRADES",
            "max_drawdown": 0.0,
            "realized_rr": 0.0,
        }

    model, blockers = _resolve_pnl_model(trades)
    effective_model = model or "UNDERLYING_INDEX_PROXY_FIXED_HURDLE"
    gross_field, cost_field, net_field = _pnl_fields(effective_model)

    gross_values = np.asarray(
        [
            float(trade.get(gross_field, trade.get("gross_pnl", 0.0)))
            for trade in trades
        ],
        dtype=float,
    )
    cost_values = np.asarray(
        [
            float(trade.get(cost_field, trade.get("costs", 0.0)))
            for trade in trades
        ],
        dtype=float,
    )
    net_values = np.asarray(
        [
            float(trade.get(net_field, trade.get("net_pnl", 0.0)))
            for trade in trades
        ],
        dtype=float,
    )

    wins = net_values[net_values > 0]
    losses = net_values[net_values <= 0]
    trade_count = len(net_values)
    win_rate = float(len(wins) / trade_count)
    average_win = float(wins.mean()) if len(wins) else 0.0
    average_loss = float(losses.mean()) if len(losses) else 0.0
    expectancy = float(net_values.mean())

    loss_sum = float(losses.sum())
    if loss_sum < 0:
        profit_factor: float | None = abs(float(wins.sum()) / loss_sum)
        profit_factor_state = "FINITE"
    elif len(wins):
        profit_factor = None
        profit_factor_state = "NO_LOSING_TRADES"
    else:
        profit_factor = 0.0
        profit_factor_state = "NO_WINNING_TRADES"

    cumulative = np.cumsum(net_values)
    running_max = np.maximum.accumulate(np.concatenate(([0.0], cumulative)))[1:]
    max_drawdown = float(np.min(cumulative - running_max))
    realized_rr = float(
        np.mean([float(trade.get("rr_realized", 0.0)) for trade in trades])
    )

    return {
        "trade_count": trade_count,
        "pnl_model": model,
        "blockers": blockers,
        "gross_pnl": float(gross_values.sum()),
        "costs": float(cost_values.sum()),
        "net_pnl": float(net_values.sum()),
        "win_rate": win_rate,
        "average_win": average_win,
        "average_loss": average_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "profit_factor_state": profit_factor_state,
        "max_drawdown": max_drawdown,
        "realized_rr": realized_rr,
    }


def _catalog_metrics(catalog: dict[str, Any]) -> dict[str, Any]:
    dates_available = catalog.get("date_range_found", [])
    trading_days = int(catalog.get("trading_days_count", len(dates_available)))
    rows_per_day = catalog.get("rows_per_day")
    symbols = catalog.get("symbols_found", [])
    symbol_count = len(symbols) if isinstance(symbols, list) and symbols else 1
    rows_processed = (
        int(trading_days * int(rows_per_day) * symbol_count)
        if rows_per_day is not None
        else None
    )
    return {
        "dates_available": dates_available,
        "trading_days": trading_days,
        "rows_per_day": rows_per_day,
        "symbol_count": symbol_count,
        "rows_processed": rows_processed,
    }


def main() -> None:
    base_dir = Path(f"runtime/strategy_validation/{STRATEGY_ID}")
    catalog = _load_json(base_dir / "historical_data_catalog.json")
    catalog_metrics = _catalog_metrics(catalog)
    has_sufficient_backtest = catalog_metrics["trading_days"] >= 30

    thresholds = _load_json(Path("configs/candidate_strategy_validation_thresholds.json"))
    minimum_wfa_windows = int(thresholds.get("minimum_wfa_windows", 6))
    min_trades = int(thresholds.get("min_trades", 30))
    min_expectancy = float(thresholds.get("min_expectancy", 0.1))

    trades = _load_jsonl(base_dir / "phase_4_trade_ledger.jsonl")
    metrics = calculate_trade_metrics(trades)
    blockers_p4 = list(metrics["blockers"])
    blockers_p4.extend(_required_audit_blockers(base_dir))

    if not has_sufficient_backtest:
        blockers_p4.append("INSUFFICIENT_HISTORICAL_DATA_FOR_BACKTEST_OR_WFA")
    if not trades:
        blockers_p4.append("PHASE4_TRADE_LEDGER_MISSING_OR_EMPTY")
    elif metrics["trade_count"] < min_trades:
        blockers_p4.append("MINIMUM_TRADE_COUNT_NOT_MET")
    if trades and metrics["expectancy"] < min_expectancy:
        blockers_p4.append("MINIMUM_EXPECTANCY_NOT_MET")

    blockers_p4 = list(dict.fromkeys(blockers_p4))
    if blockers_p4:
        verdict_p4 = (
            "FAILED"
            if "MINIMUM_EXPECTANCY_NOT_MET" in blockers_p4
            else "BLOCKED"
        )
        passed_p4 = False
    else:
        verdict_p4 = "PASSED"
        passed_p4 = True

    p4_report: dict[str, Any] = {
        "strategy_id": STRATEGY_ID,
        "phase": "phase_4",
        "phase_name": "single_strategy_research_backtest",
        "passed": passed_p4,
        "verdict": verdict_p4,
        "blockers": blockers_p4,
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False,
    }
    if trades:
        p4_report["metrics"] = {
            "trading_days_used": catalog_metrics["trading_days"],
            "rows_processed": catalog_metrics["rows_processed"],
            "rows_per_day": catalog_metrics["rows_per_day"],
            "symbol_count": catalog_metrics["symbol_count"],
            "candidate_count": metrics["trade_count"],
            "trade_count": metrics["trade_count"],
            "skipped_trades": 0,
            "gross_pnl": metrics["gross_pnl"],
            "costs": metrics["costs"],
            "net_pnl": metrics["net_pnl"],
            "win_rate": metrics["win_rate"],
            "average_win": metrics["average_win"],
            "average_loss": metrics["average_loss"],
            "expectancy": metrics["expectancy"],
            "profit_factor": metrics["profit_factor"],
            "profit_factor_state": metrics["profit_factor_state"],
            "max_drawdown": metrics["max_drawdown"],
            "average_rr": metrics["realized_rr"],
            "realized_rr": metrics["realized_rr"],
            "pnl_model": metrics["pnl_model"],
            "execution_grade": False,
        }
    write_json(base_dir / "phase_4_report.json", p4_report)

    # Phase 5 remains explicitly blocked until a strategy-specific WFA runner
    # produces real train/test windows. No placeholder window may pass.
    blockers_p5: list[str] = []
    train_windows: list[dict[str, Any]] = []
    test_windows: list[dict[str, Any]] = []
    wfa_windows_passed = 0
    wfa_windows_failed = 0
    if not passed_p4:
        blockers_p5.extend(
            ["PHASE4_NOT_PASSED", "WFA_NOT_EVALUATED_BECAUSE_PHASE4_BLOCKED"]
        )
    else:
        blockers_p5.extend(["WFA_NOT_EVALUATED", "MINIMUM_WFA_WINDOWS_NOT_MET"])
    if wfa_windows_passed + wfa_windows_failed < minimum_wfa_windows:
        if "MINIMUM_WFA_WINDOWS_NOT_MET" not in blockers_p5:
            blockers_p5.append("MINIMUM_WFA_WINDOWS_NOT_MET")

    write_json(
        base_dir / "phase_5_wfa_report.json",
        {
            "strategy_id": STRATEGY_ID,
            "phase": "phase_5_wfa",
            "phase_name": "single_strategy_walk_forward_analysis",
            "passed": False,
            "verdict": "BLOCKED",
            "phase6_shadow_candidate": False,
            "blockers": blockers_p5,
            "train_windows": train_windows,
            "test_windows": test_windows,
            "metrics": {
                "windows_passed": wfa_windows_passed,
                "windows_failed": wfa_windows_failed,
            },
            "paper_live_allowed": False,
            "live_allowed": False,
            "broker_order_allowed": False,
            "execution_allowed": False,
        },
    )

    write_json(
        base_dir / "phase6_shadow_candidate_report.json",
        {
            "classification": "NOT_PHASE6_READY",
            "phase6_shadow_candidate": False,
            "paper_live_allowed": False,
            "live_allowed": False,
            "broker_order_allowed": False,
            "execution_allowed": False,
            "blockers": ["PHASE5_WFA_NOT_PASSED"],
        },
    )
    print(f"Validated Phase 4 and Phase 5 vertical slice for {STRATEGY_ID}")


if __name__ == "__main__":
    main()
