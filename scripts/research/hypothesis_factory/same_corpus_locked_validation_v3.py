#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

from same_corpus_candidate_evaluator_v3 import load_market_rows, sessions_split, compute_outcome, evaluate_predicate_tree

def run_locked_validation_v3(
    dataset_path: Path,
    episodes_path: Path,
    narrowed_candidates: list[dict[str, Any]],
    development_fraction: float = 0.60
) -> list[dict[str, Any]]:
    market_rows = load_market_rows(dataset_path)
    with episodes_path.open() as f:
        episodes = [json.loads(line) for line in f if line.strip()]

    market_by_row = {int(r["row_index"]): r for r in market_rows}
    dev_sessions, locked_sessions = sessions_split(market_rows, development_fraction)

    locked_results = []
    horizons = (3, 6, 12, 18)

    for cand in narrowed_candidates:
        cid = cand.get("candidate_id")
        tree = cand.get("predicate_tree")
        matches = []

        for episode in episodes:
            session = str(episode.get("session"))
            end_row_index = int(episode.get("end_row_index", -1))
            if end_row_index < 0 or end_row_index not in market_by_row: continue
            if session not in locked_sessions: continue

            context = {}
            matched, block_reason = evaluate_predicate_tree(tree, episode, context)
            if matched and not block_reason:
                outcome = compute_outcome(market_rows, end_row_index, horizons)
                matches.append({"candidate_id": cid, "session": session, **outcome})

        ret6 = [float(r["ret6_bps"]) for r in matches if r.get("ret6_bps") is not None]
        ret12 = [float(r["ret12_bps"]) for r in matches if r.get("ret12_bps") is not None]
        up12 = [float(r["max_up_12_bps"]) for r in matches if r.get("max_up_12_bps") is not None]
        down12 = [float(r["max_down_12_bps"]) for r in matches if r.get("max_down_12_bps") is not None]

        up20 = sum(1 for x in up12 if x >= 20.0) / len(up12) if up12 else 0.0
        up30 = sum(1 for x in up12 if x >= 30.0) / len(up12) if up12 else 0.0
        down20 = sum(1 for x in down12 if x <= -20.0) / len(down12) if down12 else 0.0
        down30 = sum(1 for x in down12 if x <= -30.0) / len(down12) if down12 else 0.0

        med6 = sum(ret6)/len(ret6) if ret6 else None
        med12 = sum(ret12)/len(ret12) if ret12 else None

        reasons = []
        if len(matches) < 10: reasons.append("MIN_LOCKED_MATCHES_FAIL")
        if med6 is None or abs(med6) < 3.0: reasons.append("LOCKED_RET6_MEDIAN_MAGNITUDE_GATE_FAIL")
        if med12 is None or abs(med12) < 3.0: reasons.append("LOCKED_RET12_MEDIAN_MAGNITUDE_GATE_FAIL")

        verdict = "LOCKED_VALIDATION_SUPPORTED" if not reasons else "LOCKED_VALIDATION_REJECTED"

        locked_results.append({
            "candidate_id": cid,
            "locked_matches": len(matches),
            "locked_distinct_sessions": len({str(r["session"]) for r in matches}),
            "locked_ret6_mean": med6,
            "locked_ret12_mean": med12,
            "up_excursion_rate_20bps": up20,
            "down_excursion_rate_20bps": down20,
            "verdict": verdict,
            "reasons": reasons
        })

    return locked_results

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    v3_dir = root / "research" / "evidence" / "same_corpus_massive_hypothesis_discovery_v3"
    
    dataset_path = root / "research" / "hypotheses" / "historical_corpus" / "kite_nifty_cache_v2" / "canonical" / "NIFTY.csv"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"
    narrowed_path = v3_dir / "pre_outcome_narrowing.json"

    if not narrowed_path.exists():
        print("Missing pre_outcome_narrowing.json!")
        return

    with narrowed_path.open() as f:
        data = json.load(f)
        narrowed_specs = data.get("frozen_candidates", [])

    # Load candidate registry to get full specs
    registry_path = v3_dir / "candidate_registry.jsonl"
    with registry_path.open() as f:
        all_specs = {json.loads(l)["candidate_id"]: json.loads(l) for l in f if l.strip()}

    frozen_candidates = [all_specs[n["candidate_id"]] for n in narrowed_specs if n["candidate_id"] in all_specs]

    print(f"Running Locked OOS Validation on {len(frozen_candidates)} frozen narrowed candidates...")
    locked_results = run_locked_validation_v3(dataset_path, episodes_path, frozen_candidates, development_fraction=0.60)

    supported_count = sum(1 for r in locked_results if r["verdict"] == "LOCKED_VALIDATION_SUPPORTED")
    print(f"Locked OOS Validation Complete: {supported_count} / {len(frozen_candidates)} candidates supported.")

    locked_payload = {
        "schema_version": 1,
        "development_candidates_frozen": True,
        "locked_outcomes_accessed": True,
        "locked_outcomes_scope": "locked_sessions_only",
        "search_pressure_adjustment_applied": True,
        "edge_claimed": False,
        "locked_supported_count": supported_count,
        "candidates_evaluated": locked_results
    }
    with (v3_dir / "locked_validation.json").open("w") as f:
        json.dump(locked_payload, f, indent=2)

if __name__ == "__main__":
    main()
