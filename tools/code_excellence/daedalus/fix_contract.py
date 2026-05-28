from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


FIX_NOW = "FIX_NOW"
BACKLOG = "BACKLOG"
DEFER = "DEFER"
FALSE_POSITIVE = "FALSE_POSITIVE"
ACCEPTED_UNKNOWN = "ACCEPTED_UNKNOWN"
REFUSE = "REFUSE"
INCOMPLETE = "INCOMPLETE"

_ALLOWED_DECISIONS = {FIX_NOW, BACKLOG, DEFER, FALSE_POSITIVE, ACCEPTED_UNKNOWN}


@dataclass(frozen=True)
class DaedalusInput:
    root_cause: str | None
    confidence: str
    affected_files: tuple[str, ...]
    proposed_files: tuple[str, ...]
    tests_required: tuple[str, ...]
    negative_tests_required: tuple[str, ...]
    evidence_required: tuple[str, ...]
    proof: tuple[str, ...] = field(default_factory=tuple)
    decision: str = FIX_NOW
    patch_behavior: str = "minimal_scoped_patch"
    regression_risks: tuple[str, ...] = field(default_factory=tuple)
    done_means: tuple[str, ...] = field(default_factory=tuple)
    files_not_to_touch: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DaedalusFixContract:
    allowed: bool
    status: str
    reason: str
    root_cause: str
    decision: str
    files_to_change: tuple[str, ...]
    files_not_to_touch: tuple[str, ...]
    patch_behavior: str
    tests_required: tuple[str, ...]
    negative_tests_required: tuple[str, ...]
    evidence_required: tuple[str, ...]
    regression_risks: tuple[str, ...]
    done_means: tuple[str, ...]
    blockers: tuple[str, ...] = field(default_factory=tuple)


def generate_fix_contract(source: DaedalusInput) -> DaedalusFixContract:
    blockers = list(_base_blockers(source))
    proposed_files = tuple(_ordered_unique(source.proposed_files))
    allowed_scope = set(source.affected_files)
    unrelated = tuple(path for path in proposed_files if path not in allowed_scope)
    if unrelated:
        blockers.append("unrelated_file_change_blocked")
    if not source.negative_tests_required:
        blockers.append("negative_tests_required")
    if not source.tests_required:
        blockers.append("tests_required")
    if not source.evidence_required:
        blockers.append("evidence_required")
    if source.decision not in _ALLOWED_DECISIONS:
        blockers.append("invalid_decision")

    if blockers:
        return _blocked_contract(source, blockers, proposed_files)

    return DaedalusFixContract(
        allowed=True,
        status="READY",
        reason="scoped_fix_contract_ready",
        root_cause=str(source.root_cause),
        decision=source.decision,
        files_to_change=proposed_files,
        files_not_to_touch=_files_not_to_touch(source, proposed_files),
        patch_behavior=source.patch_behavior,
        tests_required=tuple(_ordered_unique(source.tests_required)),
        negative_tests_required=tuple(_ordered_unique(source.negative_tests_required)),
        evidence_required=tuple(_ordered_unique(source.evidence_required)),
        regression_risks=tuple(_ordered_unique(source.regression_risks)),
        done_means=tuple(_ordered_unique(source.done_means or ("contract_acceptance_met",))),
        blockers=(),
    )


def _base_blockers(source: DaedalusInput) -> tuple[str, ...]:
    blockers: list[str] = []
    if not source.root_cause or not str(source.root_cause).strip():
        blockers.append("root_cause_absent")
    if source.confidence == "UNKNOWN":
        blockers.append("root_cause_unknown")
    if not source.proof:
        blockers.append("proof_absent")
    if not source.affected_files:
        blockers.append("affected_files_absent")
    if not source.proposed_files:
        blockers.append("files_to_change_absent")
    return tuple(blockers)


def _blocked_contract(source: DaedalusInput, blockers: list[str], proposed_files: tuple[str, ...]) -> DaedalusFixContract:
    status = INCOMPLETE if blockers and set(blockers) <= {"negative_tests_required", "tests_required", "evidence_required"} else REFUSE
    return DaedalusFixContract(
        allowed=False,
        status=status,
        reason="fix_contract_blocked",
        root_cause=str(source.root_cause or "UNKNOWN"),
        decision=source.decision if source.decision in _ALLOWED_DECISIONS else ACCEPTED_UNKNOWN,
        files_to_change=proposed_files,
        files_not_to_touch=_files_not_to_touch(source, proposed_files),
        patch_behavior=source.patch_behavior,
        tests_required=tuple(_ordered_unique(source.tests_required)),
        negative_tests_required=tuple(_ordered_unique(source.negative_tests_required)),
        evidence_required=tuple(_ordered_unique(source.evidence_required)),
        regression_risks=tuple(_ordered_unique(source.regression_risks)),
        done_means=tuple(_ordered_unique(source.done_means)),
        blockers=tuple(_ordered_unique(blockers)),
    )


def _files_not_to_touch(source: DaedalusInput, proposed_files: tuple[str, ...]) -> tuple[str, ...]:
    protected = set(source.files_not_to_touch)
    protected.update(path for path in source.affected_files if path not in proposed_files)
    return tuple(_ordered_unique(protected))


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
