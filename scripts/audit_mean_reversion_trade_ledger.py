#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


STRATEGY_ID = "MEAN_REVERSION_EXTENSION"


def parse_iso(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def audit_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    failed_blockers: list[str] = []
    suspicious_blockers: list[str] = []

    if not trades:
        return {
            "classification": "TRADE_LEDGER_AUDIT_FAILED",
            "trade_count": 0,
            "failed_blockers": ["TRADE_LEDGER_MISSING_OR_EMPTY"],
            "suspicious_blockers": [],
            "win_rate": 0.0,
            "profit_factor": None,
            "profit_factor_state": "NO_TRADES",
        }

    wins = 0
    win_pnl = 0.0
    loss_pnl = 0.0

    for trade in trades:
        entry_time = parse_iso(trade.get("entry_time"))
        exit_time = parse_iso(trade.get("exit_time"))
        if entry_time is None or exit_time is None:
            failed_blockers.append("INVALID_ENTRY_OR_EXIT_TIMESTAMP")
        elif entry_time >= exit_time:
            failed_blockers.append("LOOKAHEAD_OR_SAME_CANDLE_FILL_RISK")

        required = (
            "entry_price",
            "exit_price",
            "direction",
            "gross_pnl",
            "costs",
            "net_pnl",
            "stop_loss",
            "rr_realized",
        )
        if any(field not in trade for field in required):
            failed_blockers.append("LEDGER_SCHEMA_REQUIRED_FIELD_MISSING")
            continue

        direction = str(trade["direction"]).upper()
        if direction not in {"LONG", "SHORT"}:
            failed_blockers.append("INVALID_DIRECTION")
            continue

        entry_price = float(trade["entry_price"])
        exit_price = float(trade["exit_price"])
        expected_gross = (
            exit_price - entry_price
            if direction == "LONG"
            else entry_price - exit_price
        )
        if abs(expected_gross - float(trade["gross_pnl"])) > 0.001:
            failed_blockers.append("PNL_MISMATCH")

        expected_net = expected_gross - float(trade["costs"])
        if abs(expected_net - float(trade["net_pnl"])) > 0.001:
            failed_blockers.append("PNL_MISMATCH")

        risk = (
            entry_price - float(trade["stop_loss"])
            if direction == "LONG"
            else float(trade["stop_loss"]) - entry_price
        )
        expected_rr = expected_gross / risk if risk > 0 else 0.0
        if abs(expected_rr - float(trade["rr_realized"])) > 0.001:
            failed_blockers.append("RR_MISMATCH")

        net_pnl = float(trade["net_pnl"])
        if net_pnl > 0:
            wins += 1
            win_pnl += net_pnl
        else:
            loss_pnl += abs(net_pnl)

    trade_count = len(trades)
    win_rate = wins / trade_count
    if win_rate == 1.0 and trade_count > 20:
        suspicious_blockers.append("SUSPICIOUS_PERFECT_WIN_RATE")

    if loss_pnl > 0:
        profit_factor: float | None = win_pnl / loss_pnl
        profit_factor_state = "FINITE"
        if profit_factor > 50:
            suspicious_blockers.append("SUSPICIOUS_PROFIT_FACTOR")
    elif win_pnl > 0:
        profit_factor = None
        profit_factor_state = "NO_LOSING_TRADES"
        if trade_count > 20:
            suspicious_blockers.append("SUSPICIOUS_NO_LOSING_TRADES")
    else:
        profit_factor = 0.0
        profit_factor_state = "NO_WINNING_TRADES"

    failed_blockers = sorted(set(failed_blockers))
    suspicious_blockers = sorted(set(suspicious_blockers))
    if failed_blockers:
        classification = "TRADE_LEDGER_AUDIT_FAILED"
    elif suspicious_blockers:
        classification = "TRADE_LEDGER_AUDIT_SUSPICIOUS"
    else:
        classification = "TRADE_LEDGER_AUDIT_PASSED"

    return {
        "classification": classification,
        "trade_count": trade_count,
        "failed_blockers": failed_blockers,
        "suspicious_blockers": suspicious_blockers,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "profit_factor_state": profit_factor_state,
    }


def main() -> None:
    base_dir = Path(f"runtime/strategy_validation/{STRATEGY_ID}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    trades: list[dict[str, Any]] = []
    if ledger_path.exists():
        for line in ledger_path.read_text().splitlines():
            if line.strip():
                trades.append(json.loads(line))

    report = audit_trades(trades)
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "phase_4_trade_ledger_audit.json").write_text(
        json.dumps(report, indent=2)
    )
    markdown = [
        "# Phase 4 Trade Ledger Audit",
        "",
        f"- Classification: {report['classification']}",
        f"- Trade Count: {report['trade_count']}",
        f"- Profit Factor State: {report['profit_factor_state']}",
    ]
    if report["failed_blockers"]:
        markdown.append(
            f"- Failed Blockers: {', '.join(report['failed_blockers'])}"
        )
    if report["suspicious_blockers"]:
        markdown.append(
            f"- Suspicious Blockers: {', '.join(report['suspicious_blockers'])}"
        )
    (base_dir / "phase_4_trade_ledger_audit.md").write_text(
        "\n".join(markdown) + "\n"
    )
    print(
        f"Audited Phase 4 trade ledger. Result: {report['classification']}"
    )


if __name__ == "__main__":
    main()
