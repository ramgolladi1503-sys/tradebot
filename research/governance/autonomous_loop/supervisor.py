from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import re

import yaml

from .dependency_graph import build_dependencies_satisfied, build_eligible_task_ids, eligible_task_ids, validate_dependencies
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

    def next_build_eligible_task(self) -> str | None:
        """Select the next implementation task without weakening certification."""

        candidates = build_eligible_task_ids(self.tasks)
        if not candidates:
            return None
        return min(candidates, key=lambda task_id: (self.tasks[task_id].get("priority", 1000), _task_number(task_id)))

    def transition(self, task_id: str, target: TaskState | str) -> None:
        task = self._task(task_id)
        current = TaskState(task["status"])
        target_state = TaskState(target)
        assert_transition(current, target_state)
        if target_state == TaskState.IMPLEMENTATION_VALID and not build_dependencies_satisfied(task, self.tasks):
            raise RegistryError("cannot mark implementation valid before build-eligible prerequisites")
        if target_state == TaskState.NO_STRUCTURAL_EDGE_FOUND:
            exit_gates = {str(gate) for gate in task.get("exit_gates", [])}
            if not any("NO_EDGE" in gate or "NO_STRUCTURAL_EDGE_FOUND" in gate for gate in exit_gates):
                raise RegistryError("NO_STRUCTURAL_EDGE_FOUND is not a declared terminal outcome for this task")
        if target_state == TaskState.SEALED:
            self._assert_sealable(task)
        task["status"] = target_state.value

    def record_prepared_artifacts(self, task_id: str, *, prepared_candidate_sha: str, artifacts: list[str]) -> None:
        """Record downstream readiness without changing the authoritative task state."""
        task = self._task(task_id)
        if not re.fullmatch(r"[0-9a-f]{40}", prepared_candidate_sha):
            raise RegistryError("prepared_candidate_sha must be an exact 40-hex Git SHA")
        task.setdefault("evidence", {})["prepared_candidate_sha"] = prepared_candidate_sha
        task["evidence"]["implementation_artifacts_ready"] = list(artifacts)

    def create_dynamic_task(self, task: dict) -> None:
        """Add a governed T36+ task and make its declared blockers real dependencies.

        A task's `blocks` field is not documentation-only. If T36 says it blocks T02,
        T02 must depend on T36 before the registry update is accepted. The update is
        built on a copy and committed to supervisor state only after complete graph
        validation, so a malformed dynamic task cannot partially mutate orchestration.
        """

        validate_dynamic_task(task)
        task_id = task["task_id"]
        if task_id in self.tasks:
            raise RegistryError(f"task already exists: {task_id}")
        expected = self.next_dynamic_task_id()
        if task_id != expected:
            raise RegistryError(f"dynamic task ids are monotonic; expected {expected}, got {task_id}")

        existing_ids = set(self.tasks)
        unknown_dependencies = [dep for dep in task.get("depends_on", []) if dep not in existing_ids]
        unknown_blockers = [blocked for blocked in task.get("blocks", []) if blocked not in existing_ids]
        if unknown_dependencies:
            raise RegistryError(f"dynamic task depends on unknown tasks: {unknown_dependencies}")
        if unknown_blockers:
            raise RegistryError(f"dynamic task blocks unknown tasks: {unknown_blockers}")

        proposed = deepcopy(self.tasks)
        proposed[task_id] = deepcopy(task)
        for blocked_id in task.get("blocks", []):
            deps = proposed[blocked_id].setdefault("depends_on", [])
            if task_id not in deps:
                deps.append(task_id)

        validate_dependencies(proposed)
        self.registry["tasks"] = proposed
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
        candidate_sha = evidence.get("candidate_sha")
        if not isinstance(candidate_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
            raise RegistryError("cannot seal; candidate_sha must be an exact 40-hex Git SHA")

        required = ["focused", "adversarial", "integration", "regression"]
        if task.get("independent_verification", {}).get("required", True):
            required.append("independent_verification")
        if task.get("ci", {}).get("required", True):
            required.append("ci")

        missing = [name for name in required if not evidence.get(name)]
        if missing:
            raise RegistryError(f"cannot seal; missing evidence: {missing}")

        for name in required:
            gate = evidence[name]
            if not isinstance(gate, dict):
                raise RegistryError(f"cannot seal; {name} evidence must be SHA-bound structured evidence")
            if gate.get("status") != "PASS":
                raise RegistryError(f"cannot seal; {name} evidence is not PASS")
            if gate.get("candidate_sha") != candidate_sha:
                raise RegistryError(f"cannot seal; {name} evidence is not bound to candidate_sha")


def _task_number(task_id: str) -> int:
    if task_id.startswith("T") and task_id[1:].isdigit():
        return int(task_id[1:])
    return 10**9
