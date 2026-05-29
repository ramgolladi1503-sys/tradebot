from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core.feed.runtime_store import read_latest_runtime_snapshot, write_runtime_snapshot
import core.feed.runtime_store as runtime_store
import core.kite_depth_ws as depth_ws
from core.runtime_status_overlay import derive_effective_ws_connected, derive_feed_ok


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
    assert captured["kwargs"]["check_same_thread"] is False


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
    monkeypatch.setattr(depth_ws, "_STALE_STRIKES", 0, raising=False)
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)

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
    captured = {}

    def fake_write_json_atomic(path, payload):
        captured["path"] = path
        captured["payload"] = payload
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
    monkeypatch.setattr(depth_ws, "_INTENDED_TOKEN_COUNT", 2, raising=False)

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

    assert captured["path"] == logs_path / "feed_runtime_latest.json"
    assert captured["payload"]["ws_connected"] is True
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
