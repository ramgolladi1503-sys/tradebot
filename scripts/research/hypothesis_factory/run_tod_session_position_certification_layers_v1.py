#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

RUNNER_ID = "TOD_SESSION_POSITION_CERTIFICATION_LAYERS_V1"
SEARCH_FAMILY_ID = "TIME_OF_DAY_SESSION_POSITION_FAMILY_V1"
TARGET_CANDIDATE_ID = "TIME_OF_DAY_SESSION_POSITION_FAMILY_V1_PRE_CLOSE_30_UPSIDE_ESCAPE"

def load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def load_market_rows(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    rows: list[dict[str, object]] = []
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

def summarize(values: list[float]) -> dict[str, object]:
    return {"n": len(values), "mean": mean(values), "median": median(values)}

def compute_outcome(market_rows: list[dict[str, object]], row_index: int, horizons: tuple[int, ...]) -> dict[str, object]:
    base = float(market_rows[row_index]["close"])
    result: dict[str, object] = {}
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

def evaluate_matches(rows: list[dict[str, object]], min_matches: int = 15, min_sessions: int = 10) -> tuple[dict[str, object], list[str]]:
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
    if len(rows) < min_matches: reasons.append("MIN_MATCHES_FAIL")
    if distinct_sessions < min_sessions: reasons.append("MIN_DISTINCT_SESSIONS_FAIL")
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

    summary = {
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
        "verdict": "SUPPORTED" if not reasons else "REJECTED",
        "reasons": reasons
    }
    return summary, reasons

def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    
    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    dataset_path = root / "research" / "hypotheses" / "historical_corpus" / "kite_nifty_cache_v2" / "canonical" / "NIFTY.csv"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"
    locked_evidence_path = bde2_dir / "NIFTY_tod_session_position_locked_validation_v1.json"
    
    if not dataset_path.exists() or not episodes_path.exists() or not locked_evidence_path.exists():
        print("BLOCKED: Missing required inputs")
        sys.exit(1)

    with locked_evidence_path.open() as f:
        locked_ev = json.load(f)

    if TARGET_CANDIDATE_ID not in locked_ev.get("supported_candidates", []):
        print(f"BLOCKED: Candidate {TARGET_CANDIDATE_ID} not supported in locked validation")
        sys.exit(1)

    market_rows = load_market_rows(dataset_path)
    episodes = load_jsonl(episodes_path)
    market_by_row = {int(r["row_index"]): r for r in market_rows}
    horizons = (3, 6, 12, 18)

    from build_tod_session_position_candidates_v1 import get_tod_bucket

    # Gather all episode matches for TARGET_CANDIDATE_ID
    candidate_matches = []
    for episode in episodes:
        session = str(episode.get("session"))
        end_row_index = int(episode.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue
        
        seq = [str(x) for x in episode.get("state_sequence", [])]
        tod = get_tod_bucket(episode.get("end_timestamp"))
        
        if tod == "PRE_CLOSE_30" and "UPSIDE_ESCAPE" in seq:
            outcome = compute_outcome(market_rows, end_row_index, horizons)
            row = {
                "candidate_id": TARGET_CANDIDATE_ID,
                "session": session,
                "end_timestamp": episode.get("end_timestamp"),
                "end_row_index": end_row_index,
                **outcome
            }
            candidate_matches.append(row)

    # 1. WFA & ROBUSTNESS LAYER (4 Chronological Folds)
    sessions = sorted({str(r["session"]) for r in market_rows})
    num_sessions = len(sessions)
    fold_size = num_sessions // 4
    folds = [
        ("fold_1", set(sessions[:fold_size])),
        ("fold_2", set(sessions[fold_size:2*fold_size])),
        ("fold_3", set(sessions[2*fold_size:3*fold_size])),
        ("fold_4", set(sessions[3*fold_size:]))
    ]

    fold_results = []
    passing_folds = 0
    opposite_catastrophic = False

    for fold_id, fold_sessions in folds:
        fold_matches = [r for r in candidate_matches if r["session"] in fold_sessions]
        summary, reasons = evaluate_matches(fold_matches, min_matches=15, min_sessions=10)
        summary["fold_id"] = fold_id
        summary["sessions_in_fold"] = len(fold_sessions)
        fold_results.append(summary)
        
        if not reasons:
            passing_folds += 1
        
        med6 = summary["ret6_bps"]["median"]
        if med6 is not None and med6 <= -10.0:
            opposite_catastrophic = True

    wfa_status = "WFA_ROBUSTNESS_SUPPORTED" if (passing_folds / 4.0 >= 0.60 and not opposite_catastrophic) else "WFA_ROBUSTNESS_FAILED"

    wfa_payload = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "search_family_id": SEARCH_FAMILY_ID,
        "candidate_id": TARGET_CANDIDATE_ID,
        "chronological_folds": 4,
        "candidate_definition_frozen": True,
        "minimum_passing_folds_fraction": 0.60,
        "passing_folds": passing_folds,
        "no_catastrophic_opposite_fold": not opposite_catastrophic,
        "runtime_authority": "NONE",
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "edge_claimed": False,
        "structural_edge_certified": False,
        "fold_results": fold_results,
        "status": wfa_status
    }

    wfa_path = bde2_dir / "NIFTY_tod_session_position_wfa_robustness_v1.json"
    with wfa_path.open("w") as f:
        json.dump(wfa_payload, f, indent=2)

    # 2. NEGATIVE CONTROLS LAYER
    control_results = []
    
    # Control 1: Wrong Time Bucket (MID_SESSION + UPSIDE_ESCAPE)
    c1_matches = []
    for episode in episodes:
        session = str(episode.get("session"))
        end_row_index = int(episode.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue
        seq = [str(x) for x in episode.get("state_sequence", [])]
        tod = get_tod_bucket(episode.get("end_timestamp"))
        if tod == "MID_SESSION" and "UPSIDE_ESCAPE" in seq:
            outcome = compute_outcome(market_rows, end_row_index, horizons)
            c1_matches.append({"session": session, **outcome})
    s1, r1 = evaluate_matches(c1_matches)
    s1["control_id"] = "WRONG_TIME_MID_SESSION_UPSIDE_ESCAPE"
    control_results.append(s1)

    # Control 2: Wrong State (PRE_CLOSE_30 + RANGE_BALANCE)
    c2_matches = []
    for episode in episodes:
        session = str(episode.get("session"))
        end_row_index = int(episode.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue
        seq = [str(x) for x in episode.get("state_sequence", [])]
        tod = get_tod_bucket(episode.get("end_timestamp"))
        if tod == "PRE_CLOSE_30" and "RANGE_BALANCE" in seq:
            outcome = compute_outcome(market_rows, end_row_index, horizons)
            c2_matches.append({"session": session, **outcome})
    s2, r2 = evaluate_matches(c2_matches)
    s2["control_id"] = "WRONG_STATE_PRE_CLOSE_30_RANGE_BALANCE"
    control_results.append(s2)

    # Control 3: Direction Inversion (Target matches tested for DOWN direction)
    c3_summary, c3_reasons = evaluate_matches(candidate_matches)
    # Check if it passed DOWN direction asymmetry
    c3_passed_down = ("DOWN_EXCURSION_20BPS_ASYMMETRY_FAIL" not in c3_reasons and "DOWN_EXCURSION_30BPS_ASYMMETRY_FAIL" not in c3_reasons)
    c3_summary["control_id"] = "DIRECTION_INVERSION_TEST_DOWN"
    c3_summary["passed_down_gates"] = c3_passed_down
    control_results.append(c3_summary)

    # Negative controls pass if controls FAIL the edge gates (confirming specificity)
    controls_passed = (s1["verdict"] == "REJECTED" and s2["verdict"] == "REJECTED" and not c3_passed_down)
    negative_controls_status = "NEGATIVE_CONTROLS_SUPPORTED" if controls_passed else "NEGATIVE_CONTROLS_FAILED"

    neg_payload = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "search_family_id": SEARCH_FAMILY_ID,
        "candidate_id": TARGET_CANDIDATE_ID,
        "runtime_authority": "NONE",
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "edge_claimed": False,
        "structural_edge_certified": False,
        "controls": control_results,
        "status": negative_controls_status
    }

    neg_path = bde2_dir / "NIFTY_tod_session_position_negative_controls_v1.json"
    with neg_path.open("w") as f:
        json.dump(neg_payload, f, indent=2)

    # 3. COST & SLIPPAGE LAYER (Index-bps scenarios)
    gross_med6 = locked_ev["candidate_summaries"][0]["ret6_bps"]["median"]
    gross_med12 = locked_ev["candidate_summaries"][0]["ret12_bps"]["median"]

    cost_scenarios = [2, 5, 8, 12, 20]
    cost_results = []
    for c_bps in cost_scenarios:
        net6 = gross_med6 - c_bps
        net12 = gross_med12 - c_bps
        cost_results.append({
            "cost_bps": c_bps,
            "net_ret6_bps": net6,
            "net_ret12_bps": net12,
            "survives_min_3bps_gate": (net6 >= 3.0 and net12 >= 3.0)
        })

    # Survives at least 5bps cost
    survives_cost = cost_results[1]["survives_min_3bps_gate"]
    cost_status = "COST_SLIPPAGE_SUPPORTED_INDEX_ONLY" if survives_cost else "COST_SLIPPAGE_FAILED"

    cost_payload = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "search_family_id": SEARCH_FAMILY_ID,
        "candidate_id": TARGET_CANDIDATE_ID,
        "gross_ret6_median_bps": gross_med6,
        "gross_ret12_median_bps": gross_med12,
        "cost_scenarios": cost_results,
        "execution_viable": False,
        "blocked_options_execution_data": True,
        "runtime_authority": "NONE",
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "edge_claimed": False,
        "structural_edge_certified": False,
        "status": cost_status
    }

    cost_path = bde2_dir / "NIFTY_tod_session_position_cost_slippage_v1.json"
    with cost_path.open("w") as f:
        json.dump(cost_payload, f, indent=2)

    # 4. CERTIFICATION STATUS PAYLOAD
    cert_status = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "search_family_id": SEARCH_FAMILY_ID,
        "candidate_id": TARGET_CANDIDATE_ID,
        "development_supported": True,
        "locked_supported": True,
        "wfa_robustness_status": wfa_status,
        "negative_controls_status": negative_controls_status,
        "cost_slippage_status": cost_status,
        "execution_viable": False,
        "prospective_supported": False,
        "structural_edge_certified": False,
        "edge_claimed": False,
        "runtime_authority": "NONE",
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "status": "ADVANCE_TO_OPTIONS_DATA_REQUIREMENT" if (wfa_status == "WFA_ROBUSTNESS_SUPPORTED" and negative_controls_status == "NEGATIVE_CONTROLS_SUPPORTED" and cost_status == "COST_SLIPPAGE_SUPPORTED_INDEX_ONLY") else "STRUCTURAL_EDGE_NOT_CERTIFIED",
        "next_action": "ACQUIRE_OPTIONS_DEPTH_DATA_BEFORE_EXECUTION_CERTIFICATION"
    }

    cert_path = bde2_dir / "NIFTY_tod_session_position_certification_status_v1.json"
    with cert_path.open("w") as f:
        json.dump(cert_status, f, indent=2)

    print(cert_status["status"])

if __name__ == "__main__":
    main()
