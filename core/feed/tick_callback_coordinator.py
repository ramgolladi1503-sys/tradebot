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


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    token: int | None
    reason: str
    tick_epoch: float | None
    receipt_epoch: float | None
    callback_gen: int
    active_gen: int
    payload_sample: dict[str, Any] | None = None


class TickQuarantine:
    """Bounded, thread-safe in-memory ring-buffer for quarantined ticks."""

    def __init__(self, maxlen: int = 1000) -> None:
        self._maxlen = maxlen
        self._lock = threading.Lock()
        self._records: deque[QuarantineRecord] = deque(maxlen=maxlen)
        self._quarantined_count = 0
        self._quarantined_by_reason: dict[str, int] = {}

    def quarantine(
        self,
        *,
        token: int | None,
        reason: str,
        callback_gen: int,
        active_gen: int,
        tick_epoch: float | None = None,
        receipt_epoch: float | None = None,
        payload_sample: dict[str, Any] | None = None,
    ) -> QuarantineRecord:
        record = QuarantineRecord(
            token=token,
            reason=str(reason),
            tick_epoch=tick_epoch,
            receipt_epoch=receipt_epoch,
            callback_gen=int(callback_gen),
            active_gen=int(active_gen),
            payload_sample=payload_sample,
        )
        with self._lock:
            self._records.append(record)
            self._quarantined_count += 1
            reason_str = str(reason)
            self._quarantined_by_reason[reason_str] = (
                self._quarantined_by_reason.get(reason_str, 0) + 1
            )
        return record

    @property
    def total_count(self) -> int:
        with self._lock:
            return self._quarantined_count

    @property
    def counts_by_reason(self) -> dict[str, int]:
        with self._lock:
            return dict(self._quarantined_by_reason)

    def recent_records(self, limit: int = 50) -> list[QuarantineRecord]:
        with self._lock:
            return list(self._records)[-max(0, limit):]


_GLOBAL_TICK_QUARANTINE = TickQuarantine()


def get_tick_quarantine() -> TickQuarantine:
    return _GLOBAL_TICK_QUARANTINE


class TickCoordinationStatus(str, Enum):
    SYNCED_OK = "SYNCED_OK"
    TIMESTAMP_REPEATED_OK = "TIMESTAMP_REPEATED_OK"
    EXPLICIT_SEQUENCE_GAP = "EXPLICIT_SEQUENCE_GAP"
    TIMESTAMP_RETROGRADE = "TIMESTAMP_RETROGRADE"
    EPOCH_RESET = "EPOCH_RESET"
    INVALID_TICK = "INVALID_TICK"


@dataclass(frozen=True)
class TokenSequenceSummary:
    instrument_token: int
    feed_epoch: int
    last_exchange_timestamp: float | None
    last_sequence_id: int | None
    arrival_count: int
    consecutive_clean_ticks: int
    is_desynced: bool
    total_gaps: int
    total_retrograde: int
    last_gap_size: int
    last_anomaly_epoch: float | None


@dataclass(frozen=True)
class FeedDesyncTelemetry:
    feed_epoch: int
    active_desync_tokens: tuple[int, ...]
    total_gap_count: int
    total_retrograde_count: int
    tokens_tracked: int
    token_summaries: dict[int, TokenSequenceSummary]
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "feed_epoch": self.feed_epoch,
            "active_desync_tokens": list(self.active_desync_tokens),
            "active_desync_count": len(self.active_desync_tokens),
            "total_gap_count": self.total_gap_count,
            "total_retrograde_count": self.total_retrograde_count,
            "tokens_tracked": self.tokens_tracked,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class TickCoordinationResult:
    accepted: bool
    status: TickCoordinationStatus
    instrument_token: int
    feed_epoch: int
    exchange_epoch: float | None
    arrival_seq: int
    gap_size: int
    reason: str
    telemetry_snapshot: FeedDesyncTelemetry | None = None
    is_order_action: bool = False
    broker_api_called: bool = False
    read_only: bool = True


class _MutableTokenState:
    __slots__ = (
        "instrument_token",
        "feed_epoch",
        "last_exchange_timestamp",
        "last_sequence_id",
        "arrival_count",
        "consecutive_clean_ticks",
        "is_desynced",
        "total_gaps",
        "total_retrograde",
        "last_gap_size",
        "last_anomaly_epoch",
    )

    def __init__(self, instrument_token: int, feed_epoch: int):
        self.instrument_token = instrument_token
        self.feed_epoch = feed_epoch
        self.last_exchange_timestamp: float | None = None
        self.last_sequence_id: int | None = None
        self.arrival_count = 0
        self.consecutive_clean_ticks = 0
        self.is_desynced = False
        self.total_gaps = 0
        self.total_retrograde = 0
        self.last_gap_size = 0
        self.last_anomaly_epoch: float | None = None

    def snapshot(self) -> TokenSequenceSummary:
        return TokenSequenceSummary(
            instrument_token=self.instrument_token,
            feed_epoch=self.feed_epoch,
            last_exchange_timestamp=self.last_exchange_timestamp,
            last_sequence_id=self.last_sequence_id,
            arrival_count=self.arrival_count,
            consecutive_clean_ticks=self.consecutive_clean_ticks,
            is_desynced=self.is_desynced,
            total_gaps=self.total_gaps,
            total_retrograde=self.total_retrograde,
            last_gap_size=self.last_gap_size,
            last_anomaly_epoch=self.last_anomaly_epoch,
        )


class TickSequenceCoordinator:
    """Zero-buffering, causal sequence gap detector and feed desync telemetry tracker.

    Adheres strictly to Hermes Invariants I-1 through I-5:
    - Domain partitioning per (feed_epoch, instrument_token).
    - Permissive non-decreasing timestamps (t_k >= t_{k-1}) allowing subsecond bursts.
    - Retrograde timestamp rejection (t_k < t_{k-1}) failing closed for bar updates.
    - Soft diagnostic isolation with K=10 consecutive clean ticks hysteresis recovery.
    - Strict read_only=True, is_order_action=False, broker_api_called=False.
    """

    RECOVERY_THRESHOLD_K: int = 10

    def __init__(self, feed_epoch: int = 0):
        self._lock = threading.Lock()
        self._feed_epoch = int(feed_epoch)
        self._token_states: dict[tuple[int, int], _MutableTokenState] = {}
        self._total_gaps = 0
        self._total_retrogrades = 0

    @property
    def feed_epoch(self) -> int:
        with self._lock:
            return self._feed_epoch

    def reset_epoch(self, new_epoch: int) -> None:
        with self._lock:
            self._feed_epoch = int(new_epoch)

    def coordinate_tick(
        self,
        tick: Mapping[str, Any],
        receipt_epoch: float | None = None,
        feed_epoch: int | None = None,
    ) -> TickCoordinationResult:
        import time

        now_epoch = float(receipt_epoch if receipt_epoch is not None else time.time())
        token_val = tick.get("instrument_token") or tick.get("token")
        try:
            token = int(token_val)
        except (TypeError, ValueError):
            return TickCoordinationResult(
                accepted=False,
                status=TickCoordinationStatus.INVALID_TICK,
                instrument_token=0,
                feed_epoch=self._feed_epoch,
                exchange_epoch=None,
                arrival_seq=0,
                gap_size=0,
                reason="MISSING_OR_INVALID_INSTRUMENT_TOKEN",
            )

        # Extract timestamp
        ts_val = (
            tick.get("exchange_timestamp")
            or tick.get("timestamp")
            or tick.get("last_trade_time")
        )
        exchange_epoch: float | None = None
        if ts_val is not None:
            if hasattr(ts_val, "timestamp"):
                exchange_epoch = float(ts_val.timestamp())
            elif isinstance(ts_val, (int, float)):
                exchange_epoch = float(ts_val)
            elif isinstance(ts_val, str):
                try:
                    from datetime import datetime
                    exchange_epoch = float(datetime.fromisoformat(ts_val).timestamp())
                except Exception:
                    pass

        # Extract sequence id if explicitly provided
        seq_val = (
            tick.get("sequence_number")
            or tick.get("seq_id")
            or tick.get("packet_id")
            or tick.get("sequence")
        )
        explicit_seq: int | None = None
        if seq_val is not None:
            try:
                explicit_seq = int(seq_val)
            except (TypeError, ValueError):
                pass

        with self._lock:
            cur_epoch = int(self._feed_epoch if feed_epoch is None else feed_epoch)
            key = (cur_epoch, token)
            state = self._token_states.get(key)
            if state is None:
                state = _MutableTokenState(instrument_token=token, feed_epoch=cur_epoch)
                self._token_states[key] = state

            state.arrival_count += 1
            arrival_seq = state.arrival_count

            # 1. Check explicit sequence gap
            gap_size = 0
            if explicit_seq is not None:
                if state.last_sequence_id is not None:
                    if explicit_seq > state.last_sequence_id + 1:
                        gap_size = explicit_seq - state.last_sequence_id - 1
                        state.total_gaps += 1
                        self._total_gaps += 1
                        state.last_gap_size = gap_size
                        state.is_desynced = True
                        state.consecutive_clean_ticks = 0
                        state.last_anomaly_epoch = now_epoch
                        state.last_sequence_id = explicit_seq
                        if exchange_epoch is not None:
                            state.last_exchange_timestamp = max(
                                state.last_exchange_timestamp or 0.0, exchange_epoch
                            )
                        return TickCoordinationResult(
                            accepted=True,
                            status=TickCoordinationStatus.EXPLICIT_SEQUENCE_GAP,
                            instrument_token=token,
                            feed_epoch=cur_epoch,
                            exchange_epoch=exchange_epoch,
                            arrival_seq=arrival_seq,
                            gap_size=gap_size,
                            reason=f"EXPLICIT_SEQUENCE_GAP_DETECTED gap_size={gap_size}",
                        )
                state.last_sequence_id = explicit_seq

            # 2. Check exchange timestamp monotonicity
            if exchange_epoch is not None:
                if state.last_exchange_timestamp is not None:
                    if exchange_epoch < state.last_exchange_timestamp:
                        # Retrograde timestamp: reject from bar creation
                        state.total_retrograde += 1
                        self._total_retrogrades += 1
                        state.is_desynced = True
                        state.consecutive_clean_ticks = 0
                        state.last_anomaly_epoch = now_epoch
                        return TickCoordinationResult(
                            accepted=False,
                            status=TickCoordinationStatus.TIMESTAMP_RETROGRADE,
                            instrument_token=token,
                            feed_epoch=cur_epoch,
                            exchange_epoch=exchange_epoch,
                            arrival_seq=arrival_seq,
                            gap_size=0,
                            reason=f"TIMESTAMP_RETROGRADE curr={exchange_epoch} prev={state.last_exchange_timestamp}",
                        )
                    elif exchange_epoch == state.last_exchange_timestamp:
                        # Permissible subsecond burst tie
                        state.consecutive_clean_ticks += 1
                        if state.is_desynced and state.consecutive_clean_ticks >= self.RECOVERY_THRESHOLD_K:
                            state.is_desynced = False
                        return TickCoordinationResult(
                            accepted=True,
                            status=TickCoordinationStatus.TIMESTAMP_REPEATED_OK,
                            instrument_token=token,
                            feed_epoch=cur_epoch,
                            exchange_epoch=exchange_epoch,
                            arrival_seq=arrival_seq,
                            gap_size=0,
                            reason="TIMESTAMP_REPEATED_OK",
                        )

                state.last_exchange_timestamp = exchange_epoch

            # Clean advancement
            state.consecutive_clean_ticks += 1
            if state.is_desynced and state.consecutive_clean_ticks >= self.RECOVERY_THRESHOLD_K:
                state.is_desynced = False

            return TickCoordinationResult(
                accepted=True,
                status=TickCoordinationStatus.SYNCED_OK,
                instrument_token=token,
                feed_epoch=cur_epoch,
                exchange_epoch=exchange_epoch,
                arrival_seq=arrival_seq,
                gap_size=0,
                reason="SYNCED_OK",
            )

    def coordinate_batch(
        self,
        ticks: Sequence[Mapping[str, Any]],
        receipt_epoch: float | None = None,
        feed_epoch: int | None = None,
    ) -> tuple[TickCoordinationResult, ...]:
        return tuple(
            self.coordinate_tick(t, receipt_epoch=receipt_epoch, feed_epoch=feed_epoch)
            for t in ticks
        )

    def get_telemetry(self) -> FeedDesyncTelemetry:
        import time

        with self._lock:
            active_desync = tuple(
                state.instrument_token
                for (ep, tok), state in self._token_states.items()
                if ep == self._feed_epoch and state.is_desynced
            )
            summaries = {
                state.instrument_token: state.snapshot()
                for (ep, tok), state in self._token_states.items()
                if ep == self._feed_epoch
            }
            return FeedDesyncTelemetry(
                feed_epoch=self._feed_epoch,
                active_desync_tokens=active_desync,
                total_gap_count=self._total_gaps,
                total_retrograde_count=self._total_retrogrades,
                tokens_tracked=len(summaries),
                token_summaries=summaries,
                timestamp=time.time(),
            )

    def get_token_summary(self, instrument_token: int) -> TokenSequenceSummary | None:
        with self._lock:
            state = self._token_states.get((self._feed_epoch, int(instrument_token)))
            return state.snapshot() if state is not None else None
