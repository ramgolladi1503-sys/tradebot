"""Fail-closed governed shutdown/seal contract."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ShutdownState(str, Enum):
    RUNNING = "RUNNING"
    SHUTDOWN_REQUESTED = "SHUTDOWN_REQUESTED"
    STOP_INGRESS = "STOP_INGRESS"
    QUIESCE_PRODUCERS = "QUIESCE_PRODUCERS"
    DRAINING = "DRAINING"
    COMMITTED = "COMMITTED"
    SEALED = "SEALED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ShutdownContract:
    state: ShutdownState = ShutdownState.RUNNING
    post_quiesce_enqueue_count: int = 0
    queues_zero: bool = False
    unfinished_tasks_zero: bool = False
    workers_joined: bool = False
    locks_released: bool = False
    row_reconciliation_pass: bool = False

    def request(self) -> "ShutdownContract":
        if self.state is not ShutdownState.RUNNING:
            raise ValueError("shutdown_request_invalid_state")
        return ShutdownContract(ShutdownState.SHUTDOWN_REQUESTED, **self._facts())

    def quiesce(self, *, post_quiesce_enqueue_count: int) -> "ShutdownContract":
        if self.state is not ShutdownState.SHUTDOWN_REQUESTED:
            raise ValueError("quiesce_invalid_state")
        if post_quiesce_enqueue_count != 0:
            return ShutdownContract(ShutdownState.FAILED, post_quiesce_enqueue_count=post_quiesce_enqueue_count, **self._facts(exclude="post_quiesce_enqueue_count"))
        return ShutdownContract(ShutdownState.QUIESCE_PRODUCERS, post_quiesce_enqueue_count=0, **self._facts(exclude="post_quiesce_enqueue_count"))

    def drain(self, *, queues_zero: bool, unfinished_tasks_zero: bool, workers_joined: bool, locks_released: bool, row_reconciliation_pass: bool) -> "ShutdownContract":
        if self.state is not ShutdownState.QUIESCE_PRODUCERS:
            raise ValueError("drain_invalid_state")
        facts = dict(queues_zero=queues_zero, unfinished_tasks_zero=unfinished_tasks_zero, workers_joined=workers_joined, locks_released=locks_released, row_reconciliation_pass=row_reconciliation_pass)
        return ShutdownContract(ShutdownState.DRAINING if all(facts.values()) else ShutdownState.FAILED, self.post_quiesce_enqueue_count, **facts)

    def seal(self) -> "ShutdownContract":
        if self.state is not ShutdownState.DRAINING:
            raise ValueError("seal_requires_complete_drain")
        return ShutdownContract(ShutdownState.SEALED, **self._facts())

    def _facts(self, exclude: str | None = None) -> dict[str, object]:
        facts = {"post_quiesce_enqueue_count": self.post_quiesce_enqueue_count, "queues_zero": self.queues_zero, "unfinished_tasks_zero": self.unfinished_tasks_zero, "workers_joined": self.workers_joined, "locks_released": self.locks_released, "row_reconciliation_pass": self.row_reconciliation_pass}
        if exclude: facts.pop(exclude, None)
        return facts
