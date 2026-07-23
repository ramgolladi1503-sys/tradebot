#!/usr/bin/env python3
"""Run the research-only constituent lead-lag evaluation.

The command fails closed when point-in-time weights or aligned five-minute bars
are absent. It never backfills current constituents into historical dates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from research.constituent_lead_lag import (
    DataContractError,
    StrategyThresholds,
    evaluate_first_signal_per_session,
    generate_signal_states,
    summarize_outcomes,
)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise DataContractError(f"unsupported table type: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--index", choices=["NIFTY", "BANKNIFTY"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    blockers = []
    if not args.bars.is_file():
        blockers.append(f"missing constituent/index bars: {args.bars}")
    if not args.weights.is_file():
        blockers.append(f"missing point-in-time constituent weights: {args.weights}")
    if blockers:
        print(json.dumps({
            "status": "NEED_AUTHORITATIVE_CONSTITUENT_DATA",
            "blockers": blockers,
            "required_bar_columns": ["timestamp", "session", "symbol", "open", "high", "low", "close"],
            "required_weight_columns": ["index_symbol", "constituent_symbol", "effective_from", "effective_to", "weight"],
            "research_only": True,
            "allowed_for_live_execution": False,
        }, indent=2))
        return 2

    try:
        bars = read_table(args.bars)
        weights = read_table(args.weights)
        thresholds = StrategyThresholds()
        states = generate_signal_states(bars, weights, args.index, thresholds=thresholds)
        trades = evaluate_first_signal_per_session(states, bars, thresholds)
    except (DataContractError, ValueError, KeyError) as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED_DATA_CONTRACT",
            "error": str(exc),
            "research_only": True,
            "allowed_for_live_execution": False,
        }, indent=2))
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    state_df = pd.DataFrame([s.to_payload() for s in states])
    trade_df = pd.DataFrame([t.to_payload() for t in trades])
    state_df.to_parquet(args.output / "signal_states.parquet", index=False)
    trade_df.to_parquet(args.output / "trade_outcomes.parquet", index=False)
    summary = {
        "status": "RESEARCH_EVALUATION_COMPLETE",
        "index_symbol": args.index,
        "bars_sha256": file_hash(args.bars),
        "weights_sha256": file_hash(args.weights),
        "thresholds": thresholds.__dict__,
        "state_rows": len(state_df),
        "qualifying_signals": int(state_df["side"].isin(["LONG", "SHORT"]).sum()) if len(state_df) else 0,
        "outcome_summary": summarize_outcomes(trades),
        "research_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
