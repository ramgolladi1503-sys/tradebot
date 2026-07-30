from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.repo_forensics.artifact_freshness import evaluate_artifact_freshness
from tools.repo_forensics.candidate_evidence_trace import score_candidate_trace
from tools.repo_forensics.config_loader import ForensicsConfig


NON_ACTION_FIELDS = ("is_order_action", "broker_api_called", "live_order_action", "broker_order_action")
DEFAULT_REQUIRED_FIELDS = ("mode", "candidate_id", "decision", "reason", "timestamp", "is_order_action", "broker_api_called", "source")
_DECISION_IDENTITY_FIELDS = {"candidate_id", "decision", *NON_ACTION_FIELDS}
_DECISION_EVENT_MARKERS = (
    "candidate",
    "decision",
    "recommendation",
    "signal",
    "trade_suggestion",
    "execution_intent",
)


@dataclass(frozen=True)
class EvidenceFinding:
    path: str
    severity: str
    evidence_type: str
    evidence: str
    missing_fields: list[str] = field(default_factory=list)
    scope: str = "new_regression"


@dataclass(frozen=True)
class EvidenceAuditReport:
    reviewed_files: int = 0
    findings: list[EvidenceFinding] = field(default_factory=list)

    @property
    def high(self) -> list[EvidenceFinding]:
        return [item for item in self.findings if item.severity == "HIGH"]

    @property
    def medium(self) -> list[EvidenceFinding]:
        return [item for item in self.findings if item.severity == "MEDIUM"]

    @property
    def unknown(self) -> list[EvidenceFinding]:
        return [item for item in self.findings if item.severity == "UNKNOWN"]

    @property
    def new_regressions(self) -> list[EvidenceFinding]:
        return [item for item in self.findings if item.scope == "new_regression"]

    @property
    def baseline_debt(self) -> list[EvidenceFinding]:
        return [item for item in self.findings if item.scope == "baseline_debt"]


def audit_evidence(repo_root: str | Path, config: ForensicsConfig) -> EvidenceAuditReport:
    root = Path(repo_root).resolve()
    required_fields = _required_fields(config)
    strict_non_action_gate = _strict_non_action_gate(config)
    trace_completeness_gate = _trace_completeness_gate(config)
    freshness_gate = _freshness_gate(config)
    max_age_seconds = _freshness_max_age_seconds(config)
    freshness_now = _freshness_now(config)
    findings: list[EvidenceFinding] = []
    reviewed = 0

    for evidence_path in config.runtime_evidence_paths:
        path = root / evidence_path
        if not path.exists():
            continue
        for file_path in _iter_evidence_files(path):
            rel = file_path.relative_to(root).as_posix()
            reviewed += 1
            findings.extend(
                _audit_file(
                    rel,
                    file_path,
                    root,
                    required_fields,
                    strict_non_action_gate,
                    trace_completeness_gate,
                    freshness_gate,
                    max_age_seconds,
                    freshness_now,
                )
            )
    return EvidenceAuditReport(reviewed_files=reviewed, findings=findings)


def _iter_evidence_files(path: Path):
    if path.is_file():
        yield path
        return
    for file_path in sorted(path.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() in {".json", ".jsonl", ".md", ".txt"}:
            yield file_path


def _audit_file(
    rel: str,
    file_path: Path,
    repo_root: Path,
    required_fields: list[str],
    strict_non_action_gate: bool,
    trace_completeness_gate: bool,
    freshness_gate: bool,
    max_age_seconds: int,
    freshness_now: datetime | None,
) -> list[EvidenceFinding]:
    suffix = file_path.suffix.lower()
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [EvidenceFinding(rel, "UNKNOWN", "file_read", "unreadable_evidence_file", scope=_scope_for_path(rel))]

    if suffix == ".json":
        return _audit_json(
            rel,
            text,
            repo_root,
            required_fields,
            strict_non_action_gate,
            trace_completeness_gate,
            freshness_gate,
            max_age_seconds,
            freshness_now,
        )
    if suffix == ".jsonl":
        return _audit_jsonl(
            rel,
            text,
            repo_root,
            required_fields,
            strict_non_action_gate,
            trace_completeness_gate,
            freshness_gate,
            max_age_seconds,
            freshness_now,
        )
    return _audit_text(rel, text, strict_non_action_gate)


def _audit_json(
    rel: str,
    text: str,
    repo_root: Path,
    required_fields: list[str],
    strict_non_action_gate: bool,
    trace_completeness_gate: bool,
    freshness_gate: bool,
    max_age_seconds: int,
    freshness_now: datetime | None,
) -> list[EvidenceFinding]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [EvidenceFinding(rel, "UNKNOWN", "json", "invalid_json", scope=_scope_for_path(rel))]
    records = payload if isinstance(payload, list) else [payload]
    findings: list[EvidenceFinding] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            findings.append(EvidenceFinding(rel, "UNKNOWN", "json", f"non_object_record:index={index}", scope=_scope_for_path(rel)))
            continue
        findings.extend(
            _audit_record(
                rel,
                record,
                repo_root,
                required_fields,
                strict_non_action_gate,
                trace_completeness_gate,
                freshness_gate,
                max_age_seconds,
                freshness_now,
                f"json_record:index={index}",
            )
        )
    return findings


def _audit_jsonl(
    rel: str,
    text: str,
    repo_root: Path,
    required_fields: list[str],
    strict_non_action_gate: bool,
    trace_completeness_gate: bool,
    freshness_gate: bool,
    max_age_seconds: int,
    freshness_now: datetime | None,
) -> list[EvidenceFinding]:
    findings: list[EvidenceFinding] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            findings.append(EvidenceFinding(rel, "UNKNOWN", "jsonl", f"invalid_jsonl_line:{index}", scope=_scope_for_path(rel)))
            continue
        if not isinstance(record, dict):
            findings.append(EvidenceFinding(rel, "UNKNOWN", "jsonl", f"non_object_line:{index}", scope=_scope_for_path(rel)))
            continue
        findings.extend(
            _audit_record(
                rel,
                record,
                repo_root,
                required_fields,
                strict_non_action_gate,
                trace_completeness_gate,
                freshness_gate,
                max_age_seconds,
                freshness_now,
                f"jsonl_line:{index}",
            )
        )
    return findings


def _audit_record(
    rel: str,
    record: dict[str, Any],
    repo_root: Path,
    required_fields: list[str],
    strict_non_action_gate: bool,
    trace_completeness_gate: bool,
    freshness_gate: bool,
    max_age_seconds: int,
    freshness_now: datetime | None,
    evidence: str,
) -> list[EvidenceFinding]:
    scope = _scope_for_path(rel)
    if _is_status_only(record):
        return [EvidenceFinding(rel, "MEDIUM", "record", f"weak_status_only:{evidence}", scope=scope)]

    if not _is_decision_like(record):
        return []

    findings: list[EvidenceFinding] = []
    missing = [field for field in required_fields if field not in record]
    if missing:
        severity = "HIGH" if any(field in missing for field in ("decision", "reason", *NON_ACTION_FIELDS)) else "MEDIUM"
        findings.append(EvidenceFinding(rel, severity, "record", f"required_fields_absent:{evidence}", missing_fields=missing, scope=scope))

    if strict_non_action_gate:
        missing_extended_non_action = [field for field in NON_ACTION_FIELDS if field not in required_fields and field not in record]
        if missing_extended_non_action:
            findings.append(
                EvidenceFinding(
                    rel,
                    "MEDIUM",
                    "record",
                    f"extended_non_action_fields_absent:{evidence}",
                    missing_fields=missing_extended_non_action,
                    scope="baseline_debt",
                )
            )

    unsafe_non_action_fields = [field for field in NON_ACTION_FIELDS if field in record and record[field] is not False]
    if unsafe_non_action_fields:
        findings.append(
            EvidenceFinding(
                rel,
                "HIGH" if strict_non_action_gate else "MEDIUM",
                "record",
                f"non_action_field_not_false:{evidence}",
                missing_fields=unsafe_non_action_fields,
                scope=scope if strict_non_action_gate else "baseline_debt",
            )
        )

    if trace_completeness_gate:
        findings.extend(_trace_findings(rel, record, evidence, scope))
    if freshness_gate:
        findings.extend(_freshness_findings(rel, record, repo_root, max_age_seconds, freshness_now, evidence, scope))
    return findings


def _trace_findings(rel: str, record: dict[str, Any], evidence: str, scope: str) -> list[EvidenceFinding]:
    trace_score = score_candidate_trace(record)
    if trace_score.trace_complete:
        return []

    severity = "HIGH" if trace_score.hard_failed else "MEDIUM"
    trace_evidence = f"candidate_trace_score:{trace_score.score}:{evidence}"
    return [
        EvidenceFinding(
            rel,
            severity,
            "candidate_trace",
            trace_evidence,
            missing_fields=list(trace_score.missing_fields),
            scope=scope,
        )
    ]


def _freshness_findings(
    rel: str,
    record: dict[str, Any],
    repo_root: Path,
    max_age_seconds: int,
    freshness_now: datetime | None,
    evidence: str,
    scope: str,
) -> list[EvidenceFinding]:
    freshness = evaluate_artifact_freshness(
        record,
        artifact_path=rel,
        repo_root=repo_root,
        max_age_seconds=max_age_seconds,
        now=freshness_now,
    )
    if freshness.complete:
        return []
    severity = "HIGH" if "latest_marker_target_absent" in freshness.issues else freshness.freshness
    return [
        EvidenceFinding(
            rel,
            severity,
            "artifact_freshness",
            f"artifact_freshness:{freshness.freshness}:{evidence}",
            missing_fields=list(freshness.issues),
            scope=scope,
        )
    ]


def _audit_text(rel: str, text: str, strict_non_action_gate: bool) -> list[EvidenceFinding]:
    compact = text.lower().replace(" ", "")
    findings: list[EvidenceFinding] = []
    scope = _scope_for_path(rel)
    if any(marker in compact for marker in ["status:ok", "status=ok", "safe:true", "ok:true"]):
        if not any(marker in compact for marker in ["reason", "decision", "broker_api_called", "is_order_action"]):
            findings.append(EvidenceFinding(rel, "MEDIUM", "text", "weak_status_only_text", scope=scope))
    present_non_action = [field for field in NON_ACTION_FIELDS if field in compact]
    if strict_non_action_gate and present_non_action and set(present_non_action) != set(NON_ACTION_FIELDS):
        missing = [field for field in NON_ACTION_FIELDS if field not in present_non_action]
        findings.append(EvidenceFinding(rel, "MEDIUM", "text", "partial_non_action_fields", missing_fields=missing, scope="baseline_debt"))
    for field in NON_ACTION_FIELDS:
        if field in compact and f"{field}:false" not in compact and f"{field}=false" not in compact:
            findings.append(
                EvidenceFinding(
                    rel,
                    "HIGH" if strict_non_action_gate else "MEDIUM",
                    "text",
                    "non_action_field_not_false",
                    missing_fields=[field],
                    scope=scope if strict_non_action_gate else "baseline_debt",
                )
            )
    return findings


def _is_status_only(record: dict[str, Any]) -> bool:
    keys = set(record.keys())
    weak_key_sets = [
        {"status"},
        {"status", "safe"},
        {"ok"},
        {"safe"},
    ]
    return any(keys <= weak for weak in weak_key_sets)


def _is_decision_like(record: dict[str, Any]) -> bool:
    """Classify records by decision identity, not generic metadata.

    ``mode`` and ``reason`` occur in execution fills, health snapshots, and
    operational events. They cannot, by themselves, justify applying the
    candidate-decision schema. Strong decision fields or an explicit
    decision/candidate/signal event type are required.
    """

    keys = set(record.keys())
    if keys & _DECISION_IDENTITY_FIELDS:
        return True

    event_name = str(
        record.get("event_type")
        or record.get("event")
        or record.get("record_type")
        or record.get("type")
        or ""
    ).strip().lower()
    return any(marker in event_name for marker in _DECISION_EVENT_MARKERS)


def _required_fields(config: ForensicsConfig) -> list[str]:
    evidence = config.data.get("evidence", {})
    if isinstance(evidence, dict):
        configured = evidence.get("required_fields")
        if isinstance(configured, list) and configured:
            return [str(field) for field in configured]
    return list(DEFAULT_REQUIRED_FIELDS)


def _strict_non_action_gate(config: ForensicsConfig) -> bool:
    evidence = config.data.get("evidence", {})
    if not isinstance(evidence, dict):
        return False
    return bool(evidence.get("strict_non_action_gate", False))


def _trace_completeness_gate(config: ForensicsConfig) -> bool:
    evidence = config.data.get("evidence", {})
    if not isinstance(evidence, dict):
        return False
    return bool(evidence.get("trace_completeness_gate", False))


def _freshness_gate(config: ForensicsConfig) -> bool:
    evidence = config.data.get("evidence", {})
    if not isinstance(evidence, dict):
        return False
    return bool(evidence.get("freshness_gate", False))


def _freshness_max_age_seconds(config: ForensicsConfig) -> int:
    evidence = config.data.get("evidence", {})
    if not isinstance(evidence, dict):
        return 3600
    raw = evidence.get("freshness_max_age_seconds", 3600)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 3600
    return max(value, 0)


def _freshness_now(config: ForensicsConfig) -> datetime | None:
    evidence = config.data.get("evidence", {})
    if not isinstance(evidence, dict):
        return None
    raw = evidence.get("freshness_now")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _scope_for_path(rel: str) -> str:
    lowered = rel.lower()
    baseline_markers = ("archive", "baseline", "historical", "legacy")
    return "baseline_debt" if any(marker in lowered for marker in baseline_markers) else "new_regression"
