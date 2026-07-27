#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from research.existing_strategy_exit_policy_edge_v1.contract import ExitPolicy, MAX_HOLD_MINUTES, TARGET_R_MULTIPLES
from research.existing_strategy_exit_policy_edge_v1.evaluator import CostModel, OptionBar, evaluate_long_option_trade, remove_top_winners, summarize


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return payload["rows"]
    raise ValueError("input must be CSV, JSON list, or {'rows': [...]} payload")


def _dt(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only exit-policy evaluation for frozen TradeBot signals")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--entry-slippage-points", type=float, default=0.0)
    parser.add_argument("--exit-slippage-points", type=float, default=0.0)
    parser.add_argument("--fixed-round-trip-rupees", type=float, default=0.0)
    parser.add_argument("--quantity", type=int, default=1)
    args = parser.parse_args()

    rows = _load_rows(args.input)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["strategy_id"]), str(row["signal_id"]))].append(row)

    costs = CostModel(
        entry_slippage_points=args.entry_slippage_points,
        exit_slippage_points=args.exit_slippage_points,
        fixed_round_trip_rupees=args.fixed_round_trip_rupees,
        quantity=args.quantity,
    )
    result: dict[str, Any] = {"input_rows": len(rows), "policies": {}}

    for target_r in TARGET_R_MULTIPLES:
        for hold in MAX_HOLD_MINUTES:
            policy = ExitPolicy(target_r=target_r, max_hold_minutes=hold)
            outcomes = []
            for (strategy_id, signal_id), signal_rows in sorted(grouped.items()):
                signal_rows.sort(key=lambda row: _dt(row["timestamp"]))
                first = signal_rows[0]
                bars = [
                    OptionBar(
                        timestamp=_dt(row["timestamp"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                    )
                    for row in signal_rows
                ]
                outcomes.append(
                    evaluate_long_option_trade(
                        strategy_id=strategy_id,
                        signal_id=signal_id,
                        bars=bars,
                        entry_price=float(first.get("entry_price", first["open"])),
                        risk_points=float(first["risk_points"]),
                        policy=policy,
                        costs=costs,
                    )
                )
            result["policies"][policy.policy_id] = {
                "summary": summarize(outcomes),
                "top_3_removed_summary": summarize(remove_top_winners(outcomes, 3)),
            }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
