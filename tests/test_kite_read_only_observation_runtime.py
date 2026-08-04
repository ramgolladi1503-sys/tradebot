import json
import sys

import pytest

from core.kite_read_only_observation_runtime import (
    BrokerWriteFirewall,
    ObservationLifecycle,
    assert_import_boundary,
    safety_contract,
    safe_environment,
    write_authority_snapshot,
)


def test_lifecycle_shutdown_is_idempotent_and_rejects_late_start(monkeypatch):
    calls = []

    class Feed:
        def start_depth_ws(self, tokens, **kwargs):
            calls.append(("start", list(tokens), kwargs))
            return True

        def stop_depth_ws(self, **kwargs):
            calls.append(("stop", kwargs))

    import core.tick_store as tick_store
    import core.depth_store as depth_store
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "shutdown_runtime_persistence", lambda **_: {"complete": True, "queue_depth": 0, "worker_alive": False})
    monkeypatch.setattr(runtime_store, "runtime_persistence_state", lambda: {"worker_alive": False, "pending": 0})
    monkeypatch.setattr(tick_store, "shutdown_persistence_worker", lambda **_: {"complete": True})
    monkeypatch.setattr(tick_store, "get_persistence_worker_state", lambda: {"worker_join_completed": True, "queue_depth_at_shutdown": 0})
    monkeypatch.setattr(depth_store.depth_store, "shutdown_persistence", lambda **_: {"complete": True})
    monkeypatch.setattr(depth_store.depth_store, "persistence_state", lambda: {"worker_alive": False, "queue_depth": 0})
    monkeypatch.setattr("core.market_event_graph_live_runtime_bridge.flush_live_source_bridge", lambda: {"flushed": True})

    lifecycle = ObservationLifecycle(Feed(), drain_deadline_seconds=1.0)
    lifecycle.start([256265, 738561])
    first = lifecycle.shutdown()
    second = lifecycle.shutdown("late_callback")
    assert first == second
    assert first["accepting"] is False
    assert first["late_callback_policy"] == "REJECTED_AFTER_ACCEPTING_FALSE"
    assert [call[0] for call in calls] == ["start", "stop"]
    with pytest.raises(RuntimeError, match="ALREADY_SHUT_DOWN"):
        lifecycle.start([256265])


def test_lifecycle_drain_report_uses_real_persistence_shutdown_apis(monkeypatch):
    class Feed:
        def start_depth_ws(self, tokens, **kwargs):
            return True

        def stop_depth_ws(self, **kwargs):
            return None

    import core.tick_store as tick_store
    import core.depth_store as depth_store
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "shutdown_runtime_persistence", lambda **_: {"complete": True, "queue_depth": 0, "worker_alive": False})
    monkeypatch.setattr(runtime_store, "runtime_persistence_state", lambda: {"worker_alive": False, "pending": 0})
    monkeypatch.setattr(tick_store, "shutdown_persistence_worker", lambda **_: {"complete": True})
    monkeypatch.setattr(tick_store, "get_persistence_worker_state", lambda: {"worker_join_completed": True, "queue_depth_at_shutdown": 0})
    monkeypatch.setattr(depth_store.depth_store, "shutdown_persistence", lambda **_: {"complete": True})
    monkeypatch.setattr(depth_store.depth_store, "persistence_state", lambda: {"worker_alive": False, "queue_depth": 0})
    monkeypatch.setattr("core.market_event_graph_live_runtime_bridge.flush_live_source_bridge", lambda: {"flushed": True})

    lifecycle = ObservationLifecycle(Feed())
    lifecycle.start([256265])
    report = lifecycle.shutdown()
    assert report["shutdown_drain_complete"] is True
    assert report["feed_close_requested"] is True
    assert report["meg_bridge_flush"]["flushed"] is True


def test_safe_environment_overwrites_inherited_live_values():
    env = safe_environment({
        "TRADING_MODE": "LIVE",
        "EXECUTION_MODE": "LIVE",
        "LIVE_BROKER_ADAPTER_ACTIVE": "1",
        "ALLOW_LIVE_ORDERS": "1",
    })
    contract = safety_contract(env, child_command=[sys.executable])
    assert contract["resolved_trading_mode"] == "SIM"
    assert contract["resolved_execution_mode"] == "SIM"
    assert contract["live_broker_adapter_active"] is False
    assert contract["broker_write_authority"] is False
    assert contract["order_authority"] is False
    assert "TRADING_MODE" in contract["unsafe_inherited_values"]


def test_import_boundary_has_no_broker_or_execution_modules():
    assert_import_boundary()


def test_broker_write_firewall_records_and_rejects(tmp_path):
    firewall = BrokerWriteFirewall(tmp_path / "safety.jsonl")
    with pytest.raises(RuntimeError, match="SAFETY_BLOCKER_BROKER_WRITE_ATTEMPT"):
        firewall.reject("place_order")
    row = json.loads((tmp_path / "safety.jsonl").read_text().strip())
    assert row["method"] == "place_order"


def test_safe_environment_disables_paper_and_live_execution():
    env = safe_environment({})
    contract = safety_contract(env, child_command=[sys.executable])
    assert contract["paper_execution_allowed"] is False
    assert contract["live_execution_allowed"] is False
    assert contract["manual_approval_cannot_route_orders"] is True


def test_authority_snapshot_uses_canonical_serializer_and_pr782_parser(tmp_path):
    snapshot = tmp_path / "authority.jsonl"
    row = write_authority_snapshot({
        "candidate_id": "blocked-1",
        "trade_id": "blocked-1",
        "quote_source": "synthetic_offhours",
        "synthetic": True,
        "fallback_used": False,
        "selection_score": 0.9,
    }, snapshot)
    from core.ai_reliability_agent.pr763_session import verify_authority_snapshots
    result = verify_authority_snapshots([snapshot])
    assert result.passed is True, result.errors
    assert row["authority_allowed"] is False
    assert row["selection_score"] == 0.0
    assert row["capital_assigned"] == 0.0


def test_real_composition_wires_launch_plan_to_feed_start(monkeypatch, tmp_path):
    import core.auth as auth
    import core.kite_depth_ws as feed
    import core.runtime_snapshot_producer as snapshots
    observed = {}

    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_: ("api-key", "token"))
    monkeypatch.setattr(auth, "get_kite_client", lambda **_: type("Profile", (), {"profile": lambda self: {"user_id": "redacted"}})())
    monkeypatch.setattr(feed, "activate_market_event_graph_launch_plan", lambda plan: observed.setdefault("plan", plan) or {"ok": True})
    monkeypatch.setattr(feed, "start_depth_ws", lambda tokens, **kwargs: observed.update(tokens=list(tokens), kwargs=kwargs) or True)
    monkeypatch.setattr(feed, "stop_depth_ws", lambda **kwargs: observed.setdefault("stopped", True))
    monkeypatch.setattr(snapshots, "produce_and_store_runtime_snapshots", lambda **_: observed.setdefault("snapshot_cycles", 0) or 1)

    token_path = tmp_path / "token"
    token_path.write_text("redacted")
    plan = {"final_union_tokens": [256265, 6401], "observation_tokens": [256265, 6401]}
    from core.kite_read_only_observation_runtime import run_observation
    assert run_observation(launch_plan=plan, output_root=tmp_path / "out", token_path=token_path, session_date="2026-08-04", max_runtime_sec=0.06) == 0
    assert observed["tokens"] == [256265, 6401]
    assert observed["kwargs"]["profile_verified"] is True
    assert observed["stopped"] is True
