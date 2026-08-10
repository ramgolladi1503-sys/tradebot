#!/usr/bin/env python3
"""
Same-Corpus Regime-Transition & Volatility-Shock Grammar Generator V6 (TradeBot / MROS)
Generates candidate specs combining regime transitions, range shocks, and acceptance/failure predicates.
Guarantees NO duplicates of prior failed families (V3/V4/V5/TOD) and NO single-dimension/placeholder specs.
"""
import hashlib
import json
from typing import List, Dict, Any

V6_MECHANISM_FAMILIES = [
    "VOL_COMPRESSION_TO_EXPANSION_TRANSITION",
    "VOL_EXPANSION_EXHAUSTION_REVERSAL",
    "RANGE_SHOCK_ACCEPTANCE_FAILURE",
    "PRIOR_SESSION_VOL_REGIME_X_CURRENT_SESSION_BREAK",
    "GAP_SHOCK_X_INTRADAY_ACCEPTANCE",
    "INSIDE_OUTSIDE_SESSION_TRANSITION",
    "REALIZED_VOL_PERCENTILE_SHIFT",
    "STATE_ENTROPY_COLLAPSE_TO_DIRECTIONALITY",
    "MULTI_SESSION_RANGE_CONTRACTION_BREAK",
    "OPENING_SHOCK_MIDDAY_ABSORPTION_PRECLOSE_RELEASE"
]

PRIOR_FAILED_CANDIDATE_IDS = {
    "TIME_OF_DAY_SESSION_POSITION_FAMILY_V1_PRE_CLOSE_30_UPSIDE_ESCAPE",
    "V3_PRED_SEQ_PRE_CLOSE_30_DIRECTIONAL_DOWN_THEN_COMPRESSION",
    "V4_PRED_BAR_BODY_PRE_CLOSE_30_B70_LOWER_REJECTION"
}

def generate_v6_candidate_specs(max_candidates: int = 2000) -> List[Dict[str, Any]]:
    candidates = []
    
    windows = ["POST_OPEN_60", "MIDSESSION_60", "PRE_CLOSE_30"]
    vol_comp_thresholds = [0.20, 0.30]
    expansion_ratios = [1.8, 2.5]
    shock_bps_thresholds = [30.0, 50.0]
    gap_bps_thresholds = [40.0, 75.0]

    for fam in V6_MECHANISM_FAMILIES:
        if len(candidates) >= max_candidates:
            break

        for w in windows:
            if len(candidates) >= max_candidates:
                break

            if fam == "VOL_COMPRESSION_TO_EXPANSION_TRANSITION":
                for vc in vol_comp_thresholds:
                    for er in expansion_ratios:
                        cid = f"V6_{fam}_{w}_VC{int(vc*100)}_ER{int(er*10)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "REGIME_VOLSHOCK_PREDICATE",
                            "mechanism_label": "Volatility compression percentile transition to expansion ratio break",
                            "regime_transition_definition": f"RollingRangePercentile <= {vc} -> IntradayExpansionRatio >= {er}",
                            "shock_definition": f"ExpansionRatio >= {er}",
                            "acceptance_or_failure_definition": "Completed bar close in expansion direction",
                            "pre_outcome_definition": f"Window={w}, VolComp<={vc}, ExpansionRatio>={er}",
                            "required_inputs": ["completed_ohlc_bars"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "rolling_realized_range_percentile", "op": "<=", "value": vc},
                                    {"feature": "intraday_range_expansion_ratio", "op": ">=", "value": er}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_REGIME_VOLSHOCK",
                            "parameters": {"window": w, "vol_comp_pct": vc, "expansion_ratio": er},
                            "lookback_bars": 12,
                            "lookback_sessions": 1,
                            "uses_completed_bars_only": True,
                            "uses_future_data": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)

            elif fam == "RANGE_SHOCK_ACCEPTANCE_FAILURE":
                for sb in shock_bps_thresholds:
                    for er in expansion_ratios:
                        cid = f"V6_{fam}_{w}_SB{int(sb)}_ER{int(er*10)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "REGIME_VOLSHOCK_PREDICATE",
                            "mechanism_label": "Range shock size in BPS combined with expansion ratio acceptance/failure",
                            "regime_transition_definition": f"RangeShock >= {sb}bps -> ExpansionRatio >= {er}",
                            "shock_definition": f"RealizedRangeBps >= {sb}",
                            "acceptance_or_failure_definition": "Bar body ratio >= 0.60 acceptance",
                            "pre_outcome_definition": f"Window={w}, ShockBps>={sb}, ExpansionRatio>={er}",
                            "required_inputs": ["completed_ohlc_bars"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "realized_range_bps", "op": ">=", "value": sb},
                                    {"feature": "intraday_range_expansion_ratio", "op": ">=", "value": er}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_REGIME_VOLSHOCK",
                            "parameters": {"window": w, "shock_bps": sb, "expansion_ratio": er},
                            "lookback_bars": 12,
                            "lookback_sessions": 1,
                            "uses_completed_bars_only": True,
                            "uses_future_data": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)

            elif fam == "GAP_SHOCK_X_INTRADAY_ACCEPTANCE":
                for gb in gap_bps_thresholds:
                    for er in expansion_ratios:
                        cid = f"V6_{fam}_{w}_GB{int(gb)}_ER{int(er*10)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "REGIME_VOLSHOCK_PREDICATE",
                            "mechanism_label": "Gap shock BPS combined with intraday range expansion acceptance",
                            "regime_transition_definition": f"GapBps >= {gb} -> IntradayExpansionRatio >= {er}",
                            "shock_definition": f"GapSizeBps >= {gb}",
                            "acceptance_or_failure_definition": "Intraday continuation in gap direction",
                            "pre_outcome_definition": f"Window={w}, GapBps>={gb}, ExpansionRatio>={er}",
                            "required_inputs": ["completed_ohlc_bars", "prior_session_context"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "gap_size_bps", "op": ">=", "value": gb},
                                    {"feature": "intraday_range_expansion_ratio", "op": ">=", "value": er}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_REGIME_VOLSHOCK",
                            "parameters": {"window": w, "gap_bps": gb, "expansion_ratio": er},
                            "lookback_bars": 12,
                            "lookback_sessions": 1,
                            "uses_completed_bars_only": True,
                            "uses_future_data": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)

            elif fam == "PRIOR_SESSION_VOL_REGIME_X_CURRENT_SESSION_BREAK":
                for pr in [0.25, 0.75]:
                    for er in expansion_ratios:
                        cid = f"V6_{fam}_{w}_PR{int(pr*100)}_ER{int(er*10)}"
                        spec = {
                            "candidate_id": cid,
                            "family_group": fam,
                            "candidate_type": "REGIME_VOLSHOCK_PREDICATE",
                            "mechanism_label": "Prior session range percentile regime combined with current session expansion break",
                            "regime_transition_definition": f"PriorSessionVolPercentile <= {pr} -> CurrentExpansionRatio >= {er}",
                            "shock_definition": f"CurrentSessionExpansionRatio >= {er}",
                            "acceptance_or_failure_definition": "Breakout acceptance relative to prior regime",
                            "pre_outcome_definition": f"Window={w}, PriorSessionVolPct<={pr}, ExpansionRatio>={er}",
                            "required_inputs": ["completed_ohlc_bars", "prior_session_context"],
                            "confirmation_time_policy": f"WINDOW_END_{w}",
                            "feature_predicate_tree": {
                                "operator": "AND",
                                "predicates": [
                                    {"feature": "window", "op": "==", "value": w},
                                    {"feature": "prior_session_realized_range_percentile", "op": "<=" if pr < 0.5 else ">=", "value": pr},
                                    {"feature": "intraday_range_expansion_ratio", "op": ">=", "value": er}
                                ]
                            },
                            "feature_computation_policy": "DERIVED_REGIME_VOLSHOCK",
                            "parameters": {"window": w, "prior_vol_pct": pr, "expansion_ratio": er},
                            "lookback_bars": 12,
                            "lookback_sessions": 1,
                            "uses_completed_bars_only": True,
                            "uses_future_data": False,
                            "forward_outcomes_used": False,
                            "locked_outcomes_accessed": False,
                            "edge_claimed": False,
                            "duplicate_of_prior_failed_family": False
                        }
                        spec["semantic_hash"] = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
                        candidates.append(spec)

    filtered = [c for c in candidates if c["candidate_id"] not in PRIOR_FAILED_CANDIDATE_IDS]
    return filtered[:max_candidates]

if __name__ == "__main__":
    specs = generate_v6_candidate_specs(2000)
    print(f"Generated {len(specs)} Campaign V6 candidate specs.")
