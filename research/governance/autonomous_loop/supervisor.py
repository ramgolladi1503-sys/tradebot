from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .dependency_graph import eligible_task_ids, validate_dependencies
from .evidence_contract import SafetyBoundary, validate_dynamic_task, validate_task_shape
from .task_state_machine import TaskState, assert_transition


class RegistryError(ValueError):
    pass


class AutonomousLoopSupervisor:
    """Pure-governance supervisor.

    It mutates only in-memory/registry state supplied by the caller. It has no broker,
    order, paper, live, process-launch, shell, network, or credential authority.
    """

    def __init__(self, registry: dict[str, Any]) -> None:
        self.registry = deepcopy(registry)
        self.safety = SafetyBoundary(**self.registry.get("safety", {}))
        self.safety.validate_fail_closed()
        self._validate_registry()

    @classmethod
    def from_path(cls, path: str | Path) -> "AutonomousLoopSupervisor":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RegistryError("registry root must be a mapping")
        return cls(data)

    @property
    def tasks(self) -> dict[str, dict]:
        return self.registry["tasks"]

    def next_eligible_task(self) -> str | None:
        candidates = eligible_task_ids(self.tasks)
        if not candidates:
            return None
        # Critical-path/safety weighting can be encoded explicitly in registry priority.
        return min(candidates, key=lambda task_id: (self.tasks[task_id].get("priority", 1000), _task_number(task_id)))

    def transition(self, task_id: str, target: TaskState | str) -> None:
        task = self._task(task_id)
        current = TaskState(task["status"])
        target_state = TaskState(target)
        assert_transition(current, target_state)
        if target_state == TaskState.SEALED:
            self._assert_sealable(task)
        task["status"] = target_state.value

    def create_dynamic_task(self, task: dict) -> None:
        validate_dynamic_task(task)
        task_id = task["task_id"]
        if task_id in self.tasks:
            raise RegistryError(f"task already exists: {task_id}")
        expected = self.next_dynamic_task_id()
        if task_id != expected:
            raise RegistryError(f"dynamic task ids are monotonic; expected {expected}, got {task_id}")
        self.tasks[task_id] = deepcopy(task)
        self._validate_registry()

    def next_dynamic_task_id(self) -> str:
        numbers = [int(task_id[1:]) for task_id in self.tasks if task_id.startswith("T") and task_id[1:].isdigit()]
        return f"T{max([35, *numbers]) + 1:02d}"

    def dump(self) -> str:
        return yaml.safe_dump(self.registry, sort_keys=False, allow_unicode=True)

    def _task(self, task_id: str) -> dict:
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise RegistryError(f"unknown task: {task_id}") from exc

    def _validate_registry(self) -> None:
        if self.registry.get("schema_version") != 1:
            raise RegistryError("unsupported registry schema_version")
        tasks = self.registry.get("tasks")
        if not isinstance(tasks, dict) or not tasks:
            raise RegistryError("registry must contain non-empty tasks mapping")
        for task_id, task in tasks.items():
            if task.get("task_id") != task_id:
                raise RegistryError(f"task key/id mismatch: {task_id}")
            validate_task_shape(task)
            TaskState(task["status"])
        validate_dependencies(tasks)

    @staticmethod
    def _assert_sealable(task: dict) -> None:
        if task.get("mandatory_unknowns", 0) != 0:
            raise RegistryError("cannot seal with mandatory UNKNOWNs")
        if task.get("major_findings", 0) != 0 or task.get("critical_findings", 0) != 0:
            raise RegistryError("cannot seal with unresolved MAJOR/CRITICAL findings")
        evidence = task.get("evidence", {})
        required = ["candidate_sha", "focused", "adversarial", "integration", "regression"]
        if task.get("independent_verification", {}).get("required", True):
            required.append("independent_verification")
        if task.get("ci", {}).get("required", True):
            required.append("ci")
        missing = [name for name in required if not evidence.get(name)]
        if missing:
            raise RegistryError(f"cannot seal; missing evidence: {missing}")


def _task_number(task_id: str) -> int:
    if task_id.startswith("T") and task_id[1:].isdigit():
        return int(task_id[1:])
    return 10**9
