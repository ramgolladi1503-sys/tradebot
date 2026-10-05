from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from statistics import median
from typing import Any, Iterable, Mapping
import math

from .contracts import CanonicalEvent


VALID = "VALID_RESEARCH_CAPTURE"
PARTIAL = "PARTIAL_CAPTURE"
INVALID = "INVALID_CAPTURE"
_CONTROL_EVENT_TYPES = frozenset({"SESSION_STARTED", "SESSION_ENDED"})
_COVERAGE_EXCLUDED_TYPES = frozenset({
    "SESSION_STARTED", "SESSION_ENDED", "INCIDENT_RAISED", "OBSERVER_STOPPED"
})


@dataclass(frozen=True, slots=True)
class SessionManifest:
    session_id: str
    verdict: str
    reason_codes: tuple[str, ...]
    event_count: int
    unique_event_count: int
    duplicate_event_ids: int
    conflicting_duplicate_ids: int
    event_type_counts: Mapping[str, int]
    producer_counts: Mapping[str, int]
    instrument_count: int
    observed_instruments: tuple[str, ...]
    missing_expected_instruments: tuple[str, ...]
    missing_expected_event_types: tuple[str, ...]
    producer_sequence_gaps: Mapping[str, tuple[int, ...]]
    producer_sequence_regressions: Mapping[str, int]
    lookahead_violations: int
    timestamp_order_violations: int
    source_to_receive_latency_ms: Mapping[str, float | None]
    receive_to_persist_latency_ms: Mapping[str, float | None]
    event_time_start: str | None
    event_time_end: str | None
    declared_start: str | None
    declared_end: str | None
    coverage_ratio: float | None
    expected_counts: Mapping[str, int]
    reconciled_counts: Mapping[str, bool]
    data_quality_states: Mapping[str, int]
    authority_classes: Mapping[str, int]
    schema_versions: Mapping[str, int]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _empty_manifest() -> SessionManifest:
    return SessionManifest(
        session_id="",
        verdict=INVALID,
        reason_codes=("NO_EVENTS",),
        event_count=0,
        unique_event_count=0,
        duplicate_event_ids=0,
        conflicting_duplicate_ids=0,
        event_type_counts={},
        producer_counts={},
        instrument_count=0,
        observed_instruments=(),
        missing_expected_instruments=(),
        missing_expected_event_types=("SESSION_STARTED", "SESSION_ENDED"),
        producer_sequence_gaps={},
        producer_sequence_regressions={},
        lookahead_violations=0,
        timestamp_order_violations=0,
        source_to_receive_latency_ms=_latency_summary([]),
        receive_to_persist_latency_ms=_latency_summary([]),
        event_time_start=None,
        event_time_end=None,
        declared_start=None,
        declared_end=None,
        coverage_ratio=None,
        expected_counts={},
        reconciled_counts={},
        data_quality_states={},
        authority_classes={},
        schema_versions={},
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _float_ms(seconds: float) -> float:
    return round(seconds * 1000.0, 6)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    return {
        "count": float(len(values)),
        "min": round(min(values), 6) if values else None,
        "median": round(median(values), 6) if values else None,
        "p95": round(_percentile(values, 0.95), 6) if values else None,
        "p99": round(_percentile(values, 0.99), 6) if values else None,
        "max": round(max(values), 6) if values else None,
    }


def _session_contract(events: tuple[CanonicalEvent, ...]) -> tuple[dict[str, Any], dict[str, Any]]:
    starts = [event for event in events if event.event_type == "SESSION_STARTED"]
    ends = [event for event in events if event.event_type == "SESSION_ENDED"]
    start_payload = dict(starts[0].payload) if starts else {}
    end_payload = dict(ends[-1].payload) if ends else {}
    return start_payload, end_payload


def _declared_datetime(payload: Mapping[str, Any], key: str) -> datetime | None:
    value = payload.get(key)
    if not value:
        return None
    from .contracts import parse_timestamp

    return parse_timestamp(value, field_name=key)


def _deduplicate(
    events: tuple[CanonicalEvent, ...],
) -> tuple[tuple[CanonicalEvent, ...], int, int]:
    by_id: dict[str, CanonicalEvent] = {}
    duplicates = 0
    conflicts = 0
    for event in events:
        existing = by_id.get(event.event_id)
        if existing is None:
            by_id[event.event_id] = event
            continue
        duplicates += 1
        if existing.to_json() != event.to_json():
            conflicts += 1
    return tuple(by_id.values()), duplicates, conflicts


def validate_session(events: Iterable[CanonicalEvent]) -> SessionManifest:
    raw_events = tuple(events)
    if not raw_events:
        return _empty_manifest()

    materialized, duplicate_event_ids, conflicting_duplicate_ids = _deduplicate(raw_events)
    reason_codes: list[str] = []
    warnings: list[str] = []
    if conflicting_duplicate_ids:
        reason_codes.append("CONFLICTING_DUPLICATE_EVENT_ID")
    elif duplicate_event_ids:
        warnings.append("IDEMPOTENT_DUPLICATES_DEDUPLICATED")

    session_ids = {event.session_id for event in materialized}
    if len(session_ids) != 1:
        reason_codes.append("MULTIPLE_SESSION_IDS")
    session_id = sorted(session_ids)[0] if session_ids else ""

    event_type_counts = Counter(event.event_type for event in materialized)
    producer_counts = Counter(event.producer_id or event.source_component for event in materialized)
    quality_counts = Counter(event.data_quality_state for event in materialized)
    authority_counts = Counter(event.authority_class for event in materialized)
    schema_counts = Counter(event.schema_version for event in materialized)

    starts = event_type_counts.get("SESSION_STARTED", 0)
    ends = event_type_counts.get("SESSION_ENDED", 0)
    if starts != 1:
        reason_codes.append("SESSION_STARTED_COUNT_INVALID")
    if ends != 1:
        reason_codes.append("SESSION_ENDED_COUNT_INVALID")

    start_payload, end_payload = _session_contract(materialized)
    expected_instruments = tuple(
        sorted({str(value) for value in start_payload.get("expected_instruments", []) if str(value)})
    )
    observed_instruments = tuple(sorted({event.instrument_key for event in materialized if event.instrument_key}))
    missing_expected_instruments = tuple(sorted(set(expected_instruments) - set(observed_instruments)))
    if missing_expected_instruments:
        reason_codes.append("EXPECTED_INSTRUMENTS_MISSING")

    expected_event_types = {
        str(value) for value in start_payload.get("expected_event_types", []) if str(value)
    }
    expected_event_types.update(_CONTROL_EVENT_TYPES)
    missing_expected_event_types = tuple(
        sorted(value for value in expected_event_types if event_type_counts.get(value, 0) == 0)
    )
    if missing_expected_event_types:
        reason_codes.append("EXPECTED_EVENT_TYPES_MISSING")

    sequence_values: dict[str, list[int]] = defaultdict(list)
    sequence_regressions: dict[str, int] = defaultdict(int)
    events_by_producer: dict[str, list[CanonicalEvent]] = defaultdict(list)
    for event in materialized:
        producer = event.producer_id or event.source_component
        events_by_producer[producer].append(event)
        if event.producer_sequence:
            sequence_values[producer].append(event.producer_sequence)

    sequence_gaps: dict[str, tuple[int, ...]] = {}
    for producer, values in sequence_values.items():
        unique_sequences = sorted(set(values))
        gaps: list[int] = []
        for previous_sequence, current_sequence in zip(unique_sequences, unique_sequences[1:]):
            if current_sequence > previous_sequence + 1:
                gaps.extend(range(previous_sequence + 1, current_sequence))
        if gaps:
            sequence_gaps[producer] = tuple(gaps)
        previous_sequence: int | None = None
        for event in events_by_producer[producer]:
            if not event.producer_sequence:
                continue
            if previous_sequence is not None and event.producer_sequence < previous_sequence:
                sequence_regressions[producer] += 1
            previous_sequence = event.producer_sequence
    if sequence_gaps:
        reason_codes.append("PRODUCER_SEQUENCE_GAP")
    if sequence_regressions:
        reason_codes.append("PRODUCER_SEQUENCE_REGRESSION")

    lookahead_violations = 0
    timestamp_order_violations = 0
    source_latencies: list[float] = []
    persist_latencies: list[float] = []
    for event in materialized:
        if event.event_type in {"STRATEGY_EVALUATED", "SIGNAL_GENERATED", "CANDIDATE_CREATED"}:
            feature_times = event.payload.get("feature_available_times") or {}
            if isinstance(feature_times, Mapping):
                from .contracts import parse_timestamp

                for name, value in feature_times.items():
                    try:
                        feature_time = parse_timestamp(value, field_name=f"feature_available_times.{name}")
                    except Exception:
                        lookahead_violations += 1
                        continue
                    if feature_time > event.event_time:
                        lookahead_violations += 1
        if not (
            event.event_time <= event.available_time <= event.persist_time
            and event.receive_time <= event.available_time
            and event.receive_time <= event.parse_time <= event.persist_time
        ):
            timestamp_order_violations += 1
        if event.source_time is not None:
            source_latencies.append(_float_ms((event.receive_time - event.source_time).total_seconds()))
        persist_latencies.append(_float_ms((event.persist_time - event.receive_time).total_seconds()))
    if lookahead_violations:
        reason_codes.append("LOOKAHEAD_VIOLATION")
    if timestamp_order_violations:
        reason_codes.append("TIMESTAMP_ORDER_VIOLATION")

    observational_events = tuple(
        event for event in materialized if event.event_type not in _COVERAGE_EXCLUDED_TYPES
    )
    if not observational_events:
        reason_codes.append("NO_OBSERVATIONAL_EVENTS")
        event_start = None
        event_end = None
    else:
        event_start = min(event.event_time for event in observational_events)
        event_end = max(event.event_time for event in observational_events)

    declared_start = _declared_datetime(start_payload, "declared_start")
    declared_end = _declared_datetime(start_payload, "declared_end")
    coverage_ratio: float | None = None
    if declared_start and declared_end and declared_end > declared_start and event_start and event_end:
        observed_start = max(event_start, declared_start)
        observed_end = min(event_end, declared_end)
        covered = max(0.0, (observed_end - observed_start).total_seconds())
        total = (declared_end - declared_start).total_seconds()
        coverage_ratio = round(covered / total, 9)
        if event_start > declared_start or event_end < declared_end:
            reason_codes.append("DECLARED_TIME_COVERAGE_INCOMPLETE")

    expected_counts_raw = end_payload.get("expected_producer_counts") or {}
    expected_counts = (
        {
            str(key): int(value)
            for key, value in expected_counts_raw.items()
            if isinstance(value, (int, float)) and int(value) >= 0
        }
        if isinstance(expected_counts_raw, Mapping)
        else {}
    )
    reconciled_counts = {
        producer: producer_counts.get(producer, 0) == expected
        for producer, expected in expected_counts.items()
    }
    if any(not passed for passed in reconciled_counts.values()):
        reason_codes.append("PRODUCER_COUNT_RECONCILIATION_FAILED")

    fatal_reasons = {
        "NO_EVENTS",
        "NO_OBSERVATIONAL_EVENTS",
        "MULTIPLE_SESSION_IDS",
        "CONFLICTING_DUPLICATE_EVENT_ID",
        "SESSION_STARTED_COUNT_INVALID",
        "SESSION_ENDED_COUNT_INVALID",
        "LOOKAHEAD_VIOLATION",
        "TIMESTAMP_ORDER_VIOLATION",
        "PRODUCER_SEQUENCE_GAP",
        "PRODUCER_SEQUENCE_REGRESSION",
        "PRODUCER_COUNT_RECONCILIATION_FAILED",
    }
    partial_reasons = {
        "EXPECTED_INSTRUMENTS_MISSING",
        "EXPECTED_EVENT_TYPES_MISSING",
        "DECLARED_TIME_COVERAGE_INCOMPLETE",
    }

    if any(reason in fatal_reasons for reason in reason_codes):
        verdict = INVALID
    elif any(reason in partial_reasons for reason in reason_codes):
        verdict = PARTIAL
    else:
        verdict = VALID

    return SessionManifest(
        session_id=session_id,
        verdict=verdict,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        event_count=len(raw_events),
        unique_event_count=len(materialized),
        duplicate_event_ids=duplicate_event_ids,
        conflicting_duplicate_ids=conflicting_duplicate_ids,
        event_type_counts=dict(sorted(event_type_counts.items())),
        producer_counts=dict(sorted(producer_counts.items())),
        instrument_count=len(observed_instruments),
        observed_instruments=observed_instruments,
        missing_expected_instruments=missing_expected_instruments,
        missing_expected_event_types=missing_expected_event_types,
        producer_sequence_gaps=dict(sorted(sequence_gaps.items())),
        producer_sequence_regressions=dict(sorted(sequence_regressions.items())),
        lookahead_violations=lookahead_violations,
        timestamp_order_violations=timestamp_order_violations,
        source_to_receive_latency_ms=_latency_summary(source_latencies),
        receive_to_persist_latency_ms=_latency_summary(persist_latencies),
        event_time_start=_iso(event_start),
        event_time_end=_iso(event_end),
        declared_start=_iso(declared_start),
        declared_end=_iso(declared_end),
        coverage_ratio=coverage_ratio,
        expected_counts=expected_counts,
        reconciled_counts=reconciled_counts,
        data_quality_states=dict(sorted(quality_counts.items())),
        authority_classes=dict(sorted(authority_counts.items())),
        schema_versions=dict(sorted(schema_counts.items())),
        warnings=tuple(warnings),
    )
