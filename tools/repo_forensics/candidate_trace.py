from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


STAGE_GENERATED = "candidate_generated"
STAGE_FINALIZED = "candidate_finalized"
STAGE_SCORED = "scored"
STAGE_RANKED = "ranked"
STAGE_DATA_QUALITY = "data_quality_checked"
STAGE_GATEKEEPER = "gatekeeper_checked"
STAGE_RISK = "risk_evaluated"
STAGE_FINAL_DECISION = "final_decision"
STAGE_EVIDENCE_OUTPUT = "evidence_output"

REQUIRED_CANDIDATE_STAGES = (
    STAGE_GENERATED,
    STAGE_FINALIZED,
    STAGE_SCORED,
    STAGE_RANKED,
    STAGE_DATA_QUALITY,
    STAGE_GATEKEEPER,
    STAGE_RISK,
    STAGE_FINAL_DECISION,
    STAGE_EVIDENCE_OUTPUT,
)

_STAGE_ALIASES = {
    "candidate_generation": STAGE_GENERATED,
    "candidate_generated": STAGE_GENERATED,
    "generated": STAGE_GENERATED,
    "candidate_finalization": STAGE_FINALIZED,
    "candidate_finalized": STAGE_FINALIZED,
    "finalized": STAGE_FINALIZED,
    "opportunity_scoring": STAGE_SCORED,
    "score": STAGE_SCORED,
    "scored": STAGE_SCORED,
    "trade_scoring": STAGE_SCORED,
    "ranking": STAGE_RANKED,
    "ranked": STAGE_RANKED,
    "data_quality_gate": STAGE_DATA_QUALITY,
    "data_quality_checked": STAGE_DATA_QUALITY,
    "quality_gate": STAGE_DATA_QUALITY,
    "no_trade_or_gatekeeper": STAGE_GATEKEEPER,
    "gatekeeper": STAGE_GATEKEEPER,
    "gatekeeper_checked": STAGE_GATEKEEPER,
    "risk_evaluation": STAGE_RISK,
    "risk_evaluated": STAGE_RISK,
    "risk_result": STAGE_RISK,
    "decision": STAGE_FINAL_DECISION,
    "final_decision": STAGE_FINAL_DECISION,
    "review_queue_or_evidence": STAGE_EVIDENCE_OUTPUT,
    "evidence_output": STAGE_EVIDENCE_OUTPUT,
    "evidence_written": STAGE_EVIDENCE_OUTPUT,
}


@dataclass(frozen=True)
class CandidateTraceFinding:
    candidate_id: str | None
    severity: str
    finding_type: str
    evidence: str


@dataclass(frozen=True)
class CandidateLifecycleTrace:
    candidate_id: str
    stages_present: tuple[str, ...]
    missing_stages: tuple[str, ...]
    findings: tuple[CandidateTraceFinding, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        return not self.missing_stages and not any(item.severity == "HIGH" for item in self.findings)


@dataclass(frozen=True)
class CandidateLifecycleTraceReport:
    traces: tuple[CandidateLifecycleTrace, ...]
    orphan_findings: tuple[CandidateTraceFinding, ...] = field(default_factory=tuple)

    @property
    def failures(self) -> list[CandidateTraceFinding]:
        result: list[CandidateTraceFinding] = [item for item in self.orphan_findings if item.severity == "HIGH"]
        for trace in self.traces:
            result.extend([item for item in trace.findings if item.severity == "HIGH"])
        return result

    @property
    def unknowns(self) -> list[CandidateTraceFinding]:
        result: list[CandidateTraceFinding] = [item for item in self.orphan_findings if item.severity == "UNKNOWN"]
        for trace in self.traces:
            result.extend([item for item in trace.findings if item.severity == "UNKNOWN"])
        return result

    @property
    def warnings(self) -> list[CandidateTraceFinding]:
        result: list[CandidateTraceFinding] = [item for item in self.orphan_findings if item.severity == "MEDIUM"]
        for trace in self.traces:
            result.extend([item for item in trace.findings if item.severity == "MEDIUM"])
        return result


def build_candidate_lifecycle_trace_report(records: Iterable[Mapping[str, Any]]) -> CandidateLifecycleTraceReport:
    """Build deterministic candidate lifecycle trace proof from evidence records.

    The function is intentionally data-only. It does not import Tradebot runtime
    modules, call brokers, execute strategies, or read live state. Callers pass
    already-collected evidence records.
    """

    by_candidate: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    orphan_findings: list[CandidateTraceFinding] = []

    for index, record in enumerate(records):
        candidate_id = _text(record.get("candidate_id"))
        stage = normalize_candidate_stage(record.get("stage") or record.get("flow_step") or record.get("decision_stage") or record.get("decision"))
        if not candidate_id:
            orphan_findings.append(
                CandidateTraceFinding(
                    candidate_id=None,
                    severity="HIGH",
                    finding_type="candidate_id_missing",
                    evidence=f"record_index:{index}",
                )
            )
            continue
        if not stage:
            orphan_findings.append(
                CandidateTraceFinding(
                    candidate_id=candidate_id,
                    severity="UNKNOWN",
                    finding_type="candidate_stage_unknown",
                    evidence=f"record_index:{index}",
                )
            )
            continue
        by_candidate[candidate_id][stage] = record

    traces = tuple(_build_trace(candidate_id, stage_records) for candidate_id, stage_records in sorted(by_candidate.items()))
    return CandidateLifecycleTraceReport(traces=traces, orphan_findings=tuple(orphan_findings))


def normalize_candidate_stage(value: Any) -> str | None:
    text = _text(value).lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    return _STAGE_ALIASES.get(text)


def render_candidate_lifecycle_trace_report(report: CandidateLifecycleTraceReport) -> str:
    lines = [
        "# Candidate Lifecycle Trace Report",
        "",
        "## Scope Guard",
        "",
        "- Static/evidence-only validation.",
        "- No Tradebot runtime modules imported.",
        "- No broker calls.",
        "- No live order actions.",
        "",
        "## Summary",
        "",
        f"- Candidates reviewed: `{len(report.traces)}`",
        f"- Failures: `{len(report.failures)}`",
        f"- Unknowns: `{len(report.unknowns)}`",
        f"- Warnings: `{len(report.warnings)}`",
        "",
        "## Candidate Traces",
        "",
        "| Candidate | Complete | Stages Present | Missing Stages | Findings |",
        "|---|---|---|---|---:|",
    ]
    for trace in report.traces:
        lines.append(
            f"| `{trace.candidate_id}` | {str(trace.complete).lower()} | {', '.join(trace.stages_present) or 'none'} | "
            f"{', '.join(trace.missing_stages) or 'none'} | {len(trace.findings)} |"
        )
    if not report.traces:
        lines.append("| none | false | none | all | 0 |")
    lines.append("")
    findings = list(report.orphan_findings)
    for trace in report.traces:
        findings.extend(trace.findings)
    if findings:
        lines.append("## Findings")
        lines.append("")
        for finding in findings:
            candidate = finding.candidate_id or "unknown"
            lines.append(f"- {finding.severity}: `{candidate}` {finding.finding_type} evidence={finding.evidence}")
        lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if report.failures:
        lines.append("FAIL — candidate lifecycle trace has hard failures.")
    elif report.unknowns:
        lines.append("UNKNOWN — candidate lifecycle trace has unproven stages or ambiguous records.")
    elif report.warnings:
        lines.append("PASS_WITH_WARNINGS — candidate lifecycle trace passed with review warnings.")
    else:
        lines.append("PASS — candidate lifecycle trace is complete for supplied evidence records.")
    lines.append("")
    return "\n".join(lines)


def _build_trace(candidate_id: str, stage_records: Mapping[str, Mapping[str, Any]]) -> CandidateLifecycleTrace:
    stages_present = tuple(stage for stage in REQUIRED_CANDIDATE_STAGES if stage in stage_records)
    missing_stages = tuple(stage for stage in REQUIRED_CANDIDATE_STAGES if stage not in stage_records)
    findings: list[CandidateTraceFinding] = []

    if missing_stages:
        findings.append(
            CandidateTraceFinding(
                candidate_id=candidate_id,
                severity="UNKNOWN",
                finding_type="candidate_lifecycle_incomplete",
                evidence=f"missing_stages:{','.join(missing_stages)}",
            )
        )

    if STAGE_RANKED in stage_records and STAGE_FINAL_DECISION in stage_records:
        final_record = stage_records[STAGE_FINAL_DECISION]
        if not _truthy(final_record.get("rank_consumed")) and not _has_any(final_record, ("rank", "final_rank", "rank_reason")):
            findings.append(
                CandidateTraceFinding(
                    candidate_id=candidate_id,
                    severity="HIGH",
                    finding_type="ranking_not_consumed",
                    evidence="ranked_stage_present_but_final_decision_has_no_rank_reference",
                )
            )

    if STAGE_FINAL_DECISION in stage_records and STAGE_RISK not in stage_records:
        findings.append(
            CandidateTraceFinding(
                candidate_id=candidate_id,
                severity="HIGH",
                finding_type="risk_before_execution_not_proven",
                evidence="final_decision_present_without_risk_evaluated_stage",
            )
        )

    return CandidateLifecycleTrace(
        candidate_id=candidate_id,
        stages_present=stages_present,
        missing_stages=missing_stages,
        findings=tuple(findings),
    )


def _has_any(record: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_text(record.get(key)) for key in keys)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "on"}


def _text(value: Any) -> str:
    return str(value or "").strip()
