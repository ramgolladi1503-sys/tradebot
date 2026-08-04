from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .evidence_guardian import SourceContinuityCheckpoint


def _parse_time(value: object, *, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            raise ValueError(f"{name}_missing")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{name}_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name}_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _normalize_filters(value: object) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if value in (None, {}):
        return ()
    if not isinstance(value, Mapping):
        raise ValueError("source_file_spec_filters_must_be_object")
    normalized: list[tuple[str, tuple[str, ...]]] = []
    for raw_field, raw_allowed in sorted(value.items(), key=lambda item: str(item[0])):
        field = str(raw_field).strip()
        if not field:
            raise ValueError("source_file_spec_filter_field_missing")
        if isinstance(raw_allowed, (list, tuple, set)):
            values = tuple(str(item).strip() for item in raw_allowed if str(item).strip())
        else:
            single = str(raw_allowed).strip()
            values = (single,) if single else ()
        if not values:
            raise ValueError(f"source_file_spec_filter_values_missing={field}")
        normalized.append((field, tuple(sorted(set(values)))))
    return tuple(normalized)


@dataclass(frozen=True)
class SourceFileSpec:
    source_name: str
    path: Path
    identity_fields: tuple[str, ...]
    event_type_field: str
    source_time_field: str
    receive_time_field: str
    persist_time_field: str
    sequence_field: str | None = None
    required_event_types: tuple[str, ...] = ()
    filters: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        if not self.source_name.strip():
            raise ValueError("source_file_spec_name_missing")
        if not self.identity_fields:
            raise ValueError("source_file_spec_identity_fields_missing")
        for name in ("event_type_field", "source_time_field", "receive_time_field", "persist_time_field"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"source_file_spec_{name}_missing")
        object.__setattr__(self, "path", Path(self.path).expanduser())
        object.__setattr__(self, "identity_fields", tuple(str(value).strip() for value in self.identity_fields))
        object.__setattr__(self, "required_event_types", tuple(str(value).strip().upper() for value in self.required_event_types if str(value).strip()))
        object.__setattr__(self, "filters", _normalize_filters(dict(self.filters)))

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "SourceFileSpec":
        identity_fields = row.get("identity_fields")
        if not isinstance(identity_fields, list):
            raise ValueError("source_file_spec_identity_fields_must_be_list")
        required = row.get("required_event_types") or []
        if not isinstance(required, list):
            raise ValueError("source_file_spec_required_event_types_must_be_list")
        sequence_raw = str(row.get("sequence_field") or "").strip()
        filters = _normalize_filters(row.get("filters"))
        return cls(
            source_name=str(row.get("source_name") or ""),
            path=Path(str(row.get("path") or "")),
            identity_fields=tuple(str(value) for value in identity_fields),
            event_type_field=str(row.get("event_type_field") or "event_type"),
            source_time_field=str(row.get("source_time_field") or "source_time"),
            receive_time_field=str(row.get("receive_time_field") or "receive_time"),
            persist_time_field=str(row.get("persist_time_field") or "persist_time"),
            sequence_field=sequence_raw or None,
            required_event_types=tuple(str(value) for value in required),
            filters=filters,
        )

    def matches(self, payload: Mapping[str, object]) -> bool:
        for field, allowed_values in self.filters:
            if str(payload.get(field) or "").strip() not in allowed_values:
                return False
        return True


@dataclass(frozen=True)
class SourceScanResult:
    checkpoint: SourceContinuityCheckpoint
    path: str
    sha256: str
    file_bytes: int
    valid_row_count: int
    malformed_row_count: int
    duplicate_identity_count: int
    filtered_out_row_count: int
    partial_final_line_ignored: bool
    filters: tuple[tuple[str, tuple[str, ...]], ...]

    def to_record(self) -> dict[str, object]:
        record = self.checkpoint.__dict__.copy()
        for name in ("latest_source_time", "latest_receive_time", "latest_persist_time"):
            value = record[name]
            record[name] = value.isoformat() if isinstance(value, datetime) else None
        record["observed_event_types"] = list(self.checkpoint.observed_event_types)
        record["required_event_types"] = list(self.checkpoint.required_event_types)
        record.update(
            {
                "path": self.path,
                "sha256": self.sha256,
                "file_bytes": self.file_bytes,
                "valid_row_count": self.valid_row_count,
                "malformed_row_count": self.malformed_row_count,
                "duplicate_identity_count": self.duplicate_identity_count,
                "filtered_out_row_count": self.filtered_out_row_count,
                "partial_final_line_ignored": self.partial_final_line_ignored,
                "filters": {field: list(values) for field, values in self.filters},
            }
        )
        return record


def scan_source_file(spec: SourceFileSpec) -> SourceScanResult:
    if not spec.path.is_file():
        raise ValueError(f"source_checkpoint_path_not_file path={spec.path}")
    raw = spec.path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    partial = bool(raw) and not raw.endswith(b"\n")
    raw_lines = raw.splitlines()
    if partial and raw_lines:
        raw_lines = raw_lines[:-1]
    identities: set[tuple[str, ...]] = set()
    sequence_values: list[int] = []
    observed_event_types: set[str] = set()
    malformed = 0
    duplicates = 0
    filtered_out = 0
    valid_rows = 0
    latest_tuple: tuple[datetime, datetime, datetime] | None = None
    for line_number, raw_line in enumerate(raw_lines, start=1):
        text = raw_line.decode("utf-8").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(payload, Mapping):
            malformed += 1
            continue
        if not spec.matches(payload):
            filtered_out += 1
            continue
        try:
            identity = tuple(str(payload.get(field) or "").strip() for field in spec.identity_fields)
            if any(not value for value in identity):
                raise ValueError("identity_field_missing")
            event_type = str(payload.get(spec.event_type_field) or "").strip().upper()
            if not event_type:
                raise ValueError("event_type_missing")
            source_time = _parse_time(payload.get(spec.source_time_field), name=f"source_time_line_{line_number}")
            receive_time = _parse_time(payload.get(spec.receive_time_field), name=f"receive_time_line_{line_number}")
            persist_time = _parse_time(payload.get(spec.persist_time_field), name=f"persist_time_line_{line_number}")
            if receive_time < source_time or persist_time < receive_time:
                raise ValueError("causal_timestamp_order_invalid")
            if spec.sequence_field is not None:
                sequence_value = int(payload.get(spec.sequence_field))
                if sequence_value < 0:
                    raise ValueError("sequence_negative")
                sequence_values.append(sequence_value)
        except (TypeError, ValueError):
            malformed += 1
            continue
        if identity in identities:
            duplicates += 1
        else:
            identities.add(identity)
        observed_event_types.add(event_type)
        valid_rows += 1
        if latest_tuple is None or source_time > latest_tuple[0]:
            latest_tuple = (source_time, receive_time, persist_time)
    unique_sequences = sorted(set(sequence_values))
    first_sequence = unique_sequences[0] if unique_sequences else None
    last_sequence = unique_sequences[-1] if unique_sequences else None
    sequence_gap_events = 0
    if unique_sequences:
        sequence_gap_events = last_sequence - first_sequence + 1 - len(unique_sequences)
    latest_source = latest_tuple[0] if latest_tuple else None
    latest_receive = latest_tuple[1] if latest_tuple else None
    latest_persist = latest_tuple[2] if latest_tuple else None
    checkpoint = SourceContinuityCheckpoint(
        source_name=spec.source_name,
        observed_events=valid_rows,
        first_sequence=first_sequence,
        last_sequence=last_sequence,
        sequence_gap_events=sequence_gap_events,
        duplicate_events=duplicates,
        malformed_events=malformed,
        latest_source_time=latest_source,
        latest_receive_time=latest_receive,
        latest_persist_time=latest_persist,
        observed_event_types=tuple(sorted(observed_event_types)),
        required_event_types=spec.required_event_types,
    )
    return SourceScanResult(
        checkpoint=checkpoint,
        path=spec.path.as_posix(),
        sha256=digest,
        file_bytes=len(raw),
        valid_row_count=valid_rows,
        malformed_row_count=malformed,
        duplicate_identity_count=duplicates,
        filtered_out_row_count=filtered_out,
        partial_final_line_ignored=partial,
        filters=spec.filters,
    )


@dataclass(frozen=True)
class SourceCheckpointBundle:
    schema_version: str
    sources: tuple[SourceScanResult, ...]
    bundle_id: str

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sources": [source.to_record() for source in self.sources],
            "source_count": len(self.sources),
            "bundle_id": self.bundle_id,
        }


def build_source_checkpoint_bundle(specs: Sequence[SourceFileSpec]) -> SourceCheckpointBundle:
    if not specs:
        raise ValueError("source_checkpoint_specs_empty")
    names = [spec.source_name for spec in specs]
    if len(names) != len(set(names)):
        raise ValueError("source_checkpoint_duplicate_source_name")
    results = tuple(scan_source_file(spec) for spec in sorted(specs, key=lambda item: item.source_name))
    canonical = {
        "schema_version": "1.0.0",
        "sources": [result.to_record() for result in results],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
    bundle_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return SourceCheckpointBundle("1.0.0", results, bundle_id)
