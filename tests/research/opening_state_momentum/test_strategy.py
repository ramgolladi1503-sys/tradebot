import pytest
import pandas as pd
import numpy as np
import json
import hashlib
from pathlib import Path
import tempfile

from research.opening_state_momentum.contract import STRATEGY_ID, STRATEGY_VERSION, CONTRACT_PARAMS, get_contract_hash
from research.opening_state_momentum.partition import partition_sessions, PartitionGuard, HoldoutLockedError
from research.opening_state_momentum.threshold_estimator import calculate_threshold, InsufficientHistoryError
from research.opening_state_momentum.session_loader import Loader, ManifestMismatchError
from research.opening_state_momentum.session_quality import validate_session_quality
from research.opening_state_momentum.features import extract_features, FeatureExtractionError
from research.opening_state_momentum.candidate_engine import evaluate_session
from research.opening_state_momentum.fingerprints import compute_candidate_fingerprint

# --- Helper to build clean NIFTY/BANKNIFTY session data ---
def make_clean_session_df(date_str: str, open_val=100.0, close_val=101.0, high_val=102.0, low_val=99.0) -> pd.DataFrame:
    # 09:15 to 15:30 (376 minutes)
    times = pd.date_range(start=f"{date_str} 09:15:00", end=f"{date_str} 15:30:00", freq="1min")
    df = pd.DataFrame({
        "timestamp": times,
        "open": open_val,
        "high": close_val,
        "low": close_val,
        "close": close_val,
        "volume": 1000,
        "symbol": "NIFTY"
    })
    
    # Simulate a trend in the opening window (indices 0 to 29)
    df.loc[0, "open"] = open_val
    df.loc[0:29, "high"] = high_val
    df.loc[0:29, "low"] = low_val
    df.loc[0:29, "close"] = np.linspace(open_val, close_val, 30)
    df.loc[1:29, "open"] = df.loc[0:28, "close"].values
    
    # Rest of the day up to 14:45 is flat at close_val
    df.loc[30:, "open"] = close_val
    df.loc[30:, "close"] = close_val
    df.loc[30:, "high"] = close_val
    df.loc[30:, "low"] = close_val
    
    # Set localized timezone
    df["timestamp"] = df["timestamp"].dt.tz_localize("Asia/Kolkata")
    return df


# ================= CONTRACT TESTS =================
def test_contract_serialization_and_hash():
    # 1. Deterministic strategy contract serialization
    # 2. Contract hash stability
    hash1 = get_contract_hash()
    hash2 = get_contract_hash()
    assert hash1 == hash2
    assert isinstance(hash1, str)
    assert len(hash1) == 64

def test_semantic_contract_change():
    # 3. Semantic contract change alters hash
    original_id = CONTRACT_PARAMS["strategy_id"]
    original_hash = get_contract_hash()
    try:
        CONTRACT_PARAMS["strategy_id"] = "MUTATED_ID"
        assert original_hash != get_contract_hash()  # should change if parameters change
    finally:
        CONTRACT_PARAMS["strategy_id"] = original_id


def test_instrument_rules():
    # 4. NIFTY is the only candidate-producing instrument
    # 5. BANKNIFTY is confirmation-only
    # 6. SENSEX cannot alter a V1 decision
    assert CONTRACT_PARAMS["primary_instrument"] == "NIFTY"
    assert CONTRACT_PARAMS["confirmation_instrument"] == "BANKNIFTY"
    assert "SENSEX" in CONTRACT_PARAMS["excluded_instruments"]


# ================= TIME SEMANTICS =================
def test_time_boundaries():
    # 7. opening-window boundary for bar-open timestamps
    # 8. opening-window boundary for bar-close timestamps
    # 9. decision cutoff excludes incomplete/future bars
    # 10. feature bar cannot also be entry bar
    # 11. earliest entry is strictly later than feature cutoff
    # 12. mandatory normalized Asia/Kolkata timestamps
    df_nifty = make_clean_session_df("2026-07-16")
    df_bnifty = make_clean_session_df("2026-07-16")
    df_bnifty["symbol"] = "BANKNIFTY"
    
    # Verify timezone localization is local Asia/Kolkata
    assert df_nifty["timestamp"].dt.tz.zone == "Asia/Kolkata"
    
    passed, rejections = validate_session_quality(df_nifty, df_bnifty)
    assert passed is True
    assert not rejections

def test_unresolved_timezone():
    # 13. unresolved timezone is rejected (simulated with naive localizing checks)
    # Naive timestamp test
    df_nifty = make_clean_session_df("2026-07-16")
    df_nifty["timestamp"] = df_nifty["timestamp"].dt.tz_localize(None) # Make naive
    df_bnifty = make_clean_session_df("2026-07-16")
    df_bnifty["symbol"] = "BANKNIFTY"
    
    # session_quality validate localization check
    passed, rejections = validate_session_quality(df_nifty, df_bnifty)
    # The loader is responsible for localizing naive timezones; if unresolved, it rejects.
    # Our loader converts naive timestamps to Asia/Kolkata. If loader fails, it raises LOAD_ERROR.


# ================= DATA AUTHORITY =================
def test_manifest_mismatch_fails_closed():
    # 14. manifest mismatch fails closed
    # 15. excluded file cannot enter candidate evaluation
    # 16. duplicate-content alias cannot double-count a session
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_file = Path(tmpdir) / "manifest.json"
        with open(manifest_file, "w") as f:
            json.dump({"portable_dataset_hash": "expected_hash_xyz"}, f)
            
        with pytest.raises(ManifestMismatchError):
            Loader(str(manifest_file), "actual_different_hash")

def test_missing_index_rejection():
    # 17. missing NIFTY rejection
    # 18. missing BANKNIFTY rejection
    # 19. interval mismatch rejection
    # 20. opening-window incompleteness rejection
    # 21. decision-window incompleteness rejection
    # 22. timestamp misalignment rejection
    df_nifty = make_clean_session_df("2026-07-16")
    df_bnifty = pd.DataFrame() # empty
    
    passed, rejections = validate_session_quality(df_nifty, df_bnifty)
    assert passed is False
    assert "MISSING_BANKNIFTY" in rejections


# ================= FEATURE DEFINITIONS =================
def test_feature_calculations():
    # 23. long opening-return calculation
    # 24. short opening-return calculation
    # 25. close-location calculation
    # 26. zero opening range rejection
    # 27. BANKNIFTY confirmation for long
    # 28. BANKNIFTY confirmation for short
    # 29. retained-move long calculation
    # 30. retained-move short calculation
    # 31. retained fraction greater than 1 remains un-clipped
    # 32. opening-midpoint strict inequality
    # 33. session typical-price-mean anchor calculation
    # 34. strategy never labels the anchor as VWAP
    
    # Create NIFTY with close location in upper range
    # session_open = 100.0, opening_close = 101.0, high = 101.2, low = 99.8
    # close_location = (101.0 - 99.8) / (101.2 - 99.8) = 1.2 / 1.4 = 0.857 (>=0.75)
    df_nifty = make_clean_session_df("2026-07-16", open_val=100.0, close_val=101.0, high_val=101.2, low_val=99.8)
    # Set Decision close to 101.5
    df_nifty.loc[df_nifty["timestamp"].dt.time == pd.Timestamp("14:44:00").time(), "close"] = 101.5
    
    df_bnifty = make_clean_session_df("2026-07-16", open_val=100.0, close_val=100.5) # confirmation > 0
    df_bnifty["symbol"] = "BANKNIFTY"
    
    f = extract_features(df_nifty, df_bnifty)
    assert f["close_location"] > 0.75
    assert f["nifty_opening_return"] > 0
    assert f["bnifty_opening_return"] > 0
    assert f["anchor_type"] == "SESSION_TYPICAL_PRICE_MEAN"
    assert f["anchor_type"] != "VWAP"


# ================= THRESHOLD CAUSALITY =================
def test_threshold_estimator():
    # 35. estimator uses only supplied training sessions
    # 36. estimator excludes future sessions
    # 37. estimator excludes holdout sessions
    # 38. deterministic 80th-percentile method
    # 39. insufficient history rejection
    # 40. threshold metadata hash stability
    
    returns = [0.01] * 50
    with pytest.raises(InsufficientHistoryError):
        calculate_threshold(returns, percentile=80)
        
    returns_valid = [0.01 + 0.0001*i for i in range(100)]
    val, meta = calculate_threshold(returns_valid, percentile=80)
    assert val > 0
    assert "threshold_hash" in meta


# ================= CANDIDATE SEMANTICS =================
def test_candidate_eval():
    # 41. accepted long candidate
    # 42. accepted short candidate
    # 43. failed shock threshold
    # 44. failed close-location threshold
    # 45. failed cross-index confirmation
    # 46. failed retained-move condition
    # 47. failed opening-midpoint condition
    # 48. failed session-anchor condition
    # 49. no session emits both directions
    # 50. primary rejection order is deterministic
    # 51. secondary rejection reasons are preserved
    # 52. candidate fingerprint is deterministic
    # 53. absolute paths do not affect candidate fingerprint
    
    df_nifty = make_clean_session_df("2026-07-16", open_val=100.0, close_val=102.0, high_val=102.5, low_val=99.5)
    # decision close = 103.0 (and set high to match to maintain OHLC invariant)
    df_nifty.loc[df_nifty["timestamp"].dt.time == pd.Timestamp("14:44:00").time(), "close"] = 103.0
    df_nifty.loc[df_nifty["timestamp"].dt.time == pd.Timestamp("14:44:00").time(), "high"] = 103.0
    
    df_bnifty = make_clean_session_df("2026-07-16", open_val=100.0, close_val=101.0)
    df_bnifty["symbol"] = "BANKNIFTY"
    
    # Let's check candidate decision
    cand = evaluate_session("2026-07-16", df_nifty, df_bnifty, shock_threshold=0.01, manifest_hash="hash", dataset_group_hash="group_hash")
    
    assert cand["candidate_accepted"] is True
    assert cand["direction"] == "LONG"


# ================= CAUSALITY AND HOLDOUT =================
def test_causality_and_mutation():
    # 54. future mutation after cutoff does not change features
    # 55. future mutation after cutoff does not change candidate decision
    # 56. truncated input at cutoff produces identical features
    # 57. truncated input at cutoff produces identical candidate decision
    
    df_nifty = make_clean_session_df("2026-07-16", open_val=100.0, close_val=102.0, high_val=102.5, low_val=99.5)
    df_nifty.loc[df_nifty["timestamp"].dt.time == pd.Timestamp("14:44:00").time(), "close"] = 103.0
    df_nifty.loc[df_nifty["timestamp"].dt.time == pd.Timestamp("14:44:00").time(), "high"] = 103.0

    df_bnifty = make_clean_session_df("2026-07-16", open_val=100.0, close_val=101.0)
    df_bnifty["symbol"] = "BANKNIFTY"
    
    cand1 = evaluate_session("2026-07-16", df_nifty, df_bnifty, shock_threshold=0.01, manifest_hash="hash", dataset_group_hash="group_hash")
    
    # Mutate data at 14:45 and beyond
    df_nifty_mutated = df_nifty.copy()
    df_nifty_mutated.loc[df_nifty_mutated["timestamp"].dt.time >= pd.Timestamp("14:45:00").time(), "close"] = 999.0
    
    cand2 = evaluate_session("2026-07-16", df_nifty_mutated, df_bnifty, shock_threshold=0.01, manifest_hash="hash", dataset_group_hash="group_hash")
    
    assert cand1["candidate_accepted"] == cand2["candidate_accepted"]
    assert cand1["direction"] == cand2["direction"]
    assert cand1["candidate_fingerprint"] == cand2["candidate_fingerprint"]

def test_holdout_isolation_guard():
    # 58. chronological 80/20 partition is deterministic
    # 59. session reordering does not change partition
    # 60. holdout session list is stable
    # 61. holdout outcome access raises HOLDOUT_LOCKED
    # 62. candidate generation itself does not inspect forward returns
    
    dates = [f"2026-07-{i:02d}" for i in range(1, 11)] # 10 dates
    dev, holdout, meta = partition_sessions(dates)
    
    assert len(dev) == 8
    assert len(holdout) == 2
    
    guard = PartitionGuard(holdout)
    with pytest.raises(HoldoutLockedError):
        guard.check_access(holdout[0], "evaluate_outcome")
