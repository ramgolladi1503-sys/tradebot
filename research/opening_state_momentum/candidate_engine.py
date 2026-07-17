import pandas as pd
from typing import Dict, Any, List, Optional
from .contract import STRATEGY_ID, STRATEGY_VERSION, CONTRACT_PARAMS, get_contract_hash
from .session_quality import validate_session_quality
from .features import extract_features, FeatureExtractionError
from .fingerprints import compute_candidate_fingerprint

def evaluate_session(
    session_date: str,
    nifty_df: pd.DataFrame,
    banknifty_df: pd.DataFrame,
    shock_threshold: Optional[float],
    manifest_hash: str,
    dataset_group_hash: str
) -> Dict[str, Any]:
    
    # Base candidate record
    candidate = {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "contract_hash": get_contract_hash(),
        "dataset_group_hash": dataset_group_hash,
        "source_manifest_hash": manifest_hash,
        "session_date": session_date,
        "primary_instrument": "NIFTY",
        "confirmation_instrument": "BANKNIFTY",
        "direction": "NONE",
        "candidate_accepted": False,
        "primary_rejection_reason": "NONE",
        "all_rejections": [],
        "session_quality_status": "PASSED",
        "nifty_opening_return": 0.0,
        "bnifty_opening_return": 0.0,
        "shock_threshold": shock_threshold if shock_threshold is not None else 0.0,
        "shock_percentile": CONTRACT_PARAMS["canonical_percentile"],
        "close_location": 0.0,
        "retained_move_fraction": 0.0,
        "opening_high": 0.0,
        "opening_low": 0.0,
        "opening_midpoint": 0.0,
        "session_open": 0.0,
        "opening_close": 0.0,
        "decision_close": 0.0,
        "session_anchor": 0.0,
        "anchor_type": CONTRACT_PARAMS["anchor_type"],
        "feature_cutoff_timestamp": f"{session_date}T14:45:00+05:30",
        "signal_timestamp": f"{session_date}T14:45:00+05:30",
        "earliest_legal_entry_timestamp": f"{session_date}T14:46:00+05:30",
        "source_file_identities": [],
        "candidate_fingerprint": ""
    }
    
    # 1. Quality Gates
    quality_passed, rejections = validate_session_quality(nifty_df, banknifty_df)
    if not quality_passed:
        candidate["session_quality_status"] = "FAILED"
        candidate["primary_rejection_reason"] = rejections[0]
        candidate["all_rejections"] = rejections
        candidate["candidate_fingerprint"] = compute_candidate_fingerprint(candidate)
        return candidate
        
    # 2. Feature Extraction
    try:
        f = extract_features(nifty_df, banknifty_df)
    except FeatureExtractionError as e:
        candidate["primary_rejection_reason"] = str(e)
        candidate["all_rejections"] = [str(e)]
        candidate["candidate_fingerprint"] = compute_candidate_fingerprint(candidate)
        return candidate

    # Update candidate fields with extracted features
    for key in ["session_open", "opening_close", "opening_high", "opening_low", 
                "opening_midpoint", "nifty_opening_return", "bnifty_opening_return", 
                "close_location", "decision_close", "session_anchor"]:
        candidate[key] = f[key]
        
    # 3. Strategy Conditions in Order
    # Determine hypothetical direction based on NIFTY return
    ret = f["nifty_opening_return"]
    direction = "LONG" if ret > 0 else ("SHORT" if ret < 0 else "NONE")
    
    all_fails = []
    
    # Gate 1.5: Sufficient history for threshold
    if shock_threshold is None:
        all_fails.append("INSUFFICIENT_HISTORY")
    
    # Gate 2: Absolute NIFTY shock threshold
    if shock_threshold is not None and abs(ret) < shock_threshold:
        all_fails.append("FAILED_SHOCK_THRESHOLD")
        
    # Gate 3: NIFTY direction
    if direction == "NONE":
        all_fails.append("ZERO_NIFTY_RETURN")
        
    # Gate 4: Opening close location
    if direction == "LONG" and f["close_location"] < CONTRACT_PARAMS["close_location_long_threshold"]:
        all_fails.append("FAILED_CLOSE_LOCATION")
    elif direction == "SHORT" and f["close_location"] > CONTRACT_PARAMS["close_location_short_threshold"]:
        all_fails.append("FAILED_CLOSE_LOCATION")
        
    # Gate 5: BANKNIFTY confirmation
    if direction == "LONG" and f["bnifty_opening_return"] <= 0:
        all_fails.append("FAILED_CONFIRMATION")
    elif direction == "SHORT" and f["bnifty_opening_return"] >= 0:
        all_fails.append("FAILED_CONFIRMATION")
        
    # Gate 6: Retained move fraction
    if direction == "LONG":
        denom = f["long_retained_denom"]
        if denom <= 0:
            all_fails.append("UNDEFINED_RETAINED_MOVE")
            retained_frac = 0.0
        else:
            retained_frac = (f["decision_close"] - f["session_open"]) / denom
            if retained_frac < CONTRACT_PARAMS["retained_move_fraction_threshold"]:
                all_fails.append("FAILED_RETAINED_MOVE")
    else: # SHORT
        denom = f["short_retained_denom"]
        if denom <= 0:
            all_fails.append("UNDEFINED_RETAINED_MOVE")
            retained_frac = 0.0
        else:
            retained_frac = (f["session_open"] - f["decision_close"]) / denom
            if retained_frac < CONTRACT_PARAMS["retained_move_fraction_threshold"]:
                all_fails.append("FAILED_RETAINED_MOVE")
                
    candidate["retained_move_fraction"] = retained_frac
    
    # Gate 7: Opening midpoint persistence (strict inequality)
    if direction == "LONG" and f["decision_close"] <= f["opening_midpoint"]:
        all_fails.append("FAILED_MIDPOINT_PERSISTENCE")
    elif direction == "SHORT" and f["decision_close"] >= f["opening_midpoint"]:
        all_fails.append("FAILED_MIDPOINT_PERSISTENCE")
        
    # Gate 8: Session anchor persistence
    if direction == "LONG" and f["decision_close"] <= f["session_anchor"]:
        all_fails.append("FAILED_ANCHOR_PERSISTENCE")
    elif direction == "SHORT" and f["decision_close"] >= f["session_anchor"]:
        all_fails.append("FAILED_ANCHOR_PERSISTENCE")

    # Determine final acceptance
    if len(all_fails) == 0:
        candidate["candidate_accepted"] = True
        candidate["direction"] = direction
        candidate["primary_rejection_reason"] = "NONE"
    else:
        candidate["candidate_accepted"] = False
        candidate["direction"] = "NONE"
        candidate["primary_rejection_reason"] = all_fails[0]
        candidate["all_rejections"] = all_fails
        
    candidate["candidate_fingerprint"] = compute_candidate_fingerprint(candidate)
    return candidate
