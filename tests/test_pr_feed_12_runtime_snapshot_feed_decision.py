from __future__ import annotations

from core.runtime_snapshot_producer import _build_feed_health_truth_latest_payload, _feed_health_symbols


# Runtime snapshot feed decision coverage: canonical feed truth must be visible in snapshots without feed lifecycle changes.


def test_feed_health_symbols_collects_all_known_symbol_maps():
    payload = {
        "option_feed_block_reason_by_symbol": {"nifty": "OK"},
        "option_last_tick_age_by_symbol": {"BANKNIFTY": 0.5},
        "symbol_feed_ok_by_symbol": {"sensex": True},
        "feed_ok_by_symbol": {"FINNIFTY": True},
    }

    assert _feed_health_symbols(payload) == ("BANKNIFTY", "FINNIFTY", "NIFTY", "SENSEX")


def test_feed_health_truth_snapshot_payload_is_read_only_for_healthy_feed():
    payload = {
        "feed_ok": True,
        "effective_ws_connected": True,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE"},
        "last_tick_age_sec": 0.4,
        "last_depth_age_sec": 1.2,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.8},
        "symbol_feed_ok_by_symbol": {"NIFTY": True},
    }

    snapshot = _build_feed_health_truth_latest_payload(payload)

    assert snapshot["schema_version"] == 1
    assert snapshot["read_only"] is True
    assert snapshot["is_order_action"] is False
    assert snapshot["append"] is False
    assert snapshot["source_snapshot"] == "feed_runtime_latest"
    assert snapshot["source_payload_present"] is True
    assert snapshot["feed_ok"] is True
    assert snapshot["blockers"] == []
    assert snapshot["feed_health_truth"]["feed_ok"] is True
    assert snapshot["feed_health_truth"]["reason_code"] == "ok"
    assert snapshot["feed_health_truth"]["symbols"][0]["symbol"] == "NIFTY"
    assert snapshot["metadata"]["symbols_evaluated"] == ["NIFTY"]


def test_feed_health_truth_snapshot_blocks_unhealthy_feed():
    payload = {
        "feed_ok": False,
        "effective_ws_connected": False,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE"},
        "last_tick_age_sec": 0.4,
        "last_depth_age_sec": 1.2,
        "option_feed_block_reason_by_symbol": {"NIFTY": "STALE_OPTION_LTP"},
        "option_last_tick_age_by_symbol": {"NIFTY": 9.0},
        "symbol_feed_ok_by_symbol": {"NIFTY": False},
    }

    snapshot = _build_feed_health_truth_latest_payload(payload)

    assert snapshot["read_only"] is True
    assert snapshot["is_order_action"] is False
    assert snapshot["feed_ok"] is False
    assert "global_feed_unhealthy" in snapshot["blockers"]
    assert "websocket_disconnected" in snapshot["blockers"]
    assert "NIFTY:option_feed_blocked" in snapshot["blockers"]
    assert "NIFTY:option_ticks_stale" in snapshot["blockers"]
    assert snapshot["feed_health_truth"]["reason_code"] == "feed_health_truth_failed"


def test_feed_health_truth_snapshot_fails_closed_for_invalid_payload():
    snapshot = _build_feed_health_truth_latest_payload(None)

    assert snapshot["read_only"] is True
    assert snapshot["is_order_action"] is False
    assert snapshot["source_payload_present"] is False
    assert snapshot["feed_ok"] is False
    assert snapshot["blockers"] == ["invalid_payload"]
    assert snapshot["feed_health_truth"]["reason_code"] == "feed_health_truth_failed"


def test_feed_health_truth_snapshot_detects_runtime_state_unsafe():
    payload = {
        "feed_ok": True,
        "effective_ws_connected": True,
        "runtime_state": "HALTED",
        "state_machine": {"state": "LIVE"},
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.4},
        "symbol_feed_ok_by_symbol": {"NIFTY": True},
    }

    snapshot = _build_feed_health_truth_latest_payload(payload)

    assert snapshot["feed_ok"] is False
    assert "runtime_state_unsafe" in snapshot["blockers"]
