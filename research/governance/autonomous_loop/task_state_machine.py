from __future__ import annotations

from enum import Enum


class TaskState(str, Enum):
    PENDING = "PENDING"
    SPEC_FROZEN = "SPEC_FROZEN"
    IMPLEMENTING = "IMPLEMENTING"
    IMPLEMENTATION_VALID = "IMPLEMENTATION_VALID"
    ADVERSARIAL_VALID = "ADVERSARIAL_VALID"
    INTEGRATION_VALID = "INTEGRATION_VALID"
    REGRESSION_VALID = "REGRESSION_VALID"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    CI_GREEN = "CI_GREEN"
    SEALED = "SEALED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    BLOCKED = "BLOCKED"
    INVALIDATED = "INVALIDATED"
    NO_STRUCTURAL_EDGE_FOUND = "NO_STRUCTURAL_EDGE_FOUND"
    BLOCKED_LIVE_WINDOW = "BLOCKED_LIVE_WINDOW"
    BLOCKED_DATA = "BLOCKED_DATA"
    BLOCKED_AUTH = "BLOCKED_AUTH"
    SUPERSEDED = "SUPERSEDED"


_PROGRESS = [
    TaskState.PENDING,
    TaskState.SPEC_FROZEN,
    TaskState.IMPLEMENTING,
    TaskState.IMPLEMENTATION_VALID,
    TaskState.ADVERSARIAL_VALID,
    TaskState.INTEGRATION_VALID,
    TaskState.REGRESSION_VALID,
    TaskState.INDEPENDENTLY_VERIFIED,
    TaskState.CI_GREEN,
    TaskState.SEALED,
]

_TERMINAL = {
    TaskState.SEALED,
    TaskState.INVALIDATED,
    TaskState.NO_STRUCTURAL_EDGE_FOUND,
    TaskState.SUPERSEDED,
}

_BLOCKED = {
    TaskState.BLOCKED,
    TaskState.BLOCKED_LIVE_WINDOW,
    TaskState.BLOCKED_DATA,
    TaskState.BLOCKED_AUTH,
}

_ALLOWED: dict[TaskState, set[TaskState]] = {state: set() for state in TaskState}
for current, nxt in zip(_PROGRESS, _PROGRESS[1:]):
    _ALLOWED[current].add(nxt)

for current in TaskState:
    if current not in _TERMINAL:
        _ALLOWED[current].update({TaskState.REPAIR_REQUIRED, TaskState.INVALIDATED})
        _ALLOWED[current].update(_BLOCKED)

_ALLOWED[TaskState.REPAIR_REQUIRED].update({TaskState.IMPLEMENTING, TaskState.INVALIDATED})
for blocked in _BLOCKED:
    _ALLOWED[blocked].update({TaskState.PENDING, TaskState.REPAIR_REQUIRED, TaskState.INVALIDATED})

# Research tasks can terminate honestly without a positive result, but only after
# their implementation/validation path has begun.
for current in {
    TaskState.IMPLEMENTATION_VALID,
    TaskState.ADVERSARIAL_VALID,
    TaskState.INTEGRATION_VALID,
    TaskState.REGRESSION_VALID,
    TaskState.INDEPENDENTLY_VERIFIED,
    TaskState.CI_GREEN,
}:
    _ALLOWED[current].add(TaskState.NO_STRUCTURAL_EDGE_FOUND)


def assert_transition(current: TaskState | str, target: TaskState | str) -> None:
    current_state = TaskState(current)
    target_state = TaskState(target)
    if target_state == current_state:
        return
    if target_state not in _ALLOWED[current_state]:
        raise ValueError(f"illegal task transition: {current_state.value} -> {target_state.value}")


def is_valid_terminal(state: TaskState | str) -> bool:
    return TaskState(state) in _TERMINAL
