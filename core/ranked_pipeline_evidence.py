"""Runtime evidence writer for ranked opportunity pipeline reports.

This module persists ranked pipeline evidence only. It does not build reports,
select trades, place orders, call brokers, mutate ranking output, or touch the
dashboard.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.paths import logs_dir
from core.time_utils import ist_date_key, utc_now

RANKED_PIPELINE_EVIDENCE_SCHEMA_VERSION = 1
LATEST_FILENAME = "ranked_pipeline_runtime_latest.json"
DAILY_FILENAME_PREFIX = "ranked_pipeline_runtime"


class RankedPipelineEvidenceError(ValueError):
    """Raised when ranked pipeline evidence is unsafe or invalid to persist."""


def _to_mapping(report: Any) -> Mapping[str, Any]:
    if isinstance(report, Mapping):
        return report
    to_dict = getattr(report, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise RankedPipelineEvidenceError("ranked_pipeline_report_missing_or_invalid")


def _json_safe_copy(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe defensive copy without mutating the source object."""

    return json.loads(json.dumps(dict(payload), sort_keys=True, default=str))


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _validate_ranked_report(report: Mapping[str, Any]) -> None:
    if not _bool(report.get("read_only"), default=False):
        raise RankedPipelineEvidenceError("ranked_pipeline_report_not_read_only")
    if _bool(report.get("is_order_action"), default=False):
        raise RankedPipelineEvidenceError("ranked_pipeline_report_contains_order_action")
    if _bool(report.get("append"), default=False):
        raise RankedPipelineEvidenceError("ranked_pipeline_report_append_true")
    metadata = report.get("metadata")
    if not isinstance(metadata, Mapping):
        raise RankedPipelineEvidenceError("ranked_pipeline_metadata_missing")
    if str(metadata.get("orchestrator") or "").strip() != "ranked_opportunity_pipeline_v1":
        raise RankedPipelineEvidenceError("ranked_pipeline_non_canonical_orchestrator")


def _evidence_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp_path.replace(path)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


@dataclass(frozen=True)
class RankedPipelineEvidenceWriteResult:
    schema_version: int
    latest_path: str
    daily_path: str
    evidence_hash: str
    latest_written: bool
    daily_appended: bool
    is_order_action: bool = False
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_ranked_pipeline_evidence_payload(
    ranked_report: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the JSON evidence envelope for a ranked pipeline report."""

    source_report = _to_mapping(ranked_report)
    _validate_ranked_report(source_report)
    report_payload = _json_safe_copy(source_report)
    now_dt = now or utc_now()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    else:
        now_dt = now_dt.astimezone(timezone.utc)

    envelope = {
        "schema_version": RANKED_PIPELINE_EVIDENCE_SCHEMA_VERSION,
        "event": "RANKED_PIPELINE_RUNTIME_EVIDENCE",
        "ts": now_dt.isoformat(),
        "session_date": ist_date_key(now_dt),
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "report": report_payload,
    }
    envelope["evidence_hash"] = _evidence_hash(envelope)
    return envelope


def write_ranked_pipeline_evidence(
    ranked_report: Any,
    *,
    output_dir: Path | str | None = None,
    now: datetime | None = None,
) -> RankedPipelineEvidenceWriteResult:
    """Persist latest JSON and daily JSONL evidence for one ranked report."""

    target_dir = Path(output_dir) if output_dir is not None else logs_dir()
    payload = build_ranked_pipeline_evidence_payload(ranked_report, now=now)
    session_date = str(payload["session_date"])
    latest_path = target_dir / LATEST_FILENAME
    daily_path = target_dir / f"{DAILY_FILENAME_PREFIX}_{session_date}.jsonl"

    _atomic_write_json(latest_path, payload)
    _append_jsonl(daily_path, payload)

    return RankedPipelineEvidenceWriteResult(
        schema_version=RANKED_PIPELINE_EVIDENCE_SCHEMA_VERSION,
        latest_path=str(latest_path),
        daily_path=str(daily_path),
        evidence_hash=str(payload["evidence_hash"]),
        latest_written=True,
        daily_appended=True,
    )


__all__ = [
    "DAILY_FILENAME_PREFIX",
    "LATEST_FILENAME",
    "RANKED_PIPELINE_EVIDENCE_SCHEMA_VERSION",
    "RankedPipelineEvidenceError",
    "RankedPipelineEvidenceWriteResult",
    "build_ranked_pipeline_evidence_payload",
    "write_ranked_pipeline_evidence",
]
