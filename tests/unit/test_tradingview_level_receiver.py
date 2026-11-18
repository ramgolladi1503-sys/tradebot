"""Unit Tests for TradingView Level Receiver
==========================================
Verifies HMAC/passphrase authentication, date validation, structural hierarchy validation,
and atomic file persistence.

Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
"""

import hashlib
import hmac
import json
import pytest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from core.webhooks.tradingview_level_receiver import (
    OptionMateLevelData,
    TradingViewLevelReceiver,
)


def _clocked(payload, sequence=1):
    payload = dict(payload)
    payload.setdefault("timestamp", datetime.now(timezone.utc).timestamp())
    payload.setdefault("sequence", sequence)
    return payload


def test_safety_invariants(tmp_path):
    receiver = TradingViewLevelReceiver(require_auth=False, storage_path=tmp_path / "levels.json")
    payload = {
        "index": "NIFTY",
        "trend_decider": 25283.0,
        "rp1_upper": 25360.0,
        "rp2_upper": 25424.65,
        "rp1_lower": 25195.0,
        "rp2_lower": 25134.0,
        "date": datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d"),
    }
    res = receiver.process_webhook(_clocked(payload))
    assert res["read_only"] is True
    assert res["is_order_action"] is False
    assert res["broker_api_called"] is False
    assert res["allowed_for_live_execution"] is False


def test_default_auth_missing_timestamp_sequence_and_nonfinite_levels_fail_closed(tmp_path):
    receiver = TradingViewLevelReceiver(storage_path=tmp_path / "levels.json")
    payload = {
        "index": "NIFTY", "trend_decider": 25283.0, "rp1_upper": 25360.0,
        "rp2_upper": 25424.65, "rp1_lower": 25195.0, "rp2_lower": 25134.0,
        "date": datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d"),
    }
    assert receiver.process_webhook(payload)["success"] is False
    assert receiver.process_webhook(_clocked(payload))["success"] is False  # no auth configured

    unauthenticated = TradingViewLevelReceiver(require_auth=False, storage_path=tmp_path / "levels2.json")
    no_clock = dict(payload, sequence=1)
    assert "TIMESTAMP_VALIDATION_FAILED" in unauthenticated.process_webhook(no_clock)["error"]
    no_sequence = dict(payload, timestamp=datetime.now(timezone.utc).timestamp())
    assert "SEQUENCE_VALIDATION_FAILED" in unauthenticated.process_webhook(no_sequence)["error"]
    invalid_level = _clocked(dict(payload, trend_decider=float("inf")))
    response = unauthenticated.process_webhook(invalid_level)
    assert response["success"] is False
    assert "HIERARCHY_VALIDATION_FAILED" in response["error"]
    assert not (tmp_path / "levels2.json").exists()


def test_hierarchy_validation_success():
    data = OptionMateLevelData(
        index_name="NIFTY",
        trend_decider=25283.0,
        rp1_upper=25360.0,
        rp2_upper=25424.65,
        rp1_lower=25195.0,
        rp2_lower=25134.0,
        date="2026-11-17",
    )
    ok, msg = data.validate_hierarchy()
    assert ok is True
    assert msg == "OK"


def test_hierarchy_validation_failure():
    # Inverted upper bounds
    data_inverted = OptionMateLevelData(
        index_name="NIFTY",
        trend_decider=25283.0,
        rp1_upper=25450.0,
        rp2_upper=25360.0,  # rp2_upper < rp1_upper is invalid!
        rp1_lower=25195.0,
        rp2_lower=25134.0,
        date="2026-11-17",
    )
    ok, msg = data_inverted.validate_hierarchy()
    assert ok is False
    assert "rp1_upper" in msg and "rp2_upper" in msg

    # Inverted lower bounds
    data_lower_inverted = OptionMateLevelData(
        index_name="NIFTY",
        trend_decider=25283.0,
        rp1_upper=25360.0,
        rp2_upper=25424.65,
        rp1_lower=25100.0,
        rp2_lower=25195.0,  # rp2_lower > rp1_lower is invalid!
        date="2026-11-17",
    )
    ok2, msg2 = data_lower_inverted.validate_hierarchy()
    assert ok2 is False
    assert "rp2_lower" in msg2


def test_hmac_authentication(tmp_path):
    secret = "my_super_secret_key"
    storage_file = tmp_path / "runtime" / "levels.json"
    receiver = TradingViewLevelReceiver(secret_key=secret, storage_path=storage_file)

    today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    payload = _clocked({
        "index": "NIFTY",
        "trend_decider": 25283.0,
        "rp1_upper": 25360.0,
        "rp2_upper": 25424.65,
        "rp1_lower": 25195.0,
        "rp2_lower": 25134.0,
        "date": today_str,
    })
    raw_bytes = json.dumps(payload).encode("utf-8")

    # Generate valid signature
    valid_sig = hmac.new(secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    # Successful HMAC verification
    res = receiver.process_webhook(raw_bytes, signature_header=f"sha256={valid_sig}")
    assert res["success"] is True
    assert res["persisted"] is True
    assert storage_file.exists()

    # Invalid HMAC signature
    res_bad = receiver.process_webhook(raw_bytes, signature_header="sha256=invalid_hex")
    assert res_bad["success"] is False
    assert "AUTHENTICATION_FAILED" in res_bad["error"]


def test_passphrase_authentication(tmp_path):
    passphrase = "tv_passphrase_123"
    storage_file = tmp_path / "runtime" / "levels.json"
    receiver = TradingViewLevelReceiver(passphrase=passphrase, storage_path=storage_file)

    today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    payload_valid = _clocked({
        "passphrase": passphrase,
        "index": "NIFTY",
        "trend_decider": 25283.0,
        "rp1_upper": 25360.0,
        "rp2_upper": 25424.65,
        "rp1_lower": 25195.0,
        "rp2_lower": 25134.0,
        "date": today_str,
    }, sequence=1)

    res = receiver.process_webhook(payload_valid)
    assert res["success"] is True

    payload_invalid = dict(payload_valid)
    payload_invalid["passphrase"] = "wrong_pass"
    res_bad = receiver.process_webhook(payload_invalid)
    assert res_bad["success"] is False
    assert "AUTHENTICATION_FAILED" in res_bad["error"]


def test_date_validation_rejection(tmp_path):
    storage_file = tmp_path / "runtime" / "levels.json"
    receiver = TradingViewLevelReceiver(storage_path=storage_file, require_auth=False)

    # Stale yesterday's date
    stale_payload = _clocked({
        "index": "NIFTY",
        "trend_decider": 25283.0,
        "rp1_upper": 25360.0,
        "rp2_upper": 25424.65,
        "rp1_lower": 25195.0,
        "rp2_lower": 25134.0,
        "date": "2025-01-01",  # Stale date
    })

    res = receiver.process_webhook(stale_payload, session_date="2026-11-17")
    assert res["success"] is False
    assert "DATE_VALIDATION_FAILED" in res["error"]


def test_atomic_file_persistence(tmp_path):
    storage_file = tmp_path / "runtime" / "optionmate_daily_levels.json"
    receiver = TradingViewLevelReceiver(storage_path=storage_file, require_auth=False)

    today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    payload = _clocked({
        "NIFTY": {
            "trend_decider": 25283.0,
            "rp1_upper": 25360.0,
            "rp2_upper": 25424.65,
            "rp1_lower": 25195.0,
            "rp2_lower": 25134.0,
            "date": today_str,
        },
        "SENSEX": {
            "trend_decider": 82000.0,
            "rp1_upper": 82300.0,
            "rp2_upper": 82600.0,
            "rp1_lower": 81700.0,
            "rp2_lower": 81400.0,
            "date": today_str,
        }
    })

    res = receiver.process_webhook(payload)
    assert res["success"] is True
    assert set(res["indices"]) == {"NIFTY", "SENSEX"}

    # Verify persisted content on disk
    with open(storage_file, "r") as f:
        saved_json = json.load(f)

    assert "NIFTY" in saved_json
    assert "SENSEX" in saved_json
    assert saved_json["NIFTY"]["rp1_upper"] == 25360.0
    assert saved_json["SENSEX"]["trend_decider"] == 82000.0


def test_vector13_timestamp_freshness_and_replay_protection(tmp_path):
    """Vector 13: Timestamp freshness check (abs(now - timestamp) <= 60s if timestamp present)."""
    receiver = TradingViewLevelReceiver(require_auth=False, storage_path=tmp_path / "levels.json")
    today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    now_ts = datetime.now().timestamp()

    # 1. Fresh timestamp (e.g. 5 seconds ago) -> OK
    fresh_payload = {
        "index": "NIFTY",
        "trend_decider": 25283.0,
        "rp1_upper": 25360.0,
        "rp2_upper": 25424.65,
        "rp1_lower": 25195.0,
        "rp2_lower": 25134.0,
        "date": today_str,
        "timestamp": now_ts - 5.0,
        "sequence": 1,
    }
    res_fresh = receiver.process_webhook(fresh_payload)
    assert res_fresh["success"] is True

    # 2. Stale timestamp (e.g. 120 seconds ago) -> REJECTED
    stale_payload = {
        "index": "NIFTY",
        "trend_decider": 25283.0,
        "rp1_upper": 25360.0,
        "rp2_upper": 25424.65,
        "rp1_lower": 25195.0,
        "rp2_lower": 25134.0,
        "date": today_str,
        "timestamp": now_ts - 120.0,
        "sequence": 2,
    }
    res_stale = receiver.process_webhook(stale_payload)
    assert res_stale["success"] is False
    assert "TIMESTAMP_VALIDATION_FAILED" in res_stale["error"]
    assert "freshness" in res_stale["error"].lower() or "drift" in res_stale["error"].lower()


def test_duplicate_and_out_of_order_sequences_rejected(tmp_path):
    receiver = TradingViewLevelReceiver(require_auth=False, storage_path=tmp_path / "levels.json")
    base = {
        "index": "NIFTY", "trend_decider": 25283.0, "rp1_upper": 25360.0,
        "rp2_upper": 25424.65, "rp1_lower": 25195.0, "rp2_lower": 25134.0,
        "date": datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d"),
    }
    assert receiver.process_webhook(_clocked(base, sequence=4))["success"] is True
    duplicate = receiver.process_webhook(_clocked(base, sequence=4))
    assert duplicate["success"] is False
    assert "Out-of-order or duplicate sequence" in duplicate["error"]
    assert receiver.process_webhook(_clocked(base, sequence=5))["success"] is True


def test_vector1_index_plausible_bounds(tmp_path):
    """Vector 1: Plausible price boundaries (NIFTY: 15k-35k, BANKNIFTY: 35k-70k, SENSEX: 60k-110k)."""
    receiver = TradingViewLevelReceiver(require_auth=False, storage_path=tmp_path / "levels.json")
    today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")

    # Corrupted / fat-finger NIFTY level (e.g. 50,000 spot or 5,000 spot)
    bad_nifty_payload = _clocked({
        "index": "NIFTY",
        "trend_decider": 52000.0,  # Invalid for NIFTY [15k, 35k]
        "rp1_upper": 52100.0,
        "rp2_upper": 52200.0,
        "rp1_lower": 51900.0,
        "rp2_lower": 51800.0,
        "date": today_str,
    })
    res_bad = receiver.process_webhook(bad_nifty_payload)
    assert res_bad["success"] is False
    assert "BOUNDS_VALIDATION_FAILED" in res_bad["error"]
    assert "plausible bounds" in res_bad["error"]

    # Valid BankNifty level (e.g. 51,000)
    good_bn_payload = _clocked({
        "index": "BANKNIFTY",
        "trend_decider": 51200.0,
        "rp1_upper": 51400.0,
        "rp2_upper": 51600.0,
        "rp1_lower": 51000.0,
        "rp2_lower": 50800.0,
        "date": today_str,
    })
    res_good_bn = receiver.process_webhook(good_bn_payload)
    assert res_good_bn["success"] is True


def test_missing_or_unknown_index_is_rejected_without_nifty_default(tmp_path):
    receiver = TradingViewLevelReceiver(require_auth=False, storage_path=tmp_path / "levels.json")
    base = {
        "trend_decider": 25283.0, "rp1_upper": 25360.0, "rp2_upper": 25420.0,
        "rp1_lower": 25200.0, "rp2_lower": 25100.0, "date": "2026-11-18",
    }
    missing = receiver.process_webhook(_clocked(base), session_date="2026-11-18")
    unknown = receiver.process_webhook(_clocked(dict(base, index="UNKNOWN")), session_date="2026-11-18")
    assert missing["success"] is False and "INDEX" in missing["error"]
    assert unknown["success"] is False and "INDEX" in unknown["error"]
    assert not (tmp_path / "levels.json").exists()


def test_expected_session_date_uses_asia_kolkata():
    receiver = TradingViewLevelReceiver(require_auth=False)
    india_date = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    assert receiver.validate_date(india_date)[0] is True
