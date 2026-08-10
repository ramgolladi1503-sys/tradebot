#!/usr/bin/env python3
import hashlib
import json
from typing import Any

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

WINDOW_CODES = ["OPENING_0_30", "OPENING_30_60", "MID_SESSION", "PRE_CLOSE_60", "PRE_CLOSE_30"]
BODY_RATIO_THRESHOLDS = [0.60, 0.75]
WICK_RATIO_THRESHOLDS = [0.35, 0.50]
RANGE_PERCENTILES = [0.80, 0.20]
PRIMARY_STATES = [
    "UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE",
    "EXPANSION", "COMPRESSION", "RANGE_BALANCE", "UPPER_REJECTION", "LOWER_REJECTION"
]

def generate_candidate_specs(max_candidates: int = 1500, max_family_groups: int = 30) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_ids = set()

    # Category 1: Bar Morphology + Window Predicates
    for w in WINDOW_CODES:
        for b_thresh in [0.50, 0.60, 0.70, 0.80]:
            for st in PRIMARY_STATES:
                cid = f"V4_PRED_BAR_BODY_{w}_B{int(b_thresh*100)}_{st}"
                if cid in seen_ids: continue
                tree = {
                    "op": "AND",
                    "conditions": [
                        {"type": "session_position_window_is", "window": w},
                        {"type": "bar_body_ratio_gte", "threshold": b_thresh},
                        {"type": "state_present", "state": st}
                    ]
                }
                spec = {
                    "candidate_id": cid,
                    "family_group": "BAR_MORPHOLOGY_STATE_INTERACTION",
                    "mechanism_label": f"Strong body ratio (>={b_thresh}) with {st} in window {w}",
                    "candidate_type": "BAR_MORPHOLOGY_PREDICATE",
                    "pre_outcome_definition": f"Window=={w} AND BarBodyRatio>={b_thresh} AND State=={st}",
                    "required_inputs": ["episodes", "ohlc_bars", "timestamps"],
                    "confirmation_time_policy": "BAR_CLOSE",
                    "window_policy": w,
                    "predicate_tree": tree,
                    "parameters": {"window": w, "threshold": b_thresh, "state": st},
                    "lookback_bars": 1,
                    "uses_completed_bars_only": True,
                    "forward_outcomes_used": False,
                    "locked_outcomes_accessed": False,
                    "edge_claimed": False
                }
                spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
                candidates.append(spec)
                seen_ids.add(cid)
                if len(candidates) >= max_candidates: return candidates

    # Category 2: Upper / Lower Wick Rejection Predicates
    for w in WINDOW_CODES:
        for w_thresh in [0.25, 0.35, 0.50]:
            for w_type, cond_type, label in [("UPPER", "upper_wick_ratio_gte", "Upper Wick"), ("LOWER", "lower_wick_ratio_gte", "Lower Wick")]:
                for st in PRIMARY_STATES:
                    cid = f"V4_PRED_WICK_{w}_{w_type}_W{int(w_thresh*100)}_{st}"
                    if cid in seen_ids: continue
                    tree = {
                        "op": "AND",
                        "conditions": [
                            {"type": "session_position_window_is", "window": w},
                            {"type": cond_type, "threshold": w_thresh},
                            {"type": "state_present", "state": st}
                        ]
                    }
                    spec = {
                        "candidate_id": cid,
                        "family_group": "WICK_REJECTION_INTERACTION",
                        "mechanism_label": f"{label} ratio (>={w_thresh}) with {st} in window {w}",
                        "candidate_type": "WICK_REJECTION_PREDICATE",
                        "pre_outcome_definition": f"Window=={w} AND {w_type}WickRatio>={w_thresh} AND State=={st}",
                        "required_inputs": ["episodes", "ohlc_bars", "timestamps"],
                        "confirmation_time_policy": "BAR_CLOSE",
                        "window_policy": w,
                        "predicate_tree": tree,
                        "parameters": {"window": w, "threshold": w_thresh, "state": st},
                        "lookback_bars": 1,
                        "uses_completed_bars_only": True,
                        "forward_outcomes_used": False,
                        "locked_outcomes_accessed": False,
                        "edge_claimed": False
                    }
                    spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
                    candidates.append(spec)
                    seen_ids.add(cid)
                    if len(candidates) >= max_candidates: return candidates

    # Category 3: Session Range Percentile Location Predicates
    for w in WINDOW_CODES:
        for p_val, cond_type, p_label in [(0.80, "range_percentile_gte", "Upper Range"), (0.70, "range_percentile_gte", "Upper Mid Range"), (0.30, "range_percentile_lte", "Lower Mid Range"), (0.20, "range_percentile_lte", "Lower Range")]:
            for st in PRIMARY_STATES:
                cid = f"V4_PRED_RANGE_LOC_{w}_{p_label.replace(' ', '_')}_{st}"
                if cid in seen_ids: continue
                tree = {
                    "op": "AND",
                    "conditions": [
                        {"type": "session_position_window_is", "window": w},
                        {"type": cond_type, "threshold": p_val},
                        {"type": "state_present", "state": st}
                    ]
                }
                spec = {
                    "candidate_id": cid,
                    "family_group": "SESSION_RANGE_LOCATION_INTERACTION",
                    "mechanism_label": f"Range percentile {p_label} ({p_val}) with {st} in window {w}",
                    "candidate_type": "RANGE_LOCATION_PREDICATE",
                    "pre_outcome_definition": f"Window=={w} AND RangePercentile=={p_val} AND State=={st}",
                    "required_inputs": ["episodes", "ohlc_bars", "timestamps"],
                    "confirmation_time_policy": "BAR_CLOSE",
                    "window_policy": w,
                    "predicate_tree": tree,
                    "parameters": {"window": w, "threshold": p_val, "state": st},
                    "lookback_bars": 1,
                    "uses_completed_bars_only": True,
                    "forward_outcomes_used": False,
                    "locked_outcomes_accessed": False,
                    "edge_claimed": False
                }
                spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
                candidates.append(spec)
                seen_ids.add(cid)
                if len(candidates) >= max_candidates: return candidates

    # Category 4: Prior Session Context Interactions
    for p_cond, label in [("prior_session_close_upper", "Prior Close Upper Third"), ("prior_session_close_lower", "Prior Close Lower Third")]:
        for w in ["OPENING_0_30", "OPENING_30_60", "PRE_CLOSE_30"]:
            for st in ["UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "EXPANSION", "COMPRESSION"]:
                cid = f"V4_PRED_PRIOR_CTX_{label.replace(' ', '_')}_{w}_{st}"
                if cid in seen_ids: continue
                tree = {
                    "op": "AND",
                    "conditions": [
                        {"type": p_cond},
                        {"type": "session_position_window_is", "window": w},
                        {"type": "state_present", "state": st}
                    ]
                }
                spec = {
                    "candidate_id": cid,
                    "family_group": "PRIOR_SESSION_CONTEXT_INTERACTION",
                    "mechanism_label": f"{label} with {st} in window {w}",
                    "candidate_type": "PRIOR_CONTEXT_PREDICATE",
                    "pre_outcome_definition": f"{p_cond} AND Window=={w} AND State=={st}",
                    "required_inputs": ["episodes", "prior_session_ohlc", "timestamps"],
                    "confirmation_time_policy": "BAR_CLOSE",
                    "window_policy": w,
                    "predicate_tree": tree,
                    "parameters": {"prior_context": p_cond, "window": w, "state": st},
                    "lookback_bars": 1,
                    "uses_completed_bars_only": True,
                    "forward_outcomes_used": False,
                    "locked_outcomes_accessed": False,
                    "edge_claimed": False
                }
                spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
                candidates.append(spec)
                seen_ids.add(cid)
                if len(candidates) >= max_candidates: return candidates

    return candidates
