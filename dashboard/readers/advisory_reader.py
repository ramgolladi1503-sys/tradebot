from __future__ import annotations

from pathlib import Path
from typing import Any

from core.advisory_schema import AdvisorySchemaError, deserialize_advisory_row, log_advisory_schema_error
from core.runtime_snapshot_store import ADVISORY_LATEST_PATH
from dashboard.readers.snapshot_reader import read_snapshot_payload


def read_advisory_snapshot_rows(
    path: str | Path = ADVISORY_LATEST_PATH,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    snapshot = read_snapshot_payload(path)
    if snapshot.get("state") != "ok":
        return {
            "state": snapshot.get("state"),
            "path": snapshot.get("path"),
            "errors": list(snapshot.get("errors") or []),
            "rows": [],
        }
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else {}
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return {
            "state": "invalid",
            "path": snapshot.get("path"),
            "errors": ["advisory_rows_not_list"],
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
        "path": snapshot.get("path"),
        "errors": list(snapshot.get("errors") or []),
        "rows": validated_rows,
    }
