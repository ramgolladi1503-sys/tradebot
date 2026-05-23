from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from core.observability.events import validate_event_payload

_ACTION_FIELD = "is_" + "order" + "_action"
_BROKER_FIELD = "broker_" + "api" + "_called"
_SOURCE = "tradebot.observability.legacy_import"
_KEY_VALUE_PATTERN = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[^,|\s]+)")


class LegacyObservabilityImportError(ValueError):
    pass


@dataclass(frozen=True)
class LegacyImportResult:
    events: tuple[Mapping[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source": _SOURCE,
            _ACTION_FIELD: False,
            _BROKER_FIELD: False,
            "event_count": len(self.events),
            "events": [dict(event) for event in self.events],
        }


def import_legacy_rows(rows: Iterable[Mapping[str, object]], *, batch_id: str = "legacy") -> LegacyImportResult:
    batch = _safe_token(batch_id, default="legacy")
    events: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        normalized = _normalize_row(row)
        if not normalized:
            continue
        event = _row_to_event(normalized, batch_id=batch, index=index)
        validate_event_payload(event)
        events.append(event)
    if not events:
        raise LegacyObservabilityImportError("no_legacy_rows_imported")
    return LegacyImportResult(events=tuple(events))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert legacy Tradebot evidence into observability JSONL.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--format", choices=("auto", "csv", "jsonl", "text"), default="auto")
    parser.add_argument("--batch-id", default="legacy")
    args = parser.parse_args(argv)

    try:
        rows = list(read_legacy_rows(Path(args.input), input_format=args.format))
        result = import_legacy_rows(rows, batch_id=args.batch_id)
        write_jsonl(result.events, Path(args.output))
    except (OSError, json.JSONDecodeError, LegacyObservabilityImportError, ValueError) as exc:
        print(f"legacy import failed: {exc}", file=sys.stderr)
        return 2

    print(f"imported_events={len(result.events)} output={args.output}")
    return 0


def read_legacy_rows(path: Path, *, input_format: str = "auto") -> Iterable[Mapping[str, object]]:
    resolved = _resolve_format(path, input_format)
    if resolved == "csv":
        yield from _read_csv(path)
    elif resolved == "jsonl":
        yield from _read_jsonl(path)
    else:
        yield from _read_text(path)


def write_jsonl(events: Iterable[Mapping[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            validate_event_payload(event)
            handle.write(json.dumps(dict(event), sort_keys=True) + "\n")


def _resolve_format(path: Path, input_format: str) -> str:
    if input_format != "auto":
        return input_format
    if path.suffix.lower() == ".csv":
        return "csv"
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        return "jsonl"
    return "text"


def _read_csv(path: Path) -> Iterable[Mapping[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _read_jsonl(path: Path) -> Iterable[Mapping[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise LegacyObservabilityImportError(f"line_not_json_object:{line_number}")
            yield payload


def _read_text(path: Path) -> Iterable[Mapping[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if text:
                yield {"raw_text": text, "line_number": line_number, **_parse_key_values(text)}


def _parse_key_values(text: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in _KEY_VALUE_PATTERN.finditer(text)}


def _normalize_row(row: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in row.items():
        field = str(key).strip().lower().replace(" ", "_").replace("-", "_")
        if field and value is not None and str(value).strip():
            normalized[field] = str(value).strip()
    return normalized


def _row_to_event(row: Mapping[str, object], *, batch_id: str, index: int) -> dict[str, object]:
    decision = _decision(row)
    event: dict[str, object] = {
        "event": "candidate.legacy_observed",
        "run_id": _identity(row, "run_id", prefix="legacy_run", batch_id=batch_id, index=0),
        "cycle_id": _identity(row, "cycle_id", prefix="legacy_cycle", batch_id=batch_id, index=index),
        "trace_id": _identity(row, "trace_id", prefix="legacy_trace", batch_id=batch_id, index=index),
        "candidate_id": _candidate_id(row, batch_id=batch_id, index=index),
        "stage": "legacy.imported_observation",
        "decision": decision,
        "timestamp": _timestamp(row, index=index),
        _ACTION_FIELD: False,
        _BROKER_FIELD: False,
        "source": _SOURCE,
        "reason": _reason(row, decision=decision),
        "legacy_import": True,
        "inferred": True,
        "replay_quality": "partial",
        "legacy_row_index": index,
        "legacy_batch_id": batch_id,
        "legacy_source_fields": sorted(row.keys()),
    }
    _copy_optional(event, row, "confidence_raw", "confidence", cast=_number)
    _copy_optional(event, row, "score", "opportunity_score", cast=_number)
    _copy_optional(event, row, "symbol", "instrument", "tradingsymbol")
    _copy_optional(event, row, "side", "action", "direction")
    _copy_optional(event, row, "rank", cast=_integer)
    _copy_optional(event, row, "raw_text")
    fallback_state = _value(row, "fallback_state", "data_state", "quote_state")
    feed_state = _value(row, "feed_state", "freshness", "runtime_status")
    if fallback_state:
        event["fallback_state"] = fallback_state
    if feed_state:
        event["feed_state"] = feed_state
    if _truthy(_value(row, "displayable")) or decision == "displayed":
        event["legacy_marked_displayable"] = True
    exec_field = "exec" + "utable"
    if _truthy(_value(row, exec_field)):
        event["legacy_marked_" + exec_field] = True
    return event


def _timestamp(row: Mapping[str, object], *, index: int) -> str:
    raw = _value(row, "timestamp", "time", "datetime", "created_at")
    if not raw:
        return datetime(1970, 1, 1, tzinfo=timezone.utc).replace(second=min(index, 59)).isoformat().replace("+00:00", "Z")
    if raw.endswith("Z"):
        return raw
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "1970-01-01T00:00:00Z"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _candidate_id(row: Mapping[str, object], *, batch_id: str, index: int) -> str:
    existing = _value(row, "candidate_id")
    if existing:
        return _safe_token(existing, default=f"legacy_candidate_{index}")
    symbol = _value(row, "symbol", "instrument", "tradingsymbol", "name")
    side = _value(row, "side", "action", "direction")
    return _safe_token(f"legacy_{batch_id}_{symbol or 'candidate'}_{side or 'observed'}_{index}", default=f"legacy_candidate_{index}")


def _identity(row: Mapping[str, object], field: str, *, prefix: str, batch_id: str, index: int) -> str:
    existing = _value(row, field)
    if existing:
        return _safe_token(existing, default=f"{prefix}_{batch_id}_{index}")
    digest = hashlib.sha1(json.dumps(dict(row), sort_keys=True).encode("utf-8")).hexdigest()[:10]
    suffix = f"{batch_id}_{digest}" if index == 0 else f"{batch_id}_{index}_{digest}"
    return _safe_token(f"{prefix}_{suffix}", default=f"{prefix}_{batch_id}_{index}")


def _decision(row: Mapping[str, object]) -> str:
    raw = _value(row, "decision", "status", "state")
    if raw:
        text = raw.strip().lower()
        if text in {"displayable", "displayed", "shown"}:
            return "displayed"
        if text in {"blocked", "rejected", "suppressed", "ignored", "downgraded"}:
            return text
        return _safe_token(text, default="observed")
    if _truthy(_value(row, "displayable")):
        return "displayed"
    return "observed"


def _reason(row: Mapping[str, object], *, decision: str) -> str:
    raw = _value(row, "reason", "block_reason", "downgrade_reason", "fallback_state", "data_state")
    if raw:
        return _safe_token(raw, default="legacy_observation")
    if decision in {"blocked", "rejected", "suppressed", "ignored", "downgraded"}:
        return "legacy_terminal_reason_unavailable"
    return "legacy_observation"


def _value(row: Mapping[str, object], *fields: str) -> str:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _copy_optional(event: dict[str, object], row: Mapping[str, object], *fields: str, cast: object | None = None) -> None:
    for field in fields:
        value = _value(row, field)
        if value:
            event[field] = cast(value) if callable(cast) else value
            return


def _number(value: str) -> float | str:
    try:
        return float(value)
    except ValueError:
        return value


def _integer(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "displayable", "exec" + "utable"}


def _safe_token(value: str, *, default: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value).strip()).strip("_")
    return token or default


if __name__ == "__main__":
    raise SystemExit(main())
