import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from core.kite_read_only_observation_runtime import (
    BrokerWriteFirewall,
    ObservationLifecycle,
    assert_import_boundary,
    safety_contract,
    safe_environment,
    write_authority_snapshot,
)


def test_index_ltp_age_uses_trade_event_time_not_newer_book_time():
    from core.kite_read_only_observation_runtime import _index_ltp_age_sec

    now = 1_790_000_000.0
    stale_trade = _index_ltp_age_sec(
        {
            "last_price": 25000.0,
            "ts_epoch": now,
            "last_price_ts_epoch": now - 60.0,
        },
        as_of_epoch=now,
    )
    missing_trade_time = _index_ltp_age_sec(
        {"last_price": 25000.0, "ts_epoch": now, "last_price_ts_epoch": None},
        as_of_epoch=now,
    )
    future_trade_time = _index_ltp_age_sec(
        {"last_price": 25000.0, "ts_epoch": now, "last_price_ts_epoch": now + 1.0},
        as_of_epoch=now,
    )

    assert stale_trade == 60.0
    assert missing_trade_time is None
    assert future_trade_time is None


def test_candidate_decision_batches_are_serialized_across_processes(tmp_path):
    output = tmp_path / "candidate_decisions.jsonl"
    worker = """\
import os
import time
from pathlib import Path
import core.locked_jsonl as locked_jsonl

real_write = locked_jsonl.os.write
def chunked_write(fd, data):
    data = bytes(data)
    written = real_write(fd, data[:1024])
    time.sleep(0.0005)
    return written

locked_jsonl.os.write = chunked_write
while not Path(os.environ['ISSUE10_START']).exists():
    time.sleep(0.001)
batch = os.environ['ISSUE10_BATCH']
rows = [{'batch': batch, 'index': i, 'payload': 'x' * 8192} for i in range(32)]
locked_jsonl.append_jsonl_batch(Path(os.environ['ISSUE10_PATH']), rows)
"""
    start = tmp_path / "start-writers"
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", worker],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "ISSUE10_BATCH": batch, "ISSUE10_PATH": str(output),
                 "ISSUE10_START": str(start)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for batch in ("A", "B")
    ]
    start.write_text("go\n", encoding="utf-8")
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 0, f"writer failed: {stdout}\n{stderr}"
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    try:
        rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    except json.JSONDecodeError as exc:
        pytest.fail(f"concurrent writers produced invalid JSONL: {exc}")
    assert len(rows) == 64
    assert {row["batch"] for row in rows} == {"A", "B"}
    assert all(len(row["payload"]) == 8192 for row in rows)
    assert {row["batch"]: {item["index"] for item in rows if item["batch"] == row["batch"]}
            for row in rows} == {"A": set(range(32)), "B": set(range(32))}
    batches = [row["batch"] for row in rows]
    transition = next((i for i in range(1, len(batches)) if batches[i] != batches[i - 1]), len(batches))
    assert set(batches[:transition]) in ({"A"}, {"B"})
    assert set(batches[transition:]) in (set(), {"A"}, {"B"})


def test_failed_batch_preserves_interleaved_noncooperating_append(tmp_path, monkeypatch, caplog):
    import core.locked_jsonl as locked_jsonl

    output = tmp_path / "candidate_decisions.jsonl"
    real_write = os.write
    real_open = os.open
    injected = False

    def interleave_external_append(fd, data):
        nonlocal injected
        if not injected:
            injected = True
            real_write(fd, bytes(data[:5]))
            external_fd = real_open(output, os.O_WRONLY | os.O_APPEND)
            try:
                real_write(external_fd, b'{"writer":"external"}\n')
            finally:
                os.close(external_fd)
            raise OSError("injected_batch_write_failure")
        return real_write(fd, data)

    monkeypatch.setattr(locked_jsonl.os, "write", interleave_external_append)
    with pytest.raises(OSError, match="injected_batch_write_failure"):
        locked_jsonl.append_jsonl_batch(output, ({"writer": "cooperating"},))

    raw = output.read_bytes()
    assert raw.endswith(b'{"writer":"external"}\n')
    assert raw.startswith(b'{"wri')
    assert b"cooperating" not in raw
    assert "in-place rollback skipped to preserve concurrent bytes" in caplog.text

    import core.runtime_snapshot_producer as producer

    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: output)
    monkeypatch.setattr(
        producer.cfg,
        "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE",
        False,
        raising=False,
    )
    advisory = producer._build_advisory_latest_payload()
    assert advisory["row_count"] == 0
    assert any(note.startswith("parse_error:") for note in advisory["notes"])


def test_failed_batch_without_interleaved_append_retains_partial_and_reader_reports_it(tmp_path, monkeypatch):
    import core.locked_jsonl as locked_jsonl

    output = tmp_path / "candidate_decisions.jsonl"
    real_write = os.write
    calls = 0

    def fail_after_partial_write(fd, data):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(fd, bytes(data[:5]))
        raise OSError("injected_batch_write_failure")

    monkeypatch.setattr(locked_jsonl.os, "write", fail_after_partial_write)
    with pytest.raises(OSError, match="injected_batch_write_failure"):
        locked_jsonl.append_jsonl_batch(output, ({"writer": "cooperating"},))

    assert output.read_bytes() == b'{"wri'
    from core.runtime_snapshot_producer import _read_advisory_source

    rows, state = _read_advisory_source(output, limit=10)
    assert rows == []
    assert state == "PARTIAL"


def test_failed_batch_never_attempts_destructive_truncate_and_preserves_original_error(
    tmp_path, monkeypatch, caplog
):
    import core.locked_jsonl as locked_jsonl

    output = tmp_path / "candidate_decisions.jsonl"
    real_write = os.write
    calls = 0

    def fail_after_partial_write(fd, data):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(fd, bytes(data[:5]))
        raise OSError("original_append_failure")

    truncate_calls = []

    def track_truncate(_fd, _length):
        truncate_calls.append(True)
        raise AssertionError("append failure path must not truncate shared JSONL")

    monkeypatch.setattr(locked_jsonl.os, "write", fail_after_partial_write)
    monkeypatch.setattr(locked_jsonl.os, "ftruncate", track_truncate)
    with pytest.raises(OSError, match="original_append_failure"):
        locked_jsonl.append_jsonl_batch(output, ({"writer": "cooperating"},))

    assert truncate_calls == []
    assert "in-place rollback skipped to preserve concurrent bytes" in caplog.text


_FORBIDDEN_OBSERVER_PREFIXES = (
    "core.broker",
    "core.execution_adapter",
    "core.execution_engine",
    "core.execution_router",
    "core.paper_broker",
    "core.paper_fill",
    "core.paper_order",
)


class _SyntheticBrokerRequestSession:
    def request(self, method, url, **kwargs):
        return type("Response", (), {"status_code": 200})()


class _SyntheticProfileClient:
    def __init__(self):
        self.reqsession = _SyntheticBrokerRequestSession()

    def profile(self):
        self.reqsession.request("GET", "https://api.kite.trade/user/profile")
        return {"user_id": "redacted"}


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
    monkeypatch.setattr(tick_store, "get_persistence_worker_state", lambda: {
        "worker_join_completed": True,
        "queue_depth_at_shutdown": 0,
        "pending_writes_at_shutdown": 0,
        "accounting_invariant_ok": False,
    })
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
    monkeypatch.setattr(tick_store, "get_persistence_worker_state", lambda: {
        "worker_join_completed": True,
        "queue_depth_at_shutdown": 0,
        "pending_writes_at_shutdown": 0,
        "accounting_invariant_ok": False,
    })
    monkeypatch.setattr(depth_store.depth_store, "shutdown_persistence", lambda **_: {"complete": True})
    monkeypatch.setattr(depth_store.depth_store, "persistence_state", lambda: {"worker_alive": False, "queue_depth": 0})
    monkeypatch.setattr("core.market_event_graph_live_runtime_bridge.flush_live_source_bridge", lambda: {"flushed": True})

    lifecycle = ObservationLifecycle(Feed())
    lifecycle.start([256265])
    report = lifecycle.shutdown()
    assert report["shutdown_drain_complete"] is False
    assert report["feed_close_requested"] is True
    assert report["meg_bridge_flush"]["flushed"] is True
    assert report["broker_api_called"] is False
    assert report["broker_api_call_count"] == 0
    assert report["broker_api_measurement_scope"] == "UNMEASURED_NO_ACTIVE_OBSERVER_LEDGER"


def test_lifecycle_recomputes_each_store_budget_from_one_deadline(monkeypatch):
    from types import SimpleNamespace
    import core.kite_read_only_observation_runtime as lifecycle_module
    import core.tick_store as tick_store
    import core.depth_store as depth_store
    import core.feed.runtime_store as runtime_store

    class FakeClock:
        now = 0.0

        def monotonic(self):
            self.now += 0.1
            return self.now

        @staticmethod
        def sleep(_seconds):
            return None

    class Feed:
        def start_depth_ws(self, tokens, **kwargs):
            return True

        def stop_depth_ws(self, **kwargs):
            return None

    clock = FakeClock()
    monkeypatch.setattr(lifecycle_module, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep))
    monkeypatch.setattr(runtime_store, "runtime_persistence_state", lambda: {"worker_alive": False, "pending": 0})
    monkeypatch.setattr(tick_store, "pending_tick_count", lambda: 0)
    monkeypatch.setattr(tick_store, "shutdown_persistence_worker", lambda **_: {"complete": True})
    monkeypatch.setattr(tick_store, "get_persistence_worker_state", lambda: {
        "worker_join_completed": True,
        "queue_depth_at_shutdown": 0,
        "pending_writes_at_shutdown": 0,
        "accounting_invariant_ok": True,
    })
    monkeypatch.setattr(depth_store.depth_store, "shutdown_persistence", lambda **_: {"complete": True})
    monkeypatch.setattr(depth_store.depth_store, "persistence_state", lambda: {"worker_alive": False, "queue_depth": 0})
    monkeypatch.setattr(runtime_store, "shutdown_runtime_persistence", lambda **_: {"complete": True})
    monkeypatch.setattr("core.market_event_graph_live_runtime_bridge.flush_live_source_bridge", lambda: {"flushed": True})
    passed_budgets = []

    def record_budget(**kwargs):
        passed_budgets.append(kwargs["deadline_seconds"])
        return {"complete": True}

    monkeypatch.setattr(tick_store, "shutdown_persistence_worker", record_budget)
    monkeypatch.setattr(depth_store.depth_store, "shutdown_persistence", record_budget)
    monkeypatch.setattr(runtime_store, "shutdown_runtime_persistence", record_budget)

    lifecycle = ObservationLifecycle(Feed(), drain_deadline_seconds=1.0)
    lifecycle.start([256265])
    report = lifecycle.shutdown()

    assert len(passed_budgets) == 3
    assert passed_budgets[0] > passed_budgets[1] > passed_budgets[2] > 0
    assert report["shutdown_drain_deadline_expired"] is False
    assert report["shutdown_drain_complete"] is True
    assert report["read_only"] is True
    assert report["is_order_action"] is False


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
        firewall.reject("submit_fill")
    row = json.loads((tmp_path / "safety.jsonl").read_text().strip())
    assert row["method"] == "submit_fill"


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
    monkeypatch.setattr(auth, "get_kite_client", lambda **_: _SyntheticProfileClient())
    monkeypatch.setattr(feed, "activate_market_event_graph_launch_plan", lambda plan: observed.setdefault("plan", plan) or {"ok": True})
    monkeypatch.setattr(feed, "start_depth_ws", lambda tokens, **kwargs: observed.update(tokens=list(tokens), kwargs=kwargs) or True)
    monkeypatch.setattr(feed, "stop_depth_ws", lambda **kwargs: observed.setdefault("stopped", True))
    monkeypatch.setattr(snapshots, "produce_and_store_runtime_snapshots", lambda **_: observed.setdefault("snapshot_cycles", 0) or 1)

    import core.runtime_storage_authority as rsa

    governed_root = Path(tempfile.mkdtemp(prefix="tradebot-composition-", dir=str(tmp_path)))
    fake_authority = rsa.StorageAuthority(
        volume=governed_root,
        runtime_root=governed_root / "out",
        device_id=governed_root.stat().st_dev,
    )
    monkeypatch.setattr(rsa, "establish", lambda **_: fake_authority)
    monkeypatch.setattr(rsa, "revalidate", lambda *_: None)
    token_path = governed_root / "token"
    token_path.write_text("redacted")
    plan = {
        "final_union_tokens": [256265, 6401],
        "observation_tokens": [256265, 6401],
        "commit_sha": "1" * 40,
    }
    from core.kite_read_only_observation_runtime import run_observation
    assert run_observation(launch_plan=plan, output_root=governed_root / "out", token_path=token_path, session_date="2026-08-04", max_runtime_sec=0.06) == 0
    assert observed["tokens"] == [256265, 6401]
    assert observed["kwargs"]["profile_verified"] is False
    assert observed["kwargs"]["auth_mode"] == "read_only_observer"
    assert observed["stopped"] is True
    drain = json.loads((governed_root / "out" / "shutdown_drain.json").read_text(encoding="utf-8"))
    assert drain["broker_api_called"] is False
    assert drain["broker_api_call_count"] == 0
    assert drain["broker_api_call_ledger_verified"] is True
    assert drain["broker_api_call_ledger_verification_status"] == "VERIFIED"
    assert drain["broker_write_authority"] is False
    assert drain["order_authority"] is False
    startup = json.loads((governed_root / "out" / "startup_safety_contract.json").read_text(encoding="utf-8"))
    assert startup["broker_api_called"] is False
    assert startup["broker_api_call_count"] == 0
    assert startup["broker_api_measurement_scope"] == "STARTUP_SNAPSHOT_BEFORE_OBSERVER_API_PROBES"
    assert not (governed_root / "out" / "broker_api_calls.jsonl").exists()
    coverage = json.loads((governed_root / "out" / "feed_coverage_ledger.json").read_text(encoding="utf-8"))
    assert coverage["broker_api_called"] is False
    assert coverage["broker_api_call_ledger_verified"] is True
    publication = json.loads((governed_root / "out" / "cas_heritage_publication.json").read_text(encoding="utf-8"))
    assert publication["status"] == "BLOCKED"
    assert publication["reason"] == "MANIFEST_SESSION_IDENTITY_REQUIRED"


def test_active_launch_plan_tokens_are_canonical_and_not_widened(monkeypatch):
    import core.kite_depth_ws as feed

    monkeypatch.setattr(
        feed,
        "_OBSERVATION_PLAN_STATE",
        {
            "enabled": True,
            "verdict": "PASS_LIVE_SOURCE_PRESESSION_READINESS",
            "final_union_tokens": [6401, 256265, 6401, -1],
        },
    )
    assert feed._active_launch_plan_tokens() == [6401, 256265]


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
    shadow.configure_live_source_session_store(None, session_date=None)

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
            for offset in (0, 60, 120):
                packet = []
                for token in tokens:
                    packet.append({"instrument_token": int(token), "last_price": 100.0 + (int(token) % 17) + offset / 100.0, "exchange_timestamp": base + offset + 55, "mode": "full", "volume": 10, "change": 0.1, "ohlc": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0}, "depth": {"buy": [{"price": 99.5, "quantity": 10}], "sell": [{"price": 100.5, "quantity": 10}]}})
                self.on_ticks(self, packet)
        def close(self):
            return None

    # Align synthetic ticks to the last five seconds of each completed minute.
    # The bridge cutoff then lands at the last bar boundary, so the newest
    # completed bar has a five-second source tick age.
    base = float(int(time.time() // 60) * 60 - 180)

    class FakeClient:
        _active_api_key = "api-key"
        _active_access_token = "access-token"
        def ensure(self): return self
        def profile(self): raise AssertionError("observer_feed_must_not_call_profile")

    fake = FakeTicker()
    feed_events = []
    auth_payload = {"ok": True}
    monkeypatch.setattr(feed, "get_kite_ticker", lambda **_: fake)
    monkeypatch.setattr(feed, "kite_client", FakeClient())
    monkeypatch.setattr(feed, "get_kite_auth_health", lambda **_: dict(auth_payload))
    monkeypatch.setattr(feed, "_log_ws", lambda event, payload=None, throttle_key=None: feed_events.append((event, payload or {})))
    monkeypatch.setattr(feed, "_persist_runtime_snapshot_row", lambda **_: None)
    monkeypatch.setattr(feed, "_mark_auth_required", lambda *args, **kwargs: None)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api-key")
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True)
    assert not feed.start_depth_ws(
        tokens, profile_verified=True, auth_mode="read_only_observer",
        skip_lock=True, skip_guard=True,
    )
    assert feed._RUNTIME_STATE == "AUTH_BLOCKED"
    auth_payload.update(ok=False, auth_state="PENDING_WEBSOCKET_AUTH")
    assert feed.start_depth_ws(
        tokens, profile_verified=False, auth_mode="read_only_observer",
        skip_lock=True, skip_guard=True,
    )
    attempt = next(payload for event, payload in feed_events if event == "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF")
    assert attempt["profile_verified"] is False
    assert any(event == "FEED_AUTH_PENDING_WEBSOCKET_HANDSHAKE" for event, _ in feed_events)
    authenticated = next(payload for event, payload in feed_events if event == "FEED_WS_AUTHENTICATED")
    assert authenticated["auth_state"] == "VERIFIED_BY_WEBSOCKET_HANDSHAKE"
    assert feed._RUNTIME_STATE == "RUNNING"
    result = bridge.observe_cycle(
        [],
        cycle_cutoff=__import__("datetime").datetime.fromtimestamp(
            base + 180, tz=__import__("datetime").timezone.utc
        ),
    )
    assert result.attempted is True and result.exported is True
    assert result.accepted_constituent_count == 50
    row = json.loads(export_path.read_text().splitlines()[0])
    assert len(row["constituent_bar_details"]) == 50
    assert row["read_only"] is True
    fake.on_error(fake, 403, "TokenException: invalid access token")
    assert any(event == "FEED_WS_AUTH_FAILURE_PROOF" for event, _ in feed_events)
    assert feed._RUNTIME_STATE != "RUNNING"
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


def test_run_observation_dispatches_native_pulse_to_shadow_registry(
    monkeypatch,
    tmp_path,
    clean_observer_import_boundary,
):
    import core.auth as auth
    import core.kite_depth_ws as feed
    import core.runtime_snapshot_producer as snapshots
    import core.runtime_storage_authority as rsa
    import core.paper_shadow.strategy_shadow_adapter as shadow_mod
    import core.market_heritage_graph as heritage_mod
    import core.market_quote_resolver as quote_resolver

    observed = {"shadow_pulses": 0, "shutdowns": 0}

    class FakeRegistry:
        def __init__(self, **kwargs):
            observed["registry_kwargs"] = kwargs
            self.adapters = {"INTRADAY_OPENING_DRIVE_V1": object()}
            self.disabled_strategies = {}
        def on_pulse(self, pulse, market_snapshot, feed_health_truth):
            observed["shadow_pulses"] += 1
            observed["shadow_pulse_id"] = pulse.pulse_id
            observed["shadow_market_snapshot"] = market_snapshot
            observed["shadow_feed_truth"] = feed_health_truth
            return []
        def on_session_shutdown(self):
            observed["shutdowns"] += 1
            return {"read_only": True}

    monkeypatch.setattr(shadow_mod, "StrategyShadowAdapterRegistry", FakeRegistry)
    monkeypatch.setattr(
        heritage_mod,
        "load_verified_t1_prerequisites",
        lambda **_: {
            "opening_drive_prev_contract_key": "NIFTY26SEPFUT",
            "opening_drive_prev_close_1529": 23440.7,
            "opening_drive_target_expiry": "2026-09-29",
            "overnight_prev_daily_close": 23414.3,
            "overnight_prev_sma200": 24473.368,
            "heritage_verification": {"status": "VERIFIED", "read_only": True,
                "is_order_action": False, "broker_api_called": False,
                "allowed_for_live_execution": False},
        },
    )
    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_: ("api-key", "token"))
    monkeypatch.setattr(auth, "get_kite_client", lambda **_: _SyntheticProfileClient())
    monkeypatch.setattr(feed, "activate_market_event_graph_launch_plan", lambda plan: {"ok": True})
    monkeypatch.setattr(feed, "start_depth_ws", lambda tokens, **kwargs: True)
    monkeypatch.setattr(feed, "stop_depth_ws", lambda **kwargs: None)

    snap = {
        "feed_health_truth_latest": {
            "feed_ok": True,
            "websocket_ok": True,
            "context": {"feed_state": "LIVE", "runtime_state": "RUNNING", "session_id": "shadow-runtime-test"},
            "symbols": [],
        },
        "market_snapshot": {"market_open": True},
    }
    quote_now = __import__("time").time()
    monkeypatch.setattr(
        quote_resolver,
        "get_index_quote_snapshot",
        lambda _symbol: {
            "last_price": 25000.0,
            "ts_epoch": quote_now,
            "last_price_ts_epoch": quote_now - 60.0,
            "source": "rest_quote",
        },
    )

    def capture_snapshot(**kwargs):
        observed["current_market_snapshot"] = kwargs.get("market_snapshot")
        return snap

    monkeypatch.setattr(snapshots, "produce_and_store_runtime_snapshots", capture_snapshot)

    governed_root = Path(tempfile.mkdtemp(prefix="tradebot-shadow-runtime-", dir=str(tmp_path)))
    fake_authority = rsa.StorageAuthority(
        volume=governed_root,
        runtime_root=governed_root / "out",
        device_id=governed_root.stat().st_dev,
    )
    monkeypatch.setattr(rsa, "establish", lambda **_: fake_authority)
    monkeypatch.setattr(rsa, "revalidate", lambda *_: None)

    token_path = governed_root / "token"
    token_path.write_text("redacted")
    plan = {
        "final_union_tokens": [256265],
        "observation_tokens": [256265],
        "underlying_tokens": [256265],
        "commit_sha": "2" * 40,
    }

    from core.kite_read_only_observation_runtime import run_observation
    assert run_observation(
        launch_plan=plan,
        output_root=governed_root / "out",
        token_path=token_path,
        session_date="2026-09-22",
        max_runtime_sec=0.06,
    ) == 0

    assert observed["shadow_pulses"] >= 1
    assert observed["shutdowns"] == 1
    nifty_market_row = observed["current_market_snapshot"]["symbols"]["NIFTY"]
    assert nifty_market_row["feed_health"]["status"] == "STALE"
    assert nifty_market_row["quote_truth"]["is_fresh"] is False
    assert nifty_market_row["quote_truth"]["is_executable_quote"] is False
    assert observed["registry_kwargs"]["source_sha"] == "2" * 40
    assert observed["registry_kwargs"]["prerequisite_verification"]["status"] == "VERIFIED"
    identity = json.loads((governed_root / "out" / "process_identity.json").read_text())
    assert identity["read_only"] is True
    assert identity["order_authority"] is False
    assert identity["broker_write_authority"] is False
    assert identity["shadow_strategy_ids"] == ["INTRADAY_OPENING_DRIVE_V1"]


def test_shadow_registry_shutdown_failure_is_propagated(
    monkeypatch,
    tmp_path,
    clean_observer_import_boundary,
):
    import core.auth as auth
    import core.kite_depth_ws as feed
    import core.runtime_snapshot_producer as snapshots
    import core.runtime_storage_authority as rsa
    import core.paper_shadow.strategy_shadow_adapter as shadow_mod
    import core.market_heritage_graph as heritage_mod

    observed = {}

    class FailingRegistry:
        adapters = {}
        disabled_strategies = {}
        def __init__(self, **kwargs):
            observed["registry_kwargs"] = kwargs
        def on_pulse(self, **kwargs):
            return []
        def on_session_shutdown(self):
            raise RuntimeError("synthetic_shadow_seal_failure")

    monkeypatch.setattr(shadow_mod, "StrategyShadowAdapterRegistry", FailingRegistry)
    monkeypatch.setattr(
        heritage_mod,
        "load_verified_t1_prerequisites",
        lambda **kwargs: (observed.update({"heritage_kwargs": kwargs}) or {
            "opening_drive_prev_contract_key": None,
            "opening_drive_prev_close_1529": None,
            "opening_drive_target_expiry": None,
            "overnight_prev_daily_close": None,
            "overnight_prev_sma200": None,
            "heritage_verification": {"status": "BLOCKED", "read_only": True,
                "is_order_action": False, "broker_api_called": False,
                "allowed_for_live_execution": False},
        }),
    )
    monkeypatch.setattr(auth, "get_kite_credentials", lambda **_: ("api-key", "token"))
    monkeypatch.setattr(auth, "get_kite_client", lambda **_: _SyntheticProfileClient())
    monkeypatch.setattr(feed, "activate_market_event_graph_launch_plan", lambda plan: {"ok": True})
    monkeypatch.setattr(feed, "start_depth_ws", lambda tokens, **kwargs: True)
    monkeypatch.setattr(feed, "stop_depth_ws", lambda **kwargs: None)
    monkeypatch.setattr(
        snapshots,
        "produce_and_store_runtime_snapshots",
        lambda **kwargs: (observed.update({"snapshot_kwargs": kwargs}) or {
            "feed_health_truth_latest": {"feed_ok": False, "websocket_ok": False, "context": {}, "symbols": []},
            "market_snapshot": {"market_open": False},
        }),
    )

    governed_root = Path(tempfile.mkdtemp(prefix="tradebot-shadow-seal-", dir=str(tmp_path)))
    fake_authority = rsa.StorageAuthority(
        volume=governed_root,
        runtime_root=governed_root / "out",
        device_id=governed_root.stat().st_dev,
    )
    monkeypatch.setattr(rsa, "establish", lambda **_: fake_authority)
    monkeypatch.setattr(rsa, "revalidate", lambda *_: None)
    token_path = governed_root / "token"
    token_path.write_text("redacted")
    plan = {"final_union_tokens": [256265], "commit_sha": "3" * 40,
            "t1_facts": {"opening_drive_prev_close_1529": 99999.0,
                         "overnight_prev_sma200": 99999.0}}

    from core.kite_read_only_observation_runtime import run_observation
    with pytest.raises(RuntimeError, match="synthetic_shadow_seal_failure"):
        run_observation(
            launch_plan=plan,
            output_root=governed_root / "out",
            token_path=token_path,
            session_date="2026-09-22",
            max_runtime_sec=0.01,
        )

    marker = governed_root / "out" / "STRATEGY_SHADOW_EVIDENCE_SEAL_FAIL"
    assert observed["heritage_kwargs"]["manifest_path"] is None
    assert observed["heritage_kwargs"]["expected_manifest_sha256"] is None
    assert observed["registry_kwargs"]["opening_drive_prev_close_1529"] is None
    assert observed["registry_kwargs"]["overnight_prev_sma200"] is None
    assert observed["snapshot_kwargs"]["candidate_decisions_path"] == governed_root / "out" / "candidate_decisions.jsonl"
    assert marker.is_file()
    assert "synthetic_shadow_seal_failure" in marker.read_text()
