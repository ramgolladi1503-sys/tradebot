from core.feed.runtime_snapshot_builder import (
    FeedRuntimeSnapshotInputs,
    build_feed_runtime_latest_payload,
    build_feed_runtime_store_payload,
    coerce_epoch,
    derive_runtime_state_machine,
    normalized_runtime_state,
    safe_float,
    trimmed_error,
)
from core.runtime_truth_integrity import truth_hash_from_mapping


def _sample_inputs(**overrides):
    values = dict(
        ts_epoch=1000.0,
        ws_connected=True,
        subscribed_tokens_count=3,
        intended_tokens_count=4,
        subscribed_tokens_sample=(101, 102, 103, 104),
        subscribed_tokens_count_by_symbol={"NIFTY": 2},
        missing_option_tokens_count=1,
        missing_option_tokens_count_by_symbol={"NIFTY": 1},
        subscribed_option_tokens_count=2,
        option_last_tick_age_by_symbol={"NIFTY": 1.5},
        option_last_tick_sample=({"token": 101, "tick_age_sec": 1.5},),
        option_tokens_resolved_count_by_symbol={"NIFTY": 4},
        option_tokens_subscribed_count_by_symbol={"NIFTY": 2},
        option_ticks_received_count_by_symbol={"NIFTY": 2},
        last_option_tick_ts_by_symbol={"NIFTY": 999.0},
        option_feed_block_reason_by_symbol={"NIFTY": "OK"},
        option_active_blockers_by_symbol={"NIFTY": []},
        last_db_tick_epoch=998000.0,
        last_db_tick_age_sec="2.0",
        last_ws_tick_epoch=999000.0,
        last_tick_age_sec=1.0,
        last_depth_epoch=997000.0,
        last_depth_age_sec=3.0,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        source="unit_test",
        restart_count_1h=2,
        stale_strikes=1,
        runtime_state="running",
        last_error="",
    )
    values.update(overrides)
    return FeedRuntimeSnapshotInputs(**values)


def test_scalar_helpers_fail_closed_and_normalize_values():
    assert coerce_epoch(None) is None
    assert coerce_epoch(1700000000000) == 1700000000.0
    assert safe_float("2.5") == 2.5
    assert safe_float("bad") is None
    assert normalized_runtime_state(" running ") == "RUNNING"
    assert normalized_runtime_state("") == "UNKNOWN"
    assert trimmed_error("x" * 1005) == "x" * 1000


def test_runtime_state_machine_classifies_feed_state():
    assert derive_runtime_state_machine(market_open=False, ws_connected=True, last_tick_age_sec=1.0) == {
        "state": "MARKET_CLOSED",
        "reason": "market_closed",
    }
    assert derive_runtime_state_machine(market_open=True, ws_connected=False, last_tick_age_sec=1.0) == {
        "state": "DOWN",
        "reason": "ws_disconnected",
    }
    assert derive_runtime_state_machine(market_open=True, ws_connected=True, last_tick_age_sec=None) == {
        "state": "STARTING",
        "reason": "awaiting_first_tick",
    }
    assert derive_runtime_state_machine(market_open=True, ws_connected=True, last_tick_age_sec=10.0) == {
        "state": "LIVE",
        "reason": "ticks_flowing",
    }
    assert derive_runtime_state_machine(market_open=True, ws_connected=True, last_tick_age_sec=11.0) == {
        "state": "DOWN",
        "reason": "no_ws_messages",
    }


def test_runtime_store_payload_shape_matches_existing_runtime_row_contract():
    payload = build_feed_runtime_store_payload(_sample_inputs())

    assert payload["ts_epoch"] == 1000.0
    assert payload["ws_connected"] is True
    assert payload["subscribed_tokens_count"] == 3
    assert payload["intended_tokens_count"] == 4
    assert payload["subscribed_tokens_sample"] == [101, 102, 103, 104]
    assert payload["subscribed_tokens_count_by_symbol"] == {"NIFTY": 2}
    assert payload["missing_option_tokens_count"] == 1
    assert payload["subscribed_option_tokens_count"] == 2
    assert payload["last_ws_tick_epoch"] == 999000.0
    assert payload["last_tick_age_sec"] == 1.0
    assert payload["last_depth_epoch"] == 997000.0
    assert payload["market_open"] is True
    assert payload["state_machine"] == {"state": "LIVE", "reason": "ticks_flowing"}
    assert payload["source"] == "unit_test"
    assert payload["runtime_state"] == "RUNNING"
    assert payload["last_error"] == ""


def test_runtime_latest_payload_shape_supports_derivation_and_stamping_hooks():
    def derive_effective(payload):
        return bool(payload["ws_connected"] and payload["market_open"])

    def derive_ok(payload):
        return bool(payload.get("effective_ws_connected") and payload.get("last_tick_age_sec") <= 2.0)

    def stamp(payload):
        payload["runtime_writer"] = "unit_test"
        return payload

    payload = build_feed_runtime_latest_payload(
        _sample_inputs(last_error="x" * 1005),
        derive_effective_ws_connected=derive_effective,
        derive_feed_ok=derive_ok,
        stamp_payload=stamp,
    )

    assert payload["ts_epoch"] == 1000.0
    assert payload["last_db_tick_epoch"] == 998000.0
    assert payload["last_db_tick_age_sec"] == 2.0
    assert payload["last_ws_tick_epoch"] == 999000.0
    assert payload["last_depth_age_sec"] == 3.0
    assert payload["restart_count_1h"] == 2
    assert payload["stale_strikes"] == 1
    assert payload["effective_ws_connected"] is True
    assert payload["feed_ok"] is True
    assert payload["transport_state"] == "CONNECTED"
    assert payload["transport_reason"] == "ws_connected"
    assert payload["transport_healthy"] is True
    assert payload["transport"]["state"] == "CONNECTED"
    assert payload["snapshot_hash_version"] == 1
    assert payload["snapshot_hash"] == truth_hash_from_mapping(
        payload,
        exclude_keys=(
            "snapshot_hash",
            "snapshot_hash_version",
            "transport_heartbeat",
            "transport_heartbeat_epoch",
            "transport_heartbeat_age_sec",
            "transport_heartbeat_source",
            "transport_heartbeat_state",
            "transport_heartbeat_reason",
            "truth_integrity_alerts",
            "truth_integrity_alert_count",
            "truth_integrity_status",
        ),
    )
    assert payload["transport_heartbeat_state"] == "CONNECTED"
    assert payload["transport_heartbeat_epoch"] == 1000.0
    assert payload["runtime_writer"] == "unit_test"
    assert payload["last_error"] == "x" * 1000


def test_runtime_latest_payload_preserves_explicit_current_proof_fields():
    payload = build_feed_runtime_latest_payload(
        _sample_inputs(
            option_ticks_verified=True,
            verified_option_symbols=("NIFTY", "BANKNIFTY"),
            warmup_clean_cycles=3,
            warmup_required_clean_cycles=3,
        )
    )

    assert payload["option_ticks_verified"] is True
    assert payload["verified_option_symbols"] == ["NIFTY", "BANKNIFTY"]
    assert payload["warmup_clean_cycles"] == 3
    assert payload["warmup_required_clean_cycles"] == 3


def test_runtime_latest_payload_does_not_invent_missing_proof():
    payload = build_feed_runtime_latest_payload(_sample_inputs())

    assert "option_ticks_verified" not in payload
    assert "warmup_clean_cycles" not in payload
    assert "warmup_required_clean_cycles" not in payload


def test_runtime_latest_payload_marks_reconnecting_transport_when_reconnect_is_pending():
    payload = build_feed_runtime_latest_payload(
        _sample_inputs(ws_connected=False, runtime_state="RECOVERING", reconnect_pending=True, reconnect_blocked_reason=None),
    )

    assert payload["transport_state"] == "RECONNECTING"
    assert payload["transport_reason"] in {"recovering", "reconnect_pending"}
    assert payload["transport_healthy"] is False


def test_missing_optional_values_are_deterministic_defaults():
    payload = build_feed_runtime_latest_payload(
        FeedRuntimeSnapshotInputs(
            ts_epoch=1.0,
            ws_connected=None,
            subscribed_tokens_count=0,
            intended_tokens_count=0,
            market_open=False,
        )
    )

    assert payload["missing_option_tokens_count"] == 0
    assert payload["subscribed_option_tokens_count"] == 0
    assert payload["subscribed_tokens_count_by_symbol"] == {}
    assert payload["option_last_tick_sample"] == []
    assert payload["last_db_tick_epoch"] is None
    assert payload["last_error"] == ""
    assert payload["runtime_state"] == "UNKNOWN"
