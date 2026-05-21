from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from core.debug_forensics.models import EvidenceLoadResult, ForensicEvent
from core.paths import logs_dir
from core.runtime_boot_identity import SCHEMA_VERSION
from core.runtime_startup_lifecycle import EVENTS_NAME, LATEST_NAME


class EvidenceValidationError(ValueError):
    pass


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            rows.append({"_invalid_json_line": line_no, "raw": raw})
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            rows.append({"_invalid_json_line": line_no, "raw_type": type(payload).__name__})
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_float(value: Any, *, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceValidationError(f"missing_or_invalid_{field_name}") from exc


def _as_int(value: Any, *, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceValidationError(f"missing_or_invalid_{field_name}") from exc


def _validate_event(payload: dict[str, Any], *, index: int) -> ForensicEvent:
    if "_invalid_json_line" in payload:
        raise EvidenceValidationError(f"invalid_json_line:{payload.get('_invalid_json_line')}")

    event = str(payload.get("event") or "").strip().upper()
    if not event:
        raise EvidenceValidationError(f"event_{index}:missing_event")

    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise EvidenceValidationError(f"event_{index}:{event}:missing_run_id")

    writer = str(payload.get("writer") or "").strip()
    if not writer:
        raise EvidenceValidationError(f"event_{index}:{event}:missing_writer")

    source = str(payload.get("source") or "").strip() or "unknown"
    schema_version = _as_int(payload.get("schema_version"), field_name="schema_version")
    if schema_version != SCHEMA_VERSION:
        raise EvidenceValidationError(
            f"event_{index}:{event}:schema_version_mismatch:{schema_version}!={SCHEMA_VERSION}"
        )

    boot_epoch = _as_float(payload.get("boot_epoch"), field_name="boot_epoch")
    ts_epoch = _as_float(payload.get("ts_epoch"), field_name="ts_epoch")
    is_order_action = bool(payload.get("is_order_action", False))
    details = payload.get("details")

    return ForensicEvent(
        event=event,
        run_id=run_id,
        boot_epoch=boot_epoch,
        ts_epoch=ts_epoch,
        source=source,
        writer=writer,
        schema_version=schema_version,
        is_order_action=is_order_action,
        error=str(payload.get("error") or ""),
        details=dict(details) if isinstance(details, dict) else {},
    )


def _choose_run_id(rows: Iterable[dict[str, Any]], explicit_run_id: str | None, latest: dict[str, Any]) -> str:
    if explicit_run_id:
        return explicit_run_id
    latest_run_id = str(latest.get("run_id") or "").strip()
    if latest_run_id:
        return latest_run_id
    seen = [str(row.get("run_id") or "").strip() for row in rows if isinstance(row, dict) and row.get("run_id")]
    return seen[-1] if seen else ""


def load_runtime_startup_evidence(
    *,
    profile: str = "startup",
    run_id: str | None = None,
    logs_path: str | Path | None = None,
) -> EvidenceLoadResult:
    base = Path(logs_path).expanduser() if logs_path is not None else logs_dir()
    events_path = base / EVENTS_NAME
    latest_path = base / LATEST_NAME
    raw_rows = _read_jsonl(events_path)
    latest = _read_json(latest_path)
    selected_run_id = _choose_run_id(raw_rows, run_id, latest)

    errors: list[str] = []
    warnings: list[str] = []
    events: list[ForensicEvent] = []

    if not raw_rows:
        errors.append(f"missing_or_empty_events_file:{events_path}")
    if not selected_run_id:
        errors.append("missing_run_id:no_explicit_latest_or_jsonl_run_id")

    for index, row in enumerate(raw_rows, start=1):
        try:
            event = _validate_event(row, index=index)
        except EvidenceValidationError as exc:
            errors.append(str(exc))
            continue
        if selected_run_id and event.run_id != selected_run_id:
            continue
        events.append(event)

    if selected_run_id and raw_rows and not events:
        errors.append(f"selected_run_id_has_no_events:{selected_run_id}")

    boot_epochs = {event.boot_epoch for event in events}
    selected_boot_epoch = events[-1].boot_epoch if events else None
    if len(boot_epochs) > 1:
        errors.append(f"mixed_boot_epoch_for_run:{sorted(boot_epochs)}")

    for previous, current in zip(events, events[1:]):
        if current.ts_epoch < previous.ts_epoch:
            errors.append(
                f"non_monotonic_event_ts:{previous.event}@{previous.ts_epoch}>{current.event}@{current.ts_epoch}"
            )
            break

    latest_run_id = str(latest.get("run_id") or "").strip()
    if latest and selected_run_id and latest_run_id and latest_run_id != selected_run_id:
        warnings.append(f"latest_run_id_mismatch:{latest_run_id}!={selected_run_id}")
    if latest and str(latest.get("is_order_action", False)).lower() == "true":
        errors.append("latest_payload_is_order_action_true")

    return EvidenceLoadResult(
        profile=profile,
        events_path=events_path,
        latest_path=latest_path,
        events=tuple(events),
        selected_run_id=selected_run_id,
        selected_boot_epoch=selected_boot_epoch,
        validation_errors=tuple(errors),
        validation_warnings=tuple(warnings),
    )
