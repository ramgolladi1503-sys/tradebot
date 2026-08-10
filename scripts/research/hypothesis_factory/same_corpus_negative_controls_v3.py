#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

from same_corpus_candidate_evaluator_v3 import load_market_rows, compute_outcome, evaluate_predicate_tree, summarize

def run_negative_controls_v3(
    dataset_path: Path,
    episodes_path: Path,
    target_candidate: dict[str, Any]
) -> dict[str, Any]:
    market_rows = load_market_rows(dataset_path)
    with episodes_path.open() as f:
        episodes = [json.loads(line) for line in f if line.strip()]

    market_by_row = {int(r["row_index"]): r for r in market_rows}
    tree = target_candidate.get("predicate_tree")
    horizons = (3, 6, 12, 18)

    # 1. Real Signal Baseline
    real_matches = []
    for ep in episodes:
        end_row_index = int(ep.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue
        matched, block_reason = evaluate_predicate_tree(tree, ep, {})
        if matched and not block_reason:
            outcome = compute_outcome(market_rows, end_row_index, horizons)
            real_matches.append(outcome)

    real_ret6 = summarize([float(r["ret6_bps"]) for r in real_matches if r.get("ret6_bps") is not None])

    # Control 1: Wrong Time Window (Opening 0_30 instead of Pre_Close_30)
    wrong_window_tree = {
        "op": "AND",
        "conditions": [
            {"type": "session_position_window_is", "window": "OPENING_0_30"},
            {"type": "state_sequence_ordered", "states": ["DIRECTIONAL_DOWN", "COMPRESSION"]}
        ]
    }
    wrong_window_matches = []
    for ep in episodes:
        end_row_index = int(ep.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue
        matched, block_reason = evaluate_predicate_tree(wrong_window_tree, ep, {})
        if matched and not block_reason:
            outcome = compute_outcome(market_rows, end_row_index, horizons)
            wrong_window_matches.append(outcome)

    wrong_window_ret6 = summarize([float(r["ret6_bps"]) for r in wrong_window_matches if r.get("ret6_bps") is not None])

    # Control 2: Direction Inversion (DIRECTIONAL_UP THEN COMPRESSION)
    inversion_tree = {
        "op": "AND",
        "conditions": [
            {"type": "session_position_window_is", "window": "PRE_CLOSE_30"},
            {"type": "state_sequence_ordered", "states": ["DIRECTIONAL_UP", "COMPRESSION"]}
        ]
    }
    inversion_matches = []
    for ep in episodes:
        end_row_index = int(ep.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue
        matched, block_reason = evaluate_predicate_tree(inversion_tree, ep, {})
        if matched and not block_reason:
            outcome = compute_outcome(market_rows, end_row_index, horizons)
            inversion_matches.append(outcome)

    inversion_ret6 = summarize([float(r["ret6_bps"]) for r in inversion_matches if r.get("ret6_bps") is not None])

    # Control evaluation
    reasons = []
    # If control performance is equal or stronger in return magnitude than the real signal, real signal fails specificity
    if wrong_window_ret6.get("mean") is not None and real_ret6.get("mean") is not None:
        if abs(wrong_window_ret6["mean"]) >= abs(real_ret6["mean"]):
            reasons.append("WRONG_TIME_WINDOW_CONTROL_COMPARABLE_OR_STRONGER")

    if inversion_ret6.get("mean") is not None and real_ret6.get("mean") is not None:
        if abs(inversion_ret6["mean"]) >= abs(real_ret6["mean"]):
            reasons.append("DIRECTION_INVERSION_CONTROL_COMPARABLE_OR_STRONGER")

    verdict = "NEGATIVE_CONTROLS_SUPPORTED" if not reasons else "NEGATIVE_CONTROLS_FAILED"

    return {
        "target_candidate_id": target_candidate["candidate_id"],
        "real_signal_ret6": real_ret6,
        "wrong_window_control_ret6": wrong_window_ret6,
        "inversion_control_ret6": inversion_ret6,
        "verdict": verdict,
        "reasons": reasons
    }

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    v3_dir = root / "research" / "evidence" / "same_corpus_massive_hypothesis_discovery_v3"
    
    dataset_path = root / "research" / "hypotheses" / "historical_corpus" / "kite_nifty_cache_v2" / "canonical" / "NIFTY.csv"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"
    locked_path = v3_dir / "locked_validation.json"

    if not locked_path.exists():
        print("Missing locked_validation.json!")
        return

    with locked_path.open() as f:
        locked_data = json.load(f)

    # Find the locked supported candidate
    supported_entry = next((c for c in locked_data.get("candidates_evaluated", []) if c["verdict"] == "LOCKED_VALIDATION_SUPPORTED"), None)
    if not supported_entry:
        print("No locked supported candidate found.")
        return

    target_id = supported_entry["candidate_id"]
    registry_path = v3_dir / "candidate_registry.jsonl"
    with registry_path.open() as f:
        all_specs = {json.loads(l)["candidate_id"]: json.loads(l) for l in f if l.strip()}

    target_candidate = all_specs[target_id]
    print(f"Running Negative Controls on Locked Supported Candidate: {target_id}...")

    ctrl_results = run_negative_controls_v3(dataset_path, episodes_path, target_candidate)
    print(f"Negative Controls Complete. Verdict: {ctrl_results['verdict']}")
    if ctrl_results["reasons"]:
        print(f"  Fail Reasons: {ctrl_results['reasons']}")

    ctrl_payload = {
        "schema_version": 1,
        "edge_claimed": False,
        "structural_edge_certified": False,
        "execution_viable": False,
        "prospective_supported": False,
        **ctrl_results
    }
    with (v3_dir / "negative_controls.json").open("w") as f:
        json.dump(ctrl_payload, f, indent=2)

if __name__ == "__main__":
    main()
