from __future__ import annotations

from pathlib import Path
from typing import Any

from core.advisory_schema import AdvisorySchemaError, deserialize_advisory_row, log_advisory_schema_error
from core.runtime_snapshot_store import ADVISORY_LATEST_PATH, read_snapshot


def _extract_snapshot_rows(envelope: dict[str, Any]) -> tuple[list[Any] | None, list[str]]:
    if not isinstance(envelope, dict):
        return None, ["snapshot_envelope_not_object"]
    if isinstance(envelope.get("rows"), list):
        return list(envelope.get("rows") or []), []
    if "rows" in envelope:
        return None, ["advisory_rows_not_list"]

    if "payload" not in envelope:
        return None, ["advisory_snapshot_rows_missing"]

    payload = envelope.get("payload")
    if isinstance(payload, list):
        return list(payload), []
    if not isinstance(payload, dict):
        return None, ["advisory_snapshot_payload_not_object_or_list"]

    if isinstance(payload.get("rows"), list):
        return list(payload.get("rows") or []), []
    if "rows" in payload:
        return None, ["advisory_rows_not_list"]
    return None, ["advisory_snapshot_rows_missing"]


def read_advisory_snapshot_rows(
    path: str | Path = ADVISORY_LATEST_PATH,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not target.exists():
        return {
            "state": "missing",
            "path": str(target),
            "errors": [f"missing:{target}"],
            "rows": [],
        }
    try:
        envelope = read_snapshot(target)
    except Exception as exc:
        return {
            "state": "invalid",
            "path": str(target),
            "errors": [f"read_error:{type(exc).__name__}:{exc}"],
            "rows": [],
        }

    rows, errors = _extract_snapshot_rows(envelope)
    if rows is None:
        return {
            "state": "invalid",
            "path": str(target),
            "errors": errors or ["advisory_snapshot_rows_missing"],
            "rows": [],
        }

    validated_rows: list[dict[str, Any]] = []
    for row in list(rows)[-max(1, int(limit)) :]:
        try:
            validated_rows.append(deserialize_advisory_row(row, allow_legacy=True))
        except AdvisorySchemaError as exc:
            log_advisory_schema_error("dashboard.advisory_snapshot", row, exc)
    return {
        "state": "ok",
        "path": str(target),
        "errors": [],
        "rows": validated_rows,
    }
