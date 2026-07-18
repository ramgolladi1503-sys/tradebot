import pandas as pd
from typing import Dict, Any, Tuple
from .outcome_contract import CONTRACT_PARAMS

def calculate_returns(entry_price: float, exit_price: float, direction: str) -> Tuple[float, Dict[str, float]]:
    if direction == "LONG":
        gross = (exit_price / entry_price) - 1.0
    elif direction == "SHORT":
        gross = (entry_price / exit_price) - 1.0
    else:
        raise ValueError("Invalid direction")
        
    frictions = {}
    for bps in CONTRACT_PARAMS["friction_bps_tiers"]:
        frictions[f"net_return_{bps}bps"] = gross - (2 * bps / 10000.0)
        
    return gross, frictions

from .timestamp_normalization import normalize_timestamps

def label_outcome(df: pd.DataFrame, direction: str, session_date: str) -> Dict[str, Any]:
    df = df.copy()
    try:
        df["timestamp"] = normalize_timestamps(df["timestamp"])
    except ValueError as e:
        if "Duplicate" in str(e):
            return {"status": "DUPLICATE_TIMESTAMPS"}
        return {"status": "UNPARSABLE_TIMESTAMPS"}
    except Exception as e:
        return {"status": "UNPARSABLE_TIMESTAMPS"}
        
    df_sorted = df.sort_values("timestamp").reset_index(drop=True)
    
    entry_time = pd.Timestamp(f"{session_date} {CONTRACT_PARAMS['entry_bar_time']}").tz_localize("Asia/Kolkata")
    exit_time = pd.Timestamp(f"{session_date} {CONTRACT_PARAMS['exit_bar_time']}").tz_localize("Asia/Kolkata")
    
    entry_row = df_sorted[df_sorted["timestamp"] == entry_time]
    if entry_row.empty:
        return {"status": "ENTRY_BAR_MISSING"}
    if len(entry_row) > 1:
        return {"status": "ENTRY_BAR_MULTIPLE_MATCHES"}
        
    exit_row = df_sorted[df_sorted["timestamp"] == exit_time]
    if exit_row.empty:
        return {"status": "EXIT_BAR_MISSING"}
    if len(exit_row) > 1:
        return {"status": "EXIT_BAR_MULTIPLE_MATCHES"}
        
    entry_price = float(entry_row.iloc[0]["open"])
    exit_price = float(exit_row.iloc[0]["open"])
    
    if pd.isna(entry_price) or entry_price <= 0:
        return {"status": "ENTRY_PRICE_INVALID"}
        
    if pd.isna(exit_price) or exit_price <= 0:
        return {"status": "EXIT_PRICE_INVALID"}
        
    if exit_time <= entry_time:
        return {"status": "ENTRY_EXIT_ORDER_INVALID"}
        
    duration_secs = (exit_time - entry_time).total_seconds()
    if duration_secs != CONTRACT_PARAMS["holding_period_minutes"] * 60:
        return {"status": "INVALID_HOLDING_PERIOD"}
        
    gross, frictions = calculate_returns(entry_price, exit_price, direction)
    
    result = {
        "status": "OUTCOME_LABELLED",
        "entry_timestamp": entry_time.isoformat(),
        "exit_timestamp": exit_time.isoformat(),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "holding_seconds": duration_secs,
        "gross_return": gross
    }
    result.update(frictions)
    return result
