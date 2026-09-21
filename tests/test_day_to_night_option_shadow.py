#!/usr/bin/env python3
"""
Unit tests for DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION Paper Shadow Invariants:
1. Deterministic Spot-ATM Strike Mapping & Midpoint Tie-Breaking (No bankers' rounding).
2. Expiry Parsing & Nearest Surviving Contract Selection.
3. Strict Causality & Quote Ordering.
4. Two-Sided Market Depth Validation (Rejection of non-executable / zero / crossed quotes).
5. Immutable Spec SHA256 Fingerprint Stability.
"""

import math
from datetime import datetime, time, timezone, timedelta
import pandas as pd
import pytest

from core.paper_shadow.run_day_to_night_option_shadow import (
    calculate_deterministic_spot_atm_strike,
    parse_option_symbol_expiry,
    select_nearest_surviving_contract,
    validate_two_sided_depth,
    CANDIDATE_FINGERPRINT,
    FROZEN_SPEC_DICT,
    IST_TZ,
)


def test_deterministic_spot_atm_strike_tie_break():
    # Distance checks
    assert calculate_deterministic_spot_atm_strike(23324.9) == 23300
    assert calculate_deterministic_spot_atm_strike(23325.1) == 23350
    assert calculate_deterministic_spot_atm_strike(23294.35) == 23300

    # Fixed tie-breaking at exact midpoints (.5) -> must round UP, never relying on bankers' rounding parity
    assert calculate_deterministic_spot_atm_strike(23325.0) == 23350
    assert calculate_deterministic_spot_atm_strike(23375.0) == 23400
    assert calculate_deterministic_spot_atm_strike(23425.0) == 23450


def test_parse_option_symbol_expiry():
    sym = "NIFTY 23300 CE 22 SEP 26"
    exp_dt = parse_option_symbol_expiry(sym)
    assert exp_dt is not None
    assert exp_dt.year == 2026
    assert exp_dt.month == 9
    assert exp_dt.day == 22
    assert exp_dt.hour == 15
    assert exp_dt.minute == 30
    assert exp_dt.tzinfo == IST_TZ


def test_select_nearest_surviving_contract():
    symbols = [
        "NIFTY 23300 CE 15 SEP 26",  # Expired before next session
        "NIFTY 23300 CE 22 SEP 26",  # Nearest surviving
        "NIFTY 23300 CE 29 SEP 26",  # Surviving but later
        "NIFTY 23300 PE 22 SEP 26",  # Wrong option type
        "NIFTY 23400 CE 22 SEP 26",  # Wrong strike
    ]

    # Target exit is 2026-09-18 09:16:00 IST
    exit_dt = datetime(2026, 9, 18, 9, 16, 0, tzinfo=IST_TZ)
    res = select_nearest_surviving_contract(
        available_symbols=symbols,
        atm_strike=23300,
        opt_type="CE",
        exit_timestamp=exit_dt.timestamp()
    )

    assert res is not None
    selected_symbol, selected_expiry = res
    assert selected_symbol == "NIFTY 23300 CE 22 SEP 26"
    assert selected_expiry.day == 22


def test_validate_two_sided_depth():
    # Valid two-sided depth
    assert validate_two_sided_depth(119.65, 119.70) is True

    # Crossed or zero spread
    assert validate_two_sided_depth(120.0, 119.0) is False  # Ask < Bid

    # Zero or negative quotes
    assert validate_two_sided_depth(0.0, 120.0) is False   # Bid == 0
    assert validate_two_sided_depth(119.0, 0.0) is False   # Ask == 0
    assert validate_two_sided_depth(-1.0, 120.0) is False

    # NaN / Inf
    assert validate_two_sided_depth(float('nan'), 120.0) is False
    assert validate_two_sided_depth(119.0, float('inf')) is False


def test_immutable_spec_fingerprint_integrity():
    import hashlib
    import json
    serialized = json.dumps(FROZEN_SPEC_DICT, sort_keys=True)
    computed_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    assert computed_hash == CANDIDATE_FINGERPRINT
    assert computed_hash == "fffa5dc3ffa53f8b6869d0923959c13140c8146c82b7b32b0937ac1aac24f967"
