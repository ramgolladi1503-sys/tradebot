#!/usr/bin/env python3
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from same_corpus_time_window_v3 import classify_session_position_window_v3

def evaluate_predicate_condition(cond: dict[str, Any], episode: dict[str, Any], context: dict[str, Any]) -> tuple[bool, str | None]:
    c_type = cond.get("type")
    seq = [str(x) for x in episode.get("state_sequence", [])]
    ts = episode.get("end_timestamp", "")

    if c_type == "state_present":
        target_st = cond.get("state")
        return (target_st in seq, None)

    elif c_type == "state_sequence_ordered":
        req_states = cond.get("states", [])
        idx = 0
        for item in seq:
            if idx < len(req_states) and item == req_states[idx]:
                idx += 1
        return (idx == len(req_states), None)

    elif c_type == "session_position_window_is":
        target_win = cond.get("window")
        actual_win, err_code = classify_session_position_window_v3(ts)
        if err_code:
            return (False, err_code)
        return (actual_win == target_win, None)

    elif c_type == "volatility_regime_is":
        return (False, "BLOCKED_MISSING_REQUIRED_INPUT")

    elif c_type == "gap_direction_is":
        return (False, "BLOCKED_MISSING_REQUIRED_INPUT")

    elif c_type == "range_location_is":
        return (False, "BLOCKED_MISSING_REQUIRED_INPUT")

    elif c_type == "day_of_week_is":
        return (False, "BLOCKED_MISSING_REQUIRED_INPUT")

    else:
        return (False, "UNKNOWN_PREDICATE_TYPE")

def evaluate_predicate_tree(tree: dict[str, Any], episode: dict[str, Any], context: dict[str, Any]) -> tuple[bool, str | None]:
    op = tree.get("op", "AND")
    conditions = tree.get("conditions", [])

    if op == "AND":
        for cond in conditions:
            res, block_reason = evaluate_predicate_condition(cond, episode, context)
            if block_reason:
                return (False, block_reason)
            if not res:
                return (False, None)
        return (True, None)

    elif op == "OR":
        any_true = False
        for cond in conditions:
            res, block_reason = evaluate_predicate_condition(cond, episode, context)
            if block_reason:
                return (False, block_reason)
            if res:
                any_true = True
        return (any_true, None)

    return (False, "UNKNOWN_PREDICATE_OPERATOR")

def load_market_rows(path: Path) -> list[dict[str, Any]]:
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

def sessions_split(rows: list[dict[str, Any]], development_fraction: float = 0.60) -> tuple[set[str], set[str]]:
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

def summarize(values: list[float]) -> dict[str, Any]:
    return {"n": len(values), "mean": mean(values), "median": median(values)}

def compute_outcome(market_rows: list[dict[str, Any]], row_index: int, horizons: tuple[int, ...]) -> dict[str, Any]:
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

def evaluate_candidates_development(
    dataset_path: Path,
    episodes_path: Path,
    candidates: list[dict[str, Any]],
    development_fraction: float = 0.60
) -> list[dict[str, Any]]:
    market_rows = load_market_rows(dataset_path)
    with episodes_path.open() as f:
        episodes = [json.loads(line) for line in f if line.strip()]

    market_by_row = {int(r["row_index"]): r for r in market_rows}
    dev_sessions, locked_sessions = sessions_split(market_rows, development_fraction)

    candidate_matches = defaultdict(list)
    candidate_block_reasons = {}
    horizons = (3, 6, 12, 18)

    for cand in candidates:
        cid = cand.get("candidate_id")
        tree = cand.get("predicate_tree")
        if not tree:
            candidate_block_reasons[cid] = "MISSING_PREDICATE_TREE"
            continue

        for episode in episodes:
            session = str(episode.get("session"))
            end_row_index = int(episode.get("end_row_index", -1))
            if end_row_index < 0 or end_row_index not in market_by_row: continue
            if session not in dev_sessions: continue

            context = {}
            matched, block_reason = evaluate_predicate_tree(tree, episode, context)
            if block_reason:
                candidate_block_reasons[cid] = block_reason
                break
            if matched:
                outcome = compute_outcome(market_rows, end_row_index, horizons)
                candidate_matches[cid].append({
                    "candidate_id": cid,
                    "session": session,
                    **outcome
                })

    summaries = []
    for cand in candidates:
        cid = cand.get("candidate_id")
        block_reason = candidate_block_reasons.get(cid)
        rows = candidate_matches.get(cid, [])

        if block_reason:
            summaries.append({
                "candidate_id": cid,
                "family_group": cand.get("family_group"),
                "candidate_type": cand.get("candidate_type"),
                "predicate_tree_hash": cand.get("semantic_hash"),
                "matches": 0,
                "distinct_sessions": 0,
                "verdict": "DEVELOPMENT_STRUCTURE_REJECTED",
                "reasons": [block_reason]
            })
            continue

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

    return summaries
