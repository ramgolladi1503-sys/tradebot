#!/usr/bin/env python3
"""
Intraday Opening Drive Momentum Evaluator: INTRADAY_OPENING_DRIVE_V1
Strictly non-trading, read-only analytics adhering to AGENTS.md:
- read_only = True
- broker_write_authority = False
- orders_placed = 0

Terminally Frozen Architecture:
1. Exact T-1 close timestamp at 15:29:00 (regular-session close).
2. Strict Fail-Closed Overnight Contract Continuity:
   - Requires authoritative contract key column ('selected_futures_contract_key' or 'expired_instrument_key').
   - Fails closed if metadata is missing, null, NaN, empty, or generic ('DEFAULT'/'UNKNOWN').
   - Fails closed if prev_contract_key != curr_contract_key (purging calendar/expiry rolls).
3. Signal formula:
   - Gap = Futures_Open(09:15) - Futures_Close(T-1_15:29)
   - Drive_5m = Futures_Close(09:20) - Futures_Open(09:15)
   - Thresholds: |Gap| > 30.0 pts, |Drive_5m| > 20.0 pts (Bullish if both > 0, Bearish if both < 0).
4. Explicit Timestamp Semantics:
   - Entry Model: 09:21 bar close (known and executable at 09:22:00.000).
   - Exit Model: 11:00 bar close (known and executable at 11:01:00.000).
"""

from __future__ import annotations
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import pandas as pd
import numpy as np

CANDIDATE_ID = "INTRADAY_OPENING_DRIVE_V1"
CANDIDATE_FINGERPRINT = "52904a90b2a413e80b4792cf60b824118147e18b16f807d00bf24532d141a065"
IST_TZ = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class IntradayDriveSignal:
    session_date: str
    prev_contract_key: str
    curr_contract_key: str
    prev_close_1529: float
    today_open_0915: float
    gap_pts: float
    drive_close_0920: float
    drive_5m_pts: float
    side: str
    is_valid_signal: bool
    entry_ref_0922: float
    exit_ref_1101: float


def _extract_authoritative_contract_key(row_df: pd.DataFrame) -> Optional[str]:
    """
    Extracts authoritative contract key from row slice.
    Fails closed (returns None) if missing, NaN, empty string, or generic placeholder.
    """
    if row_df.empty:
        return None

    # Supported authoritative contract key column names
    key_cols = ["selected_futures_contract_key", "expired_instrument_key", "instrument_key"]
    found_col = None
    for c in key_cols:
        if c in row_df.columns:
            found_col = c
            break

    if found_col is None:
        return None

    raw_val = row_df.iloc[0][found_col]
    if pd.isna(raw_val):
        return None

    val_str = str(raw_val).strip()
    if not val_str:
        return None

    # Strictly reject non-authoritative fallback markers
    if val_str.upper() in ["DEFAULT", "UNKNOWN", "NONE", "NAN", "NULL"]:
        return None

    return val_str


def calculate_intraday_drive_signal(
    prev_session_df: pd.DataFrame,
    curr_session_df: pd.DataFrame,
    gap_min: float = 30.0,
    drive_min: float = 20.0
) -> Optional[IntradayDriveSignal]:
    """
    Computes causal intraday opening drive signal from exact 15:29:00 T-1 bar
    and 09:15-09:20 T bars.
    Strictly fails closed on missing contract keys or roll mismatches.
    """
    if prev_session_df.empty or curr_session_df.empty:
        return None

    time_col_prev = "time_str" if "time_str" in prev_session_df.columns else "time"
    time_col_curr = "time_str" if "time_str" in curr_session_df.columns else "time"

    # Invariant 1: Exact 15:29:00 regular-session bar
    b_prev_1529 = prev_session_df[prev_session_df[time_col_prev] == "15:29:00"]
    if b_prev_1529.empty:
        return None

    # Invariant 2: Authoritative Contract Keys (Must be present, valid, and identical)
    b_0915 = curr_session_df[curr_session_df[time_col_curr] == "09:15:00"]
    b_0920 = curr_session_df[curr_session_df[time_col_curr] == "09:20:00"]
    b_0921 = curr_session_df[curr_session_df[time_col_curr] == "09:21:00"]
    b_1100 = curr_session_df[curr_session_df[time_col_curr] == "11:00:00"]

    if b_0915.empty or b_0920.empty or b_0921.empty or b_1100.empty:
        return None

    prev_key = _extract_authoritative_contract_key(b_prev_1529)
    curr_key = _extract_authoritative_contract_key(b_0915)

    # Fail closed on missing/invalid/mismatched contract keys
    if prev_key is None or curr_key is None:
        return None
    if prev_key != curr_key:
        return None

    close_col_prev = "futures_close" if "futures_close" in prev_session_df.columns else "close"
    close_col_curr = "futures_close" if "futures_close" in curr_session_df.columns else "close"
    open_col_curr = "futures_open" if "futures_open" in curr_session_df.columns else "open"

    prev_close = float(b_prev_1529.iloc[0][close_col_prev])
    today_open = float(b_0915.iloc[0][open_col_curr])
    drive_close = float(b_0920.iloc[0][close_col_curr])

    # Timestamp Semantics:
    # 09:21 close is known at 09:22:00.000
    # 11:00 close is known at 11:01:00.000
    entry_p = float(b_0921.iloc[0][close_col_curr])
    exit_p = float(b_1100.iloc[0][close_col_curr])

    gap = today_open - prev_close
    drive_5m = drive_close - today_open

    date_val = str(curr_session_df.iloc[0]["date"]) if "date" in curr_session_df.columns else str(curr_session_df.iloc[0]["timestamp"])[:10]

    if gap > gap_min and drive_5m > drive_min:
        side = "LONG"
        is_valid = True
    elif gap < -gap_min and drive_5m < -drive_min:
        side = "SHORT"
        is_valid = True
    else:
        side = "FLAT"
        is_valid = False

    return IntradayDriveSignal(
        session_date=date_val,
        prev_contract_key=prev_key,
        curr_contract_key=curr_key,
        prev_close_1529=round(prev_close, 2),
        today_open_0915=round(today_open, 2),
        gap_pts=round(gap, 2),
        drive_close_0920=round(drive_close, 2),
        drive_5m_pts=round(drive_5m, 2),
        side=side,
        is_valid_signal=is_valid,
        entry_ref_0922=round(entry_p, 2),
        exit_ref_1101=round(exit_p, 2)
    )


def calculate_spot_atm_strike(spot_price: float, grid: float = 50.0) -> int:
    """
    Deterministic Spot-ATM strike mapping with strict midpoint (.5) tie-breaker.
    """
    lower = math.floor(spot_price / grid) * grid
    upper = lower + grid
    dist_lower = abs(spot_price - lower)
    dist_upper = abs(spot_price - upper)

    if dist_lower < dist_upper:
        return int(lower)
    elif dist_upper < dist_lower:
        return int(upper)
    else:
        return int(upper)
