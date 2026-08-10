#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

from run_same_corpus_ohlc_feature_discovery_v4 import load_market_rows_with_bars, compute_v4_outcome, evaluate_v4_predicate_tree, summarize
from same_corpus_ohlc_features_v4 import compute_bar_features, compute_session_features, compute_prior_session_features
from collections import defaultdict

def run_v4_negative_controls(
    dataset_path: Path,
    episodes_path: Path,
    target_candidate: dict[str, Any]
) -> dict[str, Any]:
    market_rows = load_market_rows_with_bars(dataset_path)
    with episodes_path.open() as f:
        episodes = [json.loads(line) for line in f if line.strip()]

    session_rows_map = defaultdict(list)
    session_order = []
    for r in market_rows:
        s = str(r["session"])
        if s not in session_rows_map: session_order.append(s)
        session_rows_map[s].append(r)

    market_by_row = {int(r["row_index"]): r for r in market_rows}
    tree = target_candidate.get("predicate_tree")
    horizons = (3, 6, 12, 18)

    # 1. Real Signal Performance
    real_matches = []
    for ep in episodes:
        session = str(ep.get("session"))
        end_row_index = int(ep.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue

        bar = market_by_row[end_row_index]
        s_bars = session_rows_map[session]
        c_idx = next((i for i, b in enumerate(s_bars) if int(b["row_index"]) == end_row_index), -1)
        p_idx = session_order.index(session) - 1 if session in session_order else -1
        p_bars = session_rows_map[session_order[p_idx]] if p_idx >= 0 else []

        context = {
            "bar_features": compute_bar_features(bar),
            "session_features": compute_session_features(s_bars, c_idx),
            "prior_session_features": compute_prior_session_features(p_bars)
        }

        matched, block_reason = evaluate_v4_predicate_tree(tree, ep, context)
        if matched and not block_reason:
            outcome = compute_v4_outcome(market_rows, end_row_index, horizons)
            real_matches.append(outcome)

    real_ret6 = summarize([float(r["ret6_bps"]) for r in real_matches if r.get("ret6_bps") is not None])

    # Control 1: Wrong Time Window (OPENING_0_30 instead of PRE_CLOSE_30)
    wrong_win_tree = {
        "op": "AND",
        "conditions": [
            {"type": "session_position_window_is", "window": "OPENING_0_30"},
            {"type": "bar_body_ratio_gte", "threshold": 0.70},
            {"type": "state_present", "state": "LOWER_REJECTION"}
        ]
    }
    wrong_win_matches = []
    for ep in episodes:
        session = str(ep.get("session"))
        end_row_index = int(ep.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue

        bar = market_by_row[end_row_index]
        s_bars = session_rows_map[session]
        c_idx = next((i for i, b in enumerate(s_bars) if int(b["row_index"]) == end_row_index), -1)
        p_idx = session_order.index(session) - 1 if session in session_order else -1
        p_bars = session_rows_map[session_order[p_idx]] if p_idx >= 0 else []

        context = {
            "bar_features": compute_bar_features(bar),
            "session_features": compute_session_features(s_bars, c_idx),
            "prior_session_features": compute_prior_session_features(p_bars)
        }

        matched, block_reason = evaluate_v4_predicate_tree(wrong_win_tree, ep, context)
        if matched and not block_reason:
            outcome = compute_v4_outcome(market_rows, end_row_index, horizons)
            wrong_win_matches.append(outcome)

    wrong_win_ret6 = summarize([float(r["ret6_bps"]) for r in wrong_win_matches if r.get("ret6_bps") is not None])

    # Control 2: State Placebo (UPPER_REJECTION instead of LOWER_REJECTION)
    placebo_tree = {
        "op": "AND",
        "conditions": [
            {"type": "session_position_window_is", "window": "PRE_CLOSE_30"},
            {"type": "bar_body_ratio_gte", "threshold": 0.70},
            {"type": "state_present", "state": "UPPER_REJECTION"}
        ]
    }
    placebo_matches = []
    for ep in episodes:
        session = str(ep.get("session"))
        end_row_index = int(ep.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue

        bar = market_by_row[end_row_index]
        s_bars = session_rows_map[session]
        c_idx = next((i for i, b in enumerate(s_bars) if int(b["row_index"]) == end_row_index), -1)
        p_idx = session_order.index(session) - 1 if session in session_order else -1
        p_bars = session_rows_map[session_order[p_idx]] if p_idx >= 0 else []

        context = {
            "bar_features": compute_bar_features(bar),
            "session_features": compute_session_features(s_bars, c_idx),
            "prior_session_features": compute_prior_session_features(p_bars)
        }

        matched, block_reason = evaluate_v4_predicate_tree(placebo_tree, ep, context)
        if matched and not block_reason:
            outcome = compute_v4_outcome(market_rows, end_row_index, horizons)
            placebo_matches.append(outcome)

    placebo_ret6 = summarize([float(r["ret6_bps"]) for r in placebo_matches if r.get("ret6_bps") is not None])

    reasons = []
    if wrong_win_ret6.get("mean") is not None and real_ret6.get("mean") is not None:
        if abs(wrong_win_ret6["mean"]) >= abs(real_ret6["mean"]):
            reasons.append("WRONG_TIME_WINDOW_CONTROL_COMPARABLE_OR_STRONGER")

    if placebo_ret6.get("mean") is not None and real_ret6.get("mean") is not None:
        if abs(placebo_ret6["mean"]) >= abs(real_ret6["mean"]):
            reasons.append("STATE_PLACEBO_CONTROL_COMPARABLE_OR_STRONGER")

    verdict = "NEGATIVE_CONTROLS_SUPPORTED" if not reasons else "NEGATIVE_CONTROLS_FAILED"

    return {
        "target_candidate_id": target_candidate["candidate_id"],
        "real_signal_ret6": real_ret6,
        "wrong_window_control_ret6": wrong_win_ret6,
        "state_placebo_control_ret6": placebo_ret6,
        "verdict": verdict,
        "reasons": reasons
    }

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    v4_dir = root / "research" / "evidence" / "same_corpus_ohlc_feature_discovery_v4"

    dataset_path = root / "research" / "hypotheses" / "historical_corpus" / "kite_nifty_cache_v2" / "canonical" / "NIFTY.csv"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"
    locked_path = v4_dir / "locked_validation.json"

    with locked_path.open() as f:
        locked_data = json.load(f)

    target_entry = locked_data["results"][0]
    target_id = target_entry["candidate_id"]

    registry_path = v4_dir / "candidate_registry.jsonl"
    with registry_path.open() as f:
        all_specs = {json.loads(l)["candidate_id"]: json.loads(l) for l in f if l.strip()}

    target_cand = all_specs[target_id]
    print(f"Running Negative Controls on V4 Candidate: {target_id}...")

    ctrl_results = run_v4_negative_controls(dataset_path, episodes_path, target_cand)
    print(f"V4 Negative Controls Complete. Verdict: {ctrl_results['verdict']}")
    if ctrl_results["reasons"]:
        print(f"  Fail Reasons: {ctrl_results['reasons']}")

    with (v4_dir / "negative_controls.json").open("w") as f:
        json.dump({
            "schema_version": 1,
            "edge_claimed": False,
            "structural_edge_certified": False,
            "execution_viable": False,
            "prospective_supported": False,
            **ctrl_results
        }, f, indent=2)

    with (v4_dir / "cost_slippage_index_only.json").open("w") as f:
        json.dump({
            "schema_version": 1,
            "status": "COST_SLIPPAGE_TEST_SKIPPED_NEGATIVE_CONTROLS_FAILED",
            "edge_claimed": False,
            "execution_viable": False
        }, f, indent=2)

    with (v4_dir / "certification_status.json").open("w") as f:
        json.dump({
            "schema_version": 1,
            "candidate_id": target_id,
            "locked_validation": "SUPPORTED",
            "negative_controls": ctrl_results["verdict"],
            "structural_edge_certified": False,
            "edge_claimed": False,
            "execution_viable": False,
            "prospective_supported": False,
            "status": "STRUCTURAL_EDGE_NOT_CERTIFIED"
        }, f, indent=2)

if __name__ == "__main__":
    main()
