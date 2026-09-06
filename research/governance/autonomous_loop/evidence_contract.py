from __future__ import annotations

from dataclasses import dataclass


REQUIRED_TASK_FIELDS = {
    "task_id",
    "title",
    "architecture_version",
    "status",
    "depends_on",
    "blocks",
    "objective",
    "allowed_scope",
    "prohibited_scope",
    "required_tests",
    "independent_verification",
    "ci",
    "exit_gates",
    "stop_conditions",
    "evidence_paths",
}

DYNAMIC_REASON_CODES = {
    "NEW_PREREQUISITE",
    "NEW_INTEGRATION_SEAM",
    "NEW_SAFETY_GAP",
    "NEW_GOVERNANCE_GAP",
    "NEW_DATA_DEPENDENCY",
    "NEW_OBSERVABILITY_REQUIREMENT",
    "NEW_TEST_ISOLATION_REQUIREMENT",
    "INDEPENDENT_REVIEW_FINDING",
    "END_TO_END_GAP",
    "REGRESSION_GAP",
    "LIVE_VALIDATION_GAP",
    "MIGRATION_REQUIREMENT",
    "COMPATIBILITY_REQUIREMENT",
}


@dataclass(frozen=True)
class SafetyBoundary:
    broker_write_authority: bool = False
    order_authority: bool = False
    paper_authorized: bool = False
    live_authorized: bool = False

    def validate_fail_closed(self) -> None:
        if any((self.broker_write_authority, self.order_authority, self.paper_authorized, self.live_authorized)):
            raise ValueError("autonomous loop may not acquire broker/order/paper/live authority")


def validate_task_shape(task: dict) -> None:
    missing = sorted(REQUIRED_TASK_FIELDS - set(task))
    if missing:
        raise ValueError(f"task missing required fields: {missing}")
    if task["task_id"].startswith("T") and not task["task_id"][1:].isdigit():
        raise ValueError(f"invalid task id {task['task_id']}")
    if not isinstance(task["depends_on"], list) or not isinstance(task["blocks"], list):
        raise ValueError("depends_on and blocks must be lists")


def validate_dynamic_task(task: dict) -> None:
    validate_task_shape(task)
    number = int(task["task_id"][1:])
    if number < 36:
        raise ValueError("dynamic tasks must begin at T36")
    if task.get("reason_code") not in DYNAMIC_REASON_CODES:
        raise ValueError("dynamic task reason_code is missing or ungoverned")
    required = {
        "created_from",
        "reason",
        "required_guarantee",
        "change_budget_required",
        "rationale",
    }
    missing = sorted(required - set(task))
    if missing:
        raise ValueError(f"dynamic task missing governance fields: {missing}")
    if task["change_budget_required"] is not True:
        raise ValueError("dynamic task must protect an existing locked guarantee")
    rationale = task["rationale"]
    questions = {
        "evidence_exposed_need",
        "why_current_task_cannot_absorb",
        "protects_or_enables",
        "consequence_of_skipping",
        "dependencies_and_blocks",
        "why_not_scope_drift",
    }
    missing_rationale = sorted(questions - set(rationale))
    if missing_rationale:
        raise ValueError(f"dynamic task rationale incomplete: {missing_rationale}")
