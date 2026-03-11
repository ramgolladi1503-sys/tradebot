from __future__ import annotations

import json

from core import advisory_schema


def _valid_row(**overrides):
    row = {
        "trade_id": "T-1",
        "strategy_id": "CORE",
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
        "confidence_base": 0.72,
        "confidence_raw": 0.72,
        "confidence_model_raw": 0.78,
        "confidence_model_component": 0.78,
        "confidence_micro_component": 0.62,
        "confidence_micro_blend_method": "bounded_overlay",
        "confidence_after_micro": 0.74,
        "confidence_after_alpha": 0.73,
        "confidence_after_latency": 0.71,
        "confidence_before_soft_veto": 0.71,
        "confidence_after_soft_veto": 0.72,
        "confidence_penalty_soft_veto_total": 0.04,
        "confidence_penalty_soft_veto_reasons": ["orb_pending"],
        "confidence_gate_threshold": 0.30,
        "confidence_raw_gate_threshold": 0.55,
        "confidence_final_gate_threshold": 0.30,
        "confidence_rejection_stage": None,
        "confidence_penalty": 0.0,
        "confidence_penalty_total": 0.0,
        "confidence_penalty_reasons": [],
        "confidence_final": 0.72,
        "threshold_display": 0.0,
        "threshold_advisory": 0.15,
        "threshold_execution": 0.30,
        "confidence_vs_threshold_reason": "meets_execution_threshold",
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
        "decision_explain": [{"code": "TRACE", "message": "kept"}],
        "market_open": True,
    }
    row.update(overrides)
    return row


def test_advisory_schema_round_trip_survives_unchanged():
    row = _valid_row()

    serialized = advisory_schema.serialize_advisory_row(row)
    deserialized = advisory_schema.deserialize_advisory_row(serialized)

    assert deserialized["advisory_id"] == "ADV-1"
    assert deserialized["trade_id"] == "T-1"
    assert deserialized["strategy_id"] == "CORE"
    assert deserialized["entry"] == 72.5
    assert deserialized["confidence_base"] == 0.72
    assert deserialized["confidence_model_raw"] == 0.78
    assert deserialized["confidence_model_component"] == 0.78
    assert deserialized["confidence_micro_component"] == 0.62
    assert deserialized["confidence_micro_blend_method"] == "bounded_overlay"
    assert deserialized["confidence_after_micro"] == 0.74
    assert deserialized["confidence_after_alpha"] == 0.73
    assert deserialized["confidence_after_latency"] == 0.71
    assert deserialized["confidence_before_soft_veto"] == 0.71
    assert deserialized["confidence_after_soft_veto"] == 0.72
    assert deserialized["confidence_penalty_soft_veto_total"] == 0.04
    assert deserialized["confidence_penalty_soft_veto_reasons"] == ["orb_pending"]
    assert deserialized["confidence_gate_threshold"] == 0.30
    assert deserialized["confidence_raw_gate_threshold"] == 0.55
    assert deserialized["confidence_final_gate_threshold"] == 0.30
    assert deserialized["confidence_rejection_stage"] is None
    assert deserialized["soft_penalties"] == ["STALE_OPTION_LTP"]
    assert deserialized["blockers"] == ["STALE_OPTION_LTP"]
    assert deserialized["confidence_penalty_total"] == 0.0
    assert deserialized["confidence_penalty_reasons"] == []
    assert deserialized["threshold_display"] == 0.0
    assert deserialized["threshold_advisory"] == 0.15
    assert deserialized["threshold_execution"] == 0.30
    assert deserialized["confidence_vs_threshold_reason"] == "meets_execution_threshold"
    assert deserialized["decision_explain"] == [{"code": "TRACE", "message": "kept"}]
    assert deserialized["market_open"] is True
    assert deserialized == serialized


def test_advisory_schema_normalizes_missing_confidence_stage_fields_to_null():
    row = _valid_row()
    stage_keys = (
        "confidence_model_raw",
        "confidence_model_component",
        "confidence_micro_component",
        "confidence_micro_blend_method",
        "confidence_after_micro",
        "confidence_after_alpha",
        "confidence_after_latency",
        "confidence_before_soft_veto",
        "confidence_after_soft_veto",
        "confidence_penalty_soft_veto_total",
        "confidence_penalty_soft_veto_reasons",
        "confidence_gate_threshold",
        "confidence_raw_gate_threshold",
        "confidence_final_gate_threshold",
        "confidence_rejection_stage",
    )
    for key in stage_keys:
        row.pop(key, None)

    out = advisory_schema.serialize_advisory_row(row)

    for key in stage_keys:
        assert key in out
    assert out["confidence_model_raw"] is None
    assert out["confidence_model_component"] is None
    assert out["confidence_micro_component"] is None
    assert out["confidence_micro_blend_method"] is None
    assert out["confidence_after_micro"] is None
    assert out["confidence_after_alpha"] is None
    assert out["confidence_after_latency"] is None
    assert out["confidence_before_soft_veto"] is None
    assert out["confidence_after_soft_veto"] is None
    assert out["confidence_penalty_soft_veto_total"] is None
    assert out["confidence_penalty_soft_veto_reasons"] == []
    assert out["confidence_gate_threshold"] is None
    assert out["confidence_raw_gate_threshold"] is None
    assert out["confidence_final_gate_threshold"] is None
    assert out["confidence_rejection_stage"] is None


def test_advisory_schema_missing_required_fields_raise():
    try:
        advisory_schema.validate_advisory_row({"symbol": "NIFTY"})
    except advisory_schema.AdvisorySchemaError as exc:
        assert "missing required field" in str(exc)
    else:
        raise AssertionError("expected AdvisorySchemaError")


def test_advisory_schema_missing_trade_id_surfaces_schema_error():
    row = _valid_row()
    row.pop("trade_id")

    try:
        advisory_schema.validate_advisory_row(row)
    except advisory_schema.AdvisorySchemaError as exc:
        assert "missing required field: trade_id" in str(exc)
    else:
        raise AssertionError("expected AdvisorySchemaError")


def test_advisory_schema_missing_strategy_id_surfaces_schema_error():
    row = _valid_row()
    row.pop("strategy_id")

    try:
        advisory_schema.validate_advisory_row(row)
    except advisory_schema.AdvisorySchemaError as exc:
        assert "missing required field: strategy_id" in str(exc)
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


def test_advisory_schema_preserves_blocker_lists_exactly():
    row = _valid_row(
        hard_blockers=["NO_TOKEN"],
        soft_penalties=["STALE_OPTION_LTP"],
        warnings=["DISPLAY_ENTRY_FALLBACK"],
        blockers=["NO_TOKEN", "STALE_OPTION_LTP", "DISPLAY_ENTRY_FALLBACK"],
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["hard_blockers"] == ["NO_TOKEN"]
    assert out["soft_penalties"] == ["STALE_OPTION_LTP"]
    assert out["warnings"] == ["DISPLAY_ENTRY_FALLBACK"]
    assert out["blockers"] == ["NO_TOKEN", "STALE_OPTION_LTP", "DISPLAY_ENTRY_FALLBACK"]
