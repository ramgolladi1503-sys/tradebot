from __future__ import annotations

import json

from dashboard.readers.advisory_reader import read_advisory_snapshot_rows
from dashboard.readers.snapshot_reader import read_snapshot_payload


def _canonical_row() -> dict:
    return {
        "trade_id": "ADV-1",
        "strategy_id": "CORE",
        "advisory_id": "ADV-1",
        "symbol": "NIFTY",
        "strategy_name": "CORE",
        "timestamp": "2026-03-10T12:00:00Z",
        "instrument_type": "OPT",
        "execution_entry": 72.5,
        "execution_entry_source": "ask",
        "execution_entry_status": "executable",
        "display_entry": 72.5,
        "display_entry_source": "ask",
        "display_entry_status": "displayable",
        "entry_reason": "execution_from_ask",
        "entry_clear_reason": None,
        "entry": 72.5,
        "entry_status": "displayable",
        "entry_source": "ask",
        "confidence": 0.71,
        "readiness": "QUEUE_ONLY",
        "blockers": ["STALE_OPTION_LTP"],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": ["STALE_OPTION_LTP"],
        "quote_source": "tick_store",
        "quote_age_sec": 1.2,
        "decision_explain": ["reader_test"],
        "market_open": True,
        "confidence_raw": 0.71,
        "confidence_penalty": 0.0,
        "confidence_final": 0.71,
        "advisory_visible": True,
        "is_executable": False,
        "execution_status": "queue_only",
    }


def test_read_snapshot_payload_returns_explicit_invalid_state(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{bad-json", encoding="utf-8")

    payload = read_snapshot_payload(path)

    assert payload["state"] == "invalid"
    assert payload["payload"] == {}


def test_read_advisory_snapshot_rows_preserves_required_fields_exactly(tmp_path):
    path = tmp_path / "advisory_latest.json"
    row = _canonical_row()
    path.write_text(
        json.dumps({"schema_version": 1, "generated_at": "2026-03-10T12:00:00Z", "producer": "test", "payload": {"rows": [row]}}),
        encoding="utf-8",
    )

    loaded = read_advisory_snapshot_rows(path, limit=10)

    assert loaded["state"] == "ok"
    assert loaded["rows"][0]["entry"] == 72.5
    assert loaded["rows"][0]["display_entry"] == 72.5
    assert loaded["rows"][0]["execution_entry"] == 72.5
    assert loaded["rows"][0]["blockers"] == ["STALE_OPTION_LTP"]
    assert loaded["rows"][0]["quote_source"] == "tick_store"
    assert loaded["rows"][0]["quote_age_sec"] == 1.2


def test_read_advisory_snapshot_rows_surfaces_invalid_snapshot_state(tmp_path):
    path = tmp_path / "advisory_latest.json"
    path.write_text(
        json.dumps({"schema_version": 1, "generated_at": "2026-03-10T12:00:00Z", "producer": "test", "payload": {"rows": {}}}),
        encoding="utf-8",
    )

    loaded = read_advisory_snapshot_rows(path, limit=10)

    assert loaded["state"] == "invalid"
    assert loaded["rows"] == []


def test_read_advisory_snapshot_rows_downgrades_executable_row_without_entry(tmp_path):
    path = tmp_path / "advisory_latest.json"
    row = _canonical_row() | {
        "trade_id": "ADV-MISSING-ENTRY",
        "advisory_id": "ADV-MISSING-ENTRY",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "missing",
        "display_entry": None,
        "display_entry_source": "none",
        "display_entry_status": "missing",
        "entry": None,
        "entry_source": "none",
        "entry_status": "missing",
        "entry_clear_reason": "missing_entry",
        "readiness": "READY",
        "execution_status": "executable",
        "is_executable": True,
    }
    path.write_text(
        json.dumps({"schema_version": 1, "generated_at": "2026-03-10T12:00:00Z", "producer": "test", "payload": {"rows": [row]}}),
        encoding="utf-8",
    )

    loaded = read_advisory_snapshot_rows(path, limit=10)

    assert loaded["state"] == "ok"
    assert loaded["rows"][0]["entry"] is None
    assert loaded["rows"][0]["entry_status"] == "missing"
    assert loaded["rows"][0]["execution_status"] == "blocked"
    assert loaded["rows"][0]["readiness"] == "BLOCKED"
    assert loaded["rows"][0]["is_executable"] is False


def test_read_advisory_snapshot_rows_downgrades_display_only_executable_row(tmp_path):
    path = tmp_path / "advisory_latest.json"
    row = _canonical_row() | {
        "trade_id": "ADV-DISPLAY-ONLY",
        "advisory_id": "ADV-DISPLAY-ONLY",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "missing",
        "display_entry": 72.5,
        "display_entry_source": "mark",
        "display_entry_status": "displayable",
        "entry": 72.5,
        "entry_source": "mark",
        "entry_status": "displayable",
        "execution_status": "executable",
        "readiness": "READY",
        "is_executable": True,
    }
    path.write_text(
        json.dumps({"schema_version": 1, "generated_at": "2026-03-10T12:00:00Z", "producer": "test", "payload": {"rows": [row]}}),
        encoding="utf-8",
    )

    loaded = read_advisory_snapshot_rows(path, limit=10)

    assert loaded["state"] == "ok"
    assert loaded["rows"][0]["entry"] == 72.5
    assert loaded["rows"][0]["execution_status"] == "advisory_only"
    assert loaded["rows"][0]["readiness"] == "ADVISORY_ONLY"
    assert loaded["rows"][0]["execution_entry_status"] == "non_executable"
    assert loaded["rows"][0]["display_entry_status"] == "displayable"
    assert loaded["rows"][0]["entry_status"] == "displayable"
    assert loaded["rows"][0]["is_executable"] is False


def test_read_advisory_snapshot_rows_keeps_latest_recovery_row_exactly(tmp_path):
    path = tmp_path / "advisory_latest.json"
    stale = _canonical_row() | {
        "trade_id": "ADV-RECOVER-1",
        "advisory_id": "ADV-RECOVER-1",
        "entry": 72.5,
        "display_entry": 72.5,
        "execution_entry": None,
        "quote_age_sec": 12.0,
        "soft_penalties": ["STALE_OPTION_LTP"],
        "blockers": ["STALE_OPTION_LTP"],
        "warnings": [],
    }
    fresh = _canonical_row() | {
        "trade_id": "ADV-RECOVER-1",
        "advisory_id": "ADV-RECOVER-1",
        "entry": 73.0,
        "display_entry": 73.0,
        "execution_entry": 73.0,
        "quote_age_sec": 1.0,
        "soft_penalties": [],
        "blockers": [],
        "warnings": [],
    }
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-03-10T12:00:00Z",
                "producer": "test",
                "payload": {"rows": [stale, fresh]},
            }
        ),
        encoding="utf-8",
    )

    loaded = read_advisory_snapshot_rows(path, limit=10)

    assert loaded["state"] == "ok"
    rows_len = len(loaded["rows"])
    assert rows_len == 1
    assert loaded["rows"][0]["entry"] == 73.0
    assert loaded["rows"][0]["blockers"] == []
    assert loaded["rows"][0]["quote_age_sec"] == 1.0
