import json
from pathlib import Path
import pandas as pd
from typing import Optional, Dict, Any, List

class DatasetRegistryViolation(Exception):
    pass

class TokenReplayViolation(Exception):
    pass

def map_dataset(date_str: str) -> str:
    if date_str <= "2025-09-05":
        return "DEVELOPMENT_V1"
    elif "2025-09-08" <= date_str <= "2026-02-05":
        return "VALIDATION_V1_CONSUMED"
    elif "2026-02-06" <= date_str <= "2026-07-10":
        return "HOLDOUT_V1_LOCKED"
    elif "2026-07-11" <= date_str <= "2026-07-21":
        # The previously consumed fresh data
        return "FRESH_CONFIRMATION_V2_CONSUMED_INVALID"
    else:
        # Any date after 2026-07-21 is genuinely fresh
        return "FRESH_CONFIRMATION_V2_LOCKED"

def _enforce_no_leakage(df: pd.DataFrame, allowed_datasets: List[str]):
    df["v2_dataset"] = df["session_date"].apply(map_dataset)
    violating = df[~df["v2_dataset"].isin(allowed_datasets)]
    if not violating.empty:
        raise DatasetRegistryViolation(f"Attempted to access forbidden datasets: {violating['v2_dataset'].unique()}")
    return df[df["v2_dataset"].isin(allowed_datasets)].copy()

def load_development_for_selection(df: pd.DataFrame) -> pd.DataFrame:
    """
    Candidate selection must use only DEVELOPMENT_V1.
    """
    return _enforce_no_leakage(df, ["DEVELOPMENT_V1"])

def load_locked_confirmation_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """
    Loads metadata-only inventory. Strips all outcome and metric columns.
    Allows accessing the date and session lengths, but NO labels.
    """
    fresh_df = _enforce_no_leakage(df, ["FRESH_CONFIRMATION_V2_LOCKED", "FRESH_CONFIRMATION_V2_CONSUMED_INVALID", "DEVELOPMENT_V1"])
    # Strip any column that could leak performance
    leakage_columns = [
        "label_return_r", "expectancy", "profit_factor", "barrier_outcome", "base_rate"
    ]
    for col in leakage_columns:
        if col in fresh_df.columns:
            fresh_df = fresh_df.drop(columns=[col])
    return fresh_df

_used_tokens = set()

def evaluate_frozen_candidate_once(df: pd.DataFrame, token: str, expected_candidate_hash: str, actual_candidate_hash: str, expected_manifest_hash: str, actual_manifest_hash: str) -> pd.DataFrame:
    """
    Allows loading FRESH_CONFIRMATION_V2_LOCKED ONLY if exactly one frozen candidate is supplied,
    with a valid one-time token and matching hashes.
    """
    if not token or token == "generic_token":
        raise DatasetRegistryViolation("Generic acknowledgement is rejected.")
    
    if token in _used_tokens:
        raise TokenReplayViolation("Token replay fails. Confirmation token already consumed.")
    
    if expected_candidate_hash != actual_candidate_hash:
        raise DatasetRegistryViolation("Wrong candidate hash rejected.")
        
    if expected_manifest_hash != actual_manifest_hash:
        raise DatasetRegistryViolation("Wrong manifest hash rejected.")
    
    _used_tokens.add(token)
    
    fresh_df = df[df["session_date"].apply(map_dataset) == "FRESH_CONFIRMATION_V2_LOCKED"].copy()
    
    if fresh_df.empty:
        # Check if there is consumed data instead
        consumed_df = df[df["session_date"].apply(map_dataset) == "FRESH_CONFIRMATION_V2_CONSUMED_INVALID"]
        if not consumed_df.empty:
            raise DatasetRegistryViolation("Consumed confirmation cannot be relocked.")
        
    return fresh_df

def safe_impute(df: pd.DataFrame, impute_map: dict[str, float]) -> pd.DataFrame:
    for feature, value in impute_map.items():
        if feature in df.columns:
            if value is not None:
                df[feature] = df[feature].fillna(value)
            else:
                pass
    return df
