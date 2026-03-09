from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core.feed.runtime_store import read_latest_runtime_snapshot, write_runtime_snapshot
import core.kite_depth_ws as depth_ws


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
