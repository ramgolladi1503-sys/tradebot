#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SUPPORTED_MODELS = {
    "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
    "DELTA_PROXY_OPTION",
}


def audit_accounting(trades: list[dict[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    if not trades:
        return {
            "classification": "PHASE_4_10_ACCOUNTING_FAILED",
            "blockers": ["TRADE_LEDGER_MISSING_OR_EMPTY"],
            "metrics": {
                "total_trades": 0,
                "pnl_model_used_for_gate": None,
                "gated_expectancy": None,
            },
        }

    models = {str(trade.get("pnl_model") or "").strip() for trade in trades}
    models.discard("")
    if not models:
        blockers.append("PNL_MODEL_MISSING")
        cost_mode = None
    elif len(models) > 1:
        blockers.append("MIXED_PNL_MODELS_IN_LEDGER")
        cost_mode = None
    else:
        cost_mode = next(iter(models))
        if cost_mode not in SUPPORTED_MODELS:
            blockers.append("UNKNOWN_COST_MODEL_USED")

    required_fields = {
        "underlying_gross_pnl",
        "underlying_net_pnl_after_index_cost",
        "proxy_option_gross_pnl",
        "proxy_option_net_pnl",
    }
    if any(not required_fields.issubset(trade) for trade in trades):
        blockers.append("DIMENSIONAL_PNL_FIELDS_MISSING")

    total_trades = len(trades)
    underlying_gross = sum(
        float(trade.get("underlying_gross_pnl", 0.0)) for trade in trades
    )
    underlying_net = sum(
        float(trade.get("underlying_net_pnl_after_index_cost", 0.0))
        for trade in trades
    )
    proxy_gross = sum(
        float(trade.get("proxy_option_gross_pnl", 0.0)) for trade in trades
    )
    proxy_net = sum(
        float(trade.get("proxy_option_net_pnl", 0.0)) for trade in trades
    )

    underlying_gross_expectancy = underlying_gross / total_trades
    underlying_net_expectancy = underlying_net / total_trades
    proxy_gross_expectancy = proxy_gross / total_trades
    proxy_net_expectancy = proxy_net / total_trades

    if cost_mode == "UNDERLYING_INDEX_PROXY_FIXED_HURDLE":
        gated_expectancy: float | None = underlying_net_expectancy
    elif cost_mode == "DELTA_PROXY_OPTION":
        gated_expectancy = proxy_net_expectancy
    else:
        gated_expectancy = None

    if gated_expectancy is not None and gated_expectancy <= 0:
        blockers.append("MINIMUM_DIMENSIONAL_EXPECTANCY_NOT_MET")

    blockers = sorted(set(blockers))
    return {
        "classification": (
            "PHASE_4_10_ACCOUNTING_FAILED"
            if blockers
            else "PHASE_4_10_ACCOUNTING_PASSED"
        ),
        "blockers": blockers,
        "metrics": {
            "total_trades": total_trades,
            "underlying_gross_expectancy": underlying_gross_expectancy,
            "underlying_net_expectancy_after_index_cost": (
                underlying_net_expectancy
            ),
            "proxy_option_gross_expectancy": proxy_gross_expectancy,
            "proxy_option_net_expectancy": proxy_net_expectancy,
            "pnl_model_used_for_gate": cost_mode,
            "gated_expectancy": gated_expectancy,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, required=True)
    args = parser.parse_args()

    base_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    trades: list[dict[str, Any]] = []
    if ledger_path.exists():
        for line in ledger_path.read_text().splitlines():
            if line.strip():
                trades.append(json.loads(line))

    report = audit_accounting(trades)
    report["strategy_id"] = args.strategy
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "phase_4_10_accounting_audit.json").write_text(
        json.dumps(report, indent=2)
    )
    print(
        f"Phase 4.10 Accounting Audit complete. Result: {report['classification']}"
    )


if __name__ == "__main__":
    main()
