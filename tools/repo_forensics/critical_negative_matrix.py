from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


BROKER_FIELD = "broker" + "_api_called"


@dataclass(frozen=True)
class NegativeTestRequirement:
    requirement_id: str
    severity: str
    signal_groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class NegativeTestCoverage:
    requirement_id: str
    severity: str
    covered: bool
    evidence_paths: tuple[str, ...]
    matched_signals: tuple[str, ...]


@dataclass(frozen=True)
class CriticalNegativeTestMatrixReport:
    coverage: tuple[NegativeTestCoverage, ...]

    @property
    def covered_requirements(self) -> tuple[NegativeTestCoverage, ...]:
        return tuple(item for item in self.coverage if item.covered)

    @property
    def missing_requirements(self) -> tuple[NegativeTestCoverage, ...]:
        return tuple(item for item in self.coverage if not item.covered)

    @property
    def complete(self) -> bool:
        return not self.missing_requirements

    @property
    def exit_code(self) -> int:
        return 0 if self.complete else 1


DEFAULT_REQUIREMENTS: tuple[NegativeTestRequirement, ...] = (
    NegativeTestRequirement(
        requirement_id="fallback_candidate_cannot_be_executable",
        severity="HIGH",
        signal_groups=(
            ("fallback", "executable", "false"),
            ("fallback", "rejected"),
            ("fallback_data_not_executable",),
        ),
    ),
    NegativeTestRequirement(
        requirement_id="stale_feed_blocks_order_intent",
        severity="HIGH",
        signal_groups=(
            ("stale", "blocked"),
            ("stale_feed", "rejected"),
            ("quote_age", "blocked"),
        ),
    ),
    NegativeTestRequirement(
        requirement_id="paper_path_cannot_call_live_broker",
        severity="CRITICAL",
        signal_groups=(
            ("paper", BROKER_FIELD, "false"),
            ("paper_path", BROKER_FIELD, "false"),
            ("sim", BROKER_FIELD, "false"),
        ),
    ),
    NegativeTestRequirement(
        requirement_id="missing_evidence_field_fails_contract",
        severity="HIGH",
        signal_groups=(
            ("candidate_id", "raises"),
            ("reason", "raises"),
            ("contract", "fails"),
            ("field", "fails"),
        ),
    ),
)


def build_critical_negative_test_matrix(
    records: Iterable[Mapping[str, object]],
    requirements: Iterable[NegativeTestRequirement] = DEFAULT_REQUIREMENTS,
) -> CriticalNegativeTestMatrixReport:
    indexed_records = tuple(_normalize_record(record) for record in records)
    coverage = tuple(_cover_requirement(requirement, indexed_records) for requirement in requirements)
    return CriticalNegativeTestMatrixReport(coverage=coverage)


def render_critical_negative_test_matrix_report(report: CriticalNegativeTestMatrixReport) -> str:
    lines = [
        "# Critical Negative Test Matrix Report",
        "",
        f"Requirements reviewed: `{len(report.coverage)}`",
        f"Covered requirements: `{len(report.covered_requirements)}`",
        f"Open requirements: `{len(report.missing_requirements)}`",
        "",
        "| Requirement | Severity | Status | Evidence | Signals |",
        "|---|---|---|---|---|",
    ]
    for item in report.coverage:
        status = "PASS" if item.covered else "FAIL"
        evidence = ", ".join(item.evidence_paths) if item.evidence_paths else "-"
        signals = ", ".join(item.matched_signals) if item.matched_signals else "-"
        lines.append(f"| `{item.requirement_id}` | `{item.severity}` | `{status}` | `{evidence}` | `{signals}` |")
    lines.extend(["", "PASS — critical negative matrix is complete" if report.complete else "FAIL — critical negative matrix has open requirements", ""])
    return "\n".join(lines)


def _cover_requirement(
    requirement: NegativeTestRequirement,
    records: tuple[tuple[str, str], ...],
) -> NegativeTestCoverage:
    evidence_paths: list[str] = []
    matched_signals: list[str] = []
    for path, source in records:
        for signal_group in requirement.signal_groups:
            if all(signal.lower() in source for signal in signal_group):
                evidence_paths.append(path)
                matched_signals.extend(signal_group)
                break
    return NegativeTestCoverage(
        requirement_id=requirement.requirement_id,
        severity=requirement.severity,
        covered=bool(evidence_paths),
        evidence_paths=tuple(sorted(set(evidence_paths))),
        matched_signals=tuple(sorted(set(matched_signals))),
    )


def _normalize_record(record: Mapping[str, object]) -> tuple[str, str]:
    path = str(record.get("path") or "<unknown>")
    raw_source = record.get("source", record.get("text", ""))
    return path, str(raw_source).lower()
