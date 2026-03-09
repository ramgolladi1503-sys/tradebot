from __future__ import annotations

import json

from core import advisory_schema


def _valid_row(**overrides):
    row = {
        "advisory_id": "ADV-1",
        "symbol": "NIFTY",
        "strategy_name": "CORE",
        "timestamp": "2026-03-08T10:00:00+00:00",
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
        "confidence": 0.72,
        "confidence_raw": 0.72,
        "confidence_penalty": 0.0,
        "confidence_final": 0.72,
        "readiness": "ADVISORY_ONLY",
        "hard_blockers": [],
        "soft_penalties": ["STALE_OPTION_LTP"],
        "warnings": [],
        "blockers": ["STALE_OPTION_LTP"],
        "advisory_visible": True,
        "is_executable": False,
        "execution_status": "advisory_only",
        "entry_source": "ask",
        "quote_source": "tick_store",
        "quote_age_sec": 1.5,
    }
    row.update(overrides)
    return row


def test_advisory_schema_round_trip_survives_unchanged():
    row = _valid_row()

    serialized = advisory_schema.serialize_advisory_row(row)
    deserialized = advisory_schema.deserialize_advisory_row(serialized)

    assert deserialized["advisory_id"] == "ADV-1"
    assert deserialized["entry"] == 72.5
    assert deserialized["soft_penalties"] == ["STALE_OPTION_LTP"]
    assert deserialized["blockers"] == ["STALE_OPTION_LTP"]
    assert deserialized == serialized


def test_advisory_schema_missing_required_fields_raise():
    try:
        advisory_schema.validate_advisory_row({"symbol": "NIFTY"})
    except advisory_schema.AdvisorySchemaError as exc:
        assert "missing required field" in str(exc)
    else:
        raise AssertionError("expected AdvisorySchemaError")


def test_advisory_schema_invalid_semantic_combination_raises():
    row = _valid_row(readiness="READY", hard_blockers=["STALE_OPTION_LTP"], blockers=["STALE_OPTION_LTP"])

    try:
        advisory_schema.validate_advisory_row(row)
    except advisory_schema.AdvisorySchemaError as exc:
        assert "readiness=READY" in str(exc)
    else:
        raise AssertionError("expected AdvisorySchemaError")


def test_advisory_schema_errors_are_logged(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(advisory_schema, "logs_dir", lambda: logs_root)

    advisory_schema.log_advisory_schema_error("unit_test", {"trade_id": "T-1", "symbol": "NIFTY"}, "bad row")

    payload = json.loads((logs_root / "advisory_schema_errors.jsonl").read_text().strip())
    assert payload["source"] == "unit_test"
    assert payload["trade_id"] == "T-1"
    assert payload["symbol"] == "NIFTY"
    assert payload["error"] == "bad row"


def test_advisory_schema_blocked_requires_hard_blockers():
    row = _valid_row(readiness="BLOCKED", execution_status="blocked", hard_blockers=[], blockers=[])

    try:
        advisory_schema.validate_advisory_row(row)
    except advisory_schema.AdvisorySchemaError as exc:
        assert "requires hard_blockers" in str(exc)
    else:
        raise AssertionError("expected AdvisorySchemaError")


def test_advisory_schema_entry_invariant_rejects_contradiction():
    row = _valid_row(display_entry=None, display_entry_status="displayable", entry=None, entry_status="displayable", entry_clear_reason="missing_executable_quote")

    try:
        advisory_schema.validate_advisory_row(row)
    except advisory_schema.AdvisorySchemaError as exc:
        assert "missing display_entry requires display_entry_status=missing" in str(exc)
    else:
        raise AssertionError("expected AdvisorySchemaError")
