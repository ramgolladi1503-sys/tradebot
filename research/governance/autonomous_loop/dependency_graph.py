from __future__ import annotations

from collections.abc import Mapping

from .task_state_machine import TaskState, is_valid_terminal


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


def dependencies_satisfied(task: dict, tasks: Mapping[str, dict]) -> bool:
    for dep_id in task.get("depends_on", []):
        dep = tasks[dep_id]
        state = TaskState(dep["status"])
        if not is_valid_terminal(state):
            return False
    return True


def eligible_task_ids(tasks: Mapping[str, dict]) -> list[str]:
    validate_dependencies(tasks)
    eligible: list[str] = []
    for task_id, task in tasks.items():
        if TaskState(task["status"]) not in {TaskState.PENDING, TaskState.REPAIR_REQUIRED}:
            continue
        if dependencies_satisfied(task, tasks):
            eligible.append(task_id)
    return sorted(eligible, key=_task_sort_key)


def _task_sort_key(task_id: str) -> tuple[int, str]:
    if task_id.startswith("T") and task_id[1:].isdigit():
        return (int(task_id[1:]), task_id)
    return (10**9, task_id)
