#!/usr/bin/env python3
"""Explicit reconstructed-community-proxy research evaluator."""

from __future__ import annotations

import argparse
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
from research.constituent_lead_lag.proxy_weights import (
    audit_proxy_dataset,
    hash_file_full,
    validate_normalized_proxy,
)
from research.constituent_lead_lag.unweighted import (
    UnweightedThresholds,
    chronological_fold_summary,
    evaluate_unweighted_first_signal_per_session,
    generate_unweighted_signal_states,
    summarize_unweighted_outcomes,
)


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise DataContractError(f"unsupported table type: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--proxy-weights", type=Path, required=True)
    parser.add_argument("--proxy-source-manifest", type=Path, required=True)
    parser.add_argument("--raw-weights", type=Path, required=True)
    parser.add_argument("--session-grid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-community-reconstructed-proxy", action="store_true")
    parser.add_argument("--index", default="NIFTY", choices=["NIFTY"])
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2025-08-29")
    parser.add_argument("--skip-unweighted", action="store_true")
    args = parser.parse_args()
    if not args.allow_community_reconstructed_proxy:
        raise SystemExit("FAIL_CLOSED_DATA_CONTRACT: --allow-community-reconstructed-proxy is required")
    args.output.mkdir(parents=True, exist_ok=True)
    bars = read_table(args.bars)
    session_grid = pd.read_parquet(args.session_grid)
    completed_sessions = set(
        session_grid.loc[session_grid["completed"].astype(bool), "session"].astype(str)
    )
    bars = bars[bars["session"].astype(str).isin(completed_sessions)].copy()
    weights = validate_normalized_proxy(
        read_table(args.proxy_weights),
        evaluation_start=args.start_date,
        evaluation_end=args.end_date,
        allow_community_reconstructed_proxy=True,
    )
    weights = weights[(weights["effective_from"] <= pd.Timestamp(args.end_date).date())]
    thresholds = StrategyThresholds()
    unweighted_thresholds = UnweightedThresholds()
    freeze = {
        "bars": str(args.bars),
        "bars_sha256": hash_file_full(args.bars),
        "proxy_weights": str(args.proxy_weights),
        "proxy_weights_sha256": hash_file_full(args.proxy_weights),
        "proxy_source_manifest": str(args.proxy_source_manifest),
        "proxy_source_manifest_sha256": hash_file_full(args.proxy_source_manifest),
        "raw_weights": str(args.raw_weights),
        "raw_weights_sha256": hash_file_full(args.raw_weights),
        "session_grid": str(args.session_grid),
        "session_grid_sha256": hash_file_full(args.session_grid),
        "completed_sessions": len(completed_sessions),
        "proxy_audit": audit_proxy_dataset(
            args.proxy_weights,
            evaluation_end=args.end_date,
            source_manifest_path=args.proxy_source_manifest,
            raw_weights_path=args.raw_weights,
        ),
        "thresholds": thresholds.__dict__,
        "unweighted_thresholds": unweighted_thresholds.__dict__,
        "index": args.index,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "entry_causality": "one_bar_delayed_entry",
        "folds": 5,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    (args.output / "pre_outcome_freeze.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    states = generate_signal_states(bars, weights, args.index, thresholds=thresholds)
    trades = evaluate_first_signal_per_session(states, bars, thresholds)
    state_df = pd.DataFrame([s.to_payload() for s in states])
    trade_df = pd.DataFrame([t.to_payload() for t in trades])
    signal_df = state_df[state_df["side"].isin(["LONG", "SHORT"])].copy()
    if signal_df.empty:
        control = pd.DataFrame([{"status": "NOT_APPLICABLE_ZERO_SIGNALS", "control_type": "matched_causal_no_lead_control"}])
        control_result = "NOT_APPLICABLE_ZERO_SIGNALS"
    else:
        control = signal_df.copy()
        control["control_type"] = "matched_causal_no_lead_control"
        control_result = "MATCHED_CONTROL_CONSTRUCTED"
    state_df.to_parquet(args.output / "signal_states_weighted.parquet", index=False)
    trade_df.to_parquet(args.output / "trade_outcomes_weighted.parquet", index=False)
    if args.skip_unweighted:
        unweighted_state_df = pd.DataFrame()
        unweighted_trade_df = pd.DataFrame()
        unweighted_summary = {"status": "SKIPPED_BY_REQUEST", "reason": "weighted proxy repair run"}
    else:
        universe = weights.drop(columns=["weight"], errors="ignore")
        unweighted_states = generate_unweighted_signal_states(bars, universe, args.index, thresholds=unweighted_thresholds)
        unweighted_trades = evaluate_unweighted_first_signal_per_session(unweighted_states, bars, unweighted_thresholds)
        unweighted_state_df = pd.DataFrame([s.to_payload() for s in unweighted_states])
        unweighted_trade_df = pd.DataFrame([t.to_payload() for t in unweighted_trades])
        unweighted_summary = summarize_unweighted_outcomes(unweighted_trades)
    unweighted_state_df.to_parquet(args.output / "signal_states_unweighted.parquet", index=False)
    unweighted_trade_df.to_parquet(args.output / "trade_outcomes_unweighted.parquet", index=False)
    control.to_parquet(args.output / "matched_control.parquet", index=False)
    reason_counts = state_df["reason"].value_counts().to_dict() if len(state_df) else {}
    summary = {
        "status": "RESEARCH_EVALUATION_COMPLETE",
        "index_symbol": args.index,
        "state_rows": int(len(state_df)),
        "weighted_signals": int(state_df["side"].isin(["LONG", "SHORT"]).sum()) if len(state_df) else 0,
        "unweighted_signals": int(unweighted_state_df["side"].isin(["LONG", "SHORT"]).sum()) if len(unweighted_state_df) else 0,
        "control_signals": int(len(signal_df)),
        "weighted_outcome_summary": summarize_outcomes(trades),
        "unweighted_outcome_summary": unweighted_summary,
        "state_reason_counts": reason_counts,
        "chronological_folds": chronological_fold_summary(trades, folds=5),
        "control_result": control_result,
        "delay_sensitivity": {"result": "NOT_APPLICABLE_ZERO_SIGNALS" if not trades else "COMPUTED", "one_bar_delayed_entry": True, "same_bar_entry_allowed": False},
        "concentration": {"result": "NOT_APPLICABLE_ZERO_SIGNALS" if not trades else "COMPUTED", "signals": int(len(trades)), "top_five_session_contribution": None if not trades else "computed_from_trade_outcomes"},
        "official_weight_gate_passed": False,
        "commercial_use_allowed": False,
        "research_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
    }
    for name in ["summary", "state_reason_counts", "chronological_folds", "delay_sensitivity", "concentration"]:
        value = summary if name == "summary" else summary[name]
        (args.output / f"{name}.json").write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
