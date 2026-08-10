#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

from run_same_corpus_ohlc_feature_discovery_v4 import load_market_rows_with_bars, compute_v4_outcome, evaluate_v4_predicate_tree
from same_corpus_ohlc_features_v4 import compute_bar_features, compute_session_features, compute_prior_session_features
from same_corpus_candidate_evaluator_v3 import sessions_split
from collections import defaultdict

def run_v4_locked_validation(
    dataset_path: Path,
    episodes_path: Path,
    narrowed_candidates: list[dict[str, Any]],
    development_fraction: float = 0.60
) -> list[dict[str, Any]]:
    market_rows = load_market_rows_with_bars(dataset_path)
    with episodes_path.open() as f:
        episodes = [json.loads(line) for line in f if line.strip()]

    session_rows_map = defaultdict(list)
    session_order = []
    for r in market_rows:
        s = str(r["session"])
        if s not in session_rows_map: session_order.append(s)
        session_rows_map[s].append(r)

    dev_sessions, locked_sessions = sessions_split(market_rows, development_fraction)
    market_by_row = {int(r["row_index"]): r for r in market_rows}
    horizons = (3, 6, 12, 18)

    locked_results = []

    for cand in narrowed_candidates:
        cid = cand.get("candidate_id")
        tree = cand.get("predicate_tree")
        matches = []

        for episode in episodes:
            session = str(episode.get("session"))
            end_row_index = int(episode.get("end_row_index", -1))
            if end_row_index < 0 or end_row_index not in market_by_row: continue
            if session not in locked_sessions: continue

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

            matched, block_reason = evaluate_v4_predicate_tree(tree, episode, context)
            if matched and not block_reason:
                outcome = compute_v4_outcome(market_rows, end_row_index, horizons)
                matches.append({"candidate_id": cid, "session": session, **outcome})

        ret6 = [float(r["ret6_bps"]) for r in matches if r.get("ret6_bps") is not None]
        ret12 = [float(r["ret12_bps"]) for r in matches if r.get("ret12_bps") is not None]

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
            "verdict": verdict,
            "reasons": reasons
        })

    return locked_results

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    v4_dir = root / "research" / "evidence" / "same_corpus_ohlc_feature_discovery_v4"

    dataset_path = root / "research" / "hypotheses" / "historical_corpus" / "kite_nifty_cache_v2" / "canonical" / "NIFTY.csv"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"
    narrowed_path = v4_dir / "pre_outcome_narrowing.json"

    with narrowed_path.open() as f:
        narrowed_specs = json.load(f).get("frozen_candidates", [])

    registry_path = v4_dir / "candidate_registry.jsonl"
    with registry_path.open() as f:
        all_specs = {json.loads(l)["candidate_id"]: json.loads(l) for l in f if l.strip()}

    frozen_candidates = [all_specs[n["candidate_id"]] for n in narrowed_specs if n["candidate_id"] in all_specs]

    print(f"Running V4 Locked OOS Validation on {len(frozen_candidates)} frozen candidates...")
    locked_results = run_v4_locked_validation(dataset_path, episodes_path, frozen_candidates)

    supported_count = sum(1 for r in locked_results if r["verdict"] == "LOCKED_VALIDATION_SUPPORTED")
    print(f"V4 Locked Validation Complete. Supported: {supported_count} / {len(frozen_candidates)}")

    with (v4_dir / "locked_validation.json").open("w") as f:
        json.dump({
            "schema_version": 1,
            "development_candidates_frozen": True,
            "locked_outcomes_accessed": True,
            "locked_supported_count": supported_count,
            "results": locked_results
        }, f, indent=2)

if __name__ == "__main__":
    main()
