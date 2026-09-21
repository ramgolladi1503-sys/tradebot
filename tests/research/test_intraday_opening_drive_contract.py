#!/usr/bin/env python3
"""
Unit tests for INTRADAY_OPENING_DRIVE_V1 Terminally Frozen Contract:
1. Cryptographic Spec Hash Integrity:
   - SHA256(canonical FROZEN_SPEC.json) == CANDIDATE_FINGERPRINT
   - SHA256(canonical FROZEN_SPEC.json) == FROZEN_SPEC.sha256 file
2. Fail-Closed Contract Continuity Tests:
   - Missing key column in T-1 -> FAIL (returns None)
   - Missing key column in T   -> FAIL (returns None)
   - NaN key in T-1           -> FAIL (returns None)
   - NaN key in T             -> FAIL (returns None)
   - Generic 'DEFAULT' key    -> FAIL (returns None)
   - Generic 'UNKNOWN' key    -> FAIL (returns None)
   - Mismatched contract keys -> FAIL (returns None)
   - Valid matching keys      -> PASS
3. Exact 15:29:00 bar enforcement for T-1 close.
4. Timestamp semantics: Entry is 09:21 close (known at 09:22); Exit is 11:00 close (known at 11:01).
5. Deterministic Spot-ATM strike mapping with midpoint tie-breaker.
"""

import json
import hashlib
import math
import numpy as np
import pandas as pd
import pytest

from core.candidate_audits.intraday_opening_drive import (
    calculate_intraday_drive_signal,
    calculate_spot_atm_strike,
    _extract_authoritative_contract_key,
    CANDIDATE_ID,
    CANDIDATE_FINGERPRINT
)


def test_frozen_spec_hash_integrity():
    with open("docs/research/candidates/INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.json") as f:
        spec_dict = json.load(f)
    serialized = json.dumps(spec_dict, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    # Invariant A: Must match hardcoded CANDIDATE_FINGERPRINT
    assert digest == CANDIDATE_FINGERPRINT
    assert digest == "52904a90b2a413e80b4792cf60b824118147e18b16f807d00bf24532d141a065"

    # Invariant B: Must match FROZEN_SPEC.sha256 file
    with open("docs/research/candidates/INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.sha256") as f:
        stored_line = f.read().strip()
    stored_hash = stored_line.split()[0]
    assert digest == stored_hash


def _build_valid_dfs(prev_key="NSE_FO|NIFTY|2026-09-29", curr_key="NSE_FO|NIFTY|2026-09-29"):
    prev_df = pd.DataFrame([{
        "futures_close": 24000.0,
        "time": "15:29:00",
        "selected_futures_contract_key": prev_key
    }])
    curr_df = pd.DataFrame([
        {"futures_open": 24050.0, "futures_close": 24060.0, "time": "09:15:00", "selected_futures_contract_key": curr_key, "date": "2026-09-01"},
        {"futures_open": 24070.0, "futures_close": 24080.0, "time": "09:20:00", "selected_futures_contract_key": curr_key, "date": "2026-09-01"},
        {"futures_open": 24080.0, "futures_close": 24095.0, "time": "09:21:00", "selected_futures_contract_key": curr_key, "date": "2026-09-01"},
        {"futures_open": 24150.0, "futures_close": 24160.0, "time": "11:00:00", "selected_futures_contract_key": curr_key, "date": "2026-09-01"},
    ])
    return prev_df, curr_df


def test_contract_key_extraction():
    # Valid
    assert _extract_authoritative_contract_key(pd.DataFrame([{"selected_futures_contract_key": "NSE_FO|123"}])) == "NSE_FO|123"
    assert _extract_authoritative_contract_key(pd.DataFrame([{"expired_instrument_key": "NSE_FO|68407"}])) == "NSE_FO|68407"

    # Fails closed on generic / invalid
    assert _extract_authoritative_contract_key(pd.DataFrame([{"selected_futures_contract_key": "DEFAULT"}])) is None
    assert _extract_authoritative_contract_key(pd.DataFrame([{"selected_futures_contract_key": "UNKNOWN"}])) is None
    assert _extract_authoritative_contract_key(pd.DataFrame([{"selected_futures_contract_key": np.nan}])) is None
    assert _extract_authoritative_contract_key(pd.DataFrame([{"selected_futures_contract_key": "   "}])) is None
    assert _extract_authoritative_contract_key(pd.DataFrame([{"unrelated_col": 123}])) is None


def test_contract_continuity_missing_column_fails_closed():
    prev_df, curr_df = _build_valid_dfs()
    # Drop column from T-1
    prev_df_no_key = prev_df.drop(columns=["selected_futures_contract_key"])
    assert calculate_intraday_drive_signal(prev_df_no_key, curr_df) is None

    # Drop column from T
    curr_df_no_key = curr_df.drop(columns=["selected_futures_contract_key"])
    assert calculate_intraday_drive_signal(prev_df, curr_df_no_key) is None


def test_contract_continuity_nan_fails_closed():
    prev_df, curr_df = _build_valid_dfs(prev_key=np.nan, curr_key="NSE_FO|NIFTY|2026-09-29")
    assert calculate_intraday_drive_signal(prev_df, curr_df) is None

    prev_df2, curr_df2 = _build_valid_dfs(prev_key="NSE_FO|NIFTY|2026-09-29", curr_key=np.nan)
    assert calculate_intraday_drive_signal(prev_df2, curr_df2) is None


def test_contract_continuity_generic_placeholder_fails_closed():
    # Both having 'DEFAULT' must NOT pass
    prev_df, curr_df = _build_valid_dfs(prev_key="DEFAULT", curr_key="DEFAULT")
    assert calculate_intraday_drive_signal(prev_df, curr_df) is None

    prev_df2, curr_df2 = _build_valid_dfs(prev_key="UNKNOWN", curr_key="UNKNOWN")
    assert calculate_intraday_drive_signal(prev_df2, curr_df2) is None


def test_contract_continuity_mismatched_keys_fails_closed():
    prev_df, curr_df = _build_valid_dfs(prev_key="NSE_FO|NIFTY|2026-09-29", curr_key="NSE_FO|NIFTY|2026-10-29")
    assert calculate_intraday_drive_signal(prev_df, curr_df) is None


def test_contract_continuity_matching_authoritative_keys_passes():
    prev_df, curr_df = _build_valid_dfs(prev_key="NSE_FO|NIFTY|2026-09-29", curr_key="NSE_FO|NIFTY|2026-09-29")
    sig = calculate_intraday_drive_signal(prev_df, curr_df)
    assert sig is not None
    assert sig.is_valid_signal is True
    assert sig.prev_contract_key == "NSE_FO|NIFTY|2026-09-29"
    assert sig.curr_contract_key == "NSE_FO|NIFTY|2026-09-29"


def test_exact_1529_close_enforcement():
    prev_df_missing = pd.DataFrame([{
        "futures_close": 24000.0,
        "time": "15:28:00",
        "selected_futures_contract_key": "NSE_FO|NIFTY|2026-09-29"
    }])
    _, curr_df = _build_valid_dfs()
    assert calculate_intraday_drive_signal(prev_df_missing, curr_df) is None


def test_strict_causal_entry_and_exit_semantics():
    prev_df, curr_df = _build_valid_dfs()
    sig = calculate_intraday_drive_signal(prev_df, curr_df)
    assert sig is not None
    assert sig.is_valid_signal is True
    assert sig.side == "LONG"
    # Entry reference known at 09:22:00
    assert sig.entry_ref_0922 == 24095.0
    # Exit reference known at 11:01:00
    assert sig.exit_ref_1101 == 24160.0


def test_deterministic_spot_atm_strike():
    assert calculate_spot_atm_strike(24024.9) == 24000
    assert calculate_spot_atm_strike(24025.1) == 24050
    assert calculate_spot_atm_strike(24025.0) == 24050
    assert calculate_spot_atm_strike(24075.0) == 24100

def test_shadow_runner_fingerprint_parity():
    from core.paper_shadow.run_intraday_opening_drive_shadow import (
        CANDIDATE_FINGERPRINT as SHADOW_FP,
        CANDIDATE_ID as SHADOW_ID,
    )
    assert SHADOW_ID == CANDIDATE_ID
    assert SHADOW_FP == CANDIDATE_FINGERPRINT
    assert SHADOW_FP == "52904a90b2a413e80b4792cf60b824118147e18b16f807d00bf24532d141a065"
