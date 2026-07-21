#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def audit_integrity(trades: list[dict[str, Any]]) -> dict[str, Any]:
    failed_blockers: set[str] = set()
    metrics = {
        "max_trades_per_symbol_day": 0,
        "average_trades_per_active_symbol_day": 0.0,
        "same_candle_ambiguity_rate": 0.0,
        "max_episode_reentries": 0,
    }

    if not trades:
        failed_blockers.add("TRADE_LEDGER_MISSING_OR_EMPTY")
    else:
        trades_per_day_symbol: defaultdict[str, int] = defaultdict(int)
        same_candle_ambiguity = 0
        episodes_seen: defaultdict[str, int] = defaultdict(int)
        trades_by_symbol: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

        for trade in trades:
            symbol = str(trade.get("symbol") or "")
            entry_time = _parse_timestamp(trade.get("entry_time"))
            exit_time = _parse_timestamp(trade.get("exit_time"))
            if not symbol or entry_time is None or exit_time is None:
                failed_blockers.add("INVALID_TRADE_IDENTITY_OR_TIMESTAMP")
                continue
            if entry_time >= exit_time:
                failed_blockers.add("NON_POSITIVE_HOLDING_INTERVAL")
            trades_by_symbol[symbol].append(trade)
            trades_per_day_symbol[f"{symbol}_{entry_time.date().isoformat()}"] += 1

            episode_id = trade.get("extension_episode_id")
            if episode_id:
                episodes_seen[str(episode_id)] += 1
            if trade.get("exit_reason") == "SAME_CANDLE_AMBIGUOUS_ASSUMED_STOP":
                same_candle_ambiguity += 1

        for symbol_trades in trades_by_symbol.values():
            symbol_trades.sort(key=lambda item: str(item.get("entry_time") or ""))
            for previous, current in zip(symbol_trades, symbol_trades[1:]):
                previous_exit = _parse_timestamp(previous.get("exit_time"))
                current_entry = _parse_timestamp(current.get("entry_time"))
                if (
                    previous_exit is not None
                    and current_entry is not None
                    and current_entry < previous_exit
                ):
                    failed_blockers.add("OVERLAPPING_POSITION_SANITY_FAILED")

        counts = list(trades_per_day_symbol.values())
        max_trades = max(counts) if counts else 0
        average_trades = sum(counts) / len(counts) if counts else 0.0
        max_reentries = max(episodes_seen.values()) if episodes_seen else 0
        ambiguity_rate = same_candle_ambiguity / len(trades)

        metrics = {
            "max_trades_per_symbol_day": max_trades,
            "average_trades_per_active_symbol_day": average_trades,
            "same_candle_ambiguity_rate": ambiguity_rate,
            "max_episode_reentries": max_reentries,
        }
        if average_trades > 6:
            failed_blockers.add("OVERTRADING_SANITY_FAILED")
        if max_reentries > 1:
            failed_blockers.add("SAME_EXTENSION_REENTRY_FAILED")
        if ambiguity_rate > 0.1:
            failed_blockers.add("SAME_CANDLE_FILL_AMBIGUITY_TOO_HIGH")

    blockers = sorted(failed_blockers)
    return {
        "classification": (
            "PHASE_4_7_INTEGRITY_AUDIT_FAILED"
            if blockers
            else "PHASE_4_7_INTEGRITY_AUDIT_PASSED"
        ),
        "trades_analyzed": len(trades),
        "blockers": blockers,
        "metrics": metrics,
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

    report = audit_integrity(trades)
    report["strategy_id"] = args.strategy
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "phase_4_7_integrity_audit.json").write_text(
        json.dumps(report, indent=2)
    )
    markdown = [
        "# Phase 4.7 Integrity Audit",
        "",
        f"- Classification: {report['classification']}",
        f"- Trades Analyzed: {report['trades_analyzed']}",
    ]
    if report["blockers"]:
        markdown.append(f"- Blockers: {', '.join(report['blockers'])}")
    (base_dir / "phase_4_7_integrity_audit.md").write_text(
        "\n".join(markdown) + "\n"
    )
    print(
        f"Phase 4.7 Integrity Audit complete. Result: {report['classification']}"
    )


if __name__ == "__main__":
    main()
