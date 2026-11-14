"""Program-level release policy for the autonomous-loop authority.

This module is execution-isolated.  It only decides whether the governed research
program is eligible to be considered for merge to ``main``.  It does not perform
or authorize a merge.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class ProgramReleaseDecision:
    eligible: bool
    reason: str
    hold_task_id: str
    missing_tasks: tuple[str, ...] = ()
    unsealed_tasks: tuple[str, ...] = ()


def load_release_policy(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PROGRAM_RELEASE_POLICY_INVALID")
    return payload


def _task_number(task_id: str) -> int:
    text = str(task_id or "").strip().upper()
    if len(text) < 2 or not text.startswith("T") or not text[1:].isdigit():
        raise ValueError(f"INVALID_TASK_ID:{task_id}")
    return int(text[1:])


def evaluate_program_release(
    *,
    registry: Mapping[str, Any],
    policy: Mapping[str, Any],
    framework_certified: bool,
    exact_sha_independently_verified: bool,
    ci_green: bool,
    unresolved_major_critical: int = 0,
    mandatory_unknowns: int = 0,
) -> ProgramReleaseDecision:
    """Return a fail-closed release decision without performing any merge.

    The hold task must already exist through the governed dynamic-task mechanism.
    Merely setting a numeric threshold does not create T36/T37 or bypass their
    rationale/evidence requirements.
    """

    hold_task_id = str(policy.get("merge_hold_through_task_id") or "").strip().upper()
    hold_number = _task_number(hold_task_id)
    tasks = registry.get("tasks") if isinstance(registry, Mapping) else None
    if not isinstance(tasks, Mapping):
        return ProgramReleaseDecision(False, "TASK_REGISTRY_MISSING", hold_task_id)

    if bool(policy.get("require_framework_exact_sha_certification", True)) and not framework_certified:
        return ProgramReleaseDecision(False, "FRAMEWORK_NOT_CERTIFIED", hold_task_id)
    if bool(policy.get("require_program_exact_sha_independent_verification", True)) and not exact_sha_independently_verified:
        return ProgramReleaseDecision(False, "PROGRAM_INDEPENDENT_VERIFICATION_MISSING", hold_task_id)
    if bool(policy.get("require_program_ci_green", True)) and not ci_green:
        return ProgramReleaseDecision(False, "PROGRAM_CI_NOT_GREEN", hold_task_id)
    if bool(policy.get("require_zero_unresolved_major_critical", True)) and int(unresolved_major_critical) != 0:
        return ProgramReleaseDecision(False, "UNRESOLVED_MAJOR_CRITICAL", hold_task_id)
    if bool(policy.get("require_zero_mandatory_unknowns", True)) and int(mandatory_unknowns) != 0:
        return ProgramReleaseDecision(False, "MANDATORY_UNKNOWNS_REMAIN", hold_task_id)

    expected = tuple(f"T{number:02d}" for number in range(1, hold_number + 1))
    missing = tuple(task_id for task_id in expected if task_id not in tasks)
    if missing:
        return ProgramReleaseDecision(
            False,
            "HOLD_RANGE_TASKS_NOT_YET_GOVERNED",
            hold_task_id,
            missing_tasks=missing,
        )

    unsealed = tuple(
        task_id
        for task_id in expected
        if str((tasks.get(task_id) or {}).get("status") or "").strip().upper() != "SEALED"
    )
    if bool(policy.get("require_all_tasks_through_hold_sealed", True)) and unsealed:
        return ProgramReleaseDecision(
            False,
            "TASKS_THROUGH_HOLD_NOT_SEALED",
            hold_task_id,
            unsealed_tasks=unsealed,
        )

    if bool(policy.get("main_merge_authorized", False)):
        return ProgramReleaseDecision(True, "PROGRAM_RELEASE_ELIGIBLE", hold_task_id)

    return ProgramReleaseDecision(False, "HUMAN_MAIN_MERGE_AUTHORITY_REQUIRED", hold_task_id)
