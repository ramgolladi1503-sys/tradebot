from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.evidence_replay_report import (
    EvidenceReplayOptions,
    _as_rows,
    _evidence_root,
    _find_snapshots,
    _flatten_rows,
    _iter_candidate_like_rows,
    _read_json,
    _safe_float,
    generate_evidence_replay_report,
)

REQUIRED_CAPTURE_SECTIONS = (
    "feed",
    "freshness",
    "fallback",
    "candidate_funnel",
    "score_flattening",
    "final_no_trade_reasons",
)


@dataclass(frozen=True)
class RuntimeEvidenceCaptureOptions:
    today: date | None = None
    quote_age_mismatch_tolerance_sec: float = 5.0
    max_jsonl_lines_per_file: int = 5000
    score_flattening_tolerance: float = 0.000001


@dataclass(frozen=True)
class CaptureSection:
    name: str
    status: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeEvidenceCaptureGuardReport:
    source: str
    generated_at: str
    verdict: str
    required_sections: tuple[str, ...]
    sections: tuple[CaptureSection, ...]
    diagnosis_verdict: str
    diagnosis_totals: dict[str, Any]
    evidence_map: dict[str, str]
    snapshots: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "generated_at": self.generated_at,
            "verdict": self.verdict,
            "required_sections": list(self.required_sections),
            "sections": [section.to_dict() for section in self.sections],
            "diagnosis_verdict": self.diagnosis_verdict,
            "diagnosis_totals": dict(self.diagnosis_totals),
            "evidence_map": dict(self.evidence_map),
            "snapshots": list(self.snapshots),
            "mode": "EVIDENCE_REPLAY",
            "candidate_id": "EDGE-38-RUNTIME-EVIDENCE-CAPTURE-GUARD",
            "decision": self.verdict,
            "reason": self.diagnosis_verdict,
            "timestamp": self.generated_at,
            "is_order_action": False,
            "broker_api_called": False,
            "source_module": "core.runtime_evidence_capture_guard",
        }


@dataclass
class _SnapshotCapture:
    name: str
    feed_present: bool = False
    freshness_present: bool = False
    fallback_count: int = 0
    candidate_funnel: dict[str, Any] = field(default_factory=dict)
    score_flattening_rows: list[dict[str, Any]] = field(default_factory=list)
    final_no_trade_reasons: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "feed_present": self.feed_present,
            "freshness_present": self.freshness_present,
            "fallback_count": self.fallback_count,
            "candidate_funnel": dict(self.candidate_funnel),
            "score_flattening_rows": list(self.score_flattening_rows),
            "final_no_trade_reasons": dict(self.final_no_trade_reasons),
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _runtime_latest(snapshot_dir: Path, name: str) -> Any:
    return _read_json(snapshot_dir / "runtime_latest" / name)


def _snapshot_name(snapshot_dir: Path, root: Path) -> str:
    try:
        return str(snapshot_dir.relative_to(root))
    except ValueError:
        return snapshot_dir.name


def _iter_rows(snapshot_dir: Path, options: RuntimeEvidenceCaptureOptions) -> Iterator[dict[str, Any]]:
    replay_options = EvidenceReplayOptions(
        today=options.today,
        quote_age_mismatch_tolerance_sec=options.quote_age_mismatch_tolerance_sec,
        max_jsonl_lines_per_file=options.max_jsonl_lines_per_file,
    )
    yield from _iter_candidate_like_rows(snapshot_dir, replay_options)
    latest = snapshot_dir / "runtime_latest"
    for file_name in (
        "top_opportunities_latest.json",
        "freshness_latest.json",
        "feed_runtime_latest.json",
        "runtime_health_latest.json",
    ):
        payload = _read_json(latest / file_name)
        for row in _flatten_rows(payload):
            row.setdefault("_source_file", file_name)
            yield row


def _candidate_funnel(top_payload: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    permission_counts: Counter[str] = Counter()
    for row in rows:
        status = _lower(
            row.get("candidate_status")
            or row.get("execution_status")
            or row.get("readiness")
            or row.get("permission")
        )
        if status:
            status_counts[status] += 1
        permission = _lower(row.get("permission") or row.get("final_action") or row.get("order_policy"))
        if permission:
            permission_counts[permission] += 1

    funnel: dict[str, Any] = {
        "rows_seen": sum(status_counts.values()),
        "status_counts": dict(status_counts),
        "permission_counts": dict(permission_counts),
    }
    if isinstance(top_payload, dict):
        for key in (
            "source_candidate_count",
            "phase2_ranked_count",
            "selected_count",
            "top_executable_count",
            "top_advisory_count",
            "visible_executable_count",
            "visible_advisory_count",
            "visible_queue_only_count",
        ):
            if key in top_payload:
                funnel[key] = top_payload.get(key)
        for key in ("top_executable", "top_advisory", "ranked_candidates"):
            value = top_payload.get(key)
            if isinstance(value, list):
                funnel[f"{key}_len"] = len(value)
    return funnel


def _score_pairs(row: dict[str, Any]) -> Iterator[tuple[str, float, float]]:
    pairs = (
        ("confidence", "confidence_raw", "confidence"),
        ("confidence_terminal", "confidence_raw", "terminal_confidence"),
        ("opportunity", "opportunity_score_raw", "opportunity_score"),
        ("opportunity_terminal", "opportunity_score_raw", "terminal_opportunity_score"),
        ("final_score", "raw_score", "final_score"),
        ("score", "score_raw", "score"),
    )
    for label, raw_key, final_key in pairs:
        raw = _safe_float(row.get(raw_key))
        final = _safe_float(row.get(final_key))
        if raw is not None and final is not None:
            yield label, raw, final
    breakdown = row.get("score_breakdown")
    if isinstance(breakdown, dict):
        raw = _safe_float(breakdown.get("confidence_raw") or breakdown.get("raw_confidence"))
        final = _safe_float(row.get("confidence") or row.get("terminal_confidence"))
        if raw is not None and final is not None:
            yield "score_breakdown_confidence", raw, final


def _score_flattening_rows(rows: list[dict[str, Any]], *, tolerance: float) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for row in rows:
        for label, raw, final in _score_pairs(row):
            delta = abs(float(raw) - float(final))
            if delta <= float(tolerance):
                continue
            flattened.append(
                {
                    "source_file": row.get("_source_file"),
                    "symbol": row.get("symbol") or row.get("underlying"),
                    "trade_id": row.get("trade_id") or row.get("candidate_id"),
                    "score_label": label,
                    "raw": raw,
                    "final": final,
                    "delta": round(delta, 8),
                    "reason": row.get("score_flattening_reason") or row.get("flattening_reason"),
                }
            )
    return flattened


def _final_no_trade_reasons(top_payload: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: Counter[str] = Counter()
    payload_reasons: dict[str, Any] = {}
    if isinstance(top_payload, dict):
        for key in (
            "selector_outcome",
            "phase2_reason",
            "reason",
            "final_reason",
            "no_trade_reason",
            "primary_blocker",
        ):
            value = top_payload.get(key)
            if value not in (None, ""):
                payload_reasons[key] = value
                reasons[_lower(value)] += 1
    for row in rows:
        for key in ("reject_reason", "entry_block_code", "reason_code", "reason", "permission_reason"):
            value = row.get(key)
            if value not in (None, ""):
                reasons[_lower(value)] += 1
    return {
        "top_payload_reasons": payload_reasons,
        "reason_counts": dict(reasons.most_common(20)),
    }


def _capture_snapshot(snapshot_dir: Path, *, root: Path, options: RuntimeEvidenceCaptureOptions) -> _SnapshotCapture:
    top_payload = _runtime_latest(snapshot_dir, "top_opportunities_latest.json")
    feed_payload = _runtime_latest(snapshot_dir, "feed_runtime_latest.json")
    freshness_payload = _runtime_latest(snapshot_dir, "freshness_latest.json")
    rows = list(_iter_rows(snapshot_dir, options))
    fallback_count = sum(
        1
        for row in rows
        if any(
            _lower(row.get(key)) in {"fallback", "rest_fallback", "recovered_fallback", "subscription_failed"}
            for key in ("quote_source", "option_ltp_source", "execution_entry_source", "entry_source")
        )
    )
    return _SnapshotCapture(
        name=_snapshot_name(snapshot_dir, root),
        feed_present=isinstance(feed_payload, dict),
        freshness_present=bool(_as_rows(freshness_payload)),
        fallback_count=fallback_count,
        candidate_funnel=_candidate_funnel(top_payload, rows),
        score_flattening_rows=_score_flattening_rows(rows, tolerance=options.score_flattening_tolerance),
        final_no_trade_reasons=_final_no_trade_reasons(top_payload, rows),
    )


def _section(name: str, captures: list[_SnapshotCapture], diagnosis_totals: dict[str, Any]) -> CaptureSection:
    if not captures:
        return CaptureSection(name=name, status="missing", reason="no_snapshots_found")
    if name == "feed":
        present = sum(1 for capture in captures if capture.feed_present)
        return CaptureSection(
            name=name,
            status="covered" if present else "missing",
            reason="feed_runtime_latest_scanned" if present else "feed_runtime_latest_missing",
            details={"snapshots_with_feed": present, "feed_not_ok_snapshots": diagnosis_totals.get("feed_not_ok_snapshots", 0)},
        )
    if name == "freshness":
        present = sum(1 for capture in captures if capture.freshness_present)
        return CaptureSection(
            name=name,
            status="covered" if present else "missing",
            reason="freshness_latest_scanned" if present else "freshness_latest_missing_or_empty",
            details={"snapshots_with_freshness": present, "stale_symbols": diagnosis_totals.get("symbols_with_stale_freshness", [])},
        )
    if name == "fallback":
        total = sum(capture.fallback_count for capture in captures)
        return CaptureSection(
            name=name,
            status="covered",
            reason="fallback_sources_counted",
            details={"fallback_rows_in_capture_scan": total, "fallback_rows_in_diagnosis": diagnosis_totals.get("fallback_row_count", 0)},
        )
    if name == "candidate_funnel":
        rows_seen = sum(int(capture.candidate_funnel.get("rows_seen") or 0) for capture in captures)
        top_counts = [capture.candidate_funnel for capture in captures]
        return CaptureSection(
            name=name,
            status="covered" if rows_seen or top_counts else "missing",
            reason="candidate_funnel_counts_available" if rows_seen or top_counts else "candidate_funnel_missing",
            details={"rows_seen": rows_seen, "snapshots": top_counts},
        )
    if name == "score_flattening":
        flattened = sum(len(capture.score_flattening_rows) for capture in captures)
        return CaptureSection(
            name=name,
            status="covered",
            reason="score_flattening_scan_completed",
            details={"score_flattening_count": flattened},
        )
    if name == "final_no_trade_reasons":
        reason_counts: Counter[str] = Counter()
        payload_reason_snapshots = 0
        for capture in captures:
            if capture.final_no_trade_reasons.get("top_payload_reasons"):
                payload_reason_snapshots += 1
            reason_counts.update(capture.final_no_trade_reasons.get("reason_counts") or {})
        return CaptureSection(
            name=name,
            status="covered" if payload_reason_snapshots or reason_counts else "missing",
            reason="final_no_trade_reasons_available" if payload_reason_snapshots or reason_counts else "final_no_trade_reasons_missing",
            details={"snapshots_with_top_reason": payload_reason_snapshots, "reason_counts": dict(reason_counts.most_common(20))},
        )
    return CaptureSection(name=name, status="missing", reason="unknown_required_section")


def generate_runtime_evidence_capture_guard_report(
    source: str | Path,
    *,
    options: RuntimeEvidenceCaptureOptions | None = None,
) -> RuntimeEvidenceCaptureGuardReport:
    options = options or RuntimeEvidenceCaptureOptions()
    replay_options = EvidenceReplayOptions(
        today=options.today,
        quote_age_mismatch_tolerance_sec=options.quote_age_mismatch_tolerance_sec,
        max_jsonl_lines_per_file=options.max_jsonl_lines_per_file,
    )
    diagnosis = generate_evidence_replay_report(source, options=replay_options)
    with _evidence_root(source) as root:
        captures = [
            _capture_snapshot(snapshot, root=root, options=options)
            for snapshot in _find_snapshots(root)
        ]
    sections = tuple(_section(name, captures, diagnosis.totals) for name in REQUIRED_CAPTURE_SECTIONS)
    if not captures:
        verdict = "CAPTURE_GUARD_FAILED_NO_SNAPSHOTS"
    elif any(section.status == "missing" for section in sections):
        verdict = "CAPTURE_GUARD_INCOMPLETE"
    else:
        verdict = "CAPTURE_GUARD_OK"
    return RuntimeEvidenceCaptureGuardReport(
        source=str(Path(source)),
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        verdict=verdict,
        required_sections=REQUIRED_CAPTURE_SECTIONS,
        sections=sections,
        diagnosis_verdict=diagnosis.verdict,
        diagnosis_totals=diagnosis.totals,
        evidence_map=diagnosis.evidence_map,
        snapshots=tuple(capture.to_dict() for capture in captures),
    )


def runtime_evidence_capture_guard_to_markdown(report: RuntimeEvidenceCaptureGuardReport) -> str:
    payload = report.to_dict()
    lines = [
        "# EDGE-38 Runtime Evidence Capture Guard Report",
        "",
        f"source: `{payload['source']}`",
        f"generated_at: `{payload['generated_at']}`",
        f"verdict: `{payload['verdict']}`",
        f"diagnosis_verdict: `{payload['diagnosis_verdict']}`",
        "",
        "## Required Sections",
        "",
        "| Section | Status | Reason |",
        "|---|---|---|",
    ]
    for section in payload["sections"]:
        lines.append(f"| `{section['name']}` | `{section['status']}` | `{section['reason']}` |")
    lines.extend(["", "## Evidence Map", ""])
    for key, value in payload["evidence_map"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Diagnosis Totals", ""])
    for key, value in payload["diagnosis_totals"].items():
        lines.append(f"- {key}: `{json.dumps(value, sort_keys=True, default=str)}`")
    lines.extend(["", "## Snapshot Capture", ""])
    if not payload["snapshots"]:
        lines.append("- none")
    else:
        for snapshot in payload["snapshots"]:
            lines.append(
                f"- {snapshot['name']}: fallback_count=`{snapshot['fallback_count']}`, score_flattening_rows=`{len(snapshot['score_flattening_rows'])}`"
            )
    lines.append("")
    return "\n".join(lines)
