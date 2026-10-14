"""Deterministic tests for ordered callback publication and socket barriers."""
from __future__ import annotations

import copy
import threading
import time
from types import MappingProxyType, SimpleNamespace

import pytest

import core.kite_depth_ws as ws
from core.feed.tick_callback_coordinator import TickCallbackCoordinator


WAIT = 2.0
_REAL_THREAD = threading.Thread


@pytest.fixture
def callback_owner(monkeypatch):
    coordinator = TickCallbackCoordinator(max_pending=4)
    monkeypatch.setattr(ws, "_CALLBACK_COORDINATOR", coordinator)
    monkeypatch.setattr(ws, "_CALLBACK_INGRESS_LOCK", threading.Lock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_SOCKET_LIFECYCLE_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_SOCKET_START_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 70)
    monkeypatch.setattr(ws, "_CALLBACK_SEQUENCE", 0)
    monkeypatch.setattr(ws, "_CALLBACK_UNREADY_REASON", "")
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING")
    monkeypatch.setattr(ws, "_LAST_RUNTIME_ERROR", "")
    yield coordinator
    coordinator.shutdown(WAIT)


def _install_minimal_real_processor(monkeypatch, *, published=None):
    """Keep the production processor while replacing external effects."""
    class Evidence:
        def callback(self, *_args, **_kwargs): return None
        def inc(self, *_args, **_kwargs): return None
        def normalized(self, *_args, **_kwargs): return None
        def published(self, *_args, **_kwargs): return None
        def publication_failed(self, *_args, **_kwargs): return None

    class Health:
        def on_ws_message(self, **_kwargs): return None

    monkeypatch.setattr(ws, "feed_evidence", Evidence())
    monkeypatch.setattr(ws, "record_fd_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "append_feed_forensic_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "write_queue_depth", lambda: 0)
    monkeypatch.setattr(ws, "write_enqueue_count", lambda: 0)
    monkeypatch.setattr(ws, "write_flush_count", lambda: 0)
    monkeypatch.setattr(ws, "get_feed_health_monitor", lambda: Health())
    monkeypatch.setattr(ws, "_SCHEMA_LOG_TS", time.time() + 1000)
    monkeypatch.setattr(ws, "_should_throttle_ws_event", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ws,
        "load_observation_registry",
        lambda **_kwargs: SimpleNamespace(all_tokens=[], observation_identity=lambda _token: None),
    )
    monkeypatch.setattr(ws, "get_current_feed_session_identity", lambda: {
        "feed_session_id": "callback-test-session",
        "reconnect_generation": 0,
    })
    monkeypatch.setattr(ws, "_ensure_feed_session_id", lambda: "callback-test-session")
    monkeypatch.setattr(ws, "_observation_state_payload", lambda: {})
    monkeypatch.setattr(ws, "current_feed_epoch", lambda: 0)
    monkeypatch.setattr(ws, "_is_underlying_token", lambda _token: False)
    monkeypatch.setattr(ws, "_is_index_symbol", lambda _symbol: False)
    monkeypatch.setattr(ws, "_update_symbol_freshness", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "record_tick", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "record_depth", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "record_tick_epoch", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "_record_ws_recovery_tick_receipt", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_record_feed_restart_verify_tick", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_record_observation_callback_truth", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_normalized_tick_epoch", lambda _token, *, payload_epoch, receipt_epoch: receipt_epoch)
    monkeypatch.setattr(ws, "_timestamp_provenance", lambda _tick, *, receive_epoch: {
        "timestamp_authority": "GOVERNED_RECEIVE_TIMESTAMP",
        "timestamp_source_field": None,
        "source_timestamp_epoch": None,
        "receive_timestamp_epoch": receive_epoch,
        "timestamp_fallback_used": True,
    })
    monkeypatch.setattr(ws, "_reset_stale_on_fresh_ws_tick", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_reconnect_recovery_blocked_active", lambda: False)
    monkeypatch.setattr(ws, "_tick_option_feed_verification", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_attempt_causal_ws1006_recovery_clear", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "depth_store", SimpleNamespace(persistence_state=lambda: {
        "worker_alive": True,
        "failures": 0,
        "depth_rejected_count": 0,
        "accounting_invariant_ok": True,
    }))
    if published is not None:
        monkeypatch.setattr(ws, "insert_tick", lambda **kwargs: (published.append(kwargs), True)[1])
    else:
        monkeypatch.setattr(ws, "insert_tick", lambda **_kwargs: True)


def test_real_processor_defers_reentrant_cutover_until_entire_batch_finishes(monkeypatch, callback_owner):
    published = []
    _install_minimal_real_processor(monkeypatch, published=published)
    observed = []

    def sink(event):
        generation = ws._current_socket_generation()
        observed.append((event["instrument_token"], generation))
        if len(observed) == 1:
            assert ws._advance_socket_generation() is None

    monkeypatch.setattr(ws, "_NORMALIZED_TICK_SINK", sink)
    rows = [
        {"instrument_token": 101, "last_price": 100.0},
        {"instrument_token": 202, "last_price": 200.0},
    ]
    ws.on_ticks(None, rows, socket_generation=70)

    assert observed == [(101, 70), (202, 70)]
    assert [row["token"] for row in published] == [101, 202]
    completion = ws._LAST_DEFERRED_LIFECYCLE_EVENT
    assert completion is not None and completion.wait(WAIT)
    assert ws._current_socket_generation() == 71
    before = dict(ws._LAST_MSG_TS_BY_TOKEN)
    ws.on_ticks(None, [{"instrument_token": 303, "last_price": 300.0}], socket_generation=70)
    assert ws._LAST_MSG_TS_BY_TOKEN == before


@pytest.mark.parametrize("batch_size", [1, 50, 855])
def test_batches_are_snapshotted_and_processed_synchronously(monkeypatch, callback_owner, batch_size):
    source = [
        {"instrument_token": index + 1, "last_price": float(index + 1), "nested": {"levels": [1, 2]}}
        for index in range(batch_size)
    ]
    original = copy.deepcopy(source)
    owner_ids = []
    observed = []

    def process(_ws, rows, *, socket_generation, callback_sequence=None, callback_receive_epoch=None):
        owner_ids.append(threading.get_ident())
        assert socket_generation == 70
        assert callback_sequence is not None and callback_receive_epoch is not None
        assert isinstance(rows[0], MappingProxyType)
        assert isinstance(rows[0]["nested"], MappingProxyType)
        assert rows[0]["nested"]["levels"] == (1, 2)
        observed.append(len(rows))

    monkeypatch.setattr(ws, "_process_on_ticks", process)
    ws.on_ticks(None, source, socket_generation=70)
    assert source == original
    assert observed == [batch_size]
    assert owner_ids == [callback_owner._worker.ident]


def test_queue_full_rejects_whole_batch_without_processor_or_market_state_mutation(monkeypatch):
    coordinator = TickCallbackCoordinator(max_pending=1)
    monkeypatch.setattr(ws, "_CALLBACK_COORDINATOR", coordinator)
    monkeypatch.setattr(ws, "_CALLBACK_INGRESS_LOCK", threading.Lock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 70)
    monkeypatch.setattr(ws, "_CALLBACK_SEQUENCE", 0)
    latch_lock_states = []
    original_latch = ws._latch_callback_unready_state

    def observe_latch_lock(reason):
        latch_lock_states.append(ws._CALLBACK_INGRESS_LOCK.locked())
        return original_latch(reason)

    monkeypatch.setattr(ws, "_latch_callback_unready_state", observe_latch_lock)
    entered, release = threading.Event(), threading.Event()
    processed, events = [], []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))

    def process(_ws, rows, **_kwargs):
        processed.append(tuple(row["instrument_token"] for row in rows))
        if len(processed) == 1:
            entered.set()
            assert release.wait(WAIT)

    monkeypatch.setattr(ws, "_process_on_ticks", process)
    first = _REAL_THREAD(target=lambda: ws.on_ticks(None, [{"instrument_token": 1}], socket_generation=70), daemon=True)
    first.start()
    assert entered.wait(WAIT)
    second = _REAL_THREAD(target=lambda: ws.on_ticks(None, [{"instrument_token": 2}], socket_generation=70), daemon=True)
    second.start()
    deadline = time.monotonic() + WAIT
    while coordinator.pending_count != 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    before_state = dict(ws._LAST_MSG_TS_BY_TOKEN)
    rejected_rows = [{"instrument_token": 3}, {"instrument_token": 4}]
    source_before = copy.deepcopy(rejected_rows)
    ws.on_ticks(None, rejected_rows, socket_generation=70)
    assert rejected_rows == source_before
    assert processed == [(1,)]
    assert ws._LAST_MSG_TS_BY_TOKEN == before_state
    assert any(name == "FEED_CALLBACK_QUEUE_SATURATED" for name, _ in events)
    assert ws._CALLBACK_UNREADY_REASON == "callback_queue_full"
    assert latch_lock_states and latch_lock_states[0] is True
    assert ws._RUNTIME_STATE == "DEGRADED"
    monkeypatch.setattr(ws, "_start_depth_ws_impl", lambda *_args, **_kwargs: pytest.fail("latched feed must require process restart"))
    assert ws.start_depth_ws([101]) is False
    assert ws.restart_depth_ws(reason="queue_full_recovery_attempt") is False

    release.set()
    first.join(WAIT)
    second.join(WAIT)
    assert not first.is_alive() and not second.is_alive()
    assert processed == [(1,), (2,)]
    coordinator.shutdown(WAIT)


def test_owner_exception_latches_unready_and_never_falls_back(monkeypatch):
    coordinator = TickCallbackCoordinator(max_pending=2)
    monkeypatch.setattr(ws, "_CALLBACK_COORDINATOR", coordinator)
    monkeypatch.setattr(ws, "_CALLBACK_INGRESS_LOCK", threading.Lock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 70)
    monkeypatch.setattr(ws, "_CALLBACK_SEQUENCE", 0)
    monkeypatch.setattr(ws, "_CALLBACK_UNREADY_REASON", "")
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    calls = []

    def fail(_ws, _rows, **_kwargs):
        calls.append(threading.get_ident())
        raise RuntimeError("processor fault")

    monkeypatch.setattr(ws, "_process_on_ticks", fail)
    with pytest.raises(Exception):
        ws.on_ticks(None, [{"instrument_token": 1}], socket_generation=70)
    assert len(calls) == 1
    assert ws._CALLBACK_UNREADY_REASON
    assert ws._RUNTIME_STATE == "DEGRADED"
    ws.on_ticks(None, [{"instrument_token": 2}], socket_generation=70)
    assert len(calls) == 1
    assert coordinator.shutdown(WAIT).value == "failed"


def test_malformed_batch_latches_unready_without_publication(monkeypatch, callback_owner):
    processed = []
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "_process_on_ticks", lambda *_args, **_kwargs: processed.append(True))

    ws.on_ticks(
        None,
        [{"instrument_token": 1, "last_price": float("nan")}],
        socket_generation=70,
    )

    assert processed == []
    assert ws._CALLBACK_UNREADY_REASON == "callback_batch_preparation_failed"
    assert ws._RUNTIME_STATE == "DEGRADED"
    assert callback_owner.pending_count == 0


def test_callback_latch_publishes_process_restart_required(monkeypatch):
    persisted = []
    event_calls = []
    class RestartEvent:
        def set(self):
            event_calls.append("set")

    monkeypatch.setattr(ws, "_CALLBACK_UNREADY_REASON", "")
    monkeypatch.setattr(ws, "_PROCESS_RESTART_EVENT", RestartEvent())
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **kwargs: persisted.append(kwargs) or False)
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)

    ws._mark_callback_coordinator_failed("callback_queue_full", detail="capacity exhausted")

    assert len(persisted) == 1
    assert persisted[0]["source"] == "on_ticks"
    assert persisted[0]["runtime_state"] == "RESTART_REQUIRED"
    assert persisted[0]["process_restart_required"] is True
    assert event_calls == ["set"]


def test_restart_lifecycle_waits_for_startup_lock_to_release(monkeypatch):
    lifecycle_lock = threading.RLock()
    lifecycle_lock.acquire()
    monkeypatch.setattr(ws, "_SOCKET_LIFECYCLE_LOCK", lifecycle_lock)
    monkeypatch.setattr(ws.cfg, "FEED_RESTART_LIFECYCLE_WAIT_SEC", 1.0, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    waiter_started = threading.Event()
    acquired = []

    def wait_for_lifecycle():
        waiter_started.set()
        if ws._acquire_restart_lifecycle_lock(reason="startup_fault", path="full_restart"):
            acquired.append(True)
            lifecycle_lock.release()

    waiter = _REAL_THREAD(target=wait_for_lifecycle)
    waiter.start()
    assert waiter_started.wait(WAIT)
    lifecycle_lock.release()
    waiter.join(WAIT)

    assert not waiter.is_alive()
    assert acquired == [True]


def test_expected_transition_collision_does_not_poison_callback_coordinator(monkeypatch):
    coordinator = TickCallbackCoordinator(max_pending=2)
    monkeypatch.setattr(ws, "_CALLBACK_COORDINATOR", coordinator)
    monkeypatch.setattr(ws, "_CALLBACK_INGRESS_LOCK", threading.Lock())
    monkeypatch.setattr(ws, "_CALLBACK_UNREADY_REASON", "")
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    first = coordinator.begin_transition().transition
    assert first is not None and first.wait_ack(WAIT)

    assert ws._begin_socket_transition("concurrent_test") is None
    assert ws._CALLBACK_UNREADY_REASON == ""

    first.complete()
    assert coordinator.shutdown(WAIT).value == "completed"


def test_public_start_and_stop_serialize_before_lifecycle_mutation(monkeypatch):
    monkeypatch.setattr(ws, "_CALLBACK_COORDINATOR", SimpleNamespace(is_owner_thread=False))
    monkeypatch.setattr(ws, "_CALLBACK_UNREADY_REASON", "")
    monkeypatch.setattr(ws, "_SOCKET_LIFECYCLE_LOCK", threading.RLock())
    entered_start, release_start, entered_stop = threading.Event(), threading.Event(), threading.Event()
    active = {"count": 0, "max": 0}
    start_result, stop_result = [], []

    def fake_start(*_args, **_kwargs):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        entered_start.set()
        assert release_start.wait(WAIT)
        active["count"] -= 1
        return True

    def fake_stop(*_args, **_kwargs):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        entered_stop.set()
        active["count"] -= 1
        return True

    monkeypatch.setattr(ws, "_start_depth_ws_impl", fake_start)
    monkeypatch.setattr(ws, "_stop_depth_ws_impl", fake_stop)
    start = _REAL_THREAD(target=lambda: start_result.append(ws.start_depth_ws([1])))
    stop = _REAL_THREAD(target=lambda: stop_result.append(ws.stop_depth_ws("serialized_test")))
    start.start()
    assert entered_start.wait(WAIT)
    stop.start()
    assert not entered_stop.wait(0.05)

    release_start.set()
    start.join(WAIT)
    stop.join(WAIT)
    assert not start.is_alive() and not stop.is_alive()
    assert entered_stop.is_set()
    assert start_result == [True]
    assert stop_result == [True]
    assert active["max"] == 1


def test_lifecycle_barrier_does_not_hold_subscription_mutation_lock(monkeypatch, callback_owner):
    start_waiting, callback_acquired_lock = threading.Event(), threading.Event()
    original_begin = ws._begin_socket_transition
    result = []

    def fake_start(*_args, **_kwargs):
        start_waiting.set()
        barrier = original_begin("lock_cycle_regression")
        assert barrier is not None
        barrier.complete()
        return True

    monkeypatch.setattr(ws, "_start_depth_ws_impl", fake_start)

    def prior_callback():
        assert start_waiting.wait(WAIT)
        with ws._SOCKET_START_LOCK:
            callback_acquired_lock.set()

    prior = callback_owner.submit(prior_callback)
    assert prior.accepted
    starter = _REAL_THREAD(target=lambda: result.append(ws.start_depth_ws([1])))
    starter.start()

    assert callback_acquired_lock.wait(WAIT)
    assert prior.handles[0].wait(WAIT)
    starter.join(WAIT)
    assert not starter.is_alive()
    assert result == [True]


def test_start_rechecks_process_unready_latch_after_barrier(monkeypatch, callback_owner, tmp_path):
    class RestClient:
        def profile(self):
            return {"user_id": "TESTUSER"}

    monkeypatch.setattr(ws.cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "test_key", raising=False)
    monkeypatch.setattr(ws, "KiteTicker", object())
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda **_kwargs: {"ok": True})
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: RestClient())
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "test_key")
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "test_token")
    monkeypatch.setattr(ws, "logs_dir", lambda: tmp_path)
    monkeypatch.setattr(ws, "get_feed_health_monitor", lambda: SimpleNamespace(set_reconnect_handler=lambda _fn: None))
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **_kwargs: pytest.fail("startup state must not mutate"))
    monkeypatch.setattr(ws, "_LAST_TOKENS", [99])
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING")
    factory_calls = []
    monkeypatch.setattr(ws, "get_kite_ticker", lambda **_kwargs: factory_calls.append(True))

    original_begin = ws._begin_socket_transition

    def latch_after_barrier(reason):
        barrier = original_begin(reason)
        assert barrier is not None
        ws._latch_callback_unready_state("callback_queue_full")
        return barrier

    monkeypatch.setattr(ws, "_begin_socket_transition", latch_after_barrier)

    assert ws.start_depth_ws([101], skip_lock=True, skip_guard=True) is False
    assert ws._LAST_TOKENS == [99]
    assert ws._RUNTIME_STATE == "DEGRADED"
    assert ws._current_socket_generation() == 70
    assert factory_calls == []


def test_stop_timeout_does_not_close_ticker_or_advance_generation(monkeypatch):
    coordinator = TickCallbackCoordinator(max_pending=2)
    monkeypatch.setattr(ws, "_CALLBACK_COORDINATOR", coordinator)
    monkeypatch.setattr(ws, "_CALLBACK_INGRESS_LOCK", threading.Lock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 70)
    monkeypatch.setattr(ws.cfg, "DEPTH_WS_CALLBACK_TRANSITION_TIMEOUT_SEC", 0.01, raising=False)
    monkeypatch.setattr(ws, "_CALLBACK_UNREADY_REASON", "")
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    entered, release = threading.Event(), threading.Event()
    ticker, closes = object(), []
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker)
    monkeypatch.setattr(ws, "_WATCHDOG_THREAD", None)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", None)
    monkeypatch.setattr(ws, "_close_ticker_instance", lambda instance: closes.append(instance))

    def process(_ws, _rows, **_kwargs):
        entered.set()
        assert release.wait(WAIT)

    monkeypatch.setattr(ws, "_process_on_ticks", process)
    callback = _REAL_THREAD(target=lambda: ws.on_ticks(None, [{"instrument_token": 1}], socket_generation=70), daemon=True)
    callback.start()
    assert entered.wait(WAIT)
    assert ws.stop_depth_ws("barrier_timeout_test") is False
    assert closes == []
    assert ws._KITE_TICKER is ticker
    assert ws._current_socket_generation() == 70
    release.set()
    callback.join(WAIT)
    assert not callback.is_alive()
    resumed = coordinator.submit(lambda: True)
    assert resumed.accepted and resumed.handles[0].result(WAIT) is True
    coordinator.shutdown(WAIT)


def test_stop_closes_only_after_accepted_callback_drains_and_generation_retires(monkeypatch):
    coordinator = TickCallbackCoordinator(max_pending=2)
    monkeypatch.setattr(ws, "_CALLBACK_COORDINATOR", coordinator)
    monkeypatch.setattr(ws, "_CALLBACK_INGRESS_LOCK", threading.Lock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION_LOCK", threading.RLock())
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 70)
    monkeypatch.setattr(ws, "_CALLBACK_UNREADY_REASON", "")
    monkeypatch.setattr(ws.cfg, "DEPTH_WS_CALLBACK_TRANSITION_TIMEOUT_SEC", WAIT, raising=False)
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    entered, release = threading.Event(), threading.Event()
    calls = []

    class Ticker:
        def close(self):
            calls.append(("close", ws._current_socket_generation()))

    ticker = Ticker()
    monkeypatch.setattr(ws, "_KITE_TICKER", ticker)
    monkeypatch.setattr(ws, "_WATCHDOG_THREAD", None)
    monkeypatch.setattr(ws, "_WATCHDOG_STOP", threading.Event())
    monkeypatch.setattr(ws, "campaign_raw_diagnostics", SimpleNamespace(shutdown=lambda: None))
    monkeypatch.setattr(ws, "_reset_feed_restart_verification", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_reset_option_feed_verification", lambda **_kwargs: None)
    monkeypatch.setattr(ws, "_join_ticker_threads", lambda *_args: None)
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **_kwargs: None)

    def process(_ws, _rows, **_kwargs):
        entered.set()
        assert release.wait(WAIT)
        calls.append(("callback_done", ws._current_socket_generation()))

    monkeypatch.setattr(ws, "_process_on_ticks", process)
    callback = _REAL_THREAD(target=lambda: ws.on_ticks(None, [{"instrument_token": 1}], socket_generation=70), daemon=True)
    callback.start()
    assert entered.wait(WAIT)
    result = []
    stop = _REAL_THREAD(target=lambda: result.append(ws.stop_depth_ws("barrier_success_test")), daemon=True)
    stop.start()
    time.sleep(0.02)
    assert calls == []
    assert ws._current_socket_generation() == 70

    release.set()
    callback.join(WAIT)
    stop.join(WAIT)
    assert not callback.is_alive() and not stop.is_alive()
    assert result == [True]
    assert calls == [("callback_done", 70), ("close", 71)]
    assert ws._current_socket_generation() == 71
    coordinator.shutdown(WAIT)


def test_registered_callback_rejects_retired_generation_before_processing(monkeypatch, callback_owner):
    monkeypatch.setattr(ws, "_log_ws", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 71)
    processed = []
    monkeypatch.setattr(ws, "_process_on_ticks", lambda *_args, **_kwargs: processed.append(True))
    callback_owner_obj = type("Ticker", (), {})()
    callback = ws._register_on_ticks_callback(
        callback_owner_obj,
        lambda name: name == "on_ticks",
        socket_generation=70,
    )
    callback(None, [{"instrument_token": 1}])
    assert processed == []


def test_wi07_gate1_admission_fence_quarantines_abandoned_generation(monkeypatch, callback_owner):
    """Gate G1: Callback from retired generation is rejected at admission and recorded in TickQuarantine."""
    from core.feed.tick_callback_coordinator import get_tick_quarantine
    quarantine = get_tick_quarantine()
    initial_count = quarantine.total_count

    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 80)
    # Incoming callback with old generation 79
    ws.on_ticks(None, [{"instrument_token": 101, "last_price": 100.0}], socket_generation=79)

    assert quarantine.total_count == initial_count + 1
    recent = quarantine.recent_records(1)[-1]
    assert recent.callback_gen == 79
    assert recent.active_gen == 80
    assert recent.reason == "ABANDONED_GENERATION"


def test_wi07_gate2_mid_batch_generation_bump_aborts_loop_and_quarantines(monkeypatch, callback_owner):
    """Gate G2: In a multi-tick batch, if generation increments mid-batch, subsequent ticks are quarantined."""
    _install_minimal_real_processor(monkeypatch)
    from core.feed.tick_callback_coordinator import get_tick_quarantine
    quarantine = get_tick_quarantine()
    initial_count = quarantine.total_count

    processed_tokens = []
    orig_record = ws.record_tick

    def _track_record_tick(**kwargs):
        tok = kwargs.get("token")
        processed_tokens.append(tok)
        # Advance generation mid-batch after processing first token
        if tok == 101:
            monkeypatch.setattr(ws, "_SOCKET_GENERATION", 72)

    monkeypatch.setattr(ws, "record_tick", _track_record_tick)
    monkeypatch.setattr(ws, "insert_tick", lambda **kwargs: True)

    batch = [
        {"instrument_token": 101, "last_price": 500.0},
        {"instrument_token": 102, "last_price": 505.0},
        {"instrument_token": 103, "last_price": 510.0},
    ]

    ws._process_on_ticks(None, batch, socket_generation=71)

    # First token processed, subsequent aborted
    assert 101 in processed_tokens
    assert 102 not in processed_tokens
    assert 103 not in processed_tokens
    assert quarantine.total_count > initial_count
    recent = quarantine.recent_records(1)[-1]
    assert recent.reason == "MID_BATCH_GENERATION_BUMP_ABORT"
    assert recent.callback_gen == 71
    assert recent.active_gen == 72


def test_wi07_gate3_out_of_order_timestamp_quarantined(monkeypatch, callback_owner):
    """Gate G3: Tick with timestamp earlier than previous payload timestamp is quarantined."""
    _install_minimal_real_processor(monkeypatch)
    from core.feed.tick_callback_coordinator import get_tick_quarantine
    quarantine = get_tick_quarantine()
    initial_count = quarantine.total_count

    monkeypatch.setattr(ws, "_LAST_PAYLOAD_TS_BY_TOKEN", {201: 1000.0})
    monkeypatch.setattr(ws, "insert_tick", lambda **kwargs: True)

    out_of_order_tick = {
        "instrument_token": 201,
        "last_price": 250.0,
        "exchange_timestamp": 990.0,
    }

    ws._process_on_ticks(None, [out_of_order_tick], socket_generation=70)

    assert quarantine.total_count == initial_count + 1
    recent = quarantine.recent_records(1)[-1]
    assert recent.token == 201
    assert recent.reason == "OUT_OF_ORDER_TIMESTAMP"
    assert recent.tick_epoch == 990.0


def test_wi07_gate4_quarantine_ring_buffer_bounded():
    """Gate G4: Flooding quarantine ring buffer does not exceed max capacity."""
    from core.feed.tick_callback_coordinator import TickQuarantine
    q = TickQuarantine(maxlen=10)
    for i in range(100):
        q.quarantine(token=i, reason="TEST", callback_gen=1, active_gen=2)

    assert q.total_count == 100
    assert len(q.recent_records(50)) == 10


def test_wi07_gate5_safety_non_negotiables_enforced():
    """Gate G5: Static verification of trading safety non-negotiables."""
    import inspect
    from core.feed.tick_callback_coordinator import TickCallbackCoordinator, get_tick_quarantine

    # Zero broker or order dependencies
    src = inspect.getsource(TickCallbackCoordinator)
    assert "place_order" not in src
    assert "broker" not in src
    assert "cancel_order" not in src

