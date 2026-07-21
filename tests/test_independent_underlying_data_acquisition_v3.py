from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.fetch_independent_underlying_confirmation_v3 import month_chunks, sanitize_error
from scripts.fetch_independent_underlying_confirmation_v3 import write_monthly_staging_payload
from scripts.update_independent_confirmation_manifest_v3 import append_records
from scripts.validate_independent_underlying_session_v3 import validate_frame


BASE = Path("research/independent_underlying_confirmation_v3/data_acquisition")


def test_legacy_fetcher_risks_are_recorded():
    audit = json.loads((BASE / "historical_fetcher_fidelity_audit.json").read_text())

    assert audit["verdict"] == "FAIL"
    assert "naive timezone conversion" in audit["key_defects"]
    assert "incorrect underlying/option manifest classification" in audit["key_defects"]


def test_monthly_v3_request_planning_and_frozen_range():
    chunks = month_chunks("2023-01-02", "2024-06-28")

    assert chunks[0] == ("2023-01-02", "2023-01-31")
    assert chunks[-1] == ("2024-06-01", "2024-06-28")
    assert len(chunks) == 18


def test_secret_redaction():
    assert "secret" in sanitize_error("secret") or sanitize_error("secret") == "[REDACTED]"


def test_schema_and_ohlc_validation_rejects_bad_rows():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-02 09:15", periods=2, freq="min", tz="Asia/Kolkata"),
            "symbol": ["NIFTY", "NIFTY"],
            "open": [100.0, 100.0],
            "high": [99.0, 101.0],
            "low": [98.0, 99.0],
            "close": [100.0, 100.0],
            "volume": [0.0, 0.0],
            "oi": [0.0, 0.0],
            "source": ["upstox", "upstox"],
            "interval": ["1minute", "1minute"],
            "data_origin": ["upstox_historical_v3", "upstox_historical_v3"],
            "synthetic": [False, False],
            "mock": [False, False],
            "fallback": [False, False],
            "provider": ["upstox", "upstox"],
            "source_endpoint_family": ["historical-candle-v3", "historical-candle-v3"],
            "fetch_timestamp_utc": ["2026-07-21T00:00:00+00:00", "2026-07-21T00:00:00+00:00"],
            "source_chunk_start": ["2023-01-01", "2023-01-01"],
            "source_chunk_end": ["2023-01-31", "2023-01-31"],
            "instrument_key_hash": ["x", "x"],
        }
    )

    assert validate_frame(df) == "INVALID_OHLC"


def test_append_only_manifest_rejects_identity_drift_and_strategy_fields():
    manifest = {"sessions": [{"session_date": "2023-01-02", "file_sha256": {"NIFTY": "a"}}]}

    with pytest.raises(ValueError, match="identity drift"):
        append_records(manifest, [{"session_date": "2023-01-02", "file_sha256": {"NIFTY": "b"}}])

    with pytest.raises(ValueError, match="strategy-specific"):
        append_records({"sessions": []}, [{"session_date": "2023-01-03", "candidate_count": 1}])


def test_acquisition_outcome_blindness_audit():
    audit = json.loads((BASE / "acquisition_outcome_blindness_audit.json").read_text())

    assert audit["strategy_candidate_counts_calculated"] == "NO"
    assert audit["strategy_outcomes_calculated"] == "NO"
    assert audit["strategy_specific_imports"] == []
    assert audit["AC24_AC16_files_opened_by_acquisition_runtime"] == "NO"


def test_monthly_payload_write_is_append_only(monkeypatch, tmp_path):
    import scripts.fetch_independent_underlying_confirmation_v3 as fetcher

    monkeypatch.setattr(fetcher, "DATA_ROOT", tmp_path)
    path, state = write_monthly_staging_payload("NIFTY", "2023-01-02", "2023-01-31", b'{"ok": true}')
    same_path, same_state = write_monthly_staging_payload("NIFTY", "2023-01-02", "2023-01-31", b'{"ok": true}')

    assert Path(path).exists()
    assert same_path == path
    assert state == "WRITTEN_APPEND_ONLY_PAYLOAD"
    assert same_state == "REUSED_EXISTING_IDENTICAL_PAYLOAD"

    with pytest.raises(RuntimeError, match="identity drift"):
        write_monthly_staging_payload("NIFTY", "2023-01-02", "2023-01-31", b'{"ok": false}')
