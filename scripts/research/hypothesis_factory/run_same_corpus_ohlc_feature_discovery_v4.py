#!/usr/bin/env python3
import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from same_corpus_time_window_v3 import classify_session_position_window_v3
from same_corpus_ohlc_features_v4 import compute_bar_features, compute_session_features, compute_prior_session_features
from same_corpus_ohlc_feature_grammar_v4 import generate_candidate_specs
from validate_same_corpus_ohlc_feature_discovery_v4 import validate_v4_candidate_specs

RUNNER_ID = "SAME_CORPUS_OHLC_FEATURE_DISCOVERY_V4"

def load_market_rows_with_bars(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(raw):
        try:
            open_px = float(row["open"])
            high_px = float(row["high"])
            low_px = float(row["low"])
            close_px = float(row["close"])
        except Exception:
            continue
        if min(open_px, high_px, low_px, close_px) <= 0 or high_px < low_px:
            continue
        timestamp = row["timestamp"]
        rows.append({
            "row_index": len(rows),
            "timestamp": timestamp,
            "session": row.get("session") or timestamp[:10],
            "open": open_px,
            "high": high_px,
            "low": low_px,
            "close": close_px,
        })
    rows.sort(key=lambda r: str(r["timestamp"]))
    for idx, row in enumerate(rows):
        row["row_index"] = idx
    return rows

def evaluate_v4_condition(cond: dict[str, Any], episode: dict[str, Any], context: dict[str, Any]) -> tuple[bool, str | None]:
    c_type = cond.get("type")
    ts = episode.get("end_timestamp", "")

    if c_type == "state_present":
        seq = [str(x) for x in episode.get("state_sequence", [])]
        return (cond.get("state") in seq, None)

    elif c_type == "session_position_window_is":
        target_win = cond.get("window")
        actual_win, err_code = classify_session_position_window_v3(ts)
        if err_code: return (False, err_code)
        return (actual_win == target_win, None)

    elif c_type == "bar_body_ratio_gte":
        bar_feat = context.get("bar_features", {})
        thresh = cond.get("threshold", 0.0)
        return (bar_feat.get("bar_body_ratio", 0.0) >= thresh, None)

    elif c_type == "upper_wick_ratio_gte":
        bar_feat = context.get("bar_features", {})
        thresh = cond.get("threshold", 0.0)
        return (bar_feat.get("upper_wick_ratio", 0.0) >= thresh, None)

    elif c_type == "lower_wick_ratio_gte":
        bar_feat = context.get("bar_features", {})
        thresh = cond.get("threshold", 0.0)
        return (bar_feat.get("lower_wick_ratio", 0.0) >= thresh, None)

    elif c_type == "range_percentile_gte":
        sess_feat = context.get("session_features", {})
        thresh = cond.get("threshold", 0.0)
        return (sess_feat.get("range_percentile_so_far", 0.0) >= thresh, None)

    elif c_type == "range_percentile_lte":
        sess_feat = context.get("session_features", {})
        thresh = cond.get("threshold", 1.0)
        return (sess_feat.get("range_percentile_so_far", 1.0) <= thresh, None)

    elif c_type == "prior_session_close_upper":
        prior_feat = context.get("prior_session_features", {})
        loc = prior_feat.get("prior_session_close_location")
        if loc is None: return (False, None)
        return (loc >= 0.66, None)

    elif c_type == "prior_session_close_lower":
        prior_feat = context.get("prior_session_features", {})
        loc = prior_feat.get("prior_session_close_location")
        if loc is None: return (False, None)
        return (loc <= 0.33, None)

    else:
        return (False, "UNKNOWN_PREDICATE_TYPE")

def evaluate_v4_predicate_tree(tree: dict[str, Any], episode: dict[str, Any], context: dict[str, Any]) -> tuple[bool, str | None]:
    op = tree.get("op", "AND")
    conditions = tree.get("conditions", [])

    if op == "AND":
        for cond in conditions:
            res, block_reason = evaluate_v4_condition(cond, episode, context)
            if block_reason: return (False, block_reason)
            if not res: return (False, None)
        return (True, None)
    return (False, "UNKNOWN_PREDICATE_OPERATOR")

def bps(base: float, px: float) -> float | None:
    if base > 0 and math.isfinite(base) and math.isfinite(px):
        return (px / base - 1.0) * 10000.0
    return None

def median(values: list[float]) -> float | None:
    if not values: return None
    xs = sorted(values)
    mid = len(xs) // 2
    if len(xs) % 2: return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0

def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None

def summarize(values: list[float]) -> dict[str, Any]:
    return {"n": len(values), "mean": mean(values), "median": median(values)}

def compute_v4_outcome(market_rows: list[dict[str, Any]], row_index: int, horizons: tuple[int, ...]) -> dict[str, Any]:
    base = float(market_rows[row_index]["close"])
    result: dict[str, Any] = {}
    for horizon in horizons:
        idx = row_index + horizon
        result[f"ret{horizon}_bps"] = bps(base, float(market_rows[idx]["close"])) if idx < len(market_rows) else None
    excursion_window = market_rows[row_index + 1 : min(len(market_rows), row_index + 13)]
    up_vals = [bps(base, float(r["high"])) for r in excursion_window]
    down_vals = [bps(base, float(r["low"])) for r in excursion_window]
    result["max_up_12_bps"] = max([x for x in up_vals if x is not None], default=None)
    result["max_down_12_bps"] = min([x for x in down_vals if x is not None], default=None)
    return result

def infer_direction(ret6: float | None, ret12: float | None, up20: float, down20: float, up30: float, down30: float) -> str | None:
    if ret6 is None or ret12 is None: return None
    if ret6 >= 3.0 and ret12 >= 3.0 and (up20 - down20) >= 0.08 and (up30 - down30) >= 0.03: return "UP"
    if ret6 <= -3.0 and ret12 <= -3.0 and (down20 - up20) >= 0.08 and (down30 - up30) >= 0.03: return "DOWN"
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-candidates", type=int, default=1500)
    parser.add_argument("--max-family-groups", type=int, default=30)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    v4_dir = root / "research" / "evidence" / "same_corpus_ohlc_feature_discovery_v4"
    v4_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = root / "research" / "hypotheses" / "historical_corpus" / "kite_nifty_cache_v2" / "canonical" / "NIFTY.csv"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"

    print(f"Generating Campaign V4 candidate specs (max_candidates={args.max_candidates})...")
    candidates = generate_candidate_specs(max_candidates=args.max_candidates, max_family_groups=args.max_family_groups)
    audit_metrics = validate_v4_candidate_specs(candidates)
    print(f"Audit Metrics: Valid Specs={audit_metrics['valid_specs']}, Placeholders={audit_metrics['placeholder_specs']}")

    market_rows = load_market_rows_with_bars(dataset_path)
    with episodes_path.open() as f:
        episodes = [json.loads(line) for line in f if line.strip()]

    # Group market rows by session
    session_rows_map = defaultdict(list)
    session_order = []
    for r in market_rows:
        s = str(r["session"])
        if s not in session_rows_map:
            session_order.append(s)
        session_rows_map[s].append(r)

    # 60% Development Split
    cut = int(len(session_order) * 0.60)
    dev_sessions = set(session_order[:cut])
    market_by_row = {int(r["row_index"]): r for r in market_rows}

    # Save feature catalog
    catalog = {
        "schema_version": 1,
        "available_features": [
            "bar_body_ratio", "upper_wick_ratio", "lower_wick_ratio", "close_location_value",
            "range_percentile_so_far", "session_open_to_now_return", "prior_session_close_location"
        ]
    }
    with (v4_dir / "feature_catalog.json").open("w") as f:
        json.dump(catalog, f, indent=2)

    with (v4_dir / "candidate_registry.jsonl").open("w") as f:
        for c in candidates: f.write(json.dumps(c) + "\n")

    with (v4_dir / "candidate_registry_summary.json").open("w") as f:
        json.dump({"schema_version": 1, **audit_metrics}, f, indent=2)

    # Evaluate in Development
    candidate_matches = defaultdict(list)
    horizons = (3, 6, 12, 18)

    for cand in candidates:
        cid = cand.get("candidate_id")
        tree = cand.get("predicate_tree")

        for episode in episodes:
            session = str(episode.get("session"))
            end_row_index = int(episode.get("end_row_index", -1))
            if end_row_index < 0 or end_row_index not in market_by_row: continue
            if session not in dev_sessions: continue

            # Pre-compute bar and session features
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
                candidate_matches[cid].append({"candidate_id": cid, "session": session, **outcome})

    summaries = []
    for cand in candidates:
        cid = cand.get("candidate_id")
        rows = candidate_matches.get(cid, [])

        ret3 = [float(r["ret3_bps"]) for r in rows if r.get("ret3_bps") is not None]
        ret6 = [float(r["ret6_bps"]) for r in rows if r.get("ret6_bps") is not None]
        ret12 = [float(r["ret12_bps"]) for r in rows if r.get("ret12_bps") is not None]
        ret18 = [float(r["ret18_bps"]) for r in rows if r.get("ret18_bps") is not None]
        up12 = [float(r["max_up_12_bps"]) for r in rows if r.get("max_up_12_bps") is not None]
        down12 = [float(r["max_down_12_bps"]) for r in rows if r.get("max_down_12_bps") is not None]

        up20 = sum(1 for x in up12 if x >= 20.0) / len(up12) if up12 else 0.0
        up30 = sum(1 for x in up12 if x >= 30.0) / len(up12) if up12 else 0.0
        down20 = sum(1 for x in down12 if x <= -20.0) / len(down12) if down12 else 0.0
        down30 = sum(1 for x in down12 if x <= -30.0) / len(down12) if down12 else 0.0

        med6 = median(ret6)
        med12 = median(ret12)
        direction = infer_direction(med6, med12, up20, down20, up30, down30)
        distinct_sessions = len({str(r["session"]) for r in rows})

        reasons = []
        if len(rows) < 20: reasons.append("MIN_DEVELOPMENT_MATCHES_FAIL")
        if distinct_sessions < 15: reasons.append("MIN_DISTINCT_DEVELOPMENT_SESSIONS_FAIL")
        if med6 is None or abs(med6) < 3.0: reasons.append("RET6_MEDIAN_MAGNITUDE_GATE_FAIL")
        if med12 is None or abs(med12) < 3.0: reasons.append("RET12_MEDIAN_MAGNITUDE_GATE_FAIL")
        if med6 is not None and med12 is not None and med6 * med12 <= 0: reasons.append("RET6_RET12_SIGN_CONSISTENCY_FAIL")
        if direction == "UP":
            if (up20 - down20) < 0.08: reasons.append("UP_EXCURSION_20BPS_ASYMMETRY_FAIL")
            if (up30 - down30) < 0.03: reasons.append("UP_EXCURSION_30BPS_ASYMMETRY_FAIL")
        elif direction == "DOWN":
            if (down20 - up20) < 0.08: reasons.append("DOWN_EXCURSION_20BPS_ASYMMETRY_FAIL")
            if (down30 - up30) < 0.03: reasons.append("DOWN_EXCURSION_30BPS_ASYMMETRY_FAIL")
        else:
            reasons.append("NO_DIRECTION_INFERRED")

        verdict = "DEVELOPMENT_STRUCTURE_SUPPORTED" if not reasons else "DEVELOPMENT_STRUCTURE_REJECTED"

        summary = {
            "candidate_id": cid,
            "family_group": cand.get("family_group"),
            "candidate_type": cand.get("candidate_type"),
            "predicate_tree_hash": cand.get("semantic_hash"),
            "matches": len(rows),
            "distinct_sessions": distinct_sessions,
            "ret3_bps": summarize(ret3),
            "ret6_bps": summarize(ret6),
            "ret12_bps": summarize(ret12),
            "ret18_bps": summarize(ret18),
            "up_excursion_rate_20bps": up20,
            "down_excursion_rate_20bps": down20,
            "up_excursion_rate_30bps": up30,
            "down_excursion_rate_30bps": down30,
            "inferred_direction": direction,
            "verdict": verdict,
            "reasons": reasons
        }
        summaries.append(summary)

    survivors = [s for s in summaries if s.get("verdict") == "DEVELOPMENT_STRUCTURE_SUPPORTED"]
    print(f"Campaign V4 Development Screen Complete. {len(survivors)} / {len(candidates)} candidates supported.")

    dev_payload = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "development_only": True,
        "forward_outcomes_computed": True,
        "forward_outcomes_scope": "development_sessions_only",
        "locked_outcomes_accessed": False,
        "edge_claimed": False,
        "total_evaluated": len(summaries),
        "supported_survivors_count": len(survivors),
        "status": "DEVELOPMENT_SURVIVORS_REQUIRES_PRE_OUTCOME_NARROWING" if len(survivors) > 5 else ("DEVELOPMENT_STRUCTURE_SUPPORTED" if survivors else "NO_DEVELOPMENT_SURVIVORS"),
        "candidate_summaries": summaries
    }
    with (v4_dir / "development_screen.json").open("w") as f:
        json.dump(dev_payload, f, indent=2)

    with (v4_dir / "development_survivors.jsonl").open("w") as f:
        for s in survivors: f.write(json.dumps(s) + "\n")

    # Selection Pressure
    selection_pressure = {
        "candidate_specs_generated": len(candidates),
        "valid_candidate_specs_evaluated": audit_metrics["valid_specs"],
        "development_tests_run": len(summaries),
        "survivor_count": len(survivors),
        "selection_bias_risk": "HIGH" if len(summaries) > 200 else "MODERATE",
        "locked_gate_allowed": True
    }
    with (v4_dir / "selection_pressure.json").open("w") as f:
        json.dump(selection_pressure, f, indent=2)

    # Failure Registry
    failed_candidates = [s for s in summaries if s.get("verdict") != "DEVELOPMENT_STRUCTURE_SUPPORTED"]
    with (v4_dir / "failure_registry.md").open("w") as f:
        f.write("# Campaign V4 Feature Discovery Failure Registry\n\n")
        f.write(f"**Total Evaluated**: {len(summaries)}\n")
        f.write(f"**Failed Candidates**: {len(failed_candidates)}\n\n")
        reasons_hist = {}
        for fc in failed_candidates:
            for r in fc.get("reasons", []):
                reasons_hist[r] = reasons_hist.get(r, 0) + 1
        for r, cnt in sorted(reasons_hist.items(), key=lambda x: x[1], reverse=True):
            f.write(f"- `{r}`: {cnt} candidates\n")

    manifest = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "campaign_version": "v4",
        "campaign_endpoint": "V4_DEVELOPMENT_SCREEN_COMPLETE",
        "candidate_specs_generated": len(candidates),
        "valid_candidate_specs_evaluated": audit_metrics["valid_specs"],
        "development_tests_run": len(summaries),
        "development_survivors_count": len(survivors),
        "locked_validation_run": False,
        "edge_claimed": False,
        "execution_viable": False,
        "prospective_supported": False,
        "structural_edges_certified_count": 0
    }
    with (v4_dir / "campaign_manifest.json").open("w") as f:
        json.dump(manifest, f, indent=2)

    print("Campaign V4 Master Discovery Screen Complete.")

if __name__ == "__main__":
    main()
