#!/usr/bin/env python3
import hashlib
import json
from typing import Any

def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

WINDOW_CODES = ["OPENING_0_30", "OPENING_30_60", "MID_SESSION", "PRE_CLOSE_60", "PRE_CLOSE_30"]
PRIMARY_STATES = [
    "UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE",
    "EXPANSION", "COMPRESSION", "RANGE_BALANCE", "UPPER_REJECTION", "LOWER_REJECTION",
    "DIRECTIONAL_UP", "DIRECTIONAL_DOWN", "DIRECTIONAL_ACCELERATION", "DIRECTIONAL_DECELERATION"
]
VOL_REGIMES = ["HIGH_VOL", "LOW_VOL"]
GAP_DIRECTIONS = ["GAP_UP", "GAP_DOWN", "GAP_FLAT"]
RANGE_LOCATIONS = ["UPPER_THIRD", "LOWER_THIRD", "MID_THIRD"]
DAYS_OF_WEEK = ["MON", "TUE", "WED", "THU", "FRI"]
TREND_REGIMES = ["UPTREND", "DOWNTREND", "SIDEWAYS"]

def generate_candidate_specs(max_candidates: int = 1000, max_family_groups: int = 25) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_ids = set()

    # Category 1: Window + State Predicates
    for w in WINDOW_CODES:
        for st in PRIMARY_STATES:
            cid = f"V3_PRED_WIN_STATE_{w}_{st}"
            if cid in seen_ids: continue
            tree = {
                "op": "AND",
                "conditions": [
                    {"type": "session_position_window_is", "window": w},
                    {"type": "state_present", "state": st}
                ]
            }
            spec = {
                "candidate_id": cid,
                "family_group": "WINDOW_STATE_INTERACTION",
                "mechanism_label": f"State {st} confirmed during window {w}",
                "candidate_type": "WINDOW_STATE_PREDICATE",
                "pre_outcome_definition": f"Window=={w} AND State=={st}",
                "required_inputs": ["episodes", "timestamps"],
                "confirmation_time_policy": "BAR_CLOSE",
                "window_policy": w,
                "predicate_tree": tree,
                "parameters": {"window": w, "state": st},
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "edge_claimed": False
            }
            spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
            candidates.append(spec)
            seen_ids.add(cid)
            if len(candidates) >= max_candidates: return candidates

    # Category 2: Ordered State Sequence Transitions
    for w in WINDOW_CODES:
        for s1 in PRIMARY_STATES:
            for s2 in PRIMARY_STATES:
                if s1 == s2: continue
                cid = f"V3_PRED_SEQ_{w}_{s1}_THEN_{s2}"
                if cid in seen_ids: continue
                tree = {
                    "op": "AND",
                    "conditions": [
                        {"type": "session_position_window_is", "window": w},
                        {"type": "state_sequence_ordered", "states": [s1, s2]}
                    ]
                }
                spec = {
                    "candidate_id": cid,
                    "family_group": "ORDERED_TRANSITION_MOTIF",
                    "mechanism_label": f"Ordered transition {s1} -> {s2} in window {w}",
                    "candidate_type": "SEQUENCE_TRANSITION_PREDICATE",
                    "pre_outcome_definition": f"Window=={w} AND Sequence==[{s1}, {s2}]",
                    "required_inputs": ["episodes", "timestamps"],
                    "confirmation_time_policy": "BAR_CLOSE",
                    "window_policy": w,
                    "predicate_tree": tree,
                    "parameters": {"window": w, "states": [s1, s2]},
                    "forward_outcomes_used": False,
                    "locked_outcomes_accessed": False,
                    "edge_claimed": False
                }
                spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
                candidates.append(spec)
                seen_ids.add(cid)
                if len(candidates) >= max_candidates: return candidates

    # Category 3: Multi-state combinations
    for w in WINDOW_CODES:
        for s1 in ["UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "EXPANSION", "COMPRESSION"]:
            for s2 in ["UPPER_REJECTION", "LOWER_REJECTION", "RANGE_BALANCE", "FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE"]:
                if s1 == s2: continue
                cid = f"V3_PRED_MULTI_{w}_{s1}_{s2}"
                if cid in seen_ids: continue
                tree = {
                    "op": "AND",
                    "conditions": [
                        {"type": "session_position_window_is", "window": w},
                        {"type": "state_present", "state": s1},
                        {"type": "state_present", "state": s2}
                    ]
                }
                spec = {
                    "candidate_id": cid,
                    "family_group": "MULTI_STATE_MOTIF",
                    "mechanism_label": f"Window {w} with states {s1} & {s2}",
                    "candidate_type": "MULTI_STATE_PREDICATE",
                    "pre_outcome_definition": f"Window=={w} AND State=={s1} AND State=={s2}",
                    "required_inputs": ["episodes", "timestamps"],
                    "confirmation_time_policy": "BAR_CLOSE",
                    "window_policy": w,
                    "predicate_tree": tree,
                    "parameters": {"window": w, "state1": s1, "state2": s2},
                    "forward_outcomes_used": False,
                    "locked_outcomes_accessed": False,
                    "edge_claimed": False
                }
                spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
                candidates.append(spec)
                seen_ids.add(cid)
                if len(candidates) >= max_candidates: return candidates

    return candidates
