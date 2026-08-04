from __future__ import annotations

import atexit
import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import CanonicalEvent, EventValidationError
from .publisher import FileEventPublisher
from .safe_publish import NonBlockingPublisher
from .tradebot_adapter import candidate_lineage_to_event, truth_snapshot_to_event


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_positive(value: str | None, *, name: str) -> float:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name}_required_when_enabled")
    parsed = float(text)
    if parsed <= 0:
        raise ValueError(f"{name}_must_be_positive")
    return parsed


@dataclass(frozen=True)
class RuntimeTailerConfig:
    enabled: bool
    observation_mode: str
    output_root: Path
    poll_seconds: float
    start_at_end: bool
    fsync: bool
    session_id: str
    run_id: str

    @classmethod
    def from_env(cls, *, repo_root: Path) -> "RuntimeTailerConfig":
        enabled = _truthy(os.getenv("AIXION_INTELLIGENCE_ENABLED"))
        if not enabled:
            return cls(
                enabled=False,
                observation_mode="DISABLED",
                output_root=repo_root / ".runtime" / "aixion_trade_intelligence",
                poll_seconds=1.0,
                start_at_end=True,
                fsync=True,
                session_id="disabled",
                run_id="disabled",
            )
        mode = str(os.getenv("AIXION_INTELLIGENCE_OBSERVATION_MODE") or "").strip().upper()
        if mode not in {"PAPER", "SHADOW"}:
            raise ValueError("AIXION_INTELLIGENCE_OBSERVATION_MODE_must_be_PAPER_or_SHADOW")
        output_raw = str(os.getenv("AIXION_INTELLIGENCE_OUTPUT_ROOT") or "").strip()
        output_root = Path(output_raw).expanduser().resolve() if output_raw else (
            repo_root / ".runtime" / "aixion_trade_intelligence"
        )
        poll_seconds = _parse_positive(
            os.getenv("AIXION_INTELLIGENCE_POLL_SEC"),
            name="AIXION_INTELLIGENCE_POLL_SEC",
        )
        run_id = str(os.getenv("AIXION_INTELLIGENCE_RUN_ID") or uuid.uuid4()).strip()
        session_id = str(os.getenv("AIXION_INTELLIGENCE_SESSION_ID") or "").strip()
        if not session_id:
            session_id = (
                f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-"
                f"{mode}-{run_id[:12]}"
            )
        return cls(
            enabled=True,
            observation_mode=mode,
            output_root=output_root,
            poll_seconds=poll_seconds,
            start_at_end=_truthy(os.getenv("AIXION_INTELLIGENCE_START_AT_END", "1")),
            fsync=_truthy(os.getenv("AIXION_INTELLIGENCE_FSYNC", "1")),
            session_id=session_id,
            run_id=run_id,
        )


class JsonlCursor:
    def __init__(self, path: Path, *, start_at_end: bool) -> None:
        self.path = path
        self.offset = path.stat().st_size if start_at_end and path.exists() else 0
        self._identity: tuple[int, int] | None = None

    def read_new(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        stat = self.path.stat()
        identity = (int(stat.st_dev), int(stat.st_ino))
        if self._identity is not None and identity != self._identity:
            self.offset = 0
        self._identity = identity
        if stat.st_size < self.offset:
            self.offset = 0
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            handle.seek(self.offset)
            while True:
                position = handle.tell()
                line = handle.readline()
                if not line:
                    break
                if not line.endswith("\n"):
                    handle.seek(position)
                    break
                raw = line.strip()
                if not raw:
                    continue
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError(f"jsonl_row_not_object:{self.path}")
                rows.append(payload)
            self.offset = handle.tell()
        return rows


class JsonSnapshotCursor:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._last_hash = ""

    def read_if_changed(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        raw = self.path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest == self._last_hash:
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"snapshot_not_object:{self.path}")
        self._last_hash = digest
        return payload


class RuntimeEvidenceTailer:
    """Read-only adapter over existing TradeBot evidence files."""

    def __init__(
        self,
        *,
        config: RuntimeTailerConfig,
        runtime_events_path: Path,
        candidate_lineage_path: Path,
        market_snapshot_path: Path,
    ) -> None:
        if not config.enabled:
            raise ValueError("runtime_tailer_config_disabled")
        self.config = config
        self.publisher = NonBlockingPublisher(
            FileEventPublisher(config.output_root, fsync=config.fsync)
        )
        self.runtime_cursor = JsonlCursor(runtime_events_path, start_at_end=config.start_at_end)
        self.candidate_cursor = JsonlCursor(candidate_lineage_path, start_at_end=config.start_at_end)
        self.market_cursor = JsonSnapshotCursor(market_snapshot_path)
        self.status_path = config.output_root / config.session_id / "runtime_tailer_status.json"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sequence_by_component: dict[str, int] = {}
        self._source_failures = 0
        self._last_source_error = ""

    def _next_sequence(self, component: str) -> int:
        value = self._sequence_by_component.get(component, 0) + 1
        self._sequence_by_component[component] = value
        return value

    def _publish_lifecycle(self, event_type: str) -> None:
        now = datetime.now(timezone.utc)
        event = truth_snapshot_to_event(
            {
                "observation_mode": self.config.observation_mode,
                "data_quality_state": "VALID",
                "read_only": True,
                "broker_authority": False,
            },
            event_type=event_type,
            session_id=self.config.session_id,
            run_id=self.config.run_id,
            source_component="aixion_trade_intelligence.runtime_tailer",
            event_time=now,
            receive_time=now,
            persist_time=now,
            producer_sequence=self._next_sequence("runtime_tailer"),
        )
        self.publisher.publish(event)

    def _runtime_event(self, row: Mapping[str, Any]) -> CanonicalEvent:
        payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else {}
        ts = row.get("ts") or payload.get("timestamp") or payload.get("event_time")
        if ts is None:
            raise EventValidationError("runtime_event_timestamp_missing")
        event_time = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if event_time.tzinfo is None:
            raise EventValidationError("runtime_event_timestamp_naive")
        event_type = str(row.get("type") or payload.get("event") or "RUNTIME_EVENT").strip().upper()
        event_id = str(row.get("event_id") or payload.get("event_id") or "").strip()
        if not event_id:
            encoded = json.dumps(
                {
                    "session_id": self.config.session_id,
                    "event_type": event_type,
                    "event_time": event_time.isoformat(),
                    "payload": payload,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            event_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        return CanonicalEvent(
            event_id=event_id,
            event_type=event_type,
            schema_version="1.0.0",
            session_id=self.config.session_id,
            run_id=self.config.run_id,
            cycle_id=str(payload.get("cycle_id") or ""),
            trace_id=str(payload.get("trace_id") or ""),
            event_time=event_time,
            source_time=event_time,
            receive_time=now,
            available_time=event_time,
            parse_time=now,
            persist_time=now,
            source_provider="TRADEBOT",
            source_component="core.events",
            authority_class="TRADEBOT_RUNTIME_EVENT",
            data_quality_state=str(payload.get("data_quality_state") or "VALID").upper(),
            instrument_key=str(payload.get("instrument_key") or payload.get("instrument_id") or ""),
            strategy_id=str(payload.get("strategy_id") or payload.get("strategy_name") or ""),
            strategy_version=str(payload.get("strategy_version") or ""),
            candidate_id=str(payload.get("candidate_id") or ""),
            producer_sequence=self._next_sequence("core.events"),
            payload=dict(payload),
        )

    def _publish_runtime_rows(self) -> None:
        for row in self.runtime_cursor.read_new():
            self.publisher.publish(self._runtime_event(row))

    def _publish_candidate_rows(self) -> None:
        for row in self.candidate_cursor.read_new():
            now = datetime.now(timezone.utc)
            event = candidate_lineage_to_event(
                row,
                session_id=self.config.session_id,
                run_id=self.config.run_id,
                receive_time=now,
                persist_time=now,
                producer_sequence=self._next_sequence("candidate_lineage"),
            )
            self.publisher.publish(event)

    def _publish_market_snapshot(self) -> None:
        snapshot = self.market_cursor.read_if_changed()
        if snapshot is None:
            return
        generated = snapshot.get("generated_at")
        if not generated:
            raise EventValidationError("market_snapshot_generated_at_missing")
        event_time = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
        if event_time.tzinfo is None:
            raise EventValidationError("market_snapshot_generated_at_naive")
        now = datetime.now(timezone.utc)
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
        event = CanonicalEvent(
            event_id=hashlib.sha256(
                (
                    self.config.session_id
                    + "|MARKET_SNAPSHOT|"
                    + event_time.isoformat()
                    + "|"
                    + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                ).encode("utf-8")
            ).hexdigest(),
            event_type="MARKET_SNAPSHOT",
            schema_version="1.0.0",
            session_id=self.config.session_id,
            run_id=self.config.run_id,
            event_time=event_time,
            source_time=event_time,
            receive_time=now,
            available_time=event_time,
            parse_time=now,
            persist_time=now,
            source_provider="TRADEBOT",
            source_component="core.market_snapshot_store",
            authority_class="TRADEBOT_DERIVED",
            data_quality_state="VALID" if not snapshot.get("warnings") else "PARTIAL",
            producer_sequence=self._next_sequence("market_snapshot"),
            payload=dict(snapshot),
        )
        self.publisher.publish(event)

    def _write_status(self) -> None:
        stats = self.publisher.stats()
        payload = {
            "session_id": self.config.session_id,
            "run_id": self.config.run_id,
            "observation_mode": self.config.observation_mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "attempted": stats.attempted,
            "persisted": stats.persisted,
            "duplicates": stats.duplicates,
            "publisher_failures": stats.failures,
            "publisher_last_error": stats.last_error,
            "source_failures": self._source_failures,
            "source_last_error": self._last_source_error,
            "evidence_complete": self.publisher.evidence_complete and self._source_failures == 0,
            "broker_authority": False,
            "read_only": True,
        }
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
            encoding="utf-8",
        )
        os.replace(temporary, self.status_path)

    def poll_once(self) -> None:
        try:
            self._publish_runtime_rows()
            self._publish_candidate_rows()
            self._publish_market_snapshot()
        except Exception as exc:
            self._source_failures += 1
            self._last_source_error = f"{type(exc).__name__}:{exc}"
        self._write_status()

    def _run(self) -> None:
        while not self._stop.wait(self.config.poll_seconds):
            self.poll_once()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("runtime_tailer_already_started")
        self._publish_lifecycle("SESSION_STARTED")
        self._write_status()
        self._thread = threading.Thread(
            target=self._run,
            name="aixion-trade-intelligence-tailer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.config.poll_seconds * 2.0, 1.0))
        self.poll_once()
        self._publish_lifecycle("SESSION_ENDED")
        self._write_status()


_RUNTIME_TAILER: RuntimeEvidenceTailer | None = None
_RUNTIME_TAILER_LOCK = threading.Lock()


def start_runtime_tailer_if_enabled(repo_root: Path) -> RuntimeEvidenceTailer | None:
    global _RUNTIME_TAILER
    config = RuntimeTailerConfig.from_env(repo_root=repo_root)
    if not config.enabled:
        return None
    with _RUNTIME_TAILER_LOCK:
        if _RUNTIME_TAILER is not None:
            return _RUNTIME_TAILER
        from core.candidate_lineage_ledger import candidate_lineage_paths
        from core.events import events_path
        from core.market_snapshot_store import DEFAULT_MARKET_SNAPSHOT_PATH

        candidate_path, _ = candidate_lineage_paths()
        tailer = RuntimeEvidenceTailer(
            config=config,
            runtime_events_path=events_path(),
            candidate_lineage_path=candidate_path,
            market_snapshot_path=DEFAULT_MARKET_SNAPSHOT_PATH,
        )
        tailer.start()
        atexit.register(tailer.stop)
        _RUNTIME_TAILER = tailer
        return tailer
