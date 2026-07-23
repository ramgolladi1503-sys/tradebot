#!/usr/bin/env python3
"""Run the research-only unweighted constituent-breadth lead-lag lane."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from research.constituent_lead_lag import DataContractError
from research.constituent_lead_lag.unweighted import (
    UnweightedThresholds,
    evaluate_unweighted_first_signal_per_session,
    generate_unweighted_signal_states,
    summarize_unweighted_outcomes,
    validate_universe,
)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise DataContractError(f"unsupported table type: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--index", choices=["NIFTY", "BANKNIFTY"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    blockers = []
    if not args.bars.is_file():
        blockers.append(f"missing constituent/index bars: {args.bars}")
    if not args.universe.is_file():
        blockers.append(f"missing point-in-time constituent universe: {args.universe}")
    if blockers:
        print(json.dumps({
            "status": "NEED_CONSTITUENT_BREADTH_DATA",
            "blockers": blockers,
            "required_bar_columns": [
                "timestamp", "session", "symbol", "open", "high", "low", "close",
            ],
            "required_universe_columns": [
                "index_symbol", "constituent_symbol", "effective_from", "effective_to",
            ],
            "research_lane": "UNWEIGHTED_CONSTITUENT_BREADTH",
            "research_only": True,
            "allowed_for_live_execution": False,
        }, indent=2))
        return 2

    try:
        bars = read_table(args.bars)
        universe = read_table(args.universe)
        thresholds = UnweightedThresholds()
        clean_universe = validate_universe(
            universe,
            minimum_constituent_count=thresholds.minimum_constituent_count,
        )
        states = generate_unweighted_signal_states(
            bars,
            clean_universe,
            args.index,
            thresholds=thresholds,
        )
        trades = evaluate_unweighted_first_signal_per_session(
            states,
            bars,
            thresholds,
        )
    except (DataContractError, ValueError, KeyError) as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED_DATA_CONTRACT",
            "error": str(exc),
            "research_lane": "UNWEIGHTED_CONSTITUENT_BREADTH",
            "research_only": True,
            "allowed_for_live_execution": False,
        }, indent=2))
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    state_df = pd.DataFrame([state.to_payload() for state in states])
    trade_df = pd.DataFrame([trade.to_payload() for trade in trades])
    state_df.to_parquet(args.output / "unweighted_signal_states.parquet", index=False)
    trade_df.to_parquet(args.output / "unweighted_trade_outcomes.parquet", index=False)

    eligible_sessions = int(state_df["session"].nunique()) if len(state_df) else 0
    post_warmup_sessions = (
        int(
            state_df.loc[
                state_df["reason"] != "insufficient_lead_gap_history",
                "session",
            ].nunique()
        )
        if len(state_df)
        else 0
    )
    if eligible_sessions < thresholds.minimum_history_sessions + 1:
        status = "INSUFFICIENT_HISTORY_FOR_SIGNAL_GENERATION"
    elif eligible_sessions < 120:
        status = "PRELIMINARY_UNWEIGHTED_RESEARCH_ONLY"
    else:
        status = "UNWEIGHTED_BREADTH_RESEARCH_COMPLETE"

    snapshot_types = (
        sorted(clean_universe["snapshot_type"].dropna().astype(str).unique())
        if "snapshot_type" in clean_universe
        else []
    )
    summary = {
        "status": status,
        "index_symbol": args.index,
        "research_lane": "UNWEIGHTED_CONSTITUENT_BREADTH",
        "bars_sha256": file_hash(args.bars),
        "universe_sha256": file_hash(args.universe),
        "thresholds": thresholds.__dict__,
        "snapshot_types": snapshot_types,
        "eligible_sessions": eligible_sessions,
        "warmup_sessions_required": thresholds.minimum_history_sessions,
        "post_warmup_sessions": post_warmup_sessions,
        "historical_evaluation_ready": (
            eligible_sessions >= 120 and post_warmup_sessions >= 100
        ),
        "state_rows": len(state_df),
        "qualifying_signals": (
            int(state_df["side"].isin(["LONG", "SHORT"]).sum())
            if len(state_df)
            else 0
        ),
        "outcome_summary": summarize_unweighted_outcomes(trades),
        "research_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
    }
    (args.output / "unweighted_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
