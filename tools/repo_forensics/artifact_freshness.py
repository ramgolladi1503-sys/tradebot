from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MAX_AGE_SECONDS = 3600
TIMESTAMP_FIELDS = ("timestamp", "generated_at", "created_at", "event_time")
SOURCE_FIELDS = ("source", "artifact_source")
LATEST_FIELDS = ("latest", "latest_path", "latest_artifact")
SESSION_FIELDS = ("session_id", "session")
CONSUMED_FIELDS = ("consumed_at", "read_at")


@dataclass(frozen=True)
class ArtifactFreshnessResult:
    freshness: str
    complete: bool
    checked_fields: tuple[str, ...]
    issues: tuple[str, ...] = field(default_factory=tuple)
    age_seconds: int | None = None
    gap_seconds: int | None = None


def evaluate_artifact_freshness(
    record: dict[str, Any],
    *,
    artifact_path: str,
    repo_root: str | Path,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> ArtifactFreshnessResult:
    """Evaluate runtime artifact freshness from evidence metadata only.

    This helper is static: it reads no product runtime, calls no external service,
    and performs no artifact cleanup.
    """

    current = _as_utc(now or datetime.now(timezone.utc))
    issues: list[str] = []
    checked: list[str] = []

    timestamp_value, timestamp_field = _first_value(record, TIMESTAMP_FIELDS)
    if timestamp_field:
        checked.append(timestamp_field)
    if timestamp_value is None:
        return ArtifactFreshnessResult(
            freshness="UNKNOWN",
            complete=False,
            checked_fields=tuple(checked),
            issues=("timestamp_absent",),
        )

    parsed_timestamp = _parse_timestamp(timestamp_value)
    if parsed_timestamp is None:
        return ArtifactFreshnessResult(
            freshness="UNKNOWN",
            complete=False,
            checked_fields=tuple(checked),
            issues=("timestamp_unparseable",),
        )

    age_seconds = int((current - parsed_timestamp).total_seconds())
    if age_seconds < 0:
        issues.append("timestamp_in_future")
    elif age_seconds > max_age_seconds:
        issues.append("artifact_stale")

    source_value, source_field = _first_value(record, SOURCE_FIELDS)
    if source_field:
        checked.append(source_field)
    if source_value is None or not str(source_value).strip():
        issues.append("artifact_source_absent")

    latest_value, latest_field = _first_value(record, LATEST_FIELDS)
    if latest_field:
        checked.append(latest_field)
        missing_latest_issue = _latest_marker_issue(latest_value, artifact_path=artifact_path, repo_root=repo_root)
        if missing_latest_issue:
            issues.append(missing_latest_issue)

    session_value, session_field = _first_value(record, SESSION_FIELDS)
    if _session_expected(record, artifact_path):
        if session_field:
            checked.append(session_field)
        if session_value is None or not str(session_value).strip():
            issues.append("session_id_absent")

    consumed_value, consumed_field = _first_value(record, CONSUMED_FIELDS)
    gap_seconds: int | None = None
    if consumed_field:
        checked.append(consumed_field)
        consumed_at = _parse_timestamp(consumed_value)
        if consumed_at is None:
            issues.append("consumed_at_unparseable")
        else:
            gap_seconds = int((consumed_at - parsed_timestamp).total_seconds())
            if gap_seconds < 0:
                issues.append("consumed_before_generated")
            elif gap_seconds > max_age_seconds:
                issues.append("generated_consumed_gap_exceeded")

    if issues:
        freshness = "STALE" if "artifact_stale" in issues or "generated_consumed_gap_exceeded" in issues else "UNKNOWN"
        return ArtifactFreshnessResult(
            freshness=freshness,
            complete=False,
            checked_fields=tuple(checked),
            issues=tuple(issues),
            age_seconds=age_seconds,
            gap_seconds=gap_seconds,
        )

    return ArtifactFreshnessResult(
        freshness="FRESH",
        complete=True,
        checked_fields=tuple(checked),
        issues=(),
        age_seconds=age_seconds,
        gap_seconds=gap_seconds,
    )


def _first_value(record: dict[str, Any], fields: tuple[str, ...]) -> tuple[Any | None, str | None]:
    for field in fields:
        if field in record:
            return record[field], field
    return None, None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_marker_issue(value: Any, *, artifact_path: str, repo_root: str | Path) -> str | None:
    if value is True:
        return None
    if value in (False, None, ""):
        return "latest_marker_absent"
    marker_path = Path(str(value))
    if not marker_path.is_absolute():
        marker_path = Path(repo_root) / marker_path
    if not marker_path.exists():
        return "latest_marker_target_absent"
    current = (Path(repo_root) / artifact_path).resolve()
    try:
        if marker_path.resolve() != current:
            return "latest_marker_points_elsewhere"
    except OSError:
        return "latest_marker_target_absent"
    return None


def _session_expected(record: dict[str, Any], artifact_path: str) -> bool:
    if any(field in record for field in SESSION_FIELDS):
        return True
    lowered = artifact_path.lower()
    return "session" in lowered or "live" in lowered
