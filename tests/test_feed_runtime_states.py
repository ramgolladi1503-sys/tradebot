from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core.feed.runtime_store import read_latest_runtime_snapshot, write_runtime_snapshot
import core.feed.runtime_store as runtime_store
import core.kite_depth_ws as depth_ws
from core.blocker_lifecycle import reset_blocker_registries
from core.runtime_status_overlay import derive_effective_ws_connected, derive_feed_ok
import pytest
from core.runtime_truth_integrity import truth_hash_from_mapping


def _reset_depth_ws_test_state(monkeypatch):
    reset_blocker_registries()
    for name, value in {
        "_KITE_TICKER": None,
        "_WATCHDOG_THREAD": None,
        "_WATCHDOG_STOP": None,
        "_LAST_TOKENS": [],
        "_LAST_DESIRED_TOKENS": None,
        "_STALE_STRIKES": 0,
        "_WARMUP_PENDING": False,
        "_STOP_REQUESTED": False,
        "_RESTART_ASYNC_THREAD": None,
        "_LAST_WS_TICK_EPOCH": 0.0,
        "_LAST_FEED_HEALTH_STATE": None,
        "_RECONNECT_BLOCKED_REASON": "",
        "_RECONNECT_BLOCKED_SINCE_EPOCH": 0.0,
        "_PARTIAL_RECOVERY_VERIFICATION": {},
        "_REACTOR_NOT_RESTARTABLE_DETECTED": False,
        "_AUTH_REQUIRED_LATCH": False,
        "_AUTH_REQUIRED_LOGGED": False,
        "_LAST_DISCONNECTED_CODE": None,
        "_LAST_DISCONNECTED_REASON": "",
        "_SYMBOL_LAST_LTP_TS": {},
        "_SYMBOL_LAST_DEPTH_TS": {},
        "_SYMBOL_LAST_OPTION_TICK_TS": {},
        "_LAST_MSG_TS_BY_TOKEN": {},
        "_LAST_OPTION_TOKEN_INCIDENT_TS": {},
        "_LAST_OPTION_COUNTS_BY_SYMBOL": {},
        "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL": {},
        "_TOKEN_TO_SYMBOL": {},
        "_UNDERLYING_TOKENS": set(),
        "_UNDERLYING_TOKEN_TO_SYMBOL": {},
        "_DEPTH_WS_LOCK_ACQUIRED": False,
        "_DEPTH_WS_START_EPOCH": 0.0,
        "_LAST_FEED_TICK_LOG_MINUTE": None,
        "_INTENDED_TOKEN_COUNT": 0,
        "_RUNTIME_STATE": "STOPPED",
        "_LAST_RUNTIME_ERROR": "",
        "_LAST_FULL_RESTART_EPOCH": 0.0,
        "_FULL_RESTARTS": [],
        "_FEED_HEALTH_DURATION_STATE": None,
    }.items():
        monkeypatch.setattr(depth_ws, name, value, raising=False)
    depth_ws._reset_feed_restart_verification(reason="unit_test_reset")


@pytest.fixture(autouse=True)
def _reset_feed_runtime_state(monkeypatch):
    _reset_depth_ws_test_state(monkeypatch)


def _read_feed_runtime_payload(logs_path: Path) -> dict:
    return json.loads((logs_path / "feed_runtime_latest.json").read_text())


def test_runtime_store_roundtrip_with_state_fields(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    ok = write_runtime_snapshot(
        {
            "ts_epoch": 123.0,
            "ws_connected": False,
            "subscribed_tokens_count": 0,
            "intended_tokens_count": 12,
            "subscribed_tokens_sample": [1, 2, 3],
            "last_ws_tick_epoch": None,
            "last_depth_epoch": None,
            "source": "test",
            "runtime_state": "SUBSCRIBE_FAILED",
            "last_error": "unit-test",
        }
    )
    assert ok is True
    payload = read_latest_runtime_snapshot()
    assert payload is not None
    assert payload["runtime_state"] == "SUBSCRIBE_FAILED"
    assert payload["intended_tokens_count"] == 12
    assert payload["last_error"] == "unit-test"
    assert payload["subscribed_tokens_sample"] == [1, 2, 3]


def test_runtime_store_connection_uses_busy_tolerant_settings(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    captured = {}
    real_connect = runtime_store.sqlite3.connect

    def fake_connect(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(runtime_store.sqlite3, "connect", fake_connect, raising=False)

    ok = write_runtime_snapshot(
        {
            "ts_epoch": 123.0,
            "ws_connected": True,
            "subscribed_tokens_count": 0,
            "intended_tokens_count": 0,
            "subscribed_tokens_sample": [],
            "source": "unit-test",
            "runtime_state": "RUNNING",
        }
    )

    assert ok is True
    assert captured["kwargs"]["timeout"] == 30.0
    assert captured["kwargs"].get("check_same_thread", True) is True


def test_start_depth_ws_writes_import_missing_state(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "test_key", raising=False)
    monkeypatch.setattr(depth_ws, "KiteTicker", None, raising=True)

    depth_ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True)

    payload = read_latest_runtime_snapshot()
    assert payload is not None
    assert payload["runtime_state"] == "IMPORT_MISSING"
    assert payload["intended_tokens_count"] == 2
    assert payload["ws_connected"] is False


def test_persist_runtime_snapshot_row_updates_json_artifact(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 199.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_depth_epoch_from_store", lambda: 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_db_tick_epoch", lambda: 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_SUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_UNSUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_MODE_FULL_TOKENS", set(), raising=False)

    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test",
        now_epoch=200.0,
        runtime_state="RUNNING",
        last_error="",
        intended_tokens_count=2,
    )

    path = logs_path / "feed_runtime_latest.json"
    payload = json.loads(path.read_text())
    assert payload["ws_connected"] is True
    assert payload["subscribed_tokens_count"] == 2
    assert payload["subscribed_option_tokens_count"] == 1
    assert payload["option_tokens_resolved_count_by_symbol"] == {"NIFTY": 1}
    assert payload["option_tokens_subscribed_count_by_symbol"] == {"NIFTY": 1}
    assert payload["option_feed_block_reason_by_symbol"] == {"NIFTY": "OK"}
    assert payload["feed_truth_state"] in {"LIVE", "DEGRADED", "STARTING", "DEAD", "MARKET_CLOSED"}


def test_persist_runtime_snapshot_row_writes_timing_and_health_duration(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "FEED_HEALTH_DURATION_ARTIFACT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_HEALTH_DURATION_TARGET_SEC", 60.0, raising=False)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "_FEED_HEALTH_DURATION_STATE", None, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 100.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 100.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_depth_epoch_from_store", lambda: 100.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_db_tick_epoch", lambda: 100.0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)
    monkeypatch.setattr(depth_ws, "is_market_open_ist", lambda: True)

    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test",
        now_epoch=100.0,
        runtime_state="RUNNING",
        last_error="",
        intended_tokens_count=2,
    )
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 165.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 165.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_depth_epoch_from_store", lambda: 165.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_db_tick_epoch", lambda: 165.0, raising=False)
    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test",
        now_epoch=165.0,
        runtime_state="RUNNING",
        last_error="",
        intended_tokens_count=2,
    )


def test_write_runtime_snapshot_emits_transport_health_fields(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    logs_path = tmp_path / "logs"
    repo_root = tmp_path / "repo"
    logs_path.mkdir(parents=True, exist_ok=True)
    repo_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(runtime_store, "repo_root", lambda: repo_root)
    monkeypatch.setattr("core.paths.logs_dir", lambda: logs_path)

    ok = runtime_store.write_runtime_snapshot(
        {
            "ts_epoch": 123.0,
            "ws_connected": False,
            "subscribed_tokens_count": 0,
            "intended_tokens_count": 1,
            "subscribed_tokens_sample": [],
            "runtime_state": "RECOVERING",
            "reconnect_pending": True,
            "last_error": "",
            "source": "unit-test",
        }
    )

    assert ok is True
    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text(encoding="utf-8"))
    assert payload["transport_state"] == "RECONNECTING"
    assert payload["transport_healthy"] is False
    assert payload["transport"]["state"] == "RECONNECTING"
    assert payload["snapshot_hash_version"] == 1
    assert payload["snapshot_hash"] == payload["transport_heartbeat"]["snapshot_hash"]
    assert payload["transport_heartbeat_state"] == "RECONNECTING"
    assert payload["transport_heartbeat_epoch"] == 123.0


def test_persist_runtime_snapshot_row_normalizes_ws1006_recovery_blocked_state(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 199.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_SUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_UNSUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_MODE_FULL_TOKENS", set(), raising=False)
    monkeypatch.setattr(depth_ws, "_RECONNECT_BLOCKED_REASON", "ws1006_process_restart_required", raising=False)
    monkeypatch.setattr(depth_ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(depth_ws, "is_market_open_ist", lambda: True)

    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="on_ticks",
        now_epoch=200.0,
        runtime_state="RUNNING",
        last_error="",
    )

    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text())
    assert payload["runtime_state"] == "RECOVERY_BLOCKED"
    assert payload["ws_connected"] is False
    assert payload["state_machine"]["state"] == "DOWN"
    assert payload["state_machine"]["reason"] == "ws1006_process_restart_required"
    assert payload["reconnect_blocked_reason"] == "ws1006_process_restart_required"
    assert payload["restart_blocked_reason"] == "ws1006_process_restart_required"
    assert payload["recovery_action"] == "process_restart_required"
    assert payload["process_restart_required"] is True
    assert payload["recovery_blocked"] is True
    assert payload["restart_attempt_allowed"] is False
    assert payload["restart_attempted"] is False
    assert payload["ws_reconnect_allowed"] is False
    assert payload["ws_reconnect_attempted"] is False
    assert payload["restart_suppressed"] is True
    assert payload["no_order_action"] is True
    assert payload["order_safe"] is True


def test_feed_truth_state_ticker_object_exists_but_no_ticks_is_not_live(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=200.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=None,
        last_db_tick_age_sec=None,
        last_ws_tick_epoch=None,
        last_tick_age_sec=None,
        last_depth_epoch=None,
        last_depth_age_sec=None,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "kws_connect_returned_true"},
        subscribed_option_tokens_count=1,
        option_feed_block_reason_by_symbol={"NIFTY": "OK"},
        option_ticks_received_count_by_symbol={"NIFTY": 0},
        runtime_state="RUNNING",
        last_error="",
    )

    payload = _read_feed_runtime_payload(logs_path)
    assert payload["ws_connected"] is True
    assert payload["feed_truth_state"] != "LIVE"
    assert payload["feed_truth_strict_live"] is False


def test_feed_truth_state_market_open_stale_ticks_is_dead(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=200.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=180.0,
        last_db_tick_age_sec=20.0,
        last_ws_tick_epoch=180.0,
        last_tick_age_sec=20.0,
        last_depth_epoch=190.0,
        last_depth_age_sec=10.0,
        market_open=True,
        state_machine={"state": "DOWN", "reason": "no_ws_messages"},
        subscribed_option_tokens_count=1,
        option_feed_block_reason_by_symbol={"NIFTY": "NO_LIVE_OPTION_FEED"},
        option_active_blockers_by_symbol={"NIFTY": ["NO_LIVE_OPTION_FEED"]},
        runtime_state="RUNNING",
        last_error="",
    )

    payload = _read_feed_runtime_payload(logs_path)
    assert payload["feed_truth_state"] == "DEAD"
    assert payload["feed_truth_strict_live"] is False


def test_feed_truth_state_connected_fresh_option_ticks_is_live(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=200.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=199.0,
        last_db_tick_age_sec=1.0,
        last_ws_tick_epoch=199.0,
        last_tick_age_sec=1.0,
        last_depth_epoch=199.0,
        last_depth_age_sec=1.0,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        subscribed_option_tokens_count=1,
        option_last_tick_age_by_symbol={"NIFTY": 1.0},
        option_ticks_received_count_by_symbol={"NIFTY": 1},
        option_feed_block_reason_by_symbol={"NIFTY": "OK"},
        option_active_blockers_by_symbol={"NIFTY": []},
        runtime_state="RUNNING",
        last_error="",
    )

    payload = _read_feed_runtime_payload(logs_path)
    assert payload["feed_truth_state"] == "LIVE"
    assert payload["feed_truth_strict_live"] is True


def test_feed_truth_state_degraded_coverage_with_fresh_ticks_is_degraded(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=200.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=4,
        missing_option_tokens_count=2,
        last_db_tick_epoch=199.0,
        last_db_tick_age_sec=1.0,
        last_ws_tick_epoch=199.0,
        last_tick_age_sec=1.0,
        last_depth_epoch=199.0,
        last_depth_age_sec=1.0,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        subscribed_option_tokens_count=1,
        option_last_tick_age_by_symbol={"NIFTY": 1.0},
        option_ticks_received_count_by_symbol={"NIFTY": 1},
        option_feed_block_reason_by_symbol={"NIFTY": "OK"},
        option_active_blockers_by_symbol={"NIFTY": []},
        runtime_state="RUNNING",
        last_error="",
    )

    payload = _read_feed_runtime_payload(logs_path)
    assert payload["feed_truth_state"] == "DEGRADED"
    assert payload["feed_truth_strict_live"] is False


def test_write_feed_runtime_snapshot_uses_atomic_writer(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    captured_paths: list[Path] = []
    captured_payloads: dict[Path, dict] = {}

    def fake_write_json_atomic(path, payload):
        captured_paths.append(path)
        captured_payloads[path] = payload
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"payload": payload}), encoding="utf-8")
        return path

    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "write_json_atomic", fake_write_json_atomic)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 199.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_SUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_UNSUBSCRIBE_TOKENS", set(), raising=False)
    monkeypatch.setattr(depth_ws, "_PENDING_MODE_FULL_TOKENS", set(), raising=False)

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=200.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=199.0,
        last_db_tick_age_sec=1.0,
        last_ws_tick_epoch=199.0,
        last_tick_age_sec=1.0,
        last_depth_epoch=199.0,
        last_depth_age_sec=1.0,
        market_open=True,
        runtime_state="RUNNING",
        last_error="",
    )

    assert logs_path / "feed_runtime_latest.json" in captured_paths
    assert logs_path / "feed_health_duration_latest.json" in captured_paths
    assert captured_payloads[logs_path / "feed_runtime_latest.json"]["ws_connected"] is True
    payload = captured_payloads[logs_path / "feed_runtime_latest.json"]
    assert payload["snapshot_hash"] == truth_hash_from_mapping(
        payload,
        exclude_keys=(
            "snapshot_hash", "snapshot_hash_version", "transport_heartbeat",
            "transport_heartbeat_epoch", "transport_heartbeat_age_sec",
            "transport_heartbeat_source", "transport_heartbeat_state",
            "transport_heartbeat_reason", "truth_integrity_alerts",
            "truth_integrity_alert_count", "truth_integrity_status",
        ),
    )
    assert payload["feed_ok"] is False
    assert payload["execution_feed_ready"] is True
    assert (logs_path / "feed_runtime_latest.json").exists()


def test_persist_runtime_snapshot_uses_latest_option_tick_for_symbol_freshness(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 8.0, raising=False)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101, 102], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY", 102: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 2}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 100.0, 102: 199.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_depth_epoch_from_store", lambda: 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_db_tick_epoch", lambda: 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 3, raising=False)

    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test_latest_option_tick",
        now_epoch=200.0,
        runtime_state="RUNNING",
        last_error="",
        intended_tokens_count=3,
    )

    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text())
    assert payload["option_last_tick_age_by_symbol"]["NIFTY"] == 1.0
    assert payload["last_option_tick_ts_by_symbol"]["NIFTY"] == 199.0
    assert payload["option_feed_block_reason_by_symbol"]["NIFTY"] == "OK"


def test_persist_runtime_snapshot_keeps_symbol_ok_with_fresh_option_tick_cache(monkeypatch, tmp_path):
    db_path = tmp_path / "runtime.sqlite"
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 8.0, raising=False)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101, 102], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY", 102: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 2}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 100.0, 102: 110.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_SYMBOL_LAST_OPTION_TICK_TS", {"NIFTY": 199.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_depth_epoch_from_store", lambda: 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_db_tick_epoch", lambda: 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 3, raising=False)

    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test_fresh_option_cache",
        now_epoch=200.0,
        runtime_state="RUNNING",
        last_error="",
        intended_tokens_count=3,
    )

    payload = json.loads((logs_path / "feed_runtime_latest.json").read_text())
    assert payload["ws_connected"] is True
    assert payload["last_option_tick_ts_by_symbol"]["NIFTY"] == 199.0
    assert payload["option_last_tick_age_by_symbol"]["NIFTY"] == 1.0
    assert payload["option_feed_block_reason_by_symbol"]["NIFTY"] == "OK"


def test_runtime_status_overlay_derives_silent_feed_as_not_connected():
    payload = {
        "ws_connected": True,
        "state_machine": {"state": "DOWN", "reason": "no_ws_messages"},
        "runtime_state": "RUNNING",
        "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
        "last_tick_age_sec": 18.0,
        "last_depth_age_sec": 10.0,
    }
    assert derive_effective_ws_connected(payload) is False
    assert derive_feed_ok(payload) is False


def test_write_feed_runtime_snapshot_publishes_fail_closed_status_overlay(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", True, raising=False)

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=200.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=180.0,
        last_db_tick_age_sec=20.0,
        last_ws_tick_epoch=180.0,
        last_tick_age_sec=20.0,
        last_depth_epoch=190.0,
        last_depth_age_sec=10.0,
        market_open=True,
        state_machine={"state": "DOWN", "reason": "no_ws_messages"},
        subscribed_option_tokens_count=1,
        option_feed_block_reason_by_symbol={"NIFTY": "NO_LIVE_OPTION_FEED"},
        option_active_blockers_by_symbol={"NIFTY": ["NO_LIVE_OPTION_FEED", "STALE_OPTION_LTP"]},
        runtime_state="RUNNING",
        last_error="",
    )

    feed = json.loads((logs_path / "feed_runtime_latest.json").read_text())
    suggestions = json.loads((logs_path / "suggestions_status.json").read_text())
    engine = json.loads((logs_path / "engine_cycle_status.json").read_text())
    health = json.loads((logs_path / "runtime_health_latest.json").read_text())

    assert feed["feed_ok"] is False
    assert feed["effective_ws_connected"] is False
    assert suggestions["status"] == "blocked"
    assert suggestions["reason"] == "feed_unhealthy"
    assert suggestions["visible_executable_count"] == 0
    assert suggestions["ws_connected"] is False
    assert engine["cycle_stage"] == "blocked"
    assert engine["reason"] == "feed_unhealthy"
    assert engine["visible_executable_count"] == 0
    assert health["feed"]["sla_status"] == "FAIL"
    assert health["feed"]["ws_connected"] is False


def test_recovery_blocked_snapshot_sets_executable_false_everywhere(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    logs_path = repo_root / ".runtime" / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    (repo_root / "logs").mkdir(parents=True, exist_ok=True)
    
    monkeypatch.setenv("LOG_DIR", str(repo_root / "logs"))
    import core.paths as paths
    monkeypatch.setattr(paths, "repo_root", lambda: repo_root)

    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(runtime_store, "repo_root", lambda: repo_root)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 199.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)
    monkeypatch.setattr(depth_ws, "_RECONNECT_BLOCKED_REASON", "ws1006_process_restart_required", raising=False)
    monkeypatch.setattr(depth_ws, "is_market_open_ist", lambda: True)

    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test_recovery_blocked_snapshot",
        now_epoch=200.0,
        runtime_state="RUNNING",
        last_error="",
    )

    mirror_paths = [
        repo_root / "logs" / "feed_runtime_latest.json",
        repo_root / ".runtime" / "feed_runtime_latest.json",
        repo_root / ".runtime" / "logs" / "feed_runtime_latest.json",
    ]
    payloads = [json.loads(path.read_text()) for path in mirror_paths]

    for payload in payloads:
        assert payload["runtime_state"] == "RECOVERY_BLOCKED"
        assert payload["feed_truth_state"] in {"DEAD", "RECOVERY_BLOCKED"}
        assert payload["feed_truth_allows_executable_candidates"] is False
        assert payload["process_restart_required"] is True
        assert payload["ws_reconnect_allowed"] is False
        assert payload["reconnect_blocked_reason"] == "ws1006_process_restart_required"
        assert payload["option_feed_block_reason_by_symbol"]["NIFTY"] == "NO_LIVE_OPTION_FEED"
        assert payload["option_active_blockers_by_symbol"]["NIFTY"] == ["NO_LIVE_OPTION_FEED"]

    assert payloads[0]["option_feed_block_reason_by_symbol"] == payloads[1]["option_feed_block_reason_by_symbol"] == payloads[2]["option_feed_block_reason_by_symbol"]
    assert payloads[0]["feed_truth_allows_executable_candidates"] == payloads[1]["feed_truth_allows_executable_candidates"] == payloads[2]["feed_truth_allows_executable_candidates"]


def test_healthy_runtime_snapshot_still_reports_executable_true_everywhere(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    logs_path = repo_root / ".runtime" / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    (repo_root / "logs").mkdir(parents=True, exist_ok=True)
    
    monkeypatch.setenv("LOG_DIR", str(repo_root / "logs"))
    import core.paths as paths
    monkeypatch.setattr(paths, "repo_root", lambda: repo_root)

    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(runtime_store, "repo_root", lambda: repo_root)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "is_market_open_ist", lambda: True)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 199.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_depth_epoch_from_store", lambda: 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_latest_db_tick_epoch", lambda: 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)

    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test_healthy_runtime_snapshot",
        now_epoch=200.0,
        runtime_state="RUNNING",
        last_error="",
        intended_tokens_count=2,
    )

    mirror_paths = [
        repo_root / "logs" / "feed_runtime_latest.json",
        repo_root / ".runtime" / "feed_runtime_latest.json",
        repo_root / ".runtime" / "logs" / "feed_runtime_latest.json",
    ]
    payloads = [json.loads(path.read_text()) for path in mirror_paths]

    for payload in payloads:
        assert payload["runtime_state"] == "RUNNING"
        assert payload["feed_truth_state"] == "LIVE"
        assert payload["feed_truth_allows_executable_candidates"] is True
        assert payload["option_feed_block_reason_by_symbol"] == {"NIFTY": "OK"}
        assert payload["option_active_blockers_by_symbol"] == {"NIFTY": []}


def test_runtime_snapshot_mirrors_share_canonical_blocked_truth(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    logs_path = repo_root / ".runtime" / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    (repo_root / "logs").mkdir(parents=True, exist_ok=True)
    
    monkeypatch.setenv("LOG_DIR", str(repo_root / "logs"))
    import core.paths as paths
    monkeypatch.setattr(paths, "repo_root", lambda: repo_root)

    db_path = tmp_path / "runtime.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(runtime_store, "repo_root", lambda: repo_root)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [1, 101], raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKENS", {1}, raising=False)
    monkeypatch.setattr(depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {1: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_TOKEN_TO_SYMBOL", {1: "NIFTY", 101: "NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_COUNTS_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL", {"NIFTY": 1}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {101: 199.0}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 199.0, raising=False)
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)
    monkeypatch.setattr(depth_ws, "_RECONNECT_BLOCKED_REASON", "ws1006_process_restart_required", raising=False)

    depth_ws._persist_runtime_snapshot_row(
        ws_connected=True,
        source="unit_test_canonical_mirrors",
        now_epoch=200.0,
        runtime_state="RUNNING",
        last_error="",
    )

    mirror_paths = [
        repo_root / "logs" / "feed_runtime_latest.json",
        repo_root / ".runtime" / "feed_runtime_latest.json",
        repo_root / ".runtime" / "logs" / "feed_runtime_latest.json",
    ]
    payloads = [json.loads(path.read_text()) for path in mirror_paths]

    shared_keys = (
        "runtime_state",
        "feed_truth_state",
        "feed_truth_allows_executable_candidates",
        "option_feed_block_reason_by_symbol",
        "process_restart_required",
        "ws_reconnect_allowed",
    )
    for key in shared_keys:
        baseline = payloads[0][key]
        for payload in payloads[1:]:
            assert payload[key] == baseline


def test_write_feed_runtime_snapshot_includes_reconnect_blocked_reason(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=200.0,
        ws_connected=False,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=180.0,
        last_db_tick_age_sec=20.0,
        last_ws_tick_epoch=None,
        last_tick_age_sec=None,
        last_depth_epoch=None,
        last_depth_age_sec=None,
        market_open=True,
        state_machine={"state": "DOWN", "reason": "ws_disconnected"},
        subscribed_option_tokens_count=1,
        option_feed_block_reason_by_symbol={"NIFTY": "NO_LIVE_OPTION_FEED"},
        option_active_blockers_by_symbol={"NIFTY": ["NO_LIVE_OPTION_FEED"]},
        runtime_state="RECOVERY_BLOCKED",
        last_error="reactor_not_restartable",
        reconnect_blocked_reason="reactor_not_restartable_process_restart_required",
    )

    feed = json.loads((logs_path / "feed_runtime_latest.json").read_text())
    health = json.loads((logs_path / "runtime_health_latest.json").read_text())

    assert feed["reconnect_blocked_reason"] == "reactor_not_restartable_process_restart_required"
    assert feed["feed_ok"] is False
    assert health["feed"]["runtime_state"] == "RECOVERY_BLOCKED"


def test_partial_recovery_snapshot_preserves_transport_truth():
    payload = runtime_store._canonical_runtime_artifact_payload(
        {
            "runtime_state": "VERIFYING_RECOVERY",
            "ws_connected": True,
            "market_open": True,
            "last_tick_age_sec": 1.0,
            "last_depth_age_sec": 1.0,
            "subscribed_option_tokens_count": 73,
            "reconnect_blocked_reason": "partial_recovery",
            "process_restart_required": True,
            "state_machine": {"state": "LIVE", "reason": "ticks_flowing"},
            "transport_socket_connected": True,
            "transport_callback_activity_present": True,
            "execution_feed_ready": False,
        },
        ts_epoch=200.0,
    )

    assert payload["runtime_state"] == "VERIFYING_RECOVERY"
    assert payload["ws_connected"] is True
    assert payload["reconnect_blocked_reason"] is None
    assert payload["process_restart_required"] is False
    assert payload["restart_suppressed"] is False
    assert payload["feed_truth_state"] == "VERIFYING_RECOVERY"


def test_write_feed_runtime_snapshot_heals_stale_feed_overlay_after_recovery(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(depth_ws, "logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", True, raising=False)

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=200.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=180.0,
        last_db_tick_age_sec=20.0,
        last_ws_tick_epoch=180.0,
        last_tick_age_sec=20.0,
        last_depth_epoch=190.0,
        last_depth_age_sec=10.0,
        market_open=True,
        state_machine={"state": "DOWN", "reason": "no_ws_messages"},
        subscribed_option_tokens_count=1,
        option_feed_block_reason_by_symbol={"NIFTY": "NO_LIVE_OPTION_FEED"},
        option_active_blockers_by_symbol={"NIFTY": ["NO_LIVE_OPTION_FEED"]},
        runtime_state="RUNNING",
        last_error="",
    )

    depth_ws._write_feed_runtime_snapshot(
        now_epoch=205.0,
        ws_connected=True,
        subscribed_tokens_count=2,
        intended_tokens_count=2,
        last_db_tick_epoch=204.0,
        last_db_tick_age_sec=1.0,
        last_ws_tick_epoch=204.0,
        last_tick_age_sec=1.0,
        last_depth_epoch=204.0,
        last_depth_age_sec=1.0,
        market_open=True,
        state_machine={"state": "LIVE", "reason": "ticks_flowing"},
        subscribed_option_tokens_count=1,
        option_last_tick_age_by_symbol={"NIFTY": 1.0},
        option_feed_block_reason_by_symbol={"NIFTY": "OK"},
        option_active_blockers_by_symbol={"NIFTY": []},
        runtime_state="RUNNING",
        last_error="",
    )

    suggestions = json.loads((logs_path / "suggestions_status.json").read_text())
    engine = json.loads((logs_path / "engine_cycle_status.json").read_text())
    health = json.loads((logs_path / "runtime_health_latest.json").read_text())

    assert suggestions["reason"] == "feed_recovered_waiting_cycle_refresh"
    assert suggestions["feed_ok"] is True
    assert suggestions["visible_executable_count"] == 0
    assert suggestions["overlay_state"] == "feed_recovered_waiting_cycle_refresh"
    assert engine["reason"] == "feed_recovered_waiting_cycle_refresh"
    assert engine["cycle_stage"] == "waiting_cycle_refresh"
    assert engine["feed_ok"] is True
    assert health["feed"]["sla_status"] == "OK"
    assert health["feed"]["ws_connected"] is True


def test_reset_depth_ws_test_state_clears_ws_lifecycle_pollution(monkeypatch):
    monkeypatch.setattr(depth_ws, "_RECONNECT_BLOCKED_REASON", "reactor_not_restartable_process_restart_required", raising=False)
    monkeypatch.setattr(depth_ws, "_RECONNECT_BLOCKED_SINCE_EPOCH", 123.0, raising=False)
    monkeypatch.setattr(depth_ws, "_REACTOR_NOT_RESTARTABLE_DETECTED", True, raising=False)
    monkeypatch.setattr(depth_ws, "_RUNTIME_STATE", "RECOVERY_BLOCKED", raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_RUNTIME_ERROR", "blocked", raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [101, 202], raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_DESIRED_TOKENS", [101, 202], raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_WS_TICK_EPOCH", 123.0, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_FEED_HEALTH_STATE", "DEGRADED", raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_DISCONNECTED_CODE", 1006, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_DISCONNECTED_REASON", "connection closed", raising=False)
    monkeypatch.setattr(depth_ws, "_FULL_RESTARTS", [1.0, 2.0], raising=False)

    _reset_depth_ws_test_state(monkeypatch)

    assert depth_ws._RECONNECT_BLOCKED_REASON == ""
    assert depth_ws._RECONNECT_BLOCKED_SINCE_EPOCH == 0.0
    assert depth_ws._REACTOR_NOT_RESTARTABLE_DETECTED is False
    assert depth_ws._RUNTIME_STATE == "STOPPED"
    assert depth_ws._LAST_RUNTIME_ERROR == ""
    assert depth_ws._LAST_TOKENS == []
    assert depth_ws._LAST_DESIRED_TOKENS is None
    assert depth_ws._LAST_WS_TICK_EPOCH == 0.0
    assert depth_ws._LAST_FEED_HEALTH_STATE is None
    assert depth_ws._LAST_DISCONNECTED_CODE is None
    assert depth_ws._LAST_DISCONNECTED_REASON == ""
    assert depth_ws._FULL_RESTARTS == []
