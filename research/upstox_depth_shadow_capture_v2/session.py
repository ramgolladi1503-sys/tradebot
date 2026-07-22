from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .parser import PARSER_SCHEMA_VERSION, DepthParseError, parse_market_message


IST = ZoneInfo("Asia/Kolkata")
RECORD_SCHEMA = pa.schema(
    [
        ("receive_ts_ns", pa.int64()),
        ("feed_current_ts_ms", pa.int64()),
        ("instrument_key", pa.string()),
        ("message_type", pa.string()),
        ("mode", pa.string()),
        ("parser_variant", pa.string()),
        ("ltp", pa.float64()),
        ("ltt_ms", pa.int64()),
        ("ltq", pa.int64()),
        ("close_price", pa.float64()),
        ("raw_depth_level_count", pa.int16()),
        ("valid_depth_level_count", pa.int16()),
        ("two_sided_level_count", pa.int16()),
        ("invalid_depth_level_count", pa.int16()),
        ("best_bid_price", pa.float64()),
        ("best_ask_price", pa.float64()),
        ("best_bid_qty", pa.int64()),
        ("best_ask_qty", pa.int64()),
        ("total_bid_qty", pa.int64()),
        ("total_ask_qty", pa.int64()),
        ("crossed_market", pa.bool_()),
        ("bid_ladder_monotonic", pa.bool_()),
        ("ask_ladder_monotonic", pa.bool_()),
        ("depth_json", pa.string()),
        ("payload_sha256", pa.string()),
        ("schema_version", pa.string()),
    ]
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ShadowDepthSession:
    """Append-only, research-only Upstox depth capture session.

    This class has no broker, order, risk, or production-feed dependencies. The
    access token is held by the caller and is never written to disk.
    """

    def __init__(
        self,
        *,
        output_root: Path,
        requested_instrument_keys: Iterable[str],
        mode: str,
        chunk_rows: int = 10_000,
        flush_seconds: float = 60.0,
        session_date: str | None = None,
    ) -> None:
        keys = tuple(sorted({str(key).strip() for key in requested_instrument_keys if str(key).strip()}))
        if not keys:
            raise ValueError("at least one requested instrument key is required")
        if chunk_rows <= 0:
            raise ValueError("chunk_rows must be positive")
        if flush_seconds <= 0:
            raise ValueError("flush_seconds must be positive")

        self.requested_instrument_keys = keys
        self.mode = mode
        self.chunk_rows = int(chunk_rows)
        self.flush_seconds = float(flush_seconds)
        date_key = session_date or datetime.now(IST).strftime("%Y%m%d")
        if len(date_key) != 8 or not date_key.isdigit():
            raise ValueError("session_date must use YYYYMMDD")

        self.session_dir = Path(output_root).resolve() / date_key
        self.chunk_dir = self.session_dir / "chunks"
        self.chunk_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.session_dir / "manifest.json"
        self.audit_path = self.session_dir / "readiness.json"

        self._lock = threading.RLock()
        self._buffer: list[dict[str, Any]] = []
        self._chunks: list[dict[str, Any]] = []
        self._chunk_index = 0
        self._last_flush_monotonic = time.monotonic()
        self._started_at = _utc_now()
        self._finalized_at: datetime | None = None
        self._counters: Counter[str] = Counter()
        self._instruments_seen: set[str] = set()
        self._warning_samples: list[str] = []
        self._error_samples: list[str] = []
        self._write_manifest(status="RUNNING")

    def _sample(self, target: list[str], values: Iterable[str], *, limit: int = 100) -> None:
        for value in values:
            if len(target) >= limit:
                break
            target.append(str(value))

    def record_message(self, message: Any, *, received_at_ns: int | None = None) -> None:
        timestamp_ns = int(received_at_ns or time.time_ns())
        with self._lock:
            self._counters["callback_messages"] += 1
            try:
                parsed = parse_market_message(
                    message,
                    received_at_ns=timestamp_ns,
                    mode=self.mode,
                )
            except (DepthParseError, TypeError, ValueError) as exc:
                self._counters["parse_failures"] += 1
                self._sample(self._error_samples, [f"{type(exc).__name__}:{exc}"])
                self._maybe_flush_locked()
                return

            self._counters[f"message_type:{parsed.message_type}"] += 1
            self._counters["feed_updates"] += parsed.feed_count
            self._counters["market_feed_updates"] += parsed.market_feed_count
            self._counters["index_feed_updates"] += parsed.index_feed_count
            self._counters["empty_depth_updates"] += parsed.empty_depth_count
            self._counters["invalid_depth_levels"] += parsed.invalid_level_count
            self._counters["warning_count"] += len(parsed.warnings)
            self._sample(self._warning_samples, parsed.warnings)

            for record in parsed.records:
                self._buffer.append(record)
                self._instruments_seen.add(str(record["instrument_key"]))
                self._counters["records_buffered"] += 1
                if int(record["two_sided_level_count"]) > 0:
                    self._counters["two_sided_records"] += 1
                if int(record["valid_depth_level_count"]) == 0:
                    self._counters["zero_depth_records"] += 1
                if bool(record["crossed_market"]):
                    self._counters["crossed_market_records"] += 1

            self._maybe_flush_locked()

    def note_stream_error(self, error: Any) -> None:
        with self._lock:
            self._counters["stream_errors"] += 1
            self._sample(self._error_samples, [f"STREAM_ERROR:{error}"])
            self._write_manifest(status="RUNNING")

    def note_reconnecting(self, message: Any = None) -> None:
        with self._lock:
            self._counters["reconnect_attempts"] += 1
            if message is not None:
                self._sample(self._warning_samples, [f"RECONNECTING:{message}"])
            self._write_manifest(status="RUNNING")

    def note_close(self, *details: Any) -> None:
        with self._lock:
            self._counters["stream_close_events"] += 1
            if details:
                self._sample(
                    self._warning_samples,
                    ["STREAM_CLOSE:" + ":".join(str(item) for item in details)],
                )
            self._write_manifest(status="RUNNING")

    def _maybe_flush_locked(self) -> None:
        elapsed = time.monotonic() - self._last_flush_monotonic
        if len(self._buffer) >= self.chunk_rows or (self._buffer and elapsed >= self.flush_seconds):
            self._flush_locked()
        elif elapsed >= self.flush_seconds:
            self._write_manifest(status="RUNNING")
            self._last_flush_monotonic = time.monotonic()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._buffer:
            self._write_manifest(status="RUNNING")
            self._last_flush_monotonic = time.monotonic()
            return

        self._chunk_index += 1
        name = f"depth_{self._chunk_index:06d}.parquet"
        destination = self.chunk_dir / name
        temp = self.chunk_dir / f".{name}.{os.getpid()}.tmp"
        table = pa.Table.from_pylist(self._buffer, schema=RECORD_SCHEMA)
        pq.write_table(table, temp, compression="zstd")
        os.replace(temp, destination)
        record_count = len(self._buffer)
        self._chunks.append(
            {
                "path": destination.relative_to(self.session_dir).as_posix(),
                "records": record_count,
                "size_bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
            }
        )
        self._counters["records_flushed"] += record_count
        self._buffer.clear()
        self._last_flush_monotonic = time.monotonic()
        self._write_manifest(status="RUNNING")

    def _manifest(self, *, status: str) -> dict[str, Any]:
        requested = len(self.requested_instrument_keys)
        observed = len(self._instruments_seen)
        return {
            "campaign_id": "UPSTOX_DEPTH_SHADOW_CAPTURE_V2",
            "status": status,
            "schema_version": PARSER_SCHEMA_VERSION,
            "mode": self.mode,
            "session_date": self.session_dir.name,
            "started_at_utc": self._started_at.isoformat(),
            "finalized_at_utc": (
                self._finalized_at.isoformat() if self._finalized_at else None
            ),
            "requested_instrument_keys": list(self.requested_instrument_keys),
            "requested_instrument_count": requested,
            "observed_instrument_count": observed,
            "instrument_coverage_rate": observed / requested,
            "observed_instrument_keys": sorted(self._instruments_seen),
            "chunk_count": len(self._chunks),
            "chunks": list(self._chunks),
            "counters": dict(sorted(self._counters.items())),
            "warning_samples": list(self._warning_samples),
            "error_samples": list(self._error_samples),
            "access_token_persisted": False,
            "raw_payload_persisted": False,
            "payload_hash_persisted": True,
            "broker_orders_allowed": False,
            "execution_allowed": False,
        }

    def _write_manifest(self, *, status: str) -> None:
        _atomic_json(self.manifest_path, self._manifest(status=status))

    def finalize(self) -> dict[str, Any]:
        with self._lock:
            self._flush_locked()
            self._finalized_at = _utc_now()
            manifest = self._manifest(status="COMPLETE")
            _atomic_json(self.manifest_path, manifest)
            return manifest


def audit_shadow_session(
    session_dir: Path,
    *,
    minimum_session_minutes: float = 300.0,
    minimum_two_sided_rate: float = 0.90,
    minimum_instrument_coverage_rate: float = 0.95,
    maximum_median_gap_seconds: float = 5.0,
    maximum_p95_gap_seconds: float = 30.0,
    maximum_parse_failure_rate: float = 0.001,
) -> dict[str, Any]:
    session = Path(session_dir).resolve()
    manifest_path = session / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("session manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = manifest.get("chunks") or []
    if not chunks:
        result = {
            "classification": "SHADOW_DEPTH_SESSION_NOT_READY",
            "blockers": ["NO_PARQUET_CHUNKS"],
            "session_dir": str(session),
            "execution_allowed": False,
        }
        _atomic_json(session / "readiness.json", result)
        return result

    frames: list[pd.DataFrame] = []
    for item in chunks:
        path = session / str(item["path"])
        if not path.is_file():
            raise ValueError(f"missing chunk: {item['path']}")
        if _sha256(path) != str(item["sha256"]):
            raise ValueError(f"chunk hash mismatch: {item['path']}")
        frame = pd.read_parquet(path)
        if set(RECORD_SCHEMA.names).difference(frame.columns):
            raise ValueError(f"chunk schema missing columns: {item['path']}")
        frames.append(frame)

    data = pd.concat(frames, ignore_index=True)
    if data.empty:
        raise ValueError("captured parquet chunks contain no rows")
    if set(data["schema_version"].astype(str)) != {PARSER_SCHEMA_VERSION}:
        raise ValueError("captured rows contain an unexpected schema version")

    feed_ns = pd.to_numeric(data["feed_current_ts_ms"], errors="coerce") * 1_000_000
    receive_ns = pd.to_numeric(data["receive_ts_ns"], errors="raise")
    event_ns = feed_ns.where(feed_ns.notna() & (feed_ns > 0), receive_ns)
    data = data.assign(_event_ns=event_ns.astype("int64"))

    gaps: list[float] = []
    for _, group in data.groupby("instrument_key", sort=True):
        values = np.sort(group["_event_ns"].drop_duplicates().to_numpy(dtype="int64"))
        if len(values) > 1:
            positive = np.diff(values) / 1_000_000_000.0
            gaps.extend(float(value) for value in positive if value >= 0)

    duration_minutes = float(
        (data["_event_ns"].max() - data["_event_ns"].min())
        / 1_000_000_000.0
        / 60.0
    )
    row_count = int(len(data))
    two_sided_rate = float((data["two_sided_level_count"] > 0).mean())
    crossed_rate = float(data["crossed_market"].astype(bool).mean())
    invalid_level_rate = float(
        data["invalid_depth_level_count"].sum()
        / max(int(data["raw_depth_level_count"].sum()), 1)
    )
    median_gap = float(np.median(gaps)) if gaps else None
    p95_gap = float(np.quantile(gaps, 0.95)) if gaps else None

    counters = manifest.get("counters") or {}
    callbacks = int(counters.get("callback_messages", 0))
    parse_failures = int(counters.get("parse_failures", 0))
    parse_failure_rate = parse_failures / max(callbacks, 1)
    coverage_rate = float(manifest.get("instrument_coverage_rate", 0.0))

    blockers: list[str] = []
    if duration_minutes < minimum_session_minutes:
        blockers.append(
            f"SESSION_DURATION_BELOW_MINIMUM:{duration_minutes}<{minimum_session_minutes}"
        )
    if two_sided_rate < minimum_two_sided_rate:
        blockers.append(
            f"TWO_SIDED_DEPTH_RATE_BELOW_MINIMUM:{two_sided_rate}<{minimum_two_sided_rate}"
        )
    if coverage_rate < minimum_instrument_coverage_rate:
        blockers.append(
            f"INSTRUMENT_COVERAGE_BELOW_MINIMUM:{coverage_rate}<{minimum_instrument_coverage_rate}"
        )
    if median_gap is None or median_gap > maximum_median_gap_seconds:
        blockers.append("MEDIAN_FEED_GAP_TOO_LARGE_OR_MISSING")
    if p95_gap is None or p95_gap > maximum_p95_gap_seconds:
        blockers.append("P95_FEED_GAP_TOO_LARGE_OR_MISSING")
    if parse_failure_rate > maximum_parse_failure_rate:
        blockers.append(
            f"PARSE_FAILURE_RATE_TOO_HIGH:{parse_failure_rate}>{maximum_parse_failure_rate}"
        )

    result = {
        "classification": (
            "SHADOW_DEPTH_SESSION_READY_FOR_DEVELOPMENT"
            if not blockers
            else "SHADOW_DEPTH_SESSION_NOT_READY"
        ),
        "blockers": blockers,
        "session_dir": str(session),
        "row_count": row_count,
        "duration_minutes": duration_minutes,
        "two_sided_depth_rate": two_sided_rate,
        "instrument_coverage_rate": coverage_rate,
        "median_gap_seconds": median_gap,
        "p95_gap_seconds": p95_gap,
        "crossed_market_rate": crossed_rate,
        "invalid_depth_level_rate": invalid_level_rate,
        "parse_failure_rate": parse_failure_rate,
        "minimums": {
            "session_minutes": minimum_session_minutes,
            "two_sided_rate": minimum_two_sided_rate,
            "instrument_coverage_rate": minimum_instrument_coverage_rate,
            "maximum_median_gap_seconds": maximum_median_gap_seconds,
            "maximum_p95_gap_seconds": maximum_p95_gap_seconds,
            "maximum_parse_failure_rate": maximum_parse_failure_rate,
        },
        "strategy_created": False,
        "edge_claim_allowed": False,
        "execution_allowed": False,
    }
    _atomic_json(session / "readiness.json", result)
    return result
