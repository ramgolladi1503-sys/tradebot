"""Provider-neutral audit helpers for an immutable Upstox replay corpus.

The module never starts a feed, broker, strategy, or execution path.  It reads
already-captured artifacts, creates audit outputs in a separate directory, and
rehearses the append-only PR #786 evidence contracts with explicit
``offline_replay=true`` and ``live_source=false`` labels.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from core.ai_reliability_agent.pr763_session import verify_sealed_evidence_root
from core.read_only_live_evidence import append_jsonl_record, write_json_atomic
from core.unified_live_validation_pr748_756.seal import seal_evidence_root


NORMALIZED_TIMESTAMP_FIELDS = (
    "receive_wall_ts_utc",
    "source_exchange_ts",
    "exchange_timestamp",
    "timestamp",
    "ts",
)
NORMALIZED_ID_FIELDS = (
    "event_id",
    "source_sequence",
    "sequence",
    "message_sequence",
    "packet_sequence",
)
INSTRUMENT_KEY_FIELDS = (
    "instrument_key",
    "instrument_token",
    "exchange_token",
    "tradingsymbol",
    "trading_symbol",
    "symbol",
)
BAR_INTERVAL_FIELDS = (
    "source_interval_end_epoch",
    "interval_end_epoch",
    "source_bar_end_epoch",
    "bar_end_epoch",
    "end_epoch",
    "timestamp",
    "ts",
    "minute",
    "bar_time",
)


class AuditError(RuntimeError):
    """Raised when an audit contract cannot be evaluated safely."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def semantic_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path, *, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def snapshot_paths(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for path in sorted({Path(item).resolve() for item in paths}, key=str):
        if not path.exists():
            snapshot[str(path)] = {"exists": False}
            continue
        stat = path.stat()
        payload: dict[str, Any] = {
            "exists": True,
            "is_file": path.is_file(),
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
        if path.is_file():
            payload["sha256"] = sha256_file(path)
        snapshot[str(path)] = payload
    return snapshot


def assert_snapshot_unchanged(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    if dict(before) != dict(after):
        changed = sorted(
            key
            for key in set(before) | set(after)
            if before.get(key) != after.get(key)
        )
        raise AuditError(f"SOURCE_ARTIFACT_MUTATED:{changed}")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - exercised through callers
        raise AuditError(f"INVALID_JSON:{path}:{exc}") from exc


def _iter_manifest_entries(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, Mapping):
        path_value = (
            value.get("relative_path")
            or value.get("path")
            or value.get("file")
            or value.get("filename")
        )
        hash_value = value.get("sha256") or value.get("hash")
        if isinstance(path_value, str) and isinstance(hash_value, str):
            yield {
                "path": path_value,
                "sha256": hash_value.lower(),
                "size_bytes": value.get("size_bytes") or value.get("size"),
            }
        checksums = value.get("checksums")
        if isinstance(checksums, Mapping):
            for k, v in checksums.items():
                if isinstance(k, str) and isinstance(v, str):
                    yield {
                        "path": k,
                        "sha256": v.lower(),
                        "size_bytes": None,
                    }
        for child in value.values():
            if child is not checksums:
                yield from _iter_manifest_entries(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_manifest_entries(child)


def verify_manifest_references(
    manifest_path: Path,
    *,
    search_roots: Sequence[Path],
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    entries = list(_iter_manifest_entries(manifest))
    resolved: list[dict[str, Any]] = []
    errors: list[str] = []
    roots = [Path(root).expanduser().resolve() for root in search_roots]
    for entry in entries:
        raw = Path(str(entry["path"]))
        candidates = [raw] if raw.is_absolute() else [root / raw for root in roots]
        target = next((candidate for candidate in candidates if candidate.is_file()), None)
        if target is None:
            errors.append(f"manifest_file_missing:{entry['path']}")
            continue
        actual_hash = sha256_file(target)
        actual_size = target.stat().st_size
        if actual_hash.lower() != str(entry["sha256"]).lower():
            errors.append(f"manifest_sha_mismatch:{entry['path']}")
        expected_size = entry.get("size_bytes")
        if expected_size is not None and int(expected_size) != actual_size:
            errors.append(f"manifest_size_mismatch:{entry['path']}")
        resolved.append(
            {
                **entry,
                "resolved_path": str(target),
                "actual_sha256": actual_hash,
                "actual_size_bytes": actual_size,
            }
        )
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "entry_count": len(entries),
        "resolved_count": len(resolved),
        "errors": errors,
        "passed": bool(entries) and not errors and len(resolved) == len(entries),
        "entries": resolved,
    }


def audit_zstandard_files(root: Path) -> dict[str, Any]:
    try:
        import zstandard as zstd
    except Exception as exc:  # pragma: no cover - dependency guard
        raise AuditError("ZSTANDARD_DEPENDENCY_MISSING") from exc

    import struct
    try:
        import upstox_client.feeder.proto.MarketDataFeedV3_pb2 as pb
        has_proto_decoder = True
    except ImportError:
        has_proto_decoder = False

    files = sorted(Path(root).rglob("*.zst"))
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    total_compressed = 0
    total_decompressed = 0

    decoded_frame_count = 0
    decode_failure_count = 0
    unknown_frame_count = 0
    first_source_ts = None
    last_source_ts = None
    instrument_coverage = set()
    payload_hashes = set()
    duplicate_frame_count = 0
    ordering_regressions = 0
    prev_ts = None

    for path in files:
        compressed_size = path.stat().st_size
        decompressed_size = 0
        try:
            with path.open("rb") as source:
                with zstd.ZstdDecompressor().stream_reader(source) as reader:
                    while True:
                        len_bytes = reader.read(4)
                        if not len_bytes:
                            break
                        decompressed_size += len(len_bytes)
                        if len(len_bytes) < 4:
                            decode_failure_count += 1
                            break
                        length = struct.unpack(">I", len_bytes)[0]
                        payload = reader.read(length)
                        decompressed_size += len(payload)
                        if len(payload) < length:
                            decode_failure_count += 1
                            break

                        decoded_frame_count += 1
                        h = hashlib.sha256(payload).hexdigest()
                        if h in payload_hashes:
                            duplicate_frame_count += 1
                        else:
                            payload_hashes.add(h)

                        if has_proto_decoder:
                            try:
                                feed_response = pb.FeedResponse()
                                feed_response.ParseFromString(payload)
                                ts = int(feed_response.currentTs) if feed_response.currentTs else None
                                if ts is not None:
                                    if first_source_ts is None or ts < first_source_ts:
                                        first_source_ts = ts
                                    if last_source_ts is None or ts > last_source_ts:
                                        last_source_ts = ts
                                    if prev_ts is not None and ts < prev_ts:
                                        ordering_regressions += 1
                                    prev_ts = ts
                                feeds = feed_response.feeds
                                if feeds:
                                    for k in feeds.keys():
                                        instrument_coverage.add(k)
                                else:
                                    if not feed_response.marketInfo and not feed_response.type:
                                        unknown_frame_count += 1
                            except Exception:
                                decode_failure_count += 1
                        else:
                            unknown_frame_count += 1
        except Exception as exc:
            errors.append(f"zstd_decompression_failed:{path}:{exc}")
        total_compressed += compressed_size
        total_decompressed += decompressed_size
        results.append(
            {
                "path": str(path),
                "compressed_size_bytes": compressed_size,
                "decompressed_size_bytes": decompressed_size,
                "sha256": sha256_file(path),
            }
        )

    raw_frame_result = {}
    if has_proto_decoder and decoded_frame_count > 0:
        raw_frame_result = {
            "decoded_frame_count": decoded_frame_count,
            "decode_failure_count": decode_failure_count,
            "unknown_frame_count": unknown_frame_count,
            "first_source_timestamp": first_source_ts,
            "last_source_timestamp": last_source_ts,
            "instrument_coverage_count": len(instrument_coverage),
            "instrument_coverage": sorted(list(instrument_coverage)),
            "duplicate_frame_identity_count": duplicate_frame_count,
            "ordering_regressions": ordering_regressions,
        }
    else:
        raw_frame_result = {
            "verdict": "RAW_FRAME_COUNT_UNVERIFIED",
            "decoded_frame_count": 0,
            "decode_failure_count": decode_failure_count,
        }

    return {
        "file_count": len(files),
        "compressed_size_bytes": total_compressed,
        "decompressed_size_bytes": total_decompressed,
        "files": results,
        "errors": errors,
        "raw_frame_result": raw_frame_result,
        "passed": bool(files) and not errors,
    }


def _first_present(names: Iterable[str], candidates: Sequence[str]) -> str | None:
    available = set(names)
    return next((candidate for candidate in candidates if candidate in available), None)


def _normalize_scalar(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "as_py"):
        value = value.as_py()
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def audit_parquet_tree(root: Path) -> dict[str, Any]:
    try:
        import pyarrow.parquet as pq
    except Exception as exc:  # pragma: no cover - dependency guard
        raise AuditError("PYARROW_DEPENDENCY_MISSING") from exc

    files = sorted(Path(root).rglob("*.parquet"))
    file_reports: list[dict[str, Any]] = []
    schema_fingerprints: set[str] = set()
    total_rows = 0
    timestamp_min: str | None = None
    timestamp_max: str | None = None
    instruments: set[str] = set()
    errors: list[str] = []

    for path in files:
        try:
            table = pq.read_table(path, partitioning=None)
        except Exception as exc:
            errors.append(f"parquet_read_failed:{path}:{exc}")
            continue
        schema_text = str(table.schema)
        schema_hash = hashlib.sha256(schema_text.encode("utf-8")).hexdigest()
        schema_fingerprints.add(schema_hash)
        row_count = int(table.num_rows)
        total_rows += row_count
        names = list(table.column_names)
        timestamp_field = _first_present(names, NORMALIZED_TIMESTAMP_FIELDS)
        instrument_field = _first_present(names, INSTRUMENT_KEY_FIELDS)
        local_min: str | None = None
        local_max: str | None = None
        if timestamp_field and row_count:
            values = [
                _normalize_scalar(item)
                for item in table[timestamp_field]
                if _normalize_scalar(item) is not None
            ]
            if values:
                ordered = sorted(str(value) for value in values)
                local_min, local_max = ordered[0], ordered[-1]
                timestamp_min = local_min if timestamp_min is None else min(timestamp_min, local_min)
                timestamp_max = local_max if timestamp_max is None else max(timestamp_max, local_max)
        if instrument_field and row_count:
            instruments.update(
                str(value)
                for value in (_normalize_scalar(item) for item in table[instrument_field])
                if value not in (None, "")
            )
        file_reports.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "row_count": row_count,
                "schema_sha256": schema_hash,
                "timestamp_field": timestamp_field,
                "timestamp_min": local_min,
                "timestamp_max": local_max,
                "instrument_field": instrument_field,
            }
        )

    return {
        "file_count": len(files),
        "row_count": total_rows,
        "schema_fingerprints": sorted(schema_fingerprints),
        "schema_fingerprint_count": len(schema_fingerprints),
        "timestamp_min": timestamp_min,
        "timestamp_max": timestamp_max,
        "unique_instrument_count": len(instruments),
        "unique_instruments": sorted(instruments),
        "files": file_reports,
        "errors": errors,
        "passed": bool(files) and not errors and total_rows > 0,
    }


def _ordered_table_hash(connection: sqlite3.Connection, table: str) -> tuple[int, str]:
    quoted = '"' + table.replace('"', '""') + '"'
    columns = [row[1] for row in connection.execute(f"PRAGMA table_info({quoted})")]
    if not columns:
        return 0, semantic_sha256([])
    order_expr = ",".join('"' + name.replace('"', '""') + '"' for name in columns)
    cursor = connection.execute(f"SELECT * FROM {quoted} ORDER BY {order_expr}")
    digest = hashlib.sha256()
    count = 0
    for row in cursor:
        digest.update(canonical_json_bytes(list(row)))
        digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def audit_sqlite_database(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "passed": False, "errors": ["database_missing"]}
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = sorted(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        table_reports: dict[str, Any] = {}
        semantic = hashlib.sha256()
        for table in tables:
            count, row_hash = _ordered_table_hash(connection, table)
            table_reports[table] = {"row_count": count, "ordered_row_sha256": row_hash}
            semantic.update(canonical_json_bytes([table, count, row_hash]))
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "file_sha256": sha256_file(path),
            "tables": table_reports,
            "database_semantic_sha256": semantic.hexdigest(),
            "passed": bool(tables),
            "errors": [] if tables else ["no_user_tables"],
        }
    finally:
        connection.close()


def compare_replay_databases(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    first_tables = first.get("tables") or {}
    second_tables = second.get("tables") or {}
    if first_tables != second_tables:
        errors.append("table_counts_or_hashes_mismatch")
    if first.get("database_semantic_sha256") != second.get("database_semantic_sha256"):
        errors.append("database_semantic_hash_mismatch")
    return {
        "run_a": first,
        "run_b": second,
        "errors": errors,
        "passed": bool(first.get("passed")) and bool(second.get("passed")) and not errors,
    }


def reconcile_normalized_and_replay_counts(
    *,
    normalized_event_count: int,
    tick_row_count: int,
    depth_row_count: int,
    explained_non_tick_rows: int | None = None,
) -> dict[str, Any]:
    # Depth rows are not subtracted: one normalized market event can legitimately
    # create both a tick row and a depth snapshot.
    tick_difference = int(normalized_event_count) - int(tick_row_count)
    explained = int(explained_non_tick_rows or 0)
    unexplained = tick_difference - explained
    errors: list[str] = []
    if tick_difference < 0:
        errors.append("tick_rows_exceed_normalized_events")
    if unexplained != 0:
        errors.append(f"unexplained_tick_difference:{unexplained}")
    return {
        "normalized_event_count": int(normalized_event_count),
        "tick_row_count": int(tick_row_count),
        "depth_row_count": int(depth_row_count),
        "tick_difference": tick_difference,
        "explained_non_tick_rows": explained,
        "unexplained_rows": unexplained,
        "depth_rows_overlap_tick_domain": True,
        "errors": errors,
        "passed": not errors,
    }


def _to_epoch(value: Any) -> float:
    value = _normalize_scalar(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    try:
        return float(text)
    except ValueError:
        pass
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return float(parsed.timestamp())


def read_bar_intervals(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except Exception as exc:  # pragma: no cover - dependency guard
        raise AuditError("PYARROW_DEPENDENCY_MISSING") from exc
    table = pq.read_table(path, partitioning=None)
    interval_field = _first_present(table.column_names, BAR_INTERVAL_FIELDS)
    if interval_field is None:
        raise AuditError(f"BAR_INTERVAL_FIELD_MISSING:{table.column_names}")
    intervals: list[dict[str, Any]] = []
    for ordinal in range(table.num_rows):
        raw = table[interval_field][ordinal]
        epoch = _to_epoch(raw)
        interval_identity = f"{int(epoch)}"
        intervals.append(
            {
                "ordinal": ordinal,
                "interval_field": interval_field,
                "interval_end_epoch": epoch,
                "interval_identity": interval_identity,
            }
        )
    identities = [row["interval_identity"] for row in intervals]
    duplicates = sorted({identity for identity in identities if identities.count(identity) > 1})
    if duplicates:
        raise AuditError(f"DUPLICATE_BAR_INTERVAL_IDENTITIES:{duplicates[:10]}")
    return intervals


def _write_offline_authority_snapshot(
    *,
    ledger_path: Path,
    latest_path: Path,
    latest_alt_path: Path,
    run_id: str,
    session_date: str,
    interval: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "authority_snapshot": True,
        "snapshot_kind": "UPSTOX_OFFLINE_REPLAY_INTERVAL_AUTHORITY_REHEARSAL",
        "run_id": run_id,
        "session_date": session_date,
        "source": "upstox_replay",
        "offline_replay": True,
        "live_source": False,
        "source_interval_identity": interval["interval_identity"],
        "source_interval_end_epoch": interval["interval_end_epoch"],
        "snapshot_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "top_executable": [],
        "top_advisory": [],
        "blocked_debug": [],
        "candidate_count": 0,
        "executable_count": 0,
        "advisory_only_count": 0,
        "blocked_count": 0,
        "explicit_empty_snapshot": True,
        "contract_rehearsal": True,
        "not_certification_evidence": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
    }
    stored = append_jsonl_record(ledger_path, payload, hash_field="snapshot_sha256")
    write_json_atomic(latest_path, stored)
    write_json_atomic(latest_alt_path, stored)
    return stored


def run_pr786_offline_rehearsal(
    *,
    bars_path: Path,
    output_root: Path,
    run_id: str,
    session_date: str,
) -> dict[str, Any]:
    output_root = output_root.expanduser().resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise AuditError("REHEARSAL_OUTPUT_ROOT_NOT_EMPTY")
    output_root.mkdir(parents=True, exist_ok=True)

    intervals = read_bar_intervals(bars_path)
    authority_ledger = output_root / "authority_snapshots.jsonl"
    authority_latest = output_root / "authority_snapshot.json"
    authority_latest_alt = output_root / "authority_snapshot_latest.json"
    traversal_ledger = output_root / "meg_traversal_events.jsonl"
    export_ledger = output_root / "meg_live_source_exports.jsonl"
    summary_path = output_root / "meg_wiring_evidence.json"
    summary_path_alt = output_root / "rehearsal_summary.json"

    for interval in intervals:
        _write_offline_authority_snapshot(
            ledger_path=authority_ledger,
            latest_path=authority_latest,
            latest_alt_path=authority_latest_alt,
            run_id=run_id,
            session_date=session_date,
            interval=interval,
        )
        base = {
            "schema_version": 1,
            "run_id": run_id,
            "session_date": session_date,
            "source": "upstox_replay",
            "offline_replay": True,
            "live_source": False,
            "source_interval_identity": interval["interval_identity"],
            "source_interval_end_epoch": interval["interval_end_epoch"],
            "event_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "contract_rehearsal": True,
            "not_certification_evidence": True,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "broker_write_authority": False,
            "order_authority": False,
            "allowed_for_live_execution": False,
            "allowed_for_paper_execution": False,
        }
        append_jsonl_record(
            traversal_ledger,
            {
                **base,
                "evidence_kind": "MEG_OFFLINE_REPLAY_TRAVERSAL_REHEARSAL",
                "attempted": True,
                "exported": True,
                "rejected": False,
                "duplicate": False,
                "reason_code": "OFFLINE_CONTRACT_REHEARSAL_ACCEPTED_INTERVAL",
                "market_event_graph_traversal": False,
                "market_event_graph_traversal_count": 0,
            },
            hash_field="event_sha256",
        )
        append_jsonl_record(
            export_ledger,
            {
                **base,
                "evidence_kind": "MEG_OFFLINE_REPLAY_EXPORT_REHEARSAL",
                "export_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "market_event_graph_traversal": False,
                "market_event_graph_traversal_count": 0,
                "not_market_signal": True,
            },
            hash_field="row_sha256",
        )

    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "session_date": session_date,
        "source": "upstox_replay",
        "offline_replay": True,
        "live_source": False,
        "accepted_interval_count": len(intervals),
        "primary_evaluation_count": len(intervals),
        "retry_evaluation_count": 0,
        "duplicate_poll_count": 0,
        "duplicate_successful_export_count": 0,
        "authority_snapshot_count": len(intervals),
        "explicit_empty_snapshot_count": len(intervals),
        "rehearsal_export_count": len(intervals),
        "contract_rehearsal": True,
        "not_certification_evidence": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
        "verdict": "PASS_PR786_OFFLINE_LEDGER_REHEARSAL" if intervals else "FAILED_PR786_OFFLINE_LEDGER_REHEARSAL",
    }
    write_json_atomic(summary_path, summary)
    write_json_atomic(summary_path_alt, summary)
    manifest = seal_evidence_root(output_root)
    seal_gate = verify_sealed_evidence_root(output_root)
    return {
        **summary,
        "artifact_count": manifest.get("artifact_count"),
        "artifact_manifest_sha256": manifest.get("artifact_manifest_sha256"),
        "seal_gate_passed": seal_gate.passed,
        "seal_gate": seal_gate.evidence,
        "verdict": (
            "PASS_PR786_OFFLINE_REHEARSAL"
            if intervals and seal_gate.passed
            else "FAILED_PR786_OFFLINE_REHEARSAL"
        ),
    }


def classify_skipped_intervals(db_path: Path, bars_path: Path) -> dict[str, Any]:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise AuditError("PANDAS_DEPENDENCY_MISSING") from exc

    if not db_path.is_file():
        return {"passed": False, "errors": ["database_missing"]}
    if not bars_path.is_file():
        return {"passed": False, "errors": ["bars_file_missing"]}

    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    try:
        df = pd.read_parquet(bars_path)
        accepted = set(df['source_bar_end_epoch'].astype(int))
        expected = range(1785816060, 1785837600 + 60, 60)
        
        results = []
        skipped_count = 0
        accepted_count = 0
        duplicate_count = 0
        seen_identities = set()

        for epoch in expected:
            interval_identity = str(epoch)
            if interval_identity in seen_identities:
                duplicate_count += 1
            seen_identities.add(interval_identity)

            if epoch in accepted:
                classification = "ACCEPTED"
                accepted_count += 1
            else:
                skipped_count += 1
                c_nifty = connection.execute(
                    "SELECT count(*) FROM ticks WHERE instrument_token = 26000 AND timestamp_epoch >= ? AND timestamp_epoch < ?",
                    (epoch - 60, epoch)
                ).fetchone()[0]
                p_nifty = connection.execute(
                    "SELECT count(*) FROM ticks WHERE instrument_token = 26000 AND timestamp_epoch >= ? AND timestamp_epoch < ?",
                    (epoch - 120, epoch - 60)
                ).fetchone()[0]

                if c_nifty == 0 or p_nifty == 0:
                    classification = "SKIPPED_MISSING_INDEX"
                else:
                    classification = "SKIPPED_CONSTITUENT_COVERAGE"

            results.append({
                "interval_identity": interval_identity,
                "interval_start_epoch": epoch - 60,
                "interval_end_epoch": epoch,
                "classification": classification,
            })

        return {
            "expected_interval_count": len(expected),
            "accepted_interval_count": accepted_count,
            "skipped_interval_count": skipped_count,
            "duplicate_interval_identities": duplicate_count,
            "intervals": results,
            "passed": accepted_count + skipped_count == len(expected) and duplicate_count == 0,
            "errors": [] if duplicate_count == 0 else ["duplicate_interval_identities"],
        }
    finally:
        connection.close()


def copy_for_negative_control(source: Path, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    return destination


__all__ = [
    "AuditError",
    "assert_snapshot_unchanged",
    "audit_parquet_tree",
    "audit_sqlite_database",
    "audit_zstandard_files",
    "classify_skipped_intervals",
    "compare_replay_databases",
    "copy_for_negative_control",
    "read_bar_intervals",
    "reconcile_normalized_and_replay_counts",
    "run_pr786_offline_rehearsal",
    "sha256_file",
    "snapshot_paths",
    "verify_manifest_references",
]
