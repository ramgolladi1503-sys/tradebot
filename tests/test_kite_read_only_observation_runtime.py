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


_FORBIDDEN_OBSERVER_PREFIXES = (
    "core.broker",
    "core.execution_adapter",
    "core.execution_engine",
    "core.execution_router",
    "core.paper_broker",
    "core.paper_fill",
    "core.paper_order",
)


@pytest.fixture
def clean_observer_import_boundary():
    """Temporarily remove test-preloaded broker mocks without weakening runtime checks."""
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name.startswith(_FORBIDDEN_OBSERVER_PREFIXES)
    }
    for name in saved:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name.startswith(_FORBIDDEN_OBSERVER_PREFIXES):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


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


def test_import_boundary_has_no_broker_or_execution_modules(clean_observer_import_boundary):
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


def test_real_composition_wires_launch_plan_to_feed_start(
    monkeypatch,
    tmp_path,
    clean_observer_import_boundary,
):
    import core.auth as auth
    import core.kite_depth_ws as feed
    import core.runtime_snapshot_producer as snapshots
    observed = {}

    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_: ("api-key", "token"))
    monkeypatch.setattr(auth, "get_kite_client", lambda **_: type("Profile", (), {"profile": lambda self: {"user_id": "redacted"}})())
    monkeypatch.setattr(feed, "activate_market_event_graph_launch_plan", lambda plan: observed.setdefault("plan", plan) or {"ok": True})
    monkeypatch.setattr(feed, "start_depth_ws", lambda tokens, **kwargs: observed.update(tokens=list(tokens), kwargs=kwargs) or True)
    monkeypatch.setattr(feed, "stop_depth_ws", lambda **kwargs: observed.setdefault("stopped", True))
    monkeypatch.setattr(snapshots, "produce_and_store_runtime_snapshots", lambda **_: observed.setdefault("snapshot_cycles", 0) or {})

    token_path = tmp_path / "token"
    token_path.write_text("redacted")
    plan = {
        "final_union_tokens": [256265, 6401],
        "observation_tokens": [256265, 6401],
        "commit_sha": "1" * 40,
    }
    from core.kite_read_only_observation_runtime import run_observation
    assert run_observation(launch_plan=plan, output_root=tmp_path / "out", token_path=token_path, session_date="2026-08-04", max_runtime_sec=0.06) == 0
    assert observed["tokens"] == [256265, 6401]
    assert observed["kwargs"]["profile_verified"] is True
    assert observed["stopped"] is True


def test_pre_first_tick_snapshot_wait_does_not_terminate_observation(
    monkeypatch, tmp_path, clean_observer_import_boundary,
):
    import core.auth as auth
    import core.kite_depth_ws as feed
    import core.runtime_snapshot_producer as snapshots

    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_: ("api-key", "token"))
    monkeypatch.setattr(auth, "get_kite_client", lambda **_: type("Profile", (), {"profile": lambda self: {"user_id": "redacted"}})())
    monkeypatch.setattr(feed, "activate_market_event_graph_launch_plan", lambda plan: {"ok": True})
    monkeypatch.setattr(feed, "start_depth_ws", lambda tokens, **kwargs: True)
    monkeypatch.setattr(feed, "stop_depth_ws", lambda **kwargs: None)
    calls = {"count": 0}

    def produce(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("CANONICAL_MARKET_SNAPSHOT_INPUTS_UNAVAILABLE")
        return {}

    monkeypatch.setattr(snapshots, "produce_and_store_runtime_snapshots", produce)
    token_path = tmp_path / "token"
    token_path.write_text("redacted")
    plan = {"final_union_tokens": [256265], "commit_sha": "1" * 40}

    from core.kite_read_only_observation_runtime import run_observation
    assert run_observation(
        launch_plan=plan, output_root=tmp_path / "out", token_path=token_path,
        session_date="2026-08-27", max_runtime_sec=0.12,
    ) == 0
    assert calls["count"] >= 2


def test_packet_driven_completed_bars_export_live_source_meg_row(monkeypatch, tmp_path):
    """Drive the real registered callback with a network-free KiteTicker boundary."""
    import importlib
    import json
    import time
    from config import config as cfg

    feed = importlib.import_module("core.kite_depth_ws")
    bridge_mod = importlib.import_module("core.market_event_graph_live_runtime_bridge")
    shadow = importlib.import_module("core.market_event_graph_live_ohlc_buffer")
    from core.ai_reliability_agent.pr763_session import discover_live_semantics
    from core.market_event_graph_live_runtime_bridge import LiveSourceRuntimeBridge
    from core.market_event_graph_live_source import LiveCapturedMetadataExporter

    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_OBSERVATION_REGISTRY_PATH", "runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json", raising=False)
    registry = importlib.import_module("core.market_event_graph_live_observation_registry").load_observation_registry(force=True)
    shadow.reset_live_source_shadow_buffer()
    feed.stop_depth_ws(reason="packet_proof_reset")
    feed._reset_market_event_graph_generation_evidence()
    feed._FEED_SESSION_ID = "packet-proof-session"
    feed._FEED_RECONNECT_GENERATION = 1
    token_by_symbol = {"NIFTY": registry.index_token, **registry.token_by_symbol}
    feed._TOKEN_TO_SYMBOL.update(token_by_symbol)
    feed._UNDERLYING_TOKENS.add(registry.index_token)
    tokens = list(registry.all_tokens)
    plan = {"final_union_tokens": tokens, "observation_tokens": tokens, "production_tokens": [registry.index_token], "launch_plan_sha256": registry.canonical_sha256}
    feed._set_observation_plan_state(enabled=True, verdict="PASS_LIVE_SOURCE_PRESESSION_READINESS", production_tokens=[registry.index_token], observation_tokens=tokens, final_union_tokens=tokens, configured_budget=150)

    export_path = tmp_path / "captured_live_source.jsonl"
    rejection_path = tmp_path / "rejections.jsonl"
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_REJECTION_PATH", str(rejection_path))
    universe_path = __import__("pathlib").Path("runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json")
    bridge = LiveSourceRuntimeBridge(exporter=LiveCapturedMetadataExporter(export_path), universe_contract=json.loads(universe_path.read_text()))
    monkeypatch.setattr(bridge_mod, "_LIVE_SOURCE_BRIDGE", bridge)

    class FakeTicker:
        MODE_FULL = "full"
        MODE_QUOTE = "quote"
        def __init__(self):
            self.subscribed = set()
            self.modes = {}
            self.on_connect = None
            self.on_ticks = None
        def subscribe(self, values):
            self.subscribed.update(int(v) for v in values)
        def set_mode(self, mode, values):
            for value in values:
                self.modes[int(value)] = mode
        def connect(self, threaded=True):
            self.on_connect(self, {})
            base = float(int(time.time() // 60) * 60 - 120)
            for offset in (0, 60, 120):
                packet = []
                for token in tokens:
                    packet.append({"instrument_token": int(token), "last_price": 100.0 + (int(token) % 17) + offset / 100.0, "exchange_timestamp": base + offset + 1, "mode": "full", "volume": 10, "change": 0.1, "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0}, "depth": {"buy": [{"price": 99.5, "quantity": 10}], "sell": [{"price": 100.5, "quantity": 10}]}})
                self.on_ticks(self, packet)
        def close(self):
            return None

    class FakeClient:
        _active_api_key = "api-key"
        _active_access_token = "access-token"
        def ensure(self): return self
        def profile(self): return {"user_id": "proof"}

    fake = FakeTicker()
    monkeypatch.setattr(feed, "get_kite_ticker", lambda **_: fake)
    monkeypatch.setattr(feed, "kite_client", FakeClient())
    monkeypatch.setattr(feed, "get_kite_auth_health", lambda **_: {"ok": True})
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api-key")
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True)
    assert feed.start_depth_ws(tokens, profile_verified=True, skip_lock=True, skip_guard=True)
    result = bridge.observe_cycle([], cycle_cutoff=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    assert result.attempted is True and result.exported is True
    assert result.accepted_constituent_count == 50
    row = json.loads(export_path.read_text().splitlines()[0])
    assert len(row["constituent_bar_details"]) == 50
    assert row["read_only"] is True
    from core.kite_read_only_observation_runtime import write_meg_wiring_evidence
    write_meg_wiring_evidence(
        bridge=bridge,
        result=result,
        output_path=tmp_path / "meg_wiring_evidence.json",
        cycle_count=1,
        producer_commit="1" * 40,
    )
    from core.kite_read_only_observation_runtime import ObservationLifecycle
    shutdown = ObservationLifecycle(feed).shutdown()
    (tmp_path / "shutdown_drain.json").write_text(json.dumps(shutdown) + "\n")
    semantics = discover_live_semantics(tmp_path)
    assert semantics.passed is True, semantics.evidence
    feed.stop_depth_ws(reason="packet_proof_complete")
