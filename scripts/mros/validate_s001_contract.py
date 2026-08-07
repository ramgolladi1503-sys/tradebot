#!/usr/bin/env python3
"""Deterministic, offline validator for the MROS S001 contract freeze.

This validator is intentionally narrow: it verifies the S001 governance contract
surface only. It performs no broker, network, market-data, strategy, runtime, or
scientific-certification work.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CONSTITUTION = ROOT / "research/constitution/RESEARCH_CONSTITUTION.md"
INTERFACE = ROOT / "research/evidence/sprints/S001/S001_INTERFACE_CONTRACT.md"
TRACE = ROOT / "research/evidence/sprints/S001/S001_ACCEPTANCE_TRACE.md"
STATE = ROOT / "research/program/MROS_PROGRAM_STATE.yaml"
REVIEW = ROOT / "research/evidence/sprints/S001/S001_INDEPENDENT_REVIEW.md"


class CheckFailure(Exception):
    pass


def read(path: Path) -> str:
    if not path.is_file():
        raise CheckFailure(f"missing required file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require(text: str, token: str, label: str) -> None:
    if token not in text:
        raise CheckFailure(f"{label}: missing token {token!r}")


def require_count(text: str, token: str, expected: int, label: str) -> None:
    actual = text.count(token)
    if actual != expected:
        raise CheckFailure(
            f"{label}: expected {expected} occurrence(s) of {token!r}; found {actual}"
        )


def main() -> int:
    checks: list[tuple[str, callable]] = []

    constitution = read(CONSTITUTION)
    interface = read(INTERFACE)
    trace = read(TRACE)
    state = read(STATE)
    review = read(REVIEW)

    for n in range(1, 11):
        rule = f"RC-{n:03d}"
        checks.append(
            (
                f"constitution contains {rule} exactly once",
                lambda rule=rule: require_count(constitution, f"### {rule} —", 1, rule),
            )
        )

    denominator_tokens = [
        "The denominator is part of the experiment contract, not a reporting convenience.",
        "eligible observations",
        "eligible trades/events",
        "reported metric denominators",
        "cannot be changed after observing outcomes",
        "preregistered before outcomes are inspected",
        "preserve the original denominator/result",
        "new exploratory analysis or new search family",
        "Silent removal of inconvenient trades",
    ]
    for token in denominator_tokens:
        checks.append(
            (
                f"RC-009 denominator protection: {token}",
                lambda token=token: require(constitution, token, "RC-009"),
            )
        )

    knowledge_classes = [
        "OBSERVED_FACT",
        "INFERENCE",
        "HYPOTHESIS",
        "SPECULATION",
    ]
    for token in knowledge_classes:
        checks.append(
            (f"controlled knowledge class {token}", lambda token=token: require(interface, token, "knowledge classes"))
        )

    verdicts = ["SUPPORTED", "REJECTED", "UNKNOWN", "INSUFFICIENT_EVIDENCE"]
    for token in verdicts:
        checks.append(
            (f"controlled verdict {token}", lambda token=token: require(interface, f"`{token}`", "verdicts"))
        )

    authority = [
        "Research / R",
        "Grade C",
        "Grade B",
        "Grade A",
        "Grade A+",
        "Rejected",
        "Unknown",
    ]
    for token in authority:
        checks.append(
            (f"authority grade {token}", lambda token=token: require(interface, f"`{token}`", "authority"))
        )

    statuses = ["PASS", "FAIL", "UNKNOWN", "INVALID_INPUT", "BLOCKED", "REVIEW_REQUIRED"]
    for token in statuses:
        checks.append(
            (f"controlled status {token}", lambda token=token: require(interface, f"`{token}`", "statuses"))
        )

    for n in range(1, 18):
        code = f"MROS-S001-E{n:03d}-"
        checks.append(
            (f"error code family E{n:03d}", lambda code=code: require(interface, code, "error contract"))
        )

    invariant_tokens = [
        "I-001 — Evidence-only promotion",
        "I-002 — No stage skipping",
        "I-003 — Independence is substantive",
        "I-004 — Unknown fails safe",
        "I-005 — Causal availability",
        "I-006 — Denominator immutability for confirmatory evidence",
        "I-007 — Post-hoc analyses remain distinct",
        "I-008 — Runtime cannot create research truth",
        "I-009 — No silent supersession",
        "I-010 — Invalid input cannot promote",
    ]
    for token in invariant_tokens:
        checks.append(
            (f"interface invariant {token.split(' — ')[0]}", lambda token=token: require(interface, token, "invariants"))
        )

    for n in range(1, 30):
        ac = f"S001-AC-{n:03d}"
        checks.append(
            (f"acceptance trace contains {ac}", lambda ac=ac: require(trace, ac, "acceptance trace"))
        )

    state_tokens = [
        "active_milestone: M1",
        "active_work_package: WP001",
        "active_sprint: S001",
        "active_sprint_status: REVIEW_REQUIRED",
        "M2: NOT_STARTED",
        "M9: NOT_STARTED",
        'runtime_authority: NONE',
    ]
    for token in state_tokens:
        checks.append(
            (f"program state remains pre-S002: {token}", lambda token=token: require(state, token, "program state"))
        )

    checks.extend(
        [
            (
                "original independent review is preserved",
                lambda: require(review, "S001_INDEPENDENT_REVIEW_REPAIR_REQUIRED", "review"),
            ),
            (
                "interface explicitly does not implement S002",
                lambda: require(interface, "does **not** implement S002", "scope"),
            ),
            (
                "interface explicitly blocks runtime authority",
                lambda: require(interface, "Operational authority: NONE", "runtime separation"),
            ),
            (
                "trace keeps independent re-review as blocker",
                lambda: require(trace, "BLOCKED_INDEPENDENT_REVIEW", "trace"),
            ),
        ]
    )

    failures: list[str] = []
    for label, check in checks:
        try:
            check()
            print(f"PASS | {label}")
        except CheckFailure as exc:
            failures.append(f"FAIL | {label} | {exc}")
            print(failures[-1])

    print(f"SUMMARY | checks={len(checks)} pass={len(checks)-len(failures)} fail={len(failures)}")

    if failures:
        print("S001_TARGETED_VALIDATION_FAIL")
        return 1

    print("S001_TARGETED_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
