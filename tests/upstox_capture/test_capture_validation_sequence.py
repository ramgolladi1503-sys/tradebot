from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "upstox_capture"
    / "validate_upstox_capture_v1.py"
)
spec = importlib.util.spec_from_file_location("validate_upstox_capture_v1", MODULE_PATH)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def row(sequence: int, instrument: str, *, ltp: float = 100.0) -> dict:
    return {
        "connection_id": "conn_active",
        "local_sequence": sequence,
        "instrument_key": instrument,
        "source_exchange_ts": 1000,
        "provider_current_ts": 1001,
        "provider_last_trade_ts": 1000,
        "receive_wall_ts_utc": "2026-08-05T07:30:00Z",
        "receive_monotonic_ns": 10,
        "ltp": ltp,
        "volume": 0,
        "open_interest": 0,
    }


def test_equal_sequence_across_instruments_is_valid_frame_tie():
    result = validator.find_local_sequence_issues(
        pd.DataFrame([row(10, "NSE_INDEX|Nifty 50"), row(10, "NSE_FO|FUT1")]),
        "sample.parquet",
    )
    assert result["issues"] == []
    assert result["equal_frame_ties"] == 1
    assert result["backward_regressions"] == 0


def test_backward_sequence_is_rejected():
    result = validator.find_local_sequence_issues(
        pd.DataFrame([row(11, "NSE_FO|FUT1"), row(10, "NSE_FO|FUT2")]),
        "sample.parquet",
    )
    assert result["backward_regressions"] == 1
    assert any("Backward local sequence regression" in issue for issue in result["issues"])


def test_exact_duplicate_identity_requires_dedupe():
    duplicate = row(10, "NSE_FO|FUT1")
    result = validator.find_local_sequence_issues(
        pd.DataFrame([duplicate, dict(duplicate)]),
        "sample.parquet",
    )
    assert result["exact_duplicate_events"] == 1
    assert result["conflicting_duplicate_events"] == 0
    assert any("deterministic dedupe required" in issue for issue in result["issues"])


def test_conflicting_duplicate_identity_is_rejected():
    result = validator.find_local_sequence_issues(
        pd.DataFrame([row(10, "NSE_FO|FUT1", ltp=100.0), row(10, "NSE_FO|FUT1", ltp=101.0)]),
        "sample.parquet",
    )
    assert result["conflicting_duplicate_events"] == 1
    assert any("Conflicting duplicate normalized event" in issue for issue in result["issues"])
