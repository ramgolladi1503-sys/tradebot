from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.repo_forensics.config_loader import ForensicsConfig


@dataclass(frozen=True)
class EvidenceFinding:
    path: str
    severity: str
    evidence_type: str
    evidence: str
    missing_fields: list[str] = field(default_factory=list)


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


def audit_evidence(repo_root: str | Path, config: ForensicsConfig) -> EvidenceAuditReport:
    root = Path(repo_root).resolve()
    required_fields = _required_fields(config)
    findings: list[EvidenceFinding] = []
    reviewed = 0

    for evidence_path in config.runtime_evidence_paths:
        path = root / evidence_path
        if not path.exists():
            continue
        for file_path in _iter_evidence_files(path):
            rel = file_path.relative_to(root).as_posix()
            reviewed += 1
            findings.extend(_audit_file(rel, file_path, required_fields))
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


def _audit_file(rel: str, file_path: Path, required_fields: list[str]) -> list[EvidenceFinding]:
    suffix = file_path.suffix.lower()
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [EvidenceFinding(rel, "UNKNOWN", "file_read", "unreadable_evidence_file")]

    if suffix == ".json":
        return _audit_json(rel, text, required_fields)
    if suffix == ".jsonl":
        return _audit_jsonl(rel, text, required_fields)
    return _audit_text(rel, text)


def _audit_json(rel: str, text: str, required_fields: list[str]) -> list[EvidenceFinding]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [EvidenceFinding(rel, "UNKNOWN", "json", "invalid_json")]
    records = payload if isinstance(payload, list) else [payload]
    findings: list[EvidenceFinding] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            findings.append(EvidenceFinding(rel, "UNKNOWN", "json", f"non_object_record:index={index}"))
            continue
        findings.extend(_audit_record(rel, record, required_fields, f"json_record:index={index}"))
    return findings


def _audit_jsonl(rel: str, text: str, required_fields: list[str]) -> list[EvidenceFinding]:
    findings: list[EvidenceFinding] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            findings.append(EvidenceFinding(rel, "UNKNOWN", "jsonl", f"invalid_jsonl_line:{index}"))
            continue
        if not isinstance(record, dict):
            findings.append(EvidenceFinding(rel, "UNKNOWN", "jsonl", f"non_object_line:{index}"))
            continue
        findings.extend(_audit_record(rel, record, required_fields, f"jsonl_line:{index}"))
    return findings


def _audit_record(rel: str, record: dict[str, Any], required_fields: list[str], evidence: str) -> list[EvidenceFinding]:
    if _is_status_only(record):
        return [EvidenceFinding(rel, "MEDIUM", "record", f"weak_status_only:{evidence}")]

    decision_like = _is_decision_like(record)
    if not decision_like:
        return []

    missing = [field for field in required_fields if field not in record]
    if missing:
        severity = "HIGH" if any(field in missing for field in ("decision", "reason", "is_order_action", "broker_api_called")) else "MEDIUM"
        return [EvidenceFinding(rel, severity, "record", f"missing_required_fields:{evidence}", missing_fields=missing)]
    return []


def _audit_text(rel: str, text: str) -> list[EvidenceFinding]:
    compact = text.lower().replace(" ", "")
    findings: list[EvidenceFinding] = []
    if any(marker in compact for marker in ["status:ok", "status=ok", "safe:true", "ok:true"]):
        if not any(marker in compact for marker in ["reason", "decision", "broker_api_called", "is_order_action"]):
            findings.append(EvidenceFinding(rel, "MEDIUM", "text", "weak_status_only_text"))
    if "broker_api_called" in compact and "is_order_action" not in compact:
        findings.append(EvidenceFinding(rel, "MEDIUM", "text", "broker_field_without_order_action_field"))
    if "is_order_action" in compact and "broker_api_called" not in compact:
        findings.append(EvidenceFinding(rel, "MEDIUM", "text", "order_action_field_without_broker_field"))
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
    keys = set(record.keys())
    markers = {"candidate_id", "decision", "reason", "is_order_action", "broker_api_called", "mode"}
    return bool(keys & markers)


def _required_fields(config: ForensicsConfig) -> list[str]:
    evidence = config.data.get("evidence", {})
    if isinstance(evidence, dict):
        fields = evidence.get("required_fields")
        if isinstance(fields, list):
            return [str(field) for field in fields]
    return ["mode", "candidate_id", "decision", "reason", "timestamp", "is_order_action", "broker_api_called", "source"]
