#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


INDEX_PROXY_MODEL = "UNDERLYING_INDEX_PROXY_FIXED_HURDLE"


def audit_truth(trades: list[dict[str, Any]]) -> dict[str, Any]:
    failed_blockers: list[str] = []
    if not trades:
        failed_blockers.append("TRADES_MISSING")
    else:
        trades_per_day: Counter[str] = Counter()
        for trade in trades:
            entry_time = str(trade.get("entry_time") or "")
            day = entry_time[:10] if len(entry_time) >= 10 else "UNKNOWN"
            trades_per_day[day] += 1

        counts = list(trades_per_day.values())
        variance = statistics.variance(counts) if len(counts) > 1 else 0.0
        if variance == 0.0 and len(counts) > 10:
            failed_blockers.append(
                "TRADE_FREQUENCY_SANITY_FAILED_MECHANICAL_MOCK"
            )

        for trade in trades:
            pnl_model = str(trade.get("pnl_model") or "").strip()
            is_index_proxy = bool(trade.get("is_index_proxy")) or (
                pnl_model == INDEX_PROXY_MODEL
            )
            if is_index_proxy:
                cost = trade.get(
                    "underlying_execution_cost", trade.get("costs")
                )
                if cost is None:
                    failed_blockers.append(
                        "OPTION_REALISM_FAILED_MISSING_INDEX_PROXY_COST"
                    )
                    break
                if float(cost) < 5.0:
                    failed_blockers.append(
                        "OPTION_REALISM_FAILED_INSUFFICIENT_INDEX_PROXY_SLIPPAGE"
                    )
                    break

    failed_blockers = sorted(set(failed_blockers))
    return {
        "classification": (
            "PHASE_4_5_TRUTH_AUDIT_FAILED"
            if failed_blockers
            else "PHASE_4_5_TRUTH_AUDIT_PASSED"
        ),
        "trades_analyzed": len(trades),
        "blockers": failed_blockers,
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

    report = audit_truth(trades)
    report["strategy_id"] = args.strategy
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "phase_4_5_truth_audit.json").write_text(
        json.dumps(report, indent=2)
    )
    markdown = [
        "# Phase 4.5 Truth Audit",
        "",
        f"- Classification: {report['classification']}",
        f"- Trades Analyzed: {report['trades_analyzed']}",
    ]
    if report["blockers"]:
        markdown.append(f"- Blockers: {', '.join(report['blockers'])}")
    (base_dir / "phase_4_5_truth_audit.md").write_text(
        "\n".join(markdown) + "\n"
    )
    print(
        f"Phase 4.5 Truth Audit complete. Result: {report['classification']}"
    )


if __name__ == "__main__":
    main()
