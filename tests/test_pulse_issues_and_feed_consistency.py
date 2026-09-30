import time
from pathlib import Path
import pytest

from core import kite_depth_ws as ws
from core import tick_store
from core.paper_shadow.strategy_shadow_adapter import load_canonical_t1_prerequisites


def test_reconcile_intended_tokens_accepts_launch_plan_canonical_reconcile():
    current_tokens = [100, 200]
    desired_tokens = [100, 200, 300]
    actual_tokens = [100, 200, 300]

    reconciled, updated = ws._reconcile_rebalance_intended_tokens(
        reason="launch_plan_canonical_reconcile",
        current_tokens=current_tokens,
        desired_tokens=desired_tokens,
        actual_tokens=actual_tokens,
        pending_tokens=False,
    )

    assert updated is True
    assert reconciled == [100, 200, 300]


def test_subscription_registry_consistent_true_when_intended_equals_subscribed(monkeypatch):
    class DummyCfg:
        MAX_DEPTH_AGE_SEC = 2.0
        MAX_QUOTE_AGE_SEC = 2.0

    monkeypatch.setattr(ws, "cfg", DummyCfg())
    monkeypatch.setattr(ws, "_INTENDED_TOKENS", [101, 102, 103])
    monkeypatch.setattr(ws, "_LAST_TOKENS", [101, 102, 103])
    monkeypatch.setattr(ws, "_PENDING_SUBSCRIBE_TOKENS", set())
    monkeypatch.setattr(ws, "_PENDING_UNSUBSCRIBE_TOKENS", set())
    monkeypatch.setattr(ws, "_PENDING_MODE_FULL_TOKENS", set())
    monkeypatch.setattr(ws, "_LAST_WS_TICK_EPOCH", time.time())
    monkeypatch.setattr(ws, "_LAST_MSG_TS_BY_TOKEN", {101: time.time(), 102: time.time(), 103: time.time()})

    health = ws._runtime_transport_truth_fields(
        now_epoch=time.time(),
        ws_connected=True,
        runtime_state="RUNNING",
        last_ws_tick_epoch=time.time(),
        last_tick_age_sec=0.1,
        last_depth_age_sec=0.1,
        reconnect_blocked_reason=None,
    )

    assert health["subscription_registry_consistent"] is True
    assert health["missing_tokens"] == []
    assert health["extra_tokens"] == []


def test_activate_launch_plan_synchronizes_intended_tokens(monkeypatch):
    monkeypatch.setattr(ws, "_INTENDED_TOKENS", [10, 20])
    monkeypatch.setattr(ws, "_INTENDED_TOKEN_COUNT", 2)

    plan = {
        "ok": True,
        "verdict": "PASS_LIVE_SOURCE_PRESESSION_READINESS",
        "production_tokens": [10, 20],
        "observation_tokens": [30],
        "final_union_tokens": [10, 20, 30],
        "missing_observation_tokens": [],
        "configured_budget": 150,
        "launch_plan_sha256": "abc123sha",
    }

    ws.activate_market_event_graph_launch_plan(plan)

    assert ws._INTENDED_TOKENS == [10, 20, 30]
    assert ws._INTENDED_TOKEN_COUNT == 3
    assert ws._active_launch_plan_tokens() == [10, 20, 30]


def test_tick_store_write_queue_capacity_is_50000(monkeypatch):
    assert tick_store._WRITE_QUEUE_CAPACITY >= 50000


def test_legacy_t1_loader_does_not_trust_unpinned_state_root_manifest(tmp_path, monkeypatch):
    session_date = "2026-09-29"
    sessions_dir = tmp_path / "sessions" / f"session_{session_date}"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = sessions_dir / f"t1_prerequisites_{session_date}.json"
    manifest_data = (
        '{\n'
        '  "opening_drive_prev_contract_key": "NIFTY26SEPFUT",\n'
        '  "opening_drive_prev_close_1529": 22788.25,\n'
        '  "opening_drive_target_expiry": "2026-09-29",\n'
        '  "overnight_prev_daily_close": 22788.25,\n'
        '  "overnight_prev_sma200": 22150.0\n'
        '}\n'
    )
    manifest_file.write_text(manifest_data, encoding="utf-8")

    # Clear environment variables
    for var in [
        "OPENING_DRIVE_PREV_FUTURES_KEY",
        "OPENING_DRIVE_PREV_CLOSE_1529",
        "OPENING_DRIVE_TARGET_EXPIRY",
        "OVERNIGHT_PREV_DAILY_CLOSE",
        "OVERNIGHT_PREV_SMA200",
    ]:
        monkeypatch.delenv(var, raising=False)

    prereqs = load_canonical_t1_prerequisites(
        session_date=session_date,
        launch_plan={},
        data_dir=sessions_dir,
    )

    assert all(prereqs[key] is None for key in (
        "opening_drive_prev_contract_key",
        "opening_drive_prev_close_1529",
        "opening_drive_target_expiry",
        "overnight_prev_daily_close",
        "overnight_prev_sma200",
    ))
    assert prereqs["heritage_verification"]["status"] == "BLOCKED"
    assert prereqs["heritage_verification"]["reason"] == "PINNED_HERITAGE_MANIFEST_REQUIRED"


def test_pending_tokens_cleared_on_mutation_callbacks(monkeypatch):
    monkeypatch.setattr(ws, "_PENDING_SUBSCRIBE_TOKENS", {1001, 1002})
    monkeypatch.setattr(ws, "_PENDING_UNSUBSCRIBE_TOKENS", {2001})
    monkeypatch.setattr(ws, "_LAST_TOKENS", [2001, 3001])

    # Simulate subscribe callback
    to_sub = [1001, 1002]
    ws._PENDING_SUBSCRIBE_TOKENS.difference_update(to_sub)
    ws._LAST_TOKENS = list(sorted(set(ws._LAST_TOKENS).union(set(to_sub))))

    # Simulate unsubscribe callback
    to_unsub = [2001]
    ws._PENDING_UNSUBSCRIBE_TOKENS.difference_update(to_unsub)
    ws._LAST_TOKENS = list(sorted(set(ws._LAST_TOKENS) - set(to_unsub)))

    assert len(ws._PENDING_SUBSCRIBE_TOKENS) == 0
    assert len(ws._PENDING_UNSUBSCRIBE_TOKENS) == 0
    assert ws._LAST_TOKENS == [1001, 1002, 3001]
