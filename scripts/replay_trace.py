from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from core.observability.events import validate_event_payload

_ACTION_FIELD = "is_" + "order_action"
_BROKER_FIELD = "broker_" + "api_called"


class TraceReplayError(ValueError):
    """Raised when trace replay input is invalid or no replay target matches."""


@dataclass(frozen=True)
class TraceReplayResult:
    """Deterministic read-only replay result for one trace, candidate, or cycle."""

    filter_type: str
    filter_value: str
    event_count: int
    events: tuple[Mapping[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source": "tradebot.observability.trace_replay",
            _ACTION_FIELD: False,
            _BROKER_FIELD: False,
            "filter_type": self.filter_type,
            "filter_value": self.filter_value,
            "event_count": self.event_count,
            "summary": _summary(self.events),
            "events": [dict(event) for event in self.events],
        }


def replay_trace(
    events: Iterable[Mapping[str, object]],
    *,
    trace_id: str | None = None,
    candidate_id: str | None = None,
    cycle_id: str | None = None,
) -> TraceReplayResult:
    """Replay the deterministic observability path for one identifier.

    This function is pure/read-only. It validates serialized observability events,
    filters by exactly one target identifier, and returns the ordered event path.
    """

    filter_type, filter_value = _select_filter(
        trace_id=trace_id, candidate_id=candidate_id, cycle_id=cycle_id
    )
    normalized = _normalize_events(events)
    matched = tuple(
        event for event in normalized if str(event.get(filter_type, "")) == filter_value
    )
    if not matched:
        raise TraceReplayError(f"no_events_found:{filter_type}:{filter_value}")
    return TraceReplayResult(
        filter_type=filter_type,
        filter_value=filter_value,
        event_count=len(matched),
        events=matched,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay Tradebot observability events by trace, candidate, or cycle."
    )
    parser.add_argument(
        "--input",
        default="runtime/evidence/observability_events.jsonl",
        help="JSONL observability event file.",
    )
    parser.add_argument("--trace-id", help="Trace identifier to replay.")
    parser.add_argument("--candidate-id", help="Candidate identifier to replay.")
    parser.add_argument("--cycle-id", help="Cycle identifier to replay.")
    parser.add_argument(
        "--json", action="store_true", help="Print replay as JSON instead of text."
    )
    args = parser.parse_args(argv)

    try:
        result = replay_trace(
            _read_jsonl(Path(args.input)),
            trace_id=args.trace_id,
            candidate_id=args.candidate_id,
            cycle_id=args.cycle_id,
        )
    except (OSError, json.JSONDecodeError, TraceReplayError, ValueError) as exc:
        print(f"trace replay failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print(_render_text(result))
    return 0


def _select_filter(
    *, trace_id: str | None, candidate_id: str | None, cycle_id: str | None
) -> tuple[str, str]:
    values = {
        "trace_id": trace_id,
        "candidate_id": candidate_id,
        "cycle_id": cycle_id,
    }
    selected = [
        (key, str(value).strip())
        for key, value in values.items()
        if str(value or "").strip()
    ]
    if len(selected) != 1:
        raise TraceReplayError("exactly_one_replay_filter_required")
    return selected[0]


def _read_jsonl(path: Path) -> Iterable[Mapping[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise TraceReplayError(f"line_not_json_object:{line_number}")
            yield payload


def _normalize_events(
    events: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    normalized: list[dict[str, object]] = []
    for index, event in enumerate(events):
        payload = dict(event)
        try:
            validate_event_payload(payload)
        except ValueError as exc:
            raise TraceReplayError(f"invalid_event:{index}:{exc}") from exc
        normalized.append(payload)
    return tuple(sorted(normalized, key=_event_sort_key))


def _event_sort_key(item: Mapping[str, object]) -> tuple[str, str, str, str, str, str]:
    return (
        str(item.get("timestamp", "")),
        str(item.get("run_id", "")),
        str(item.get("cycle_id", "")),
        str(item.get("candidate_id", "")),
        str(item.get("event", "")),
        str(item.get("stage", "")),
    )


def _summary(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {
        "run_ids": _unique(events, "run_id"),
        "cycle_ids": _unique(events, "cycle_id"),
        "trace_ids": _unique(events, "trace_id"),
        "candidate_ids": _unique(events, "candidate_id"),
        "decisions": _counts(events, "decision"),
        "stages": _counts(events, "stage"),
        "reasons": _counts(events, "reason"),
        "contains_blocked_decision": any(
            str(event.get("decision", "")).lower() == "blocked" for event in events
        ),
        "contains_stale_feed": any(
            str(event.get("feed_state", "")).lower() in {"stale", "stale_feed"}
            for event in events
        ),
    }


def _render_text(result: TraceReplayResult) -> str:
    payload = result.as_dict()
    summary = payload["summary"]
    lines = [
        f"Trace replay: {result.filter_type}={result.filter_value}",
        f"Events: {result.event_count}",
        f"Decisions: {summary['decisions']}",
        f"Stages: {summary['stages']}",
        "Path:",
    ]
    for index, event in enumerate(result.events, start=1):
        reason = str(event.get("reason", "")).strip()
        reason_text = f" reason={reason}" if reason else ""
        lines.append(
            "{index}. {timestamp} stage={stage} event={event_name} decision={decision}{reason}".format(
                index=index,
                timestamp=event.get("timestamp", ""),
                stage=event.get("stage", ""),
                event_name=event.get("event", ""),
                decision=event.get("decision", ""),
                reason=reason_text,
            )
        )
    return "\n".join(lines)


def _unique(events: Sequence[Mapping[str, object]], field: str) -> list[str]:
    return sorted(
        {
            str(event.get(field, "")).strip()
            for event in events
            if str(event.get(field, "")).strip()
        }
    )


def _counts(events: Sequence[Mapping[str, object]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        value = str(event.get(field, "")).strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


if __name__ == "__main__":
    raise SystemExit(main())
