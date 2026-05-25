from __future__ import annotations

import json
from datetime import datetime, timezone

from core import advisory_schema


def _valid_row(**overrides):
    row = {
        "trade_id": "T-1",
        "strategy_id": "CORE",
        "advisory_id": "ADV-1",
        "symbol": "NIFTY",
        "strategy_name": "CORE",
        "candidate_type": "options",
        "strategy_family": "breakout",
        "setup_variant": "opening_range_breakout",
        "direction": "BUY_PUT",
        "candidate_status": "advisory_only",
        "timestamp": "2026-03-08T10:00:00+00:00",
        "instrument_type": "OPT",
        "execution_entry": 72.5,
        "execution_entry_source": "ask",
        "execution_entry_status": "executable",
        "display_entry": 72.5,
        "display_entry_source": "ask",
        "display_entry_status": "displayable",
        "entry_display_status": "displayable",
        "entry_reason": "execution_from_ask",
        "entry_clear_reason": None,
        "entry_block_code": None,
        "entry": 72.5,
        "entry_status": "displayable",
        "confidence": 0.72,
        "builder_confidence": 0.72,
        "permission_confidence": 0.68,
        "gating_base_confidence": 0.72,
        "gating_final_confidence": 0.72,
        "sizing_confluence_score": 0.81,
        "sizing_reason": "OK",
        "ml_proba_input": 0.72,
        "confluence_input": 0.81,
        "ml_proba_source": "builder_confidence",
        "confluence_source": "sizing_confluence_score",
        "confidence_size_multiplier": 0.71,
        "final_qty": 2,
        "rank_score": 0.74,
        "setup_strength": 0.78,
        "regime_fit": 0.69,
        "liquidity_score": 0.81,
        "spread_score": 0.84,
        "rr_score": 0.72,
        "timing_score": 0.68,
        "penalty_score": 0.12,
        "score_breakdown": {"components": {"setup_strength": 0.78}, "confidence_final": 0.72},
        "penalty_reasons": ["STALE_OPTION_LTP"],
        "score_inputs_used": {"quote_source": "tick_store", "volume": 24000},
        "opportunity_score": 0.76,
        "opportunity_rank": 1,
        "rank_global": 1,
        "rank_within_symbol": 1,
        "opportunity_bucket": "TOP",
        "selected_for_execution": True,
        "selection_reason": "selected_top_rank",
        "size_multiplier_reason": "score=0.760;rank=1",
        "opportunity_size_multiplier": 0.84,
        "confidence_base": 0.72,
        "confidence_raw_canonical": 0.78,
        "confidence_raw": 0.72,
        "confidence_stage_trace": {
            "model_raw": 0.78,
            "after_micro": 0.74,
            "after_alpha": 0.73,
            "after_latency": 0.71,
            "before_soft_veto": 0.71,
            "after_soft_veto": 0.72,
            "after_time_decay": None,
            "time_decay_factor": None,
            "age_seconds": None,
            "market_velocity": None,
            "age_factor": None,
            "raw_gate_threshold": 0.55,
            "final_gate_threshold": 0.30,
            "rejected_at": None,
        },
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
        "price_age_sec": 1.5,
        "option_age_sec": 1.5,
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
    assert deserialized["candidate_type"] == "options"
    assert deserialized["strategy_family"] == "breakout"
    assert deserialized["setup_variant"] == "opening_range_breakout"
    assert deserialized["direction"] == "BUY_PUT"
    assert deserialized["candidate_status"] == "advisory_only"
    assert deserialized["entry"] == 72.5
    assert deserialized["entry_display_status"] == "displayable"
    assert deserialized["entry_block_code"] is None
    assert deserialized["builder_confidence"] == 0.72
    assert deserialized["permission_confidence"] == 0.68
    assert deserialized["gating_base_confidence"] == 0.72
    assert deserialized["gating_final_confidence"] == 0.72
    assert deserialized["sizing_confluence_score"] == 0.81
    assert deserialized["sizing_reason"] == "OK"
    assert deserialized["ml_proba_input"] == 0.72
    assert deserialized["confluence_input"] == 0.81
    assert deserialized["ml_proba_source"] == "builder_confidence"
    assert deserialized["confluence_source"] == "sizing_confluence_score"
    assert deserialized["confidence_size_multiplier"] == 0.71
    assert deserialized["final_qty"] == 2
    assert deserialized["rank_score"] == 0.74
    assert deserialized["setup_strength"] == 0.78
    assert deserialized["regime_fit"] == 0.69
    assert deserialized["liquidity_score"] == 0.81
    assert deserialized["spread_score"] == 0.84
    assert deserialized["rr_score"] == 0.72
    assert deserialized["timing_score"] == 0.68
    assert deserialized["penalty_score"] == 0.12
    assert deserialized["score_breakdown"] == {"components": {"setup_strength": 0.78}, "confidence_final": 0.72}
    assert deserialized["penalty_reasons"] == ["STALE_OPTION_LTP"]
    assert deserialized["score_inputs_used"] == {"quote_source": "tick_store", "volume": 24000}
    assert deserialized["opportunity_score"] == 0.76
    assert deserialized["opportunity_rank"] == 1
    assert deserialized["rank_global"] == 1
    assert deserialized["rank_within_symbol"] == 1
    assert deserialized["opportunity_bucket"] == "TOP"
    assert deserialized["selected_for_execution"] is True
    assert deserialized["selection_reason"] == "selected_top_rank"
    assert deserialized["size_multiplier_reason"] == "score=0.760;rank=1"
    assert deserialized["opportunity_size_multiplier"] == 0.84
    assert deserialized["confidence_base"] == 0.72
    assert deserialized["confidence_raw_canonical"] == 0.78
    assert deserialized["confidence_stage_trace"] == {
        "model_raw": 0.78,
        "after_micro": 0.74,
        "after_alpha": 0.73,
        "after_latency": 0.71,
        "before_soft_veto": 0.71,
        "after_soft_veto": 0.72,
        "after_time_decay": None,
        "time_decay_factor": None,
        "age_seconds": None,
        "market_velocity": None,
        "age_factor": None,
        "raw_gate_threshold": 0.55,
        "final_gate_threshold": 0.30,
        "rejected_at": None,
    }
    assert deserialized["confidence_model_raw"] == 0.78
    assert deserialized["confidence_model_component"] == 0.78
    assert deserialized["quote_age_sec"] == 1.5
    assert deserialized["price_age_sec"] == 1.5
    assert deserialized["option_age_sec"] == 1.5
    assert deserialized["confidence_micro_component"] == 0.62
    assert deserialized["confidence_micro_blend_method"] == "bounded_overlay"
    assert deserialized["confidence_after_micro"] == 0.74
    assert deserialized["confidence_after_alpha"] == 0.73
    assert deserialized["confidence_after_latency"] == 0.71
    assert isinstance(deserialized["ts_epoch"], float)
    assert deserialized["timestamp"] == datetime.fromtimestamp(deserialized["ts_epoch"], tz=timezone.utc).isoformat()
    assert deserialized["ts_utc"] == deserialized["timestamp"]
    assert deserialized["ts_ist"].endswith("+05:30")
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
        "confidence_raw_canonical",
        "confidence_stage_trace",
        "confidence_model_raw",
        "builder_confidence",
        "permission_confidence",
        "gating_base_confidence",
        "gating_final_confidence",
        "sizing_confluence_score",
        "opportunity_score",
        "opportunity_rank",
        "rank_global",
        "rank_within_symbol",
        "opportunity_bucket",
        "selected_for_execution",
        "selection_reason",
        "size_multiplier_reason",
        "opportunity_size_multiplier",
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
    assert out["confidence_raw_canonical"] is None
    assert out["confidence_stage_trace"] == {
        "model_raw": None,
        "after_micro": None,
        "after_alpha": None,
        "after_latency": None,
        "before_soft_veto": None,
        "after_soft_veto": None,
        "after_time_decay": None,
        "time_decay_factor": None,
        "age_seconds": None,
        "market_velocity": None,
        "age_factor": None,
        "raw_gate_threshold": None,
        "final_gate_threshold": None,
        "rejected_at": None,
    }
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
    assert out["opportunity_score"] is None
    assert out["opportunity_rank"] is None
    assert out["rank_global"] is None
    assert out["rank_within_symbol"] is None
    assert out["opportunity_bucket"] is None
    assert out["selected_for_execution"] is False
    assert out["selection_reason"] is None
    assert out["size_multiplier_reason"] is None
    assert out["opportunity_size_multiplier"] is None


def test_advisory_schema_missing_required_fields_raise():
    try:
        advisory_schema.validate_advisory_row({"symbol": "NIFTY"})
    except advisory_schema.AdvisorySchemaError as exc:
        assert "missing required field" in str(exc)
    else:
        raise AssertionError("expected AdvisorySchemaError")


def test_advisory_schema_defaults_identity_fields_to_unknown_when_missing():
    row = _valid_row(
        candidate_type=None,
        strategy_family=None,
        setup_variant=None,
        direction=None,
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["candidate_type"] == "options"
    assert out["strategy_family"] == "unknown"
    assert out["setup_variant"] == "unknown"
    assert out["direction"] == "UNKNOWN"
    assert out["candidate_status"] == "advisory_only"


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


def test_advisory_schema_downgrades_executable_claim_when_entry_missing():
    row = _valid_row(
        execution_entry=None,
        execution_entry_source="none",
        execution_entry_status="missing",
        display_entry=None,
        display_entry_source="none",
        display_entry_status="missing",
        entry_display_status="missing",
        entry=None,
        entry_source="none",
        entry_status="missing",
        entry_clear_reason="missing_entry",
        execution_status="executable",
        readiness="READY",
        is_executable=True,
        permission="EXECUTE",
        final_action="EXECUTE",
        status="READY",
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["entry"] is None
    assert out["entry_status"] == "missing"
    assert out["execution_status"] == "blocked"
    assert out["readiness"] == "BLOCKED"
    assert out["final_action"] == "BLOCK"
    assert out["permission"] == "BLOCK"
    assert out["status"] == "INVALID"
    assert out["is_executable"] is False


def test_advisory_schema_restores_valid_entry_from_execution_entry():
    row = _valid_row(
        execution_entry=121.5,
        execution_entry_source="ask",
        execution_entry_status="executable",
        display_entry=None,
        display_entry_source="none",
        display_entry_status="missing",
        entry_display_status="missing",
        entry=None,
        entry_source="none",
        entry_status="missing",
        entry_clear_reason="missing_display_entry",
        execution_status="executable",
        readiness="READY",
        is_executable=True,
        permission="EXECUTE",
        final_action="EXECUTE",
        status="READY",
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["execution_status"] == "executable"
    assert out["entry"] == 121.5
    assert out["display_entry"] == 121.5
    assert out["entry_source"] == "ask"
    assert out["entry_status"] == "displayable"
    assert out["display_entry_status"] == "displayable"
    assert out["entry_clear_reason"] is None
    assert out["is_executable"] is True


def test_advisory_schema_normalizes_option_type_from_tradingsymbol():
    row = _valid_row(
        instrument_type="OPT",
        option_type=None,
        right=None,
        type=None,
        tradingsymbol="NIFTY26MAR1723850PE",
        strike=23850,
        expiry_date="2026-03-17",
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["option_type"] == "PE"
    assert out["right"] == "PE"
    assert out["type"] == "PE"


def test_advisory_schema_downgrades_display_only_executable_claim():
    row = _valid_row(
        execution_entry=None,
        execution_entry_source="none",
        execution_entry_status="missing",
        display_entry=72.5,
        display_entry_source="mark",
        display_entry_status="displayable",
        entry=72.5,
        entry_source="mark",
        entry_status="displayable",
        execution_status="executable",
        readiness="READY",
        is_executable=True,
        permission="EXECUTE",
        final_action="EXECUTE",
        status="READY",
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["entry"] == 72.5
    assert out["execution_entry"] is None
    assert out["execution_entry_status"] == "non_executable"
    assert out["display_entry_status"] == "displayable"
    assert out["entry_status"] == "displayable"
    assert out["execution_status"] == "advisory_only"
    assert out["readiness"] == "ADVISORY_ONLY"
    assert out["final_action"] == "ADVISORY_ONLY"
    assert out["permission"] == "ADVISORY_ONLY"
    assert out["status"] == "ADVISORY_ONLY"
    assert out["is_executable"] is False


def test_advisory_schema_downgrades_executable_claim_from_untrusted_entry_source():
    row = _valid_row(
        execution_entry=72.5,
        execution_entry_source="last",
        execution_entry_status="executable",
        display_entry=72.5,
        display_entry_source="last",
        display_entry_status="displayable",
        entry=72.5,
        entry_source="last",
        entry_status="displayable",
        execution_status="executable",
        readiness="READY",
        is_executable=True,
        permission="EXECUTE",
        final_action="EXECUTE",
        status="READY",
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["execution_entry"] is None
    assert out["execution_entry_status"] == "non_executable"
    assert out["execution_entry_source"] == "none"
    assert out["display_entry"] == 72.5
    assert out["display_entry_status"] == "displayable"
    assert out["entry_status"] == "displayable"
    assert out["execution_status"] == "advisory_only"
    assert out["readiness"] == "ADVISORY_ONLY"
    assert out["final_action"] == "ADVISORY_ONLY"
    assert out["permission"] == "ADVISORY_ONLY"


def test_advisory_schema_derives_ts_epoch_from_timestamp_when_missing():
    row = _valid_row(ts_epoch=None, ts_utc=None, ts_ist=None)

    out = advisory_schema.serialize_advisory_row(row)

    assert isinstance(out["ts_epoch"], float)
    assert out["timestamp"] == "2026-03-08T10:00:00+00:00"
    assert out["ts_utc"] == "2026-03-08T10:00:00+00:00"
    assert out["ts_ist"] == "2026-03-08T15:30:00+05:30"


def test_advisory_schema_injects_ts_epoch_when_timestamp_missing_entirely():
    row = _valid_row(timestamp=None, ts_epoch=None, ts_utc=None, ts_ist=None)

    out = advisory_schema.serialize_advisory_row(row)

    assert isinstance(out["ts_epoch"], float)
    assert out["timestamp"] == datetime.fromtimestamp(out["ts_epoch"], tz=timezone.utc).isoformat()
    assert out["ts_utc"] == out["timestamp"]
    assert out["ts_ist"].endswith("+05:30")


def test_advisory_schema_syncs_confidence_final_to_gating_final_confidence():
    row = _valid_row(
        builder_confidence=0.55,
        gating_final_confidence=0.068,
        confidence_final=0.55,
        confidence=0.55,
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["builder_confidence"] == 0.55
    assert out["gating_final_confidence"] == 0.068
    assert out["confidence_final"] == 0.068
    assert out["confidence"] == 0.068


def test_advisory_schema_normalizes_canonical_quote_age_from_mixed_inputs():
    row = _valid_row(
        quote_age_sec=0.0,
        price_age_sec=102.9,
        option_age_sec=None,
        option_ltp_age_sec=102.9,
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["quote_age_sec"] == 0.0
    assert out["price_age_sec"] == 0.0
    assert out["option_age_sec"] == 0.0


def test_advisory_schema_drops_internal_stale_age_sentinel():
    row = _valid_row(
        quote_age_sec=10**9,
        price_age_sec=None,
        option_age_sec=None,
        option_ltp_age_sec=None,
        quote_source="none",
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["quote_age_sec"] is None
    assert out["price_age_sec"] is None
    assert out["option_age_sec"] is None


def test_advisory_schema_downgrades_executable_alias_without_executable_entry():
    row = _valid_row(
        execution_entry=None,
        execution_entry_status="missing",
        display_entry=100.0,
        display_entry_source="last",
        display_entry_status="displayable",
        entry_display_status="displayable",
        entry_block_code="missing_executable_quote",
        entry=100.0,
        entry_status="executable",
        permission="ADVISORY_ONLY",
        final_action="ADVISORY_ONLY",
    )
    out = advisory_schema.serialize_advisory_row(row)
    assert out["execution_status"] == "advisory_only"
    assert out["readiness"] == "ADVISORY_ONLY"
    assert out["final_action"] == "ADVISORY_ONLY"
    assert out["permission"] == "ADVISORY_ONLY"
    assert out["entry_status"] == "displayable"

def test_advisory_schema_downgrades_displayable_alias_with_execute_action():
    row = _valid_row(
        execution_entry=None,
        execution_entry_status="missing",
        display_entry=100.0,
        display_entry_source="last",
        display_entry_status="displayable",
        entry_display_status="displayable",
        entry_block_code="missing_executable_quote",
        entry=100.0,
        entry_status="displayable",
        permission="EXECUTE",
        final_action="EXECUTE",
    )
    out = advisory_schema.serialize_advisory_row(row)
    assert out["execution_status"] == "advisory_only"
    assert out["readiness"] == "ADVISORY_ONLY"
    assert out["final_action"] == "ADVISORY_ONLY"
    assert out["permission"] == "ADVISORY_ONLY"
    assert out["entry_status"] == "displayable"


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
    row = _valid_row(
        execution_entry=None,
        execution_entry_source="none",
        execution_entry_status="missing",
        display_entry=None,
        display_entry_source="none",
        display_entry_status="displayable",
        entry=None,
        entry_source="none",
        entry_status="displayable",
        entry_clear_reason="missing_executable_quote",
    )

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


def test_advisory_schema_backfills_instrument_type_for_advisory_only():
    row = _valid_row(
        instrument_type=None,
        instrument=None,
        candidate_type="directional",
        execution_entry=None,
        execution_entry_source="none",
        execution_entry_status="non_executable",
        display_entry=None,
        display_entry_source="none",
        display_entry_status="missing",
        entry_display_status="missing",
        entry=None,
        entry_status="missing",
        entry_source="none",
        entry_reason="soft_reject",
        entry_clear_reason="soft_reject",
        entry_block_code="soft_reject",
        readiness="ADVISORY_ONLY",
        execution_status="advisory_only",
        final_action="ADVISORY_ONLY",
        permission="ADVISORY_ONLY",
        quote_source="none",
    )

    out = advisory_schema.serialize_advisory_row(row)

    assert out["instrument_type"] == "OPT"
    assert out.get("instrument_type_source") in {"candidate_type", "option_type", "explicit", "fallback"}


def test_advisory_schema_accepts_scored_execution_status():
    row = _valid_row(
        execution_status="scored",
        permission="ADVISORY_ONLY",
        final_action="ADVISORY_ONLY",
        readiness="ADVISORY_ONLY",
    )
    out = advisory_schema.serialize_advisory_row(row)
    assert out["execution_status"] == "scored"


def test_review_queue_normalizes_legacy_compat_display_entry_source_before_schema_emit():
    from core.review_queue import _normalize_advisory_entry_sources_for_schema

    row = _valid_row(
        execution_entry=None,
        execution_entry_source="none",
        execution_entry_status="non_executable",
        display_entry=120.0,
        display_entry_source="compat",
        display_entry_status="displayable",
        entry=120.0,
        entry_source="compat",
        entry_status="displayable",
        entry_display_status="displayable",
        execution_status="advisory_only",
        readiness="ADVISORY_ONLY",
        is_executable=False,
        selected_for_execution=False,
        quote_source="unknown",
        quote_age_sec=None,
        price_age_sec=None,
        option_age_sec=None,
        hard_blockers=[],
        blockers=[],
        soft_penalties=[],
    )

    normalized = _normalize_advisory_entry_sources_for_schema(row)

    assert normalized["display_entry_source"] == "last"
    assert normalized["entry_source"] == "last"
    assert normalized["display_entry_source_raw"] == "compat"
    assert normalized["entry_source_raw"] == "compat"

    serialized = advisory_schema.serialize_advisory_row(normalized)

    assert serialized["display_entry_source"] == "last"
    assert serialized["entry_source"] == "last"
    assert serialized["execution_entry"] is None
    assert serialized["execution_entry_source"] == "none"
    assert serialized["execution_entry_status"] == "non_executable"
    assert serialized["execution_status"] == "advisory_only"


def test_review_queue_normalizer_does_not_make_legacy_compat_execution_source_executable():
    from core.review_queue import _normalize_advisory_entry_sources_for_schema

    row = _valid_row(
        execution_entry=120.0,
        execution_entry_source="compat",
        execution_entry_status="executable",
        display_entry=120.0,
        display_entry_source="compat",
        entry=120.0,
        entry_source="compat",
        execution_status="advisory_only",
        readiness="ADVISORY_ONLY",
        is_executable=False,
        selected_for_execution=False,
    )

    normalized = _normalize_advisory_entry_sources_for_schema(row)

    assert normalized["display_entry_source"] == "last"
    assert normalized["entry_source"] == "last"
    assert normalized["execution_entry_source"] == "compat"

    try:
        advisory_schema.serialize_advisory_row(normalized)
    except advisory_schema.AdvisorySchemaError as exc:
        assert "invalid execution_entry_source: compat" in str(exc)
    else:
        raise AssertionError("expected AdvisorySchemaError for executable compat source")

def test_review_queue_normalizes_legacy_sources_at_all_schema_boundaries():
    source = open("core/review_queue.py", "r", encoding="utf-8").read()

    assert (
        "advisory_payload = _normalize_blocked_candidate_lifecycle_schema(advisory_payload)\n"
        "    _print_final_emit_truth(advisory_payload)"
    ) in source

    assert (
        "advisory_payload = _backfill_instrument_identity(advisory_payload)\n"
        "    advisory_payload = _normalize_advisory_entry_sources_for_schema(advisory_payload)\n"
        "    try:\n"
        "        advisory_entry = serialize_advisory_row(advisory_payload, allow_legacy=True)"
    ) in source

    assert (
        "advisory_payload = _ensure_blocked_advisory_hard_blockers(advisory_payload)\n"
        "    advisory_payload = _normalize_advisory_entry_sources_for_schema(advisory_payload)\n"
        "    advisory_entry = serialize_advisory_row(advisory_payload, allow_legacy=True)"
    ) in source

    assert (
        "advisory_payload = _normalize_advisory_entry_sources_for_schema(advisory_payload)\n"
        "    emission_target = \"rejected_candidates\" if _is_blocked_contract_row(entry) else \"suggestions\""
    ) in source

