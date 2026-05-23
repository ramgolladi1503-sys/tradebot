from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from core.observability.events import ObservabilityEventError, validate_event_payload

EVIDENCE_FILENAMES = (
    "observability_summary.json",
    "candidate_decision_funnel.json",
    "fallback_safety_report.json",
    "feed_freshness_report.json",
    "latency_breakdown.json",
)

_ACTION_FIELD = "is_" + "order_action"
_BROKER_FIELD = "broker_" + "api_called"
_TERMINAL_DECISIONS = frozenset({"ranked", "blocked", "downgraded", "displayed", "paper_ready", "paper_submitted", "ignored"})
_FALLBACK_STATES = frozenset({"recovered_fallback", "fallback_recovered"})
_STALE_FEED_STATES = frozenset({"stale", "stale_feed"})


class ObservabilityEvidenceBundleError(ValueError):
    """Raised when observability evidence cannot be built safely."""


@dataclass(frozen=True)
class ObservabilityEvidenceBundle:
    """Deterministic review bundle built from existing observability events."""

    reports: Mapping[str, Mapping[str, object]]

    def as_dict(self) -> dict[str, Mapping[str, object]]:
        return {name: dict(self.reports[name]) for name in sorted(self.reports)}


def build_observability_evidence_bundle(events: Iterable[Mapping[str, object]]) -> ObservabilityEvidenceBundle:
    """Build the five PR-OBS-12 evidence reports from serialized events.

    The function is pure/read-only. It validates supplied observability events,
    derives deterministic summaries, and does not inspect runtime state or
    mutate trading behavior.
    """

    normalized = _normalize_events(events)
    reports: dict[str, Mapping[str, object]] = {
        "observability_summary.json": _observability_summary(normalized),
        "candidate_decision_funnel.json": _candidate_decision_funnel(normalized),
        "fallback_safety_report.json": _fallback_safety_report(normalized),
        "feed_freshness_report.json": _feed_freshness_report(normalized),
        "latency_breakdown.json": _latency_breakdown(normalized),
    }
    return ObservabilityEvidenceBundle(reports=reports)


def write_observability_evidence_bundle(
    events: Iterable[Mapping[str, object]],
    output_dir: str | Path = "runtime/evidence",
) -> dict[str, Path]:
    """Write deterministic PR-OBS-12 evidence JSON files."""

    bundle = build_observability_evidence_bundle(events)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    for filename in EVIDENCE_FILENAMES:
        path = target / filename
        path.write_text(json.dumps(bundle.reports[filename], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[filename] = path
    return written


def _normalize_events(events: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, event in enumerate(events):
        payload = dict(event)
        try:
            validate_event_payload(payload)
        except ObservabilityEventError as exc:
            raise ObservabilityEvidenceBundleError(f"invalid_event:{index}:{exc}") from exc
        normalized.append(payload)
    return sorted(normalized, key=_event_sort_key)


def _event_sort_key(item: Mapping[str, object]) -> tuple[str, str, str, str, str, str]:
    return (
        str(item.get("timestamp", "")),
        str(item.get("run_id", "")),
        str(item.get("cycle_id", "")),
        str(item.get("candidate_id", "")),
        str(item.get("event", "")),
        str(item.get("stage", "")),
    )


def _base_report(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "source": "tradebot.observability.evidence_bundle",
        _ACTION_FIELD: False,
        _BROKER_FIELD: False,
    }
    payload.update(extra)
    return payload


def _observability_summary(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return _base_report(
        event_count=len(events),
        run_count=len(_unique_values(events, "run_id")),
        cycle_count=len(_unique_values(events, "cycle_id")),
        candidate_count=len(_unique_values(events, "candidate_id")),
        runs=_unique_values(events, "run_id"),
        cycles=_unique_values(events, "cycle_id"),
        decisions=_counts_by(events, "decision"),
        stages=_counts_by(events, "stage"),
        reasons=_counts_by(events, "reason"),
    )


def _candidate_decision_funnel(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    candidate_events = [event for event in events if str(event.get("candidate_id", "")).strip()]
    grouped: dict[str, list[Mapping[str, object]]] = {}
    for event in candidate_events:
        grouped.setdefault(str(event["candidate_id"]), []).append(event)

    missing_terminal: list[str] = []
    paths: list[dict[str, object]] = []
    for candidate_id in sorted(grouped):
        path_events = grouped[candidate_id]
        decisions = [str(event.get("decision", "")) for event in path_events]
        terminal_present = any(decision in _TERMINAL_DECISIONS for decision in decisions)
        if not terminal_present:
            missing_terminal.append(candidate_id)
        paths.append(
            {
                "candidate_id": candidate_id,
                "event_count": len(path_events),
                "stages": [str(event.get("stage", "")) for event in path_events],
                "decisions": decisions,
                "terminal_state_present": terminal_present,
                "last_decision": decisions[-1] if decisions else "",
            }
        )

    return _base_report(
        candidate_count=len(grouped),
        funnel=_counts_by(candidate_events, "decision"),
        stage_counts=_counts_by(candidate_events, "stage"),
        candidate_paths=paths,
        missing_terminal_state_candidates=missing_terminal,
        complete=not missing_terminal,
    )


def _fallback_safety_report(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    fallback_events = [event for event in events if _is_fallback_event(event)]
    violations = [_event_ref(event) for event in fallback_events if _is_executable(event)]
    return _base_report(
        fallback_event_count=len(fallback_events),
        fallback_candidate_count=len(_unique_values(fallback_events, "candidate_id")),
        fallback_executable_count=len(violations),
        fallback_executable_violations=violations,
        safe=not violations,
    )


def _feed_freshness_report(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    feed_events = [event for event in events if "feed_age_ms" in event or str(event.get("feed_state", "")).strip()]
    stale_events = [event for event in feed_events if _is_stale_feed(event)]
    violations = [_event_ref(event) for event in stale_events if _is_executable(event)]
    feed_ages = [_number(event.get("feed_age_ms")) for event in feed_events]
    feed_ages = [value for value in feed_ages if value is not None]
    return _base_report(
        feed_event_count=len(feed_events),
        fresh_event_count=sum(1 for event in feed_events if str(event.get("feed_state", "")).lower() == "fresh"),
        stale_event_count=len(stale_events),
        max_feed_age_ms=max(feed_ages) if feed_ages else None,
        stale_executable_count=len(violations),
        stale_executable_violations=violations,
        safe=not violations,
    )


def _latency_breakdown(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    by_stage: dict[str, list[float]] = {}
    for event in events:
        latency = _number(event.get("latency_ms"))
        if latency is not None:
            by_stage.setdefault(str(event.get("stage", "")), []).append(latency)

    stages: list[dict[str, object]] = []
    for stage in sorted(by_stage):
        values = sorted(by_stage[stage])
        stages.append(
            {
                "stage": stage,
                "count": len(values),
                "min_latency_ms": values[0],
                "max_latency_ms": values[-1],
                "avg_latency_ms": sum(values) / len(values),
            }
        )
    return _base_report(latency_event_count=sum(int(item["count"]) for item in stages), stages=stages)


def _counts_by(events: Sequence[Mapping[str, object]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        value = str(event.get(field_name, "")).strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _unique_values(events: Sequence[Mapping[str, object]], field_name: str) -> list[str]:
    return sorted({str(event.get(field_name, "")).strip() for event in events if str(event.get(field_name, "")).strip()})


def _is_fallback_event(event: Mapping[str, object]) -> bool:
    return str(event.get("fallback_state", "")).strip().lower() in _FALLBACK_STATES


def _is_stale_feed(event: Mapping[str, object]) -> bool:
    return str(event.get("feed_state", "")).strip().lower() in _STALE_FEED_STATES


def _is_executable(event: Mapping[str, object]) -> bool:
    decision = str(event.get("decision", "")).strip().lower()
    executable = event.get("executable")
    return decision == "executable" or executable is True or str(executable).strip().lower() == "true"


def _event_ref(event: Mapping[str, object]) -> dict[str, object]:
    return {
        "event": str(event.get("event", "")),
        "run_id": str(event.get("run_id", "")),
        "cycle_id": str(event.get("cycle_id", "")),
        "trace_id": str(event.get("trace_id", "")),
        "candidate_id": str(event.get("candidate_id", "")),
        "stage": str(event.get("stage", "")),
        "decision": str(event.get("decision", "")),
        "reason": str(event.get("reason", "")),
    }


def _number(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "EVIDENCE_FILENAMES",
    "ObservabilityEvidenceBundle",
    "ObservabilityEvidenceBundleError",
    "build_observability_evidence_bundle",
    "write_observability_evidence_bundle",
]
