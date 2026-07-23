#!/usr/bin/env python3
"""Governed reconstructed-community-proxy research evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.constituent_lead_lag import (
    StrategyThresholds,
    evaluate_first_signal_per_session,
    generate_signal_states,
    summarize_outcomes,
)
from research.constituent_lead_lag.evidence_controls import (
    CONCENTRATION_SPEC_VERSION,
    CONTROL_SPEC_VERSION,
    DELAY_SPEC_VERSION,
    build_matched_no_lead_control,
    concentration_summary,
    delayed_entry_summary,
)
from research.constituent_lead_lag.proxy_weights import audit_proxy_dataset, hash_file_full, validate_normalized_proxy
from research.constituent_lead_lag.unweighted import (
    UnweightedThresholds,
    chronological_fold_summary,
    evaluate_unweighted_first_signal_per_session,
    generate_unweighted_signal_states,
    summarize_unweighted_outcomes,
)
from scripts.calculate_proxy_membership_coverage import calculate_frame

DECISION_TIMES = ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:15"]
FINAL_TAXONOMY = [
    "NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT",
    "PROXY_SUPPORTS_PURCHASING_AUTHORITATIVE_DATA",
    "PROXY_DOES_NOT_SUPPORT_PURCHASING_AUTHORITATIVE_DATA",
    "INSUFFICIENT_PROXY_OHLCV",
    "INSUFFICIENT_INSTRUMENT_RESOLUTION",
    "INSUFFICIENT_CONSTITUENT_COVERAGE",
    "PROXY_EVALUATION_FAILED_DATA_CONTRACT",
]


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported table type: {path}")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def frozen_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path.resolve()), "sha256": hash_file_full(path)}


def build_freeze(args: argparse.Namespace, thresholds: StrategyThresholds,
                 unweighted_thresholds: UnweightedThresholds) -> dict[str, object]:
    code_root = Path(__file__).resolve().parents[1]
    files = {
        "accepted_raw_manifest": args.accepted_manifest,
        "rejected_raw_manifest": args.rejected_manifest,
        "ticker_resolution": args.ticker_resolution,
        "instrument_master": args.instrument_master,
        "proxy_source_manifest": args.proxy_source_manifest,
        "raw_weights": args.raw_weights,
        "normalized_weights": args.proxy_weights,
        "normalized_bars": args.bars,
        "session_grid": args.session_grid,
        "session_policy": args.session_policy,
        "weighted_strategy_source": code_root / "research/constituent_lead_lag/model.py",
        "unweighted_strategy_source": code_root / "research/constituent_lead_lag/unweighted.py",
        "exact_bar_contract_source": code_root / "research/constituent_lead_lag/bar_grid.py",
        "evidence_controls_source": code_root / "research/constituent_lead_lag/evidence_controls.py",
        "weighted_runner_source": Path(__file__).resolve(),
        "coverage_source": code_root / "scripts/calculate_proxy_membership_coverage.py",
        "oracle_source": code_root / "scripts/audit_reconstructed_proxy_evidence.py",
    }
    return {
        "freeze_version": "constituent_lead_lag_proxy_v3",
        "frozen_files": {name: frozen_file(Path(path)) for name, path in files.items()},
        "campaign_window": {"start": args.start_date, "end": args.end_date},
        "index": args.index,
        "provider": "Upstox V3",
        "decision_times": DECISION_TIMES,
        "thresholds": thresholds.__dict__,
        "unweighted_thresholds": unweighted_thresholds.__dict__,
        "coverage_gates": {"count_min": 0.80, "weight_min": 0.80, "campaign_pass_rate_min": 0.95},
        "exact_bar_contract": "T,T-5m,T-10m exact timestamps",
        "control_spec": CONTROL_SPEC_VERSION,
        "delay_spec": DELAY_SPEC_VERSION,
        "concentration_spec": CONCENTRATION_SPEC_VERSION,
        "chronological_fold_spec": {"folds": 5, "order": "session_ascending"},
        "entry_causality": {"base_entry_delay_bars": 1, "sensitivity_entry_delay_bars": 2},
        "final_taxonomy": FINAL_TAXONOMY,
        "research_only": True,
        "allowed_for_live_execution": False,
        "official_weight_gate_passed": False,
    }


def determine_decision(*, completed_sessions: int, post_warmup_sessions: int,
                       coverage_summary: dict[str, object], weighted_signals: int,
                       unweighted_reported: bool) -> str:
    if completed_sessions < 120 or post_warmup_sessions < 100:
        return "INSUFFICIENT_PROXY_OHLCV"
    if float(coverage_summary.get("both_gates_pass_rate", 0.0)) < 0.95:
        return "INSUFFICIENT_CONSTITUENT_COVERAGE"
    if int(coverage_summary.get("state_count_coverage_mismatches", 1)) or int(coverage_summary.get("state_weight_coverage_mismatches", 1)):
        return "PROXY_EVALUATION_FAILED_DATA_CONTRACT"
    if weighted_signals == 0 and unweighted_reported:
        return "NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT"
    return "PROXY_EVALUATION_FAILED_DATA_CONTRACT"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--proxy-weights", type=Path, required=True)
    parser.add_argument("--proxy-source-manifest", type=Path, required=True)
    parser.add_argument("--raw-weights", type=Path, required=True)
    parser.add_argument("--session-grid", type=Path, required=True)
    parser.add_argument("--session-policy", type=Path, required=True)
    parser.add_argument("--accepted-manifest", type=Path, required=True)
    parser.add_argument("--rejected-manifest", type=Path, required=True)
    parser.add_argument("--ticker-resolution", type=Path, required=True)
    parser.add_argument("--instrument-master", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-community-reconstructed-proxy", action="store_true")
    parser.add_argument("--index", default="NIFTY", choices=["NIFTY"])
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2025-08-29")
    args = parser.parse_args()
    if not args.allow_community_reconstructed_proxy:
        raise SystemExit("FAIL_CLOSED_DATA_CONTRACT: --allow-community-reconstructed-proxy is required")

    args.output.mkdir(parents=True, exist_ok=True)
    evaluation_dir = args.output / "evaluation"
    reports_dir = args.output / "reports"
    manifests_dir = args.output / "manifests"
    evaluation_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)
    manifests_dir.mkdir(exist_ok=True)

    thresholds = StrategyThresholds()
    unweighted_thresholds = UnweightedThresholds()
    freeze = build_freeze(args, thresholds, unweighted_thresholds)
    freeze_path = args.output / "pre_outcome_freeze.json"
    write_json(freeze_path, freeze)

    bars = read_table(args.bars)
    session_grid = read_table(args.session_grid)
    completed_rows = session_grid[session_grid["session_classification"].eq("REGULAR_SESSION_COMPLETE")]
    completed_sessions = set(completed_rows["session"].astype(str))
    if session_grid["session_classification"].eq("MISSING_REQUIRED_INDEX_GRID").any():
        raise SystemExit("FAIL_CLOSED_DATA_CONTRACT: session policy missing sessions")
    bars = bars[bars["session"].astype(str).isin(completed_sessions)].copy()
    weights = validate_normalized_proxy(
        read_table(args.proxy_weights), evaluation_start=args.start_date, evaluation_end=args.end_date,
        allow_community_reconstructed_proxy=True,
    )
    weights = weights[weights["effective_from"] <= pd.Timestamp(args.end_date).date()]
    audit_proxy_dataset(args.proxy_weights, evaluation_end=args.end_date,
                        source_manifest_path=args.proxy_source_manifest, raw_weights_path=args.raw_weights)

    states = generate_signal_states(bars, weights, args.index, decision_times=DECISION_TIMES, thresholds=thresholds)
    trades = evaluate_first_signal_per_session(states, bars, thresholds)
    weighted_states = pd.DataFrame([state.to_payload() for state in states])
    weighted_trades = pd.DataFrame([trade.to_payload() for trade in trades])
    universe = weights.drop(columns=["weight"], errors="ignore")
    unweighted_states_list = generate_unweighted_signal_states(bars, universe, args.index, decision_times=DECISION_TIMES, thresholds=unweighted_thresholds)
    unweighted_trades_list = evaluate_unweighted_first_signal_per_session(unweighted_states_list, bars, unweighted_thresholds)
    unweighted_states = pd.DataFrame([state.to_payload() for state in unweighted_states_list])
    unweighted_trades = pd.DataFrame([trade.to_payload() for trade in unweighted_trades_list])

    weighted_states_path = evaluation_dir / "signal_states_weighted.parquet"
    weighted_trades_path = evaluation_dir / "trade_outcomes_weighted.parquet"
    unweighted_states_path = evaluation_dir / "signal_states_unweighted.parquet"
    unweighted_trades_path = evaluation_dir / "trade_outcomes_unweighted.parquet"
    weighted_states.to_parquet(weighted_states_path, index=False)
    weighted_trades.to_parquet(weighted_trades_path, index=False)
    unweighted_states.to_parquet(unweighted_states_path, index=False)
    unweighted_trades.to_parquet(unweighted_trades_path, index=False)

    control, control_summary = build_matched_no_lead_control(weighted_states)
    control_path = evaluation_dir / "matched_control.parquet"
    control.to_parquet(control_path, index=False)
    delayed_outcomes, delay_summary = delayed_entry_summary(states, bars, thresholds)
    delayed_path = evaluation_dir / "delayed_entry_outcomes.parquet"
    pd.DataFrame([outcome.to_payload() for outcome in delayed_outcomes]).to_parquet(delayed_path, index=False)
    concentration = concentration_summary(trades)
    folds = chronological_fold_summary(trades, folds=5)

    resolution = read_table(args.ticker_resolution)
    coverage, coverage_summary = calculate_frame(weighted_states, bars, weights, resolution, args.start_date, args.end_date)
    coverage_path = reports_dir / "membership_coverage.parquet"
    coverage.to_parquet(coverage_path, index=False)
    write_json(reports_dir / "membership_coverage_summary.json", coverage_summary)

    reason_counts = {str(k): int(v) for k, v in weighted_states["reason"].value_counts().to_dict().items()}
    unweighted_reason_counts = {str(k): int(v) for k, v in unweighted_states["reason"].value_counts().to_dict().items()}
    weighted_signals = int(weighted_states["side"].isin(["LONG", "SHORT"]).sum())
    unweighted_signals = int(unweighted_states["side"].isin(["LONG", "SHORT"]).sum())
    completed_count = len(completed_sessions)
    post_warmup = max(0, completed_count - thresholds.minimum_history_sessions)
    theoretical = completed_count * len(DECISION_TIMES)
    final_decision = determine_decision(
        completed_sessions=completed_count, post_warmup_sessions=post_warmup,
        coverage_summary=coverage_summary, weighted_signals=weighted_signals,
        unweighted_reported=len(unweighted_states) == theoretical,
    )
    summary = {
        "status": "RESEARCH_EVALUATION_COMPLETE",
        "campaign_window": {"start": args.start_date, "end": args.end_date},
        "completed_regular_sessions": completed_count,
        "post_warmup_sessions": post_warmup,
        "decision_times": DECISION_TIMES,
        "theoretical_max_state_rows": theoretical,
        "state_rows": int(len(weighted_states)),
        "unweighted_state_rows": int(len(unweighted_states)),
        "weighted_signals": weighted_signals,
        "unweighted_signals": unweighted_signals,
        "state_reason_counts": reason_counts,
        "unweighted_state_reason_counts": unweighted_reason_counts,
        "weighted_outcome_summary": summarize_outcomes(trades),
        "unweighted_outcome_summary": summarize_unweighted_outcomes(unweighted_trades_list),
        "control_result": control_summary,
        "delay_sensitivity": delay_summary,
        "concentration": concentration,
        "chronological_folds": folds,
        "coverage_summary": coverage_summary,
        "pre_outcome_freeze_sha256": hash_file_full(freeze_path),
        "official_weight_gate_passed": False,
        "commercial_use_allowed": False,
        "research_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
        "proxy_final_decision": final_decision,
    }
    summary_path = evaluation_dir / "summary.json"
    write_json(summary_path, summary)
    write_json(evaluation_dir / "control_summary.json", control_summary)
    write_json(evaluation_dir / "delay_sensitivity.json", delay_summary)
    write_json(evaluation_dir / "concentration.json", concentration)
    write_json(evaluation_dir / "chronological_folds.json", folds)

    artifact_paths = [
        weighted_states_path, weighted_trades_path, unweighted_states_path, unweighted_trades_path,
        control_path, delayed_path, coverage_path, reports_dir / "membership_coverage_summary.json",
        summary_path, evaluation_dir / "control_summary.json", evaluation_dir / "delay_sensitivity.json",
        evaluation_dir / "concentration.json", evaluation_dir / "chronological_folds.json",
    ]
    artifact_manifest = {str(path.relative_to(args.output)): hash_file_full(path) for path in artifact_paths}
    write_json(manifests_dir / "artifact_manifest.json", artifact_manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
