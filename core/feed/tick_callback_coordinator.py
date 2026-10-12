"""Bounded, ordered ownership for callback processor tasks.

The coordinator owns one worker thread. Accepted tasks execute on that thread
in FIFO order. It has no dependency on a websocket, persistence store, broker,
or process-global state; callers provide the complete unit of work.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable


class CoordinatorState(str, Enum):
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class RejectionReason(str, Enum):
    FULL = "full"
    TRANSITION_PENDING = "transition_pending"
    NOT_RUNNING = "not_running"


class ShutdownStatus(str, Enum):
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class CallbackCoordinatorError(RuntimeError):
    """Base error for failed or unusable coordinator operations."""


class CoordinatorFailed(CallbackCoordinatorError):
    """The owner thread failed and the coordinator rejected further work."""


class CoordinatorStopped(CallbackCoordinatorError):
    """Shutdown ended before a caller-owned transition was completed."""


class TaskWaitTimeout(TimeoutError):
    """A task did not finish before its requested wait timeout."""


@dataclass(frozen=True, slots=True)
class Admission:
    """Atomic result of a task or transition admission attempt."""

    accepted: bool
    handles: tuple["TaskHandle", ...] = ()
    transition: "TransitionHandle | None" = None
    reason: RejectionReason | None = None


class TaskHandle:
    """Completion handle for one accepted processor task."""

    __slots__ = ("_event", "_result", "_error")

    def __init__(self) -> None:
        self._event = threading.Event()
        self._result: Any = None
        self._error: BaseException | None = None

    @property
    def done(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for completion; return false only when the timeout expires."""
        return self._event.wait(timeout)

    def result(self, timeout: float | None = None) -> Any:
        if not self._event.wait(timeout):
            raise TaskWaitTimeout("callback processor task did not finish in time")
        if self._error is not None:
            raise CoordinatorFailed("callback processor task was not completed") from self._error
        return self._result

    def _finish(self, result: Any = None, error: BaseException | None = None) -> None:
        self._result = result
        self._error = error
        self._event.set()


class TransitionHandle:
    """Barrier handle that separates prior work from a caller-owned transition.

    ``wait_ack`` succeeds only after all tasks accepted before the barrier have
    completed. The caller then performs its transition and calls ``complete``
    to reopen task admission. Tasks remain rejected between acknowledgement
    and completion.
    """

    __slots__ = ("_coordinator", "_ack", "_done", "_error")

    def __init__(self, coordinator: "TickCallbackCoordinator") -> None:
        self._coordinator = coordinator
        self._ack = threading.Event()
        self._done = threading.Event()
        self._error: BaseException | None = None

    @property
    def acknowledged(self) -> bool:
        return self._ack.is_set() and self._error is None

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def wait_ack(self, timeout: float | None = None) -> bool:
        """Wait until prior tasks have drained or the coordinator fails."""
        if not self._ack.wait(timeout):
            return False
        if self._error is not None:
            raise CoordinatorFailed("transition barrier failed") from self._error
        return True

    def complete(self) -> None:
        """Complete the caller-owned transition and permit later admissions."""
        if not self._ack.is_set():
            raise CallbackCoordinatorError("cannot complete a transition before its barrier is acknowledged")
        if self._error is not None:
            raise CoordinatorFailed("cannot complete a failed transition") from self._error
        self._coordinator._complete_transition(self)

    def cancel(self) -> bool:
        """Cancel an uncompleted barrier when its caller abandons the transition.

        Cancellation is safe only before the caller performs lifecycle side
        effects. It removes the barrier and reopens admission; earlier callback
        work remains FIFO and continues normally.
        """
        return self._coordinator._cancel_transition(self)

    def wait(self, timeout: float | None = None) -> bool:
        """Wait until the caller completes this transition or it fails."""
        if not self._done.wait(timeout):
            return False
        if self._error is not None:
            raise CoordinatorFailed("transition did not complete") from self._error
        return True

    def _acknowledge(self) -> None:
        self._ack.set()

    def _finish(self, error: BaseException | None = None) -> None:
        self._error = error
        self._ack.set()
        self._done.set()


@dataclass(slots=True)
class _DataItem:
    task: Callable[[], Any]
    handle: TaskHandle


@dataclass(slots=True)
class _TransitionItem:
    handle: TransitionHandle


@dataclass(frozen=True, slots=True)
class _StopItem:
    pass


_STOP = _StopItem()
_QueueItem = _DataItem | _TransitionItem | _StopItem


class TickCallbackCoordinator:
    """Run admitted zero-argument tasks sequentially on a dedicated owner.

    ``max_pending`` bounds accepted callback tasks waiting in the internal
    queue; a currently executing task does not consume pending capacity. A
    transition barrier occupies a reserved control slot and therefore remains
    admissible when the data capacity is full.
    """

    def __init__(self, max_pending: int, *, name: str = "tick-callback-owner") -> None:
        if isinstance(max_pending, bool) or not isinstance(max_pending, int) or max_pending < 1:
            raise ValueError("max_pending must be a positive integer")
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")

        self._max_pending = max_pending
        self._condition = threading.Condition()
        self._queue: deque[_QueueItem] = deque()
        self._pending_data = 0
        self._state = CoordinatorState.RUNNING
        self._failure: BaseException | None = None
        self._transition: TransitionHandle | None = None
        self._stop_enqueued = False
        self._worker = threading.Thread(target=self._run, name=name, daemon=True)
        self._worker.start()

    @property
    def state(self) -> CoordinatorState:
        with self._condition:
            return self._state

    @property
    def pending_count(self) -> int:
        with self._condition:
            return self._pending_data

    @property
    def failure(self) -> BaseException | None:
        with self._condition:
            return self._failure

    @property
    def is_owner_thread(self) -> bool:
        """Whether the caller is the coordinator's sole task-execution thread.

        Lifecycle callers use this to defer a reentrant cutover instead of
        waiting for a barrier that is ordered behind their own active task.
        """
        return threading.current_thread() is self._worker

    def submit(self, task: Callable[[], Any]) -> Admission:
        """Admit one complete callable or reject it without queue mutation."""
        return self.submit_batch((task,))

    def submit_batch(self, tasks: Iterable[Callable[[], Any]]) -> Admission:
        """Atomically admit all tasks in a list/tuple, or admit none.

        Requiring a built-in sequence avoids partially consuming a lazy or
        user-defined iterator before admission. Every task is validated before
        queue state changes.
        """
        if type(tasks) not in (tuple, list):
            raise TypeError("tasks must be a plain list or tuple")
        prepared = tuple(tasks)
        if not prepared:
            raise ValueError("tasks must contain at least one callable")
        if any(not callable(task) for task in prepared):
            raise TypeError("every task must be callable")

        with self._condition:
            rejection = self._admission_rejection()
            if rejection is not None:
                return Admission(accepted=False, reason=rejection)
            if len(prepared) > self._max_pending - self._pending_data:
                return Admission(accepted=False, reason=RejectionReason.FULL)

            handles = tuple(TaskHandle() for _ in prepared)
            self._queue.extend(
                _DataItem(task=task, handle=handle)
                for task, handle in zip(prepared, handles)
            )
            self._pending_data += len(prepared)
            self._condition.notify()
            return Admission(accepted=True, handles=handles)

    def begin_transition(self) -> Admission:
        """Append one reserved FIFO barrier and pause new data admission."""
        with self._condition:
            rejection = self._admission_rejection()
            if rejection is not None:
                return Admission(accepted=False, reason=rejection)
            if self._transition is not None:
                return Admission(accepted=False, reason=RejectionReason.TRANSITION_PENDING)

            handle = TransitionHandle(self)
            self._transition = handle
            self._queue.append(_TransitionItem(handle))
            self._condition.notify()
            return Admission(accepted=True, transition=handle)

    def shutdown(self, timeout: float | None = None) -> ShutdownStatus:
        """Stop admission, drain accepted work, and report completion explicitly.

        Calling shutdown repeatedly is safe. A timeout leaves the worker in
        STOPPING; a later call can observe its completion. On the worker thread,
        shutdown schedules the stop marker and returns TIMED_OUT rather than
        attempting an invalid self-join.
        """
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative or None")
        with self._condition:
            if self._state is CoordinatorState.FAILED:
                return ShutdownStatus.FAILED
            if self._state is CoordinatorState.STOPPED:
                return ShutdownStatus.COMPLETED
            if self._state is CoordinatorState.RUNNING:
                self._state = CoordinatorState.STOPPING
            if not self._stop_enqueued:
                self._queue.append(_STOP)
                self._stop_enqueued = True
                self._condition.notify()

        if threading.current_thread() is self._worker:
            return ShutdownStatus.TIMED_OUT
        self._worker.join(timeout)
        with self._condition:
            if self._state is CoordinatorState.FAILED:
                return ShutdownStatus.FAILED
            if self._state is CoordinatorState.STOPPED:
                return ShutdownStatus.COMPLETED
            return ShutdownStatus.TIMED_OUT

    def _admission_rejection(self) -> RejectionReason | None:
        if self._state is not CoordinatorState.RUNNING:
            return RejectionReason.NOT_RUNNING
        if self._transition is not None:
            return RejectionReason.TRANSITION_PENDING
        return None

    def _complete_transition(self, handle: TransitionHandle) -> None:
        with self._condition:
            if self._transition is not handle:
                if self._state is CoordinatorState.FAILED:
                    raise CoordinatorFailed("coordinator failed during transition") from self._failure
                raise CallbackCoordinatorError("transition is no longer active")
            self._transition = None
            handle._finish()
            self._condition.notify_all()

    def _cancel_transition(self, handle: TransitionHandle) -> bool:
        """Remove a timed-out lifecycle barrier without discarding data work."""
        with self._condition:
            if self._transition is not handle:
                return False
            barrier = next(
                (
                    item
                    for item in self._queue
                    if isinstance(item, _TransitionItem) and item.handle is handle
                ),
                None,
            )
            if barrier is not None:
                self._queue.remove(barrier)
            self._transition = None
            handle._finish(error=CoordinatorStopped("transition was cancelled before lifecycle side effects"))
            self._condition.notify_all()
            return True

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._queue:
                    self._condition.wait()
                item = self._queue.popleft()
                if isinstance(item, _DataItem):
                    self._pending_data -= 1
                    self._condition.notify_all()
                elif isinstance(item, _TransitionItem):
                    # Acknowledge while holding the same condition used by
                    # cancel(), so timeout cancellation cannot race a popped
                    # but not-yet-acknowledged barrier.
                    item.handle._acknowledge()

            if isinstance(item, _DataItem):
                try:
                    result = item.task()
                except BaseException as exc:  # fail closed even for unusual worker exits
                    item.handle._finish(error=exc)
                    self._fail(exc)
                    return
                item.handle._finish(result=result)
            elif isinstance(item, _TransitionItem):
                continue
            else:
                with self._condition:
                    if self._state is CoordinatorState.STOPPING:
                        self._state = CoordinatorState.STOPPED
                    if self._transition is not None:
                        self._transition._finish(
                            error=CoordinatorStopped(
                                "coordinator stopped before transition completion"
                            )
                        )
                        self._transition = None
                    self._condition.notify_all()
                return

    def _fail(self, cause: BaseException) -> None:
        failed = CoordinatorFailed("callback owner thread failed; admission is closed")
        with self._condition:
            self._failure = cause
            self._state = CoordinatorState.FAILED
            while self._queue:
                item = self._queue.popleft()
                if isinstance(item, _DataItem):
                    self._pending_data -= 1
                    item.handle._finish(error=failed)
                elif isinstance(item, _TransitionItem):
                    item.handle._finish(error=cause)
            if self._transition is not None:
                self._transition._finish(error=cause)
                self._transition = None
            self._condition.notify_all()
