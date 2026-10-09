from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .roles import DeliveryRole
from .states import DeliveryState, INITIAL_STATE


class WorkItemType(str, Enum):
    EPIC = "EPIC"
    FEATURE = "FEATURE"
    STORY = "STORY"
    BUG = "BUG"
    TASK = "TASK"


class EvidenceType(str, Enum):
    SOURCE_VERIFICATION_EVIDENCE = "SOURCE_VERIFICATION_EVIDENCE"
    CORRECTNESS_VERIFICATION_EVIDENCE = "CORRECTNESS_VERIFICATION_EVIDENCE"
    ADVERSARIAL_VERIFICATION_EVIDENCE = "ADVERSARIAL_VERIFICATION_EVIDENCE"
    INDEPENDENT_EVIDENCE = "INDEPENDENT_EVIDENCE"
    REQUIREMENT_EVIDENCE = "REQUIREMENT_EVIDENCE"
    ARCHITECTURE_EVIDENCE = "ARCHITECTURE_EVIDENCE"
    DEV_TEST_EVIDENCE = "DEV_TEST_EVIDENCE"
    QA_EVIDENCE = "QA_EVIDENCE"
    DEFECT_EVIDENCE = "DEFECT_EVIDENCE"
    QA_RETEST_EVIDENCE = "QA_RETEST_EVIDENCE"
    SENIOR_QA_EVIDENCE = "SENIOR_QA_EVIDENCE"
    UAT_EVIDENCE = "UAT_EVIDENCE"
    PRODUCT_ACCEPTANCE_EVIDENCE = "PRODUCT_ACCEPTANCE_EVIDENCE"
    CI_EVIDENCE = "CI_EVIDENCE"
    RELEASE_EVIDENCE = "RELEASE_EVIDENCE"
    PRODUCTION_VERIFICATION_EVIDENCE = "PRODUCTION_VERIFICATION_EVIDENCE"


class EvidenceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DefectSeverity(str, Enum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


class DefectStatus(str, Enum):
    OPEN = "OPEN"
    FIX_IN_PROGRESS = "FIX_IN_PROGRESS"
    READY_FOR_RETEST = "READY_FOR_RETEST"
    RETEST_FAILED = "RETEST_FAILED"
    RETEST_PASSED = "RETEST_PASSED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class StateHistoryEntry:
    from_state: str
    to_state: str
    acting_role: str
    actor: str
    timestamp: str
    reason: str
    evidence_ids: tuple[str, ...]
    contract_hash: str
    previous_hash: str
    entry_hash: str


@dataclass(frozen=True)
class DefectHistoryEntry:
    defect_id: str
    from_status: str
    to_status: str
    acting_role: str
    actor: str
    timestamp: str
    reason: str
    evidence_ref: str
    regression_result: str
    previous_hash: str
    entry_hash: str


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    work_item_id: str
    evidence_type: EvidenceType
    role: DeliveryRole
    author: str
    timestamp: str
    status: EvidenceStatus
    summary: str
    references: tuple[str, ...] = ()
    content_hash: str = ""
    check_results: tuple[tuple[str, str], ...] = ()
    work_item_hash: str = ""
    sequence: int = 0
    previous_hash: str = ""


@dataclass(frozen=True)
class Defect:
    defect_id: str
    work_item_id: str
    severity: DefectSeverity
    title: str
    reproduction_steps: tuple[str, ...]
    expected_behavior: str
    actual_behavior: str
    evidence: tuple[str, ...]
    status: DefectStatus = DefectStatus.OPEN
    developer_fix_ref: str = ""
    qa_retest_ref: str = ""
    regression_result: str = ""


@dataclass(frozen=True)
class WorkItem:
    work_item_id: str
    type: WorkItemType
    parent_epic: str
    parent_feature: str
    title: str
    schema_version: int = 1
    current_state: DeliveryState = INITIAL_STATE
    priority: str = ""
    business_goal: str = ""
    current_behavior: str = ""
    expected_behavior: str = ""
    in_scope: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    safety_constraints: tuple[str, ...] = ()
    architecture_impact: str = ""
    allowed_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()
    expected_tests: tuple[str, ...] = ()
    qa_attack_plan: tuple[str, ...] = ()
    uat_criteria: tuple[str, ...] = ()
    release_gates: tuple[str, ...] = ()
    rollback_plan: str = ""
    evidence_refs: tuple[str, ...] = ()
    acting_role: str = ""
    state_history: tuple[StateHistoryEntry, ...] = ()
    defect_history: tuple[DefectHistoryEntry, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    defects: tuple[Defect, ...] = ()
    required_ci_checks: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)


WORK_ITEM_FIELDS = frozenset(WorkItem.__dataclass_fields__)
