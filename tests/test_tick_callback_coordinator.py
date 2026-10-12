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
