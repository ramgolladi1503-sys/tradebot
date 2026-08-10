#!/usr/bin/env python3
import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

RUNNER_ID = "VOLATILITY_REGIME_DEVELOPMENT_OUTCOME_V1"
SEARCH_FAMILY_ID = "VOLATILITY_REGIME_CONDITIONAL_FAMILY_V1"
OUTCOME_SCOPE = "development_sessions_only"

def load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows

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

def sessions_split(rows: list[dict[str, object]], development_fraction: float) -> tuple[set[str], set[str]]:
    sessions = sorted({str(r["session"]) for r in rows})
    cut = max(1, int(len(sessions) * development_fraction))
    return set(sessions[:cut]), set(sessions[cut:])

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates-input", default="research/evidence/behavior_discovery_engine_v2/NIFTY_volatility_regime_conditional_candidates_v1.jsonl")
    parser.add_argument("--development-output", default="research/evidence/behavior_discovery_engine_v2/NIFTY_volatility_regime_conditional_development_v1.json")
    args = parser.parse_args()
    
    root = Path(__file__).resolve().parent.parent.parent.parent
    bde2_dir = root / "research" / "evidence" / "behavior_discovery_engine_v2"
    dataset_path = root / "research" / "hypotheses" / "historical_corpus" / "kite_nifty_cache_v2" / "canonical" / "NIFTY.csv"
    episodes_path = bde2_dir / "NIFTY_behavior_episodes_v1.jsonl"
    candidates_path = root / args.candidates_input
    output_path = root / args.development_output
    
    if not dataset_path.exists() or not episodes_path.exists() or not candidates_path.exists():
        print(f"BLOCKED: Missing required inputs")
        sys.exit(1)
        
    market_rows = load_market_rows(dataset_path)
    episodes = load_jsonl(episodes_path)
    candidates = load_jsonl(candidates_path)
    
    market_by_row = {int(r["row_index"]): r for r in market_rows}
    dev_sessions, locked_sessions = sessions_split(market_rows, 0.80)
    
    candidate_matches = defaultdict(list)
    horizons = (3, 6, 12, 18)

    for episode in episodes:
        session = str(episode.get("session"))
        end_row_index = int(episode.get("end_row_index", -1))
        if end_row_index < 0 or end_row_index not in market_by_row: continue
        if session not in dev_sessions: continue
        
        seq = [str(x) for x in episode.get("state_sequence", [])]
        
        for cand in candidates:
            if cand["required_state"] not in seq: continue
            
            outcome = compute_outcome(market_rows, end_row_index, horizons)
            row = {
                "candidate_id": cand.get("candidate_id"),
                "session": session,
                **outcome
            }
            candidate_matches[cand.get("candidate_id")].append(row)
            
    supported = []
    candidate_summaries = []
    
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
        if not reasons:
            supported.append(cid)
            
        summary = {
            "candidate_id": cid,
            "required_state": cand["required_state"],
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
        candidate_summaries.append(summary)
            
    if len(supported) > 2:
        status = "DEVELOPMENT_SUPPORTED_TOO_MANY_REQUIRES_PRE_OUTCOME_NARROWING"
    elif supported:
        status = "DEVELOPMENT_STRUCTURE_SUPPORTED"
    else:
        status = "NO_DEVELOPMENT_SUPPORTED_VOLATILITY_REGIME_CONDITIONAL_CANDIDATE"
        
    out = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "search_family_id": SEARCH_FAMILY_ID,
        "development_only": True,
        "forward_outcomes_computed": True,
        "forward_outcomes_scope": OUTCOME_SCOPE,
        "locked_outcomes_accessed": False,
        "edge_claimed": False,
        "status": status,
        "supported_candidates": supported,
        "candidate_summaries": candidate_summaries
    }
    
    with output_path.open("w") as f:
        json.dump(out, f, indent=2)
        
    print(status)
        
if __name__ == "__main__":
    main()
