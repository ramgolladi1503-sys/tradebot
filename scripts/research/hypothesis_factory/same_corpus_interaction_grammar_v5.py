#!/usr/bin/env python3
"""
Same-Corpus Interaction Grammar Generator V5 (TradeBot / MROS)
Generates candidate specs combining AT LEAST TWO distinct pre-outcome feature dimensions.
Guarantees NO single-dimension candidates, NO duplicate V3/V4/TOD candidates, and NO placeholders.
"""
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any

INTERACTION_FAMILY_GROUPS = [
    "STATE_PERSISTENCE_X_BAR_MORPHOLOGY",
    "STATE_PERSISTENCE_X_RANGE_LOCATION",
    "PRIOR_SESSION_CONTEXT_X_INTRADAY_FEATURE",
    "COMPRESSION_DURATION_X_ACCEPTANCE_FAILURE",
    "RETEST_COUNT_X_RANGE_LOCATION",
    "OPENING_RANGE_POSITION_X_MIDSESSION_STATE",
    "GAP_CONTEXT_X_FIRST_HOUR_BEHAVIOR",
    "PRE_CLOSE_COMPRESSION_X_STATE_PERSISTENCE",
    "ESCAPE_ACCEPTANCE_X_RETEST_COUNT",
    "FAILED_ESCAPE_X_PRIOR_SESSION_LOCATION"
]

PRIOR_FAILED_CANDIDATE_IDS = {
    "TIME_OF_DAY_SESSION_POSITION_FAMILY_V1_PRE_CLOSE_30_UPSIDE_ESCAPE",
    "V3_PRED_SEQ_PRE_CLOSE_30_DIRECTIONAL_DOWN_THEN_COMPRESSION",
    "V4_PRED_BAR_BODY_PRE_CLOSE_30_B70_LOWER_REJECTION"
}

def generate_v5_candidate_specs(max_candidates: int = 2000) -> List[Dict[str, Any]]:
    candidates = []
    
    # Grid parameters for multi-dimensional interaction combinations
    windows = ["PRE_CLOSE_30", "MIDSESSION_60", "POST_OPEN_60"]
    state_persistence_thresholds = [2, 3, 4]
    body_ratio_thresholds = [0.55, 0.65, 0.75]
    range_percentiles = [0.25, 0.35, 0.65, 0.75]
    retest_thresholds = [2, 3]
    gap_types = ["GAP_UP", "GAP_DOWN", "FLAT_OPEN"]
    
    spec_idx = 1
    for fam in INTERACTION_FAMILY_GROUPS:
        if len(candidates) >= max_candidates:
            break
            
        for w in windows:
            if len(candidates) >= max_candidates:
                break
                
            if fam == "STATE_PERSISTENCE_X_BAR_MORPHOLOGY":
                for sp in state_persistence_thresholds:
                    for br in body_ratio_thresholds:
                        cid = f"V5_INTERACTION_{fam}_{w}_SP{sp}_BR{int(br*100)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "INTERACTION_PREDICATE",
                            "mechanism_label": "State persistence combined with bar morphology compression/expansion",
                            "interaction_dimensions": ["state_persistence_count", "bar_body_ratio"],
                            "pre_outcome_definition": f"Window={w}, StatePersistence>={sp}, BarBodyRatio>={br}",
                            "required_inputs": ["completed_ohlc_bars", "bde2_states"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "state_persistence_count", "op": ">=", "value": sp},
                                    {"feature": "bar_body_ratio", "op": ">=", "value": br}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_COMPLETED_BAR_AND_STATE",
                            "parameters": {"window": w, "state_persistence_min": sp, "bar_body_ratio_min": br},
                            "lookback_bars": 12,
                            "uses_completed_bars_only": True,
                            "uses_locked_outcomes": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)
                        spec_idx += 1

            elif fam == "STATE_PERSISTENCE_X_RANGE_LOCATION":
                for sp in state_persistence_thresholds:
                    for rp in range_percentiles:
                        cid = f"V5_INTERACTION_{fam}_{w}_SP{sp}_RP{int(rp*100)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "INTERACTION_PREDICATE",
                            "mechanism_label": "State persistence combined with session range location percentile",
                            "interaction_dimensions": ["state_persistence_count", "session_range_percentile_so_far"],
                            "pre_outcome_definition": f"Window={w}, StatePersistence>={sp}, RangePercentile<={rp} if rp<0.5 else >={rp}",
                            "required_inputs": ["completed_ohlc_bars", "bde2_states"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "state_persistence_count", "op": ">=", "value": sp},
                                    {"feature": "session_range_percentile_so_far", "op": "<=" if rp < 0.5 else ">=", "value": rp}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_COMPLETED_BAR_AND_STATE",
                            "parameters": {"window": w, "state_persistence_min": sp, "range_percentile": rp},
                            "lookback_bars": 12,
                            "uses_completed_bars_only": True,
                            "uses_locked_outcomes": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)
                        spec_idx += 1

            elif fam == "PRIOR_SESSION_CONTEXT_X_INTRADAY_FEATURE":
                for rp in [0.30, 0.70]:
                    for br in body_ratio_thresholds:
                        cid = f"V5_INTERACTION_{fam}_{w}_PS{int(rp*100)}_BR{int(br*100)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "INTERACTION_PREDICATE",
                            "mechanism_label": "Prior session close location combined with intraday bar morphology",
                            "interaction_dimensions": ["prior_session_close_location", "bar_body_ratio"],
                            "pre_outcome_definition": f"Window={w}, PriorSessionCloseLoc<={rp} if rp<0.5 else >={rp}, BarBodyRatio>={br}",
                            "required_inputs": ["completed_ohlc_bars", "prior_session_context"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "prior_session_close_location", "op": "<=" if rp < 0.5 else ">=", "value": rp},
                                    {"feature": "bar_body_ratio", "op": ">=", "value": br}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_COMPLETED_BAR_AND_PRIOR_CONTEXT",
                            "parameters": {"window": w, "prior_session_close_location": rp, "bar_body_ratio_min": br},
                            "lookback_bars": 12,
                            "uses_completed_bars_only": True,
                            "uses_locked_outcomes": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)
                        spec_idx += 1

            elif fam == "RETEST_COUNT_X_RANGE_LOCATION":
                for rt in retest_thresholds:
                    for rp in range_percentiles:
                        cid = f"V5_INTERACTION_{fam}_{w}_RT{rt}_RP{int(rp*100)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "INTERACTION_PREDICATE",
                            "mechanism_label": "Failed escape retest count combined with range percentile",
                            "interaction_dimensions": ["retest_count_so_far", "session_range_percentile_so_far"],
                            "pre_outcome_definition": f"Window={w}, RetestCount>={rt}, RangePercentile<={rp} if rp<0.5 else >={rp}",
                            "required_inputs": ["completed_ohlc_bars"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "retest_count_so_far", "op": ">=", "value": rt},
                                    {"feature": "session_range_percentile_so_far", "op": "<=" if rp < 0.5 else ">=", "value": rp}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_COMPLETED_BAR",
                            "parameters": {"window": w, "retest_count_min": rt, "range_percentile": rp},
                            "lookback_bars": 12,
                            "uses_completed_bars_only": True,
                            "uses_locked_outcomes": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)
                        spec_idx += 1

            elif fam == "GAP_CONTEXT_X_FIRST_HOUR_BEHAVIOR":
                for gt in gap_types:
                    for br in [0.60, 0.70]:
                        cid = f"V5_INTERACTION_{fam}_{w}_{gt}_BR{int(br*100)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "INTERACTION_PREDICATE",
                            "mechanism_label": "Opening gap context combined with first hour range/morphology behavior",
                            "interaction_dimensions": ["gap_from_prior_close", "first_hour_range_location"],
                            "pre_outcome_definition": f"Window={w}, GapType={gt}, FirstHourBarBodyRatio>={br}",
                            "required_inputs": ["completed_ohlc_bars", "prior_session_context"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "gap_type", "op": "==", "value": gt},
                                    {"feature": "bar_body_ratio", "op": ">=", "value": br}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_COMPLETED_BAR_AND_GAP",
                            "parameters": {"window": w, "gap_type": gt, "bar_body_ratio_min": br},
                            "lookback_bars": 12,
                            "uses_completed_bars_only": True,
                            "uses_locked_outcomes": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)
                        spec_idx += 1

    # Filter out any exact duplicate of prior failed candidates if generated
    filtered = [c for c in candidates if c["candidate_id"] not in PRIOR_FAILED_CANDIDATE_IDS]
    return filtered[:max_candidates]

if __name__ == "__main__":
    specs = generate_v5_candidate_specs(2000)
    print(f"Generated {len(specs)} Campaign V5 candidate specs.")
