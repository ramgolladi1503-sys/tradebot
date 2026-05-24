from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core.feed_health_truth import (
    FEED_STATE_UNSAFE_REASON,
    LTP_TICKS_STALE_REASON,
    OPTION_FEED_BLOCKED_REASON,
    OPTION_TICKS_STALE_REASON,
    RUNTIME_STATE_UNSAFE_REASON,
    WEBSOCKET_DISCONNECTED_REASON,
)
from core.runtime_snapshot_store import read_snapshot_with_freshness
from core.runtime_status_overlay import classify_runtime_feed_health, derive_feed_ok

# stale_feed safety regression coverage: these tests prove unsafe feed states fail closed.


def _healthy_payload(**overrides):
    payload = {
        "feed_ok": True,
        "ws_connected": True,
        "runtime_state": "RUNNING",
        "state_machine": {"state": "LIVE", "reason": ""},
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 1.0,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.4},
        "symbol_feed_ok_by_symbol": {"NIFTY": True},
    }
    payload.update(overrides)
    return payload


def _truth_payload(decision):
    return decision.to_payload()


def test_stale_feed_raw_ws_connected_cannot_hide_effective_ws_down_state():
    payload = _healthy_payload(
        ws_connected=True,
        state_machine={"state": "DOWN", "reason": "no_ws_messages_for_15s"},
    )

    decision = classify_runtime_feed_health(payload)
    truth = _truth_payload(decision)

    assert derive_feed_ok(payload) is False
    assert truth["websocket_ok"] is False
    assert WEBSOCKET_DISCONNECTED_REASON in truth["reasons"]
    assert FEED_STATE_UNSAFE_REASON in truth["reasons"]


def test_stale_feed_explicit_feed_ok_true_cannot_override_unsafe_option_blocker():
    payload = _healthy_payload(
        feed_ok=True,
        option_feed_block_reason_by_symbol={"NIFTY": "SUBSCRIPTION_FAILED"},
        option_last_tick_age_by_symbol={"NIFTY": 0.2},
    )

    decision = classify_runtime_feed_health(payload)
    truth = _truth_payload(decision)

    assert derive_feed_ok(payload) is False
    assert "NIFTY:option_feed_blocked" in truth["reasons"]
    assert OPTION_FEED_BLOCKED_REASON in truth["symbols"][0]["reasons"]


def test_stale_feed_global_feed_ok_does_not_make_stale_symbol_option_ticks_safe():
    payload = _healthy_payload(
        feed_ok=True,
        option_last_tick_age_by_symbol={"NIFTY": 12.0},
    )

    decision = classify_runtime_feed_health(payload)
    truth = _truth_payload(decision)

    assert truth["feed_ok"] is False
    assert derive_feed_ok(payload) is False
    assert "NIFTY:option_ticks_stale" in truth["reasons"]
    assert OPTION_TICKS_STALE_REASON in truth["symbols"][0]["reasons"]


def test_stale_feed_runtime_state_and_ltp_age_are_canonical_runtime_inputs():
    payload = _healthy_payload(runtime_state="STARTING", last_tick_age_sec=9.0)

    decision = classify_runtime_feed_health(payload)
    truth = _truth_payload(decision)

    assert truth["feed_ok"] is False
    assert RUNTIME_STATE_UNSAFE_REASON in truth["reasons"]
    assert LTP_TICKS_STALE_REASON in truth["reasons"]
    assert truth["context"]["runtime_state"] == "STARTING"


def test_stale_feed_fresh_artifact_does_not_override_unhealthy_feed_payload(tmp_path):
    target = tmp_path / "feed_runtime_latest.json"
    payload = _healthy_payload(option_feed_block_reason_by_symbol={"NIFTY": "SUBSCRIPTION_FAILED"})
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "producer": "test",
                "payload": payload,
            }
        ),
        encoding="utf-8",
    )

    freshness = read_snapshot_with_freshness(target, artifact_name="feed_runtime_latest")
    decision = classify_runtime_feed_health(payload)
    truth = _truth_payload(decision)

    assert freshness["fresh"] is True
    assert truth["feed_ok"] is False
    assert "NIFTY:option_feed_blocked" in truth["reasons"]


def test_stale_feed_stale_artifact_remains_separate_from_healthy_feed_payload(tmp_path):
    target = tmp_path / "feed_runtime_latest.json"
    payload = _healthy_payload()
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": old.isoformat().replace("+00:00", "Z"),
                "producer": "test",
                "payload": payload,
            }
        ),
        encoding="utf-8",
    )

    freshness = read_snapshot_with_freshness(
        target,
        artifact_name="feed_runtime_latest",
        max_age_seconds=5,
    )
    decision = classify_runtime_feed_health(payload)
    truth = _truth_payload(decision)

    assert freshness["fresh"] is False
    assert "artifact_age_exceeds_max_age" in freshness["blockers"]
    assert truth["feed_ok"] is True
