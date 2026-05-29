from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
from core.feed.runtime_store import write_runtime_snapshot
from core.feed_execution_truth import feed_truth_allows_live_selection


def test_feed_truth_allows_only_live_state():
    assert feed_truth_allows_live_selection("LIVE") is True
    for state in (
        "MARKET_CLOSED",
        "STARTING",
        "DEGRADED",
        "DEAD",
        "AUTH_BLOCKED",
        "RESTARTING",
        "RESTART_FAILED",
        "RESTART_VERIFY_FAILED",
        None,
    ):
        assert feed_truth_allows_live_selection(state) is False


def test_runtime_store_writes_canonical_truth_to_required_artifacts(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "runtime.sqlite"), raising=False)

    import core.feed.runtime_store as runtime_store

    monkeypatch.setattr(runtime_store, "repo_root", lambda: repo)

    ok = write_runtime_snapshot(
        {
            "ts_epoch": 200.0,
            "ws_connected": True,
            "effective_ws_connected": True,
            "feed_ok": True,
            "market_open": True,
            "subscribed_tokens_count": 2,
            "intended_tokens_count": 2,
            "subscribed_tokens_sample": [1, 101],
            "subscribed_option_tokens_count": 1,
            "missing_option_tokens_count": 0,
            "last_ws_tick_epoch": 199.0,
            "last_tick_age_sec": 1.0,
            "last_depth_epoch": 199.0,
            "last_depth_age_sec": 1.0,
            "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
            "runtime_state": "RUNNING",
            "source": "unit-test",
        }
    )

    assert ok is True
    for rel in ("logs/feed_runtime_latest.json", ".runtime/feed_runtime_latest.json"):
        payload = json.loads((repo / rel).read_text())
        assert payload["feed_truth_state"] == "LIVE"
        assert payload["feed_truth_allows_executable_candidates"] is True
        assert payload["feed_truth_allows_live_selection"] is True
        assert payload["read_only"] is True
        assert payload["is_order_action"] is False
        assert payload["broker_api_called"] is False


def test_runtime_store_feed_truth_fails_closed_when_ticks_missing(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "runtime.sqlite"), raising=False)

    import core.feed.runtime_store as runtime_store

    monkeypatch.setattr(runtime_store, "repo_root", lambda: repo)

    ok = write_runtime_snapshot(
        {
            "ts_epoch": 200.0,
            "ws_connected": True,
            "effective_ws_connected": True,
            "feed_ok": True,
            "market_open": True,
            "subscribed_tokens_count": 2,
            "intended_tokens_count": 2,
            "subscribed_tokens_sample": [1, 101],
            "subscribed_option_tokens_count": 1,
            "missing_option_tokens_count": 0,
            "last_ws_tick_epoch": None,
            "last_tick_age_sec": None,
            "last_depth_epoch": None,
            "last_depth_age_sec": None,
            "runtime_state": "RUNNING",
            "source": "unit-test",
        }
    )

    assert ok is True
    payload = json.loads((repo / "logs" / "feed_runtime_latest.json").read_text())
    assert payload["feed_truth_state"] != "LIVE"
    assert payload["feed_truth_allows_executable_candidates"] is False
