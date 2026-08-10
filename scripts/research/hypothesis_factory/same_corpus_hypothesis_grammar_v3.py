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
        for s1 in ["COMPRESSION", "EXPANSION", "UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "UPPER_REJECTION", "LOWER_REJECTION"]:
            for s2 in ["FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE", "RANGE_BALANCE", "DIRECTIONAL_UP", "DIRECTIONAL_DOWN"]:
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
                    "parameters": {"window": w, "first_state": s1, "second_state": s2},
                    "forward_outcomes_used": False,
                    "locked_outcomes_accessed": False,
                    "edge_claimed": False
                }
                spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
                candidates.append(spec)
                seen_ids.add(cid)
                if len(candidates) >= max_candidates: return candidates

    # Category 3: Volatility Regime + State Predicates
    for vol in VOL_REGIMES:
        for st in PRIMARY_STATES:
            cid = f"V3_PRED_VOL_{vol}_{st}"
            if cid in seen_ids: continue
            tree = {
                "op": "AND",
                "conditions": [
                    {"type": "volatility_regime_is", "regime": vol},
                    {"type": "state_present", "state": st}
                ]
            }
            spec = {
                "candidate_id": cid,
                "family_group": "VOLATILITY_REGIME_MOTIF",
                "mechanism_label": f"State {st} under {vol} volatility regime",
                "candidate_type": "VOLATILITY_STATE_PREDICATE",
                "pre_outcome_definition": f"VolRegime=={vol} AND State=={st}",
                "required_inputs": ["episodes", "realized_volatility"],
                "confirmation_time_policy": "BAR_CLOSE",
                "window_policy": "FULL_SESSION",
                "predicate_tree": tree,
                "parameters": {"vol_regime": vol, "state": st},
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "edge_claimed": False
            }
            spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
            candidates.append(spec)
            seen_ids.add(cid)
            if len(candidates) >= max_candidates: return candidates

    # Category 4: Gap Direction + Opening State Predicates
    for gap in GAP_DIRECTIONS:
        for st in ["UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "FAILED_UPSIDE_ESCAPE", "FAILED_DOWNSIDE_ESCAPE", "EXPANSION"]:
            cid = f"V3_PRED_GAP_{gap}_{st}"
            if cid in seen_ids: continue
            tree = {
                "op": "AND",
                "conditions": [
                    {"type": "gap_direction_is", "direction": gap},
                    {"type": "session_position_window_is", "window": "OPENING_0_30"},
                    {"type": "state_present", "state": st}
                ]
            }
            spec = {
                "candidate_id": cid,
                "family_group": "GAP_OPENING_MOTIF",
                "mechanism_label": f"Gap {gap} with Opening State {st}",
                "candidate_type": "GAP_STATE_PREDICATE",
                "pre_outcome_definition": f"Gap=={gap} AND Window==OPENING_0_30 AND State=={st}",
                "required_inputs": ["episodes", "prior_session_close", "timestamps"],
                "confirmation_time_policy": "BAR_CLOSE",
                "window_policy": "OPENING_0_30",
                "predicate_tree": tree,
                "parameters": {"gap_direction": gap, "state": st},
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "edge_claimed": False
            }
            spec["semantic_hash"] = sha256_str(json.dumps(spec, sort_keys=True))
            candidates.append(spec)
            seen_ids.add(cid)
            if len(candidates) >= max_candidates: return candidates

    # Category 5: Multi-state combinations in Pre-Close window
    for s1 in ["UPSIDE_ESCAPE", "DOWNSIDE_ESCAPE", "EXPANSION", "COMPRESSION"]:
        for s2 in ["UPPER_REJECTION", "LOWER_REJECTION", "RANGE_BALANCE"]:
            for w in ["PRE_CLOSE_60", "PRE_CLOSE_30"]:
                cid = f"V3_PRED_PRECLOSE_{w}_{s1}_{s2}"
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
                    "family_group": "PRE_CLOSE_MULTI_STATE_MOTIF",
                    "mechanism_label": f"Pre-close window {w} with states {s1} & {s2}",
                    "candidate_type": "PRE_CLOSE_MULTI_STATE_PREDICATE",
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
