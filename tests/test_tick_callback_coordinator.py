from __future__ import annotations

import threading

import pytest

from core.feed.tick_callback_coordinator import (
    CallbackCoordinatorError,
    CoordinatorFailed,
    CoordinatorState,
    RejectionReason,
    ShutdownStatus,
    TickCallbackCoordinator,
)


WAIT = 2.0


def _accepted(coordinator: TickCallbackCoordinator, task):
    admission = coordinator.submit(task)
    assert admission.accepted
    return admission.handles[0]


def test_tasks_run_fifo_on_one_owner_thread():
    coordinator = TickCallbackCoordinator(max_pending=8)
    order: list[int] = []
    owner_ids: list[int] = []
    owner_flag: list[bool] = []
    start = threading.Event()

    admission = coordinator.submit_batch(
        tuple(
            lambda value=value: (
                start.wait(WAIT),
                owner_ids.append(threading.get_ident()),
                owner_flag.append(coordinator.is_owner_thread),
                order.append(value),
                value,
            )[-1]
            for value in range(5)
        )
    )
    assert admission.accepted
    start.set()
    assert [handle.result(WAIT) for handle in admission.handles] == list(range(5))
    assert order == list(range(5))
    assert len(set(owner_ids)) == 1
    assert owner_ids[0] != threading.get_ident()
    assert owner_flag == [True] * 5
    assert coordinator.is_owner_thread is False
    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED


def test_batch_admission_at_capacity_is_all_or_none():
    coordinator = TickCallbackCoordinator(max_pending=2)
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    first = _accepted(
        coordinator,
        lambda: (started.set(), release.wait(WAIT), calls.append("active")),
    )
    assert started.wait(WAIT)
    queued = coordinator.submit_batch((lambda: calls.append("queued-1"), lambda: calls.append("queued-2")))
    assert queued.accepted
    rejected = coordinator.submit_batch((lambda: calls.append("partial-1"), lambda: calls.append("partial-2")))
    assert not rejected.accepted
    assert rejected.reason is RejectionReason.FULL
    assert rejected.handles == ()
    assert coordinator.pending_count == 2

    release.set()
    assert first.wait(WAIT)
    for handle in queued.handles:
        assert handle.wait(WAIT)
    assert calls == ["active", "queued-1", "queued-2"]
    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED


def test_transition_barrier_is_admitted_at_full_capacity_and_orders_after_prior_tasks():
    coordinator = TickCallbackCoordinator(max_pending=1)
    started = threading.Event()
    release = threading.Event()
    order: list[str] = []

    active = _accepted(
        coordinator,
        lambda: (started.set(), release.wait(WAIT), order.append("active")),
    )
    assert started.wait(WAIT)
    prior = _accepted(coordinator, lambda: order.append("prior"))
    assert coordinator.pending_count == 1

    barrier_admission = coordinator.begin_transition()
    assert barrier_admission.accepted
    barrier = barrier_admission.transition
    assert barrier is not None
    assert coordinator.pending_count == 1

    rejected = coordinator.submit(lambda: order.append("during-transition"))
    assert not rejected.accepted
    assert rejected.reason is RejectionReason.TRANSITION_PENDING

    release.set()
    assert active.wait(WAIT)
    assert prior.wait(WAIT)
    assert barrier.wait_ack(WAIT)
    assert barrier.acknowledged
    assert order == ["active", "prior"]

    barrier.complete()
    assert barrier.wait(WAIT)
    after = _accepted(coordinator, lambda: order.append("after-transition"))
    assert after.wait(WAIT)
    assert order == ["active", "prior", "after-transition"]
    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED


def test_transition_cannot_complete_before_its_barrier_acknowledges():
    coordinator = TickCallbackCoordinator(max_pending=2)
    started = threading.Event()
    release = threading.Event()
    _accepted(coordinator, lambda: (started.set(), release.wait(WAIT)))
    assert started.wait(WAIT)
    transition = coordinator.begin_transition().transition
    assert transition is not None
    with pytest.raises(CallbackCoordinatorError, match="before its barrier"):
        transition.complete()
    release.set()
    assert transition.wait_ack(WAIT)
    transition.complete()
    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED


def test_cancelled_transition_reopens_admission_without_dropping_prior_work():
    coordinator = TickCallbackCoordinator(max_pending=2)
    started, release = threading.Event(), threading.Event()
    calls = []
    active = _accepted(coordinator, lambda: (started.set(), release.wait(WAIT), calls.append("prior")))
    assert started.wait(WAIT)
    transition = coordinator.begin_transition().transition
    assert transition is not None
    assert transition.cancel() is True

    later = _accepted(coordinator, lambda: calls.append("later"))
    release.set()
    assert active.wait(WAIT)
    assert later.wait(WAIT)
    assert calls == ["prior", "later"]
    with pytest.raises(CoordinatorFailed, match="barrier failed"):
        transition.wait_ack(0)
    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED


def test_processor_exception_fails_closed_and_rejects_queued_and_future_work():
    coordinator = TickCallbackCoordinator(max_pending=3)
    started = threading.Event()
    release = threading.Event()
    failure = ValueError("processor failed")

    def fail_after_release():
        started.set()
        release.wait(WAIT)
        raise failure

    failed_task = _accepted(coordinator, fail_after_release)
    assert started.wait(WAIT)
    queued = _accepted(coordinator, lambda: pytest.fail("queued task must not run after failure"))
    transition = coordinator.begin_transition().transition
    assert transition is not None

    release.set()
    with pytest.raises(CoordinatorFailed, match="task was not completed"):
        failed_task.result(WAIT)
    with pytest.raises(CoordinatorFailed):
        queued.result(WAIT)
    with pytest.raises(CoordinatorFailed, match="barrier failed"):
        transition.wait_ack(WAIT)
    assert coordinator.state is CoordinatorState.FAILED
    assert coordinator.failure is failure
    rejected = coordinator.submit(lambda: None)
    assert not rejected.accepted
    assert rejected.reason is RejectionReason.NOT_RUNNING
    assert coordinator.shutdown(WAIT) is ShutdownStatus.FAILED


def test_shutdown_times_out_without_losing_work_then_drains_idempotently():
    coordinator = TickCallbackCoordinator(max_pending=2)
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    active = _accepted(
        coordinator,
        lambda: (started.set(), release.wait(WAIT), calls.append("active")),
    )
    assert started.wait(WAIT)
    queued = _accepted(coordinator, lambda: calls.append("queued"))

    assert coordinator.shutdown(timeout=0) is ShutdownStatus.TIMED_OUT
    assert coordinator.state is CoordinatorState.STOPPING
    rejected = coordinator.submit(lambda: calls.append("late"))
    assert not rejected.accepted
    assert rejected.reason is RejectionReason.NOT_RUNNING

    release.set()
    assert active.wait(WAIT)
    assert queued.wait(WAIT)
    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED
    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED
    assert calls == ["active", "queued"]


def test_transition_barrier_can_be_inserted_when_data_queue_is_full():
    coordinator = TickCallbackCoordinator(max_pending=1)
    started = threading.Event()
    release = threading.Event()
    _accepted(coordinator, lambda: (started.set(), release.wait(WAIT)))
    assert started.wait(WAIT)
    _accepted(coordinator, lambda: None)
    assert coordinator.pending_count == 1

    transition = coordinator.begin_transition()
    assert transition.accepted
    assert transition.transition is not None
    release.set()
    assert transition.transition.wait_ack(WAIT)
    transition.transition.complete()
    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED


def test_shutdown_resolves_an_uncompleted_transition_as_cancelled():
    coordinator = TickCallbackCoordinator(max_pending=1)
    transition = coordinator.begin_transition().transition
    assert transition is not None
    assert transition.wait_ack(WAIT)

    assert coordinator.shutdown(WAIT) is ShutdownStatus.COMPLETED
    with pytest.raises(CoordinatorFailed, match="did not complete"):
        transition.wait(WAIT)


# ---------------------------------------------------------------------------
# WI-12 Invariant Proof Gates: Monotonic Sequence Gap & Desync Telemetry
# ---------------------------------------------------------------------------

from core.feed.tick_callback_coordinator import (
    TickSequenceCoordinator,
    TickCoordinationStatus,
)


def test_wi12_gate1_sequential_ticks_nominal_flow():
    """Consecutive advancing ticks are accepted with SYNCED_OK and clean metrics."""
    coord = TickSequenceCoordinator(feed_epoch=1)
    for i in range(5):
        res = coord.coordinate_tick({
            "instrument_token": 256265,
            "exchange_timestamp": 1700000000.0 + i,
            "sequence_number": 100 + i,
        })
        assert res.accepted is True
        assert res.status == TickCoordinationStatus.SYNCED_OK
        assert res.gap_size == 0
        assert res.is_order_action is False
        assert res.broker_api_called is False
        assert res.read_only is True

    telemetry = coord.get_telemetry()
    assert telemetry.total_gap_count == 0
    assert telemetry.total_retrograde_count == 0
    assert len(telemetry.active_desync_tokens) == 0


def test_wi12_gate2_subsecond_burst_identical_timestamps_accepted():
    """Identical exchange timestamps within high-frequency burst are accepted (I-2)."""
    coord = TickSequenceCoordinator(feed_epoch=1)
    res1 = coord.coordinate_tick({
        "instrument_token": 256265,
        "exchange_timestamp": 1700000000.0,
    })
    assert res1.accepted is True
    assert res1.status == TickCoordinationStatus.SYNCED_OK

    # Subsequent tick with identical exchange timestamp
    res2 = coord.coordinate_tick({
        "instrument_token": 256265,
        "exchange_timestamp": 1700000000.0,
    })
    assert res2.accepted is True
    assert res2.status == TickCoordinationStatus.TIMESTAMP_REPEATED_OK
    assert res2.gap_size == 0


def test_wi12_gate3_retrograde_timestamp_rejected_fail_closed():
    """Ticks arriving with backward/retrograde exchange timestamp are rejected for bars (I-2)."""
    coord = TickSequenceCoordinator(feed_epoch=1)
    res1 = coord.coordinate_tick({
        "instrument_token": 256265,
        "exchange_timestamp": 1700000010.0,
    })
    assert res1.accepted is True

    # Regressed tick
    res2 = coord.coordinate_tick({
        "instrument_token": 256265,
        "exchange_timestamp": 1700000005.0,
    })
    assert res2.accepted is False
    assert res2.status == TickCoordinationStatus.TIMESTAMP_RETROGRADE
    assert 256265 in coord.get_telemetry().active_desync_tokens
    assert coord.get_telemetry().total_retrograde_count == 1


def test_wi12_gate4_explicit_sequence_gap_detection():
    """Gaps in explicit sequence number are detected, measured, and marked desynced (I-2)."""
    coord = TickSequenceCoordinator(feed_epoch=1)
    coord.coordinate_tick({
        "instrument_token": 256265,
        "sequence_number": 10,
    })
    # Jump from 10 to 14 -> gap of 3 dropped packets (11, 12, 13)
    res = coord.coordinate_tick({
        "instrument_token": 256265,
        "sequence_number": 14,
    })
    assert res.accepted is True
    assert res.status == TickCoordinationStatus.EXPLICIT_SEQUENCE_GAP
    assert res.gap_size == 3
    assert 256265 in coord.get_telemetry().active_desync_tokens
    assert coord.get_telemetry().total_gap_count == 1


def test_wi12_gate5_hysteresis_recovery_k10_exact():
    """Desynced token recovers to synced strictly upon receiving K=10 consecutive clean ticks (I-3)."""
    coord = TickSequenceCoordinator(feed_epoch=1)
    # Trigger desync
    coord.coordinate_tick({"instrument_token": 111, "sequence_number": 1})
    coord.coordinate_tick({"instrument_token": 111, "sequence_number": 5})  # gap of 3
    assert 111 in coord.get_telemetry().active_desync_tokens

    # Send 9 clean ticks
    for i in range(9):
        coord.coordinate_tick({"instrument_token": 111, "sequence_number": 6 + i})
        assert 111 in coord.get_telemetry().active_desync_tokens, f"premature recovery at step {i+1}"

    # 10th clean tick triggers recovery
    coord.coordinate_tick({"instrument_token": 111, "sequence_number": 15})
    assert 111 not in coord.get_telemetry().active_desync_tokens


def test_wi12_gate6_token_partition_isolation():
    """Anomalies in one token do not contaminate other tokens (I-1)."""
    coord = TickSequenceCoordinator(feed_epoch=1)
    coord.coordinate_tick({"instrument_token": 100, "exchange_timestamp": 10.0})
    coord.coordinate_tick({"instrument_token": 200, "exchange_timestamp": 10.0})

    # Retrograde only on token 100
    coord.coordinate_tick({"instrument_token": 100, "exchange_timestamp": 5.0})
    # Clean tick on token 200
    coord.coordinate_tick({"instrument_token": 200, "exchange_timestamp": 11.0})

    telemetry = coord.get_telemetry()
    assert 100 in telemetry.active_desync_tokens
    assert 200 not in telemetry.active_desync_tokens

    summary_100 = coord.get_token_summary(100)
    summary_200 = coord.get_token_summary(200)
    assert summary_100 is not None and summary_100.is_desynced is True
    assert summary_200 is not None and summary_200.is_desynced is False


def test_wi12_gate7_epoch_advancement_resets_cleanly():
    """Advancing feed_epoch resets token tracking partition without false anomalies (I-1)."""
    coord = TickSequenceCoordinator(feed_epoch=1)
    coord.coordinate_tick({"instrument_token": 555, "exchange_timestamp": 1000.0})

    # WebSocket reconnect increments epoch to 2
    coord.reset_epoch(2)
    # Next tick with lower timestamp in epoch 2 is treated as fresh epoch start, not retrograde
    res = coord.coordinate_tick({"instrument_token": 555, "exchange_timestamp": 500.0})
    assert res.accepted is True
    assert res.status == TickCoordinationStatus.SYNCED_OK
    assert 555 not in coord.get_telemetry().active_desync_tokens


def test_wi12_gate8_bridge_telemetry_integration():
    """LiveSourceRuntimeBridge exports feed_desync_telemetry into evidence rows (I-5)."""
    from core.market_event_graph_live_runtime_bridge import LiveSourceRuntimeBridge
    coord = TickSequenceCoordinator(feed_epoch=1)
    coord.coordinate_tick({"instrument_token": 777, "exchange_timestamp": 100.0})
    coord.coordinate_tick({"instrument_token": 777, "exchange_timestamp": 90.0})  # retrograde

    bridge = LiveSourceRuntimeBridge(coordinator=coord)
    assert bridge._coordinator is coord
    telemetry = bridge._coordinator.get_telemetry()
    assert 777 in telemetry.active_desync_tokens
    dict_payload = telemetry.to_dict()
    assert dict_payload["active_desync_count"] == 1
    assert dict_payload["total_retrograde_count"] == 1
