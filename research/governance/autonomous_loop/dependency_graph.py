from __future__ import annotations

from collections.abc import Mapping

from .task_state_machine import TaskState


class DependencyError(ValueError):
    pass


def validate_dependencies(tasks: Mapping[str, dict]) -> None:
    ids = set(tasks)
    for task_id, task in tasks.items():
        for dep in task.get("depends_on", []):
            if dep not in ids:
                raise DependencyError(f"{task_id} depends on unknown task {dep}")
            if dep == task_id:
                raise DependencyError(f"{task_id} cannot depend on itself")
        for blocked in task.get("blocks", []):
            if blocked not in ids:
                raise DependencyError(f"{task_id} blocks unknown task {blocked}")
            if blocked == task_id:
                raise DependencyError(f"{task_id} cannot block itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise DependencyError(f"dependency cycle includes {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dep in tasks[task_id].get("depends_on", []):
            visit(dep)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in sorted(tasks):
        visit(task_id)


def _declared_terminal_satisfies_dependency(task: dict) -> bool:
    """Return whether this task's current terminal outcome legally releases dependents.

    SEALED is always completion. Honest research outcomes such as NO_STRUCTURAL_EDGE_FOUND
    or INVALIDATED release dependents only when the task's frozen exit gate explicitly
    declares that outcome. A generic INVALIDATED/SUPERSEDED state must never become an
    implicit PASS for downstream work.
    """

    state = TaskState(task["status"])
    if state == TaskState.SEALED:
        return True

    exit_gates = {str(gate) for gate in task.get("exit_gates", [])}
    if state == TaskState.NO_STRUCTURAL_EDGE_FOUND:
        return any("NO_EDGE" in gate or "NO_STRUCTURAL_EDGE_FOUND" in gate for gate in exit_gates)
    if state == TaskState.INVALIDATED:
        return any("INVALIDATED" in gate for gate in exit_gates)

    # SUPERSEDED is intentionally fail-closed until an explicit successor binding is
    # implemented and independently validated. Blocked/repair/in-progress states also
    # never satisfy dependencies.
    return False


def dependencies_satisfied(task: dict, tasks: Mapping[str, dict]) -> bool:
    for dep_id in task.get("depends_on", []):
        if not _declared_terminal_satisfies_dependency(tasks[dep_id]):
            return False
    return True


def _build_state_satisfies_dependency(task: dict) -> bool:
    """Return whether a predecessor has reached its declared build gate.

    Build eligibility is intentionally weaker than certification eligibility.  It
    allows a later task to be implemented against an upstream interface while
    keeping checkpoint sealing dependent on the strict terminal rules above.
    """

    state = TaskState(task["status"])
    if state in {
        TaskState.IMPLEMENTATION_VALID,
        TaskState.ADVERSARIAL_VALID,
        TaskState.INTEGRATION_VALID,
        TaskState.REGRESSION_VALID,
        TaskState.INDEPENDENTLY_VERIFIED,
        TaskState.CI_GREEN,
        TaskState.SEALED,
    }:
        return True

    # Honest research exits can release implementation of a dependent task only
    # when the predecessor explicitly declares that exit gate.
    exit_gates = {str(gate) for gate in task.get("exit_gates", [])}
    if state == TaskState.NO_STRUCTURAL_EDGE_FOUND:
        return any("NO_EDGE" in gate or "NO_STRUCTURAL_EDGE_FOUND" in gate for gate in exit_gates)
    if state == TaskState.INVALIDATED:
        return any("INVALIDATED" in gate for gate in exit_gates)
    return False


def build_dependencies_satisfied(task: dict, tasks: Mapping[str, dict]) -> bool:
    """Check provisional implementation dependencies, never certification gates."""

    return all(_build_state_satisfies_dependency(tasks[dep_id]) for dep_id in task.get("depends_on", []))


def eligible_task_ids(tasks: Mapping[str, dict]) -> list[str]:
    validate_dependencies(tasks)
    eligible: list[str] = []
    for task_id, task in tasks.items():
        if TaskState(task["status"]) not in {TaskState.PENDING, TaskState.REPAIR_REQUIRED}:
            continue
        if dependencies_satisfied(task, tasks):
            eligible.append(task_id)
    return sorted(eligible, key=_task_sort_key)


def build_eligible_task_ids(tasks: Mapping[str, dict]) -> list[str]:
    """Return PENDING/REPAIR_REQUIRED tasks eligible for implementation work."""

    validate_dependencies(tasks)
    eligible: list[str] = []
    for task_id, task in tasks.items():
        if TaskState(task["status"]) not in {TaskState.PENDING, TaskState.REPAIR_REQUIRED}:
            continue
        if build_dependencies_satisfied(task, tasks):
            eligible.append(task_id)
    return sorted(eligible, key=_task_sort_key)


def _task_sort_key(task_id: str) -> tuple[int, str]:
    if task_id.startswith("T") and task_id[1:].isdigit():
        return (int(task_id[1:]), task_id)
    return (10**9, task_id)
