from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import CanonicalEvent, EventValidationError
from .safe_publish import NonBlockingPublisher
from .tradebot_adapter import candidate_lineage_to_event, truth_snapshot_to_event


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        raw = float(value)
        if raw > 1_000_000_000_000:
            raw /= 1000.0
        parsed = datetime.fromtimestamp(raw, tz=timezone.utc)
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise EventValidationError("invalid_sidecar_event_time") from exc
    else:
        raise EventValidationError("missing_sidecar_event_time")
    if parsed.tzinfo is None:
        raise EventValidationError("naive_sidecar_event_time")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class JsonlSource:
    path: Path
    source_type: str
    source_component: str
    event_type: str = ""

    def __post_init__(self) -> None:
        if self.source_type not in {"candidate_lineage", "truth"}:
            raise ValueError("unsupported_source_type")
        if not self.source_component.strip():
            raise ValueError("source_component_missing")
        if self.source_type == "truth" and not self.event_type:
            raise ValueError("truth_source_requires_event_type")


@dataclass(frozen=True)
class SidecarConfig:
    session_id: str
    run_id: str
    mode: str
    sources: tuple[JsonlSource, ...]
    poll_interval_seconds: float
    start_at_end: bool = False
    session_start_time: datetime | None = None
    session_end_time: datetime | None = None

    def __post_init__(self) -> None:
        if not self.session_id or not self.run_id:
            raise ValueError("missing_session_identity")
        if self.mode.upper() not in {"PAPER", "SHADOW"}:
            raise ValueError("sidecar_mode_must_be_paper_or_shadow")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_must_be_positive")
        if not self.sources:
            raise ValueError("at_least_one_source_required")
        if (self.session_start_time is None) != (self.session_end_time is None):
            raise ValueError("session_boundaries_must_be_paired")
        if self.session_start_time is not None and self.session_end_time is not None:
            start = _parse_datetime(self.session_start_time)
            end = _parse_datetime(self.session_end_time)
            if end < start:
                raise ValueError("session_boundaries_invalid")
            object.__setattr__(self, "session_start_time", start)
            object.__setattr__(self, "session_end_time", end)

    @classmethod
    def from_json(cls, path: str | Path) -> "SidecarConfig":
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        if "start_at_end" not in record:
            raise ValueError("sidecar_config_requires_start_at_end")
        sources = tuple(
            JsonlSource(
                path=Path(item["path"]).expanduser(),
                source_type=str(item["source_type"]),
                source_component=str(item["source_component"]),
                event_type=str(item.get("event_type") or ""),
            )
            for item in record.get("sources", [])
        )
        start_raw = record.get("session_start_time")
        end_raw = record.get("session_end_time")
        return cls(
            session_id=str(record.get("session_id") or ""),
            run_id=str(record.get("run_id") or ""),
            mode=str(record.get("mode") or ""),
            sources=sources,
            poll_interval_seconds=float(record.get("poll_interval_seconds")),
            start_at_end=bool(record.get("start_at_end")),
            session_start_time=_parse_datetime(start_raw) if start_raw is not None else None,
            session_end_time=_parse_datetime(end_raw) if end_raw is not None else None,
        )


class JsonlTailer:
    def __init__(self) -> None:
        self._offsets: dict[Path, int] = {}
        self._remainders: dict[Path, str] = {}

    def initialize(self, path: Path, *, start_at_end: bool) -> None:
        if path in self._offsets:
            return
        self._offsets[path] = path.stat().st_size if start_at_end and path.exists() else 0
        self._remainders[path] = ""

    def read_new(self, path: Path) -> list[dict[str, Any]]:
        if path not in self._offsets:
            self.initialize(path, start_at_end=False)
        if not path.exists():
            return []
        offset = self._offsets.get(path, 0)
        size = path.stat().st_size
        if size < offset:
            offset = 0
            self._remainders[path] = ""
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            chunk = handle.read()
            self._offsets[path] = handle.tell()
        text = self._remainders.get(path, "") + chunk
        lines = text.split("\n")
        self._remainders[path] = lines.pop() if lines else ""
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_jsonl_record:{path}:{line_number}") from exc
            if not isinstance(value, Mapping):
                raise ValueError(f"jsonl_record_not_object:{path}:{line_number}")
            records.append(dict(value))
        return records


class LiveSidecar:
    def __init__(
        self,
        config: SidecarConfig,
        publisher: NonBlockingPublisher,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.publisher = publisher
        self.clock = clock or (lambda: datetime.now(tz=timezone.utc))
        self.tailer = JsonlTailer()
        self._sequence_by_component: dict[str, int] = {}
        self._started = False

    def _next_sequence(self, component: str) -> int:
        value = self._sequence_by_component.get(component, 0) + 1
        self._sequence_by_component[component] = value
        return value

    def _boundary_time(self, event_type: str) -> datetime:
        if event_type == "SESSION_STARTED" and self.config.session_start_time is not None:
            return self.config.session_start_time
        if event_type == "SESSION_ENDED" and self.config.session_end_time is not None:
            return self.config.session_end_time
        return self.clock()

    def _publish_lifecycle(self, event_type: str) -> None:
        component = "aixion_trade_intelligence.live_sidecar"
        occurred = self._boundary_time(event_type)
        now = self.clock()
        if now < occurred:
            now = occurred
        event = truth_snapshot_to_event(
            {"mode": self.config.mode, "data_quality_state": "VALID", "start_at_end": self.config.start_at_end},
            event_type=event_type,
            session_id=self.config.session_id,
            run_id=self.config.run_id,
            source_component=component,
            event_time=occurred,
            receive_time=now,
            persist_time=now,
            producer_sequence=self._next_sequence(component),
        )
        self.publisher.publish(event)

    def start(self) -> None:
        if self._started:
            return
        for source in self.config.sources:
            self.tailer.initialize(source.path, start_at_end=self.config.start_at_end)
        self._publish_lifecycle("SESSION_STARTED")
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._publish_lifecycle("SESSION_ENDED")
        self._started = False

    def poll_once(self) -> dict[str, int]:
        if not self._started:
            self.start()
        attempted = persisted = failed = 0
        for source in self.config.sources:
            for row in self.tailer.read_new(source.path):
                attempted += 1
                now = self.clock()
                try:
                    event = self._convert(source, row, now)
                    before = self.publisher.stats()
                    did_persist = self.publisher.publish(event)
                    after = self.publisher.stats()
                    if did_persist:
                        persisted += 1
                    elif after.failures > before.failures:
                        failed += 1
                except (EventValidationError, ValueError, TypeError):
                    failed += 1
        return {"attempted": attempted, "persisted": persisted, "failed": failed}

    def _convert(self, source: JsonlSource, row: Mapping[str, Any], now: datetime) -> CanonicalEvent:
        if source.source_type == "candidate_lineage":
            normalized = dict(row)
            normalized.setdefault("source_file_or_component", source.source_component)
            return candidate_lineage_to_event(
                normalized,
                session_id=self.config.session_id,
                run_id=self.config.run_id,
                receive_time=now,
                persist_time=now,
                producer_sequence=self._next_sequence(source.source_component),
            )
        event_time_value = row.get("event_time") or row.get("timestamp")
        if not event_time_value:
            raise EventValidationError("truth_row_missing_event_time")
        event_time = _parse_datetime(event_time_value)
        return truth_snapshot_to_event(
            row,
            event_type=source.event_type,
            session_id=self.config.session_id,
            run_id=self.config.run_id,
            source_component=source.source_component,
            event_time=event_time,
            receive_time=now,
            persist_time=now,
            producer_sequence=self._next_sequence(source.source_component),
        )

    def run_forever(self, should_stop: Callable[[], bool]) -> None:
        self.start()
        try:
            while not should_stop():
                self.poll_once()
                time.sleep(self.config.poll_interval_seconds)
        finally:
            self.stop()
