from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from .analytics import SessionAnalytics
from .certification import CertificationResult
from .lineage import CandidateLineage
from .outcomes import HorizonOutcome
from .storage import atomic_write_json


def build_report_payload(
    *,
    certification: CertificationResult,
    lineage: Iterable[CandidateLineage],
    outcomes: Iterable[HorizonOutcome],
    analytics: SessionAnalytics | None = None,
) -> dict[str, Any]:
    lineage_rows = tuple(lineage)
    outcome_rows = tuple(outcomes)
    return {
        "report_version": "1.0",
        "session_id": certification.manifest.session_id,
        "certification": certification.to_dict(),
        "candidate_summary": {
            "candidate_count": len(lineage_rows),
            "blocked_candidates": sum(1 for row in lineage_rows if row.blockers),
            "approved_candidates": sum(1 for row in lineage_rows if row.approval_decision.upper() == "APPROVED"),
            "rejected_candidates": sum(1 for row in lineage_rows if row.approval_decision.upper() == "REJECTED"),
            "filled_candidates": sum(1 for row in lineage_rows if row.fill_count > 0),
            "blocker_counts": dict(sorted(Counter(reason for row in lineage_rows for reason in row.blockers).items())),
        },
        "outcome_summary": {
            "outcome_count": len(outcome_rows),
            "classification_counts": dict(sorted(Counter(row.classification for row in outcome_rows).items())),
            "unavailable_reason_counts": dict(
                sorted(Counter(reason for row in outcome_rows for reason in row.unavailable_reasons).items())
            ),
        },
        "candidate_lineage": [row.to_dict() for row in lineage_rows],
        "outcomes": [row.to_dict() for row in outcome_rows],
        "analytics": (analytics.to_dict() if analytics is not None else {
            "metrics": [],
            "required_metrics": [],
            "missing_required_metrics": [],
            "contract": {},
        }),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def render_markdown(payload: dict[str, Any]) -> str:
    certification = payload["certification"]
    manifest = certification["manifest"]
    candidate_summary = payload["candidate_summary"]
    outcome_summary = payload["outcome_summary"]
    lines = [
        "# Aixion Trade Intelligence Session Report",
        "",
        f"- Session: `{payload['session_id']}`",
        f"- Pipeline verdict: **{certification['verdict']}**",
        f"- Capture verdict: **{manifest['verdict']}**",
        f"- Replay hash: `{certification['replay_hash']}`",
        f"- Strategy edge certified: **{certification['strategy_edge_certified']}**",
        "",
        "## Evidence integrity",
        "",
        f"- Events: {manifest['event_count']}",
        f"- Unique events: {manifest['unique_event_count']}",
        f"- Duplicate IDs: {manifest['duplicate_event_ids']}",
        f"- Look-ahead violations: {manifest['lookahead_violations']}",
        f"- Producer sequence gaps: {len(manifest['producer_sequence_gaps'])}",
        f"- Coverage ratio: {_fmt(manifest['coverage_ratio'])}",
        f"- Reasons: {', '.join(manifest['reason_codes']) or 'none'}",
        "",
        "## Candidate funnel",
        "",
        f"- Candidates: {candidate_summary['candidate_count']}",
        f"- Blocked: {candidate_summary['blocked_candidates']}",
        f"- Approved: {candidate_summary['approved_candidates']}",
        f"- Rejected: {candidate_summary['rejected_candidates']}",
        f"- Filled: {candidate_summary['filled_candidates']}",
        "",
        "## Outcomes",
        "",
        f"- Outcome rows: {outcome_summary['outcome_count']}",
    ]
    for classification, count in outcome_summary["classification_counts"].items():
        lines.append(f"- {classification}: {count}")
    analytics = payload.get("analytics") or {}
    metrics = analytics.get("metrics") or []
    lines.extend(["", "## Deterministic analytics", ""])
    if metrics:
        for metric in metrics:
            lines.append(f"- {metric['metric_id']}: {metric['status']}" + (f" — {metric['reason']}" if metric.get('reason') else ""))
    else:
        lines.append("- No analytics metrics were produced.")
    lines.extend(
        [
            "",
            "## Certification boundary",
            "",
            certification["strategy_edge_reason"],
            "",
            "The report is derived from canonical event evidence. No LLM-generated numeric values are used.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(output_dir: str | Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = atomic_write_json(root / "session_report.json", payload)
    markdown_path = root / "session_report.md"
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, markdown_path
