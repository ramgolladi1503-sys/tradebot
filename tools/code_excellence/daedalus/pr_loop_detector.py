from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable


PASS = "PASS"
WARN = "WARN"
BLOCK = "BLOCK"

_CODE_SUFFIXES = {".py", ".sh", ".yaml", ".yml", ".toml"}
_DOC_SUFFIXES = {".md", ".txt", ".rst"}
_VAGUE_MARKERS = ("later", "tbd", "todo", "follow up", "follow-up", "future", "eventually", "next steps")
_BROAD_MARKERS = ("roadmap", "series", "many prs", "multiple prs", "long chain", "phase")


@dataclass(frozen=True)
class PRLoopInput:
    changed_files: tuple[str, ...]
    claims_fix_blocker: bool
    documentation_scoped: bool = False
    blocker_count_before: int | None = None
    blocker_count_after: int | None = None
    done_means: tuple[str, ...] = field(default_factory=tuple)
    acceptance_proof: tuple[str, ...] = field(default_factory=tuple)
    next_steps: tuple[str, ...] = field(default_factory=tuple)
    current_scope_reduced: bool = False


@dataclass(frozen=True)
class PRLoopReport:
    verdict: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    risks: tuple[str, ...]
    documentation_only: bool
    blocker_reduced: bool

    @property
    def allowed(self) -> bool:
        return self.verdict != BLOCK


def detect_pr_loop_risk(source: PRLoopInput) -> PRLoopReport:
    changed_files = tuple(_ordered_unique(source.changed_files))
    documentation_only = bool(changed_files) and all(_is_documentation_path(path) for path in changed_files)
    code_changed = any(_is_code_path(path) for path in changed_files)
    tests_changed = any(path.startswith("tests/") or "/tests/" in path for path in changed_files)
    blocker_reduced = _blocker_reduced(source)

    blockers: list[str] = []
    warnings: list[str] = []
    risks: list[str] = []

    if not changed_files:
        blockers.append("changed_files_absent")
    if code_changed and not tests_changed:
        blockers.append("code_change_without_tests")
    if source.claims_fix_blocker and not blocker_reduced and not source.current_scope_reduced:
        blockers.append("blocker_not_reduced")
    if not source.done_means:
        blockers.append("done_means_absent")
    if not source.acceptance_proof:
        blockers.append("acceptance_proof_absent")
    if documentation_only and not source.documentation_scoped and source.claims_fix_blocker:
        blockers.append("roadmap_only_claims_engineering_progress")

    if _has_vague_next_steps(source.next_steps):
        warnings.append("vague_next_steps")
    if _has_broad_follow_up_chain(source.next_steps):
        warnings.append("broad_follow_up_chain")
    if source.next_steps and not blocker_reduced and not source.current_scope_reduced:
        if source.claims_fix_blocker or code_changed:
            blockers.append("follow_up_without_current_scope_reduction")
        else:
            warnings.append("follow_up_without_current_scope_reduction")

    if documentation_only and source.documentation_scoped and source.done_means and source.acceptance_proof and not blockers:
        risks.append("documentation_only_explicit")
    if blockers:
        verdict = BLOCK
    elif warnings:
        verdict = WARN
    else:
        verdict = PASS

    return PRLoopReport(
        verdict=verdict,
        blockers=tuple(_ordered_unique(blockers)),
        warnings=tuple(_ordered_unique(warnings)),
        risks=tuple(_ordered_unique(risks)),
        documentation_only=documentation_only,
        blocker_reduced=blocker_reduced,
    )


def _blocker_reduced(source: PRLoopInput) -> bool:
    if source.blocker_count_before is None or source.blocker_count_after is None:
        return source.current_scope_reduced
    return source.blocker_count_after < source.blocker_count_before


def _is_documentation_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    suffix = PurePosixPath(normalized).suffix
    return normalized.startswith("docs/") or suffix in _DOC_SUFFIXES


def _is_code_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("tests/") or _is_documentation_path(normalized):
        return False
    return PurePosixPath(normalized).suffix in _CODE_SUFFIXES


def _has_vague_next_steps(next_steps: tuple[str, ...]) -> bool:
    return any(marker in step.lower() for step in next_steps for marker in _VAGUE_MARKERS)


def _has_broad_follow_up_chain(next_steps: tuple[str, ...]) -> bool:
    return len(next_steps) > 3 or any(marker in step.lower() for step in next_steps for marker in _BROAD_MARKERS)


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
