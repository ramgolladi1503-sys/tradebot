from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import zstandard as zstd

from core.ai_reliability_agent.pr763_session import verify_sealed_evidence_root
from core.upstox_corpus_audit import (
    AuditError,
    audit_parquet_tree,
    audit_sqlite_database,
    audit_zstandard_files,
    compare_replay_databases,
    read_bar_intervals,
    reconcile_normalized_and_replay_counts,
    run_pr786_offline_rehearsal,
    verify_manifest_references,
)


def _write_parquet(path: Path, payload: dict[str, list]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(payload), path)
    return path


def _write_database(path: Path, *, rows: list[tuple[int, float, str]]) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE ticks (instrument_token INTEGER, timestamp_epoch REAL, symbol TEXT)"
        )
        connection.execute(
            "CREATE TABLE depth_snapshots (instrument_token INTEGER, timestamp_epoch REAL)"
        )
        connection.executemany("INSERT INTO ticks VALUES (?, ?, ?)", rows)
        connection.executemany(
            "INSERT INTO depth_snapshots VALUES (?, ?)",
            [
                (row[0], row[1])
                for row in sorted(rows, key=lambda item: item[1])[:2]
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return path


def test_zstd_and_parquet_audits_are_source_read_only(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    compressed = zstd.ZstdCompressor().compress(b"frame-one\nframe-two\n")
    zstd_path = raw / "frames_000001.bin.zst"
    zstd_path.write_bytes(compressed)
    before = zstd_path.read_bytes()

    normalized = raw / "normalized"
    _write_parquet(
        normalized / "ticks.parquet",
        {
            "receive_wall_ts_utc": [
                "2026-08-04T04:00:00+00:00",
                "2026-08-04T04:00:01+00:00",
                "2026-08-04T04:00:02+00:00",
            ],
            "instrument_key": ["NSE_EQ|A", "NSE_EQ|B", "NSE_INDEX|Nifty 50"],
            "last_price": [100.0, 200.0, 25000.0],
        },
    )

    raw_report = audit_zstandard_files(raw)
    normalized_report = audit_parquet_tree(normalized)

    assert raw_report["passed"] is True
    assert raw_report["file_count"] == 1
    assert raw_report["decompressed_size_bytes"] == len(b"frame-one\nframe-two\n")
    assert normalized_report["passed"] is True
    assert normalized_report["row_count"] == 3
    assert normalized_report["unique_instrument_count"] == 3
    assert zstd_path.read_bytes() == before


def test_manifest_reference_verification_detects_tampering(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    payload = evidence / "capture.json"
    payload.write_text('{"rows":3}\n', encoding="utf-8")
    from core.upstox_corpus_audit import sha256_file

    manifest = evidence / "session_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "relative_path": "capture.json",
                        "size_bytes": payload.stat().st_size,
                        "sha256": sha256_file(payload),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    first = verify_manifest_references(manifest, search_roots=[evidence])
    assert first["passed"] is True

    payload.write_text('{"rows":4}\n', encoding="utf-8")
    second = verify_manifest_references(manifest, search_roots=[evidence])
    assert second["passed"] is False
    assert "manifest_sha_mismatch:capture.json" in second["errors"]


def test_two_replays_require_ordered_row_hash_parity(tmp_path: Path):
    rows = [(1, 1.0, "A"), (2, 2.0, "B"), (1, 3.0, "A")]
    first = audit_sqlite_database(_write_database(tmp_path / "a.db", rows=rows))
    second = audit_sqlite_database(_write_database(tmp_path / "b.db", rows=list(reversed(rows))))
    comparison = compare_replay_databases(first, second)

    assert comparison["passed"] is True
    assert first["tables"]["ticks"]["row_count"] == 3
    assert first["tables"]["depth_snapshots"]["row_count"] == 2
    assert first["database_semantic_sha256"] == second["database_semantic_sha256"]

    connection = sqlite3.connect(tmp_path / "b.db")
    try:
        connection.execute("UPDATE ticks SET symbol='BROKEN' WHERE timestamp_epoch=2.0")
        connection.commit()
    finally:
        connection.close()
    changed = audit_sqlite_database(tmp_path / "b.db")
    assert compare_replay_databases(first, changed)["passed"] is False


def test_reconciliation_does_not_double_count_depth_rows():
    unresolved = reconcile_normalized_and_replay_counts(
        normalized_event_count=100,
        tick_row_count=98,
        depth_row_count=40,
    )
    assert unresolved["passed"] is False
    assert unresolved["unexplained_rows"] == 2
    assert unresolved["depth_rows_overlap_tick_domain"] is True

    explained = reconcile_normalized_and_replay_counts(
        normalized_event_count=100,
        tick_row_count=98,
        depth_row_count=40,
        explained_non_tick_rows=2,
    )
    assert explained["passed"] is True
    assert explained["unexplained_rows"] == 0


def test_offline_rehearsal_is_append_only_sealed_and_not_live(tmp_path: Path):
    bars = _write_parquet(
        tmp_path / "bars.parquet",
        {
            "interval_end_epoch": [1785821460.0, 1785821520.0, 1785821580.0],
            "accepted_constituent_count": [50, 49, 50],
        },
    )
    output = tmp_path / "audit" / "pr786_offline_rehearsal"
    report = run_pr786_offline_rehearsal(
        bars_path=bars,
        output_root=output,
        run_id="fixture-upstox-replay",
        session_date="2026-08-04",
    )

    assert report["verdict"] == "PASS_PR786_OFFLINE_REHEARSAL"
    assert report["accepted_interval_count"] == 3
    assert report["primary_evaluation_count"] == 3
    assert report["authority_snapshot_count"] == 3
    assert report["duplicate_successful_export_count"] == 0
    assert report["seal_gate_passed"] is True
    assert (output / "artifact_manifest.json").is_file()
    assert (output / "SHA256SUMS").is_file()
    assert (output / "SEALED").is_file()

    for name in (
        "authority_snapshots.jsonl",
        "meg_traversal_events.jsonl",
        "meg_live_source_exports.jsonl",
    ):
        rows = [json.loads(line) for line in (output / name).read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 3
        assert all(row["source"] == "upstox_replay" for row in rows)
        assert all(row["offline_replay"] is True for row in rows)
        assert all(row["live_source"] is False for row in rows)
        assert all(row["not_certification_evidence"] is True for row in rows)
        assert all(row["broker_write_authority"] is False for row in rows)
        assert all(row["order_authority"] is False for row in rows)

    with pytest.raises(AuditError, match="REHEARSAL_OUTPUT_ROOT_NOT_EMPTY"):
        run_pr786_offline_rehearsal(
            bars_path=bars,
            output_root=output,
            run_id="fixture-upstox-replay",
            session_date="2026-08-04",
        )

    with (output / "authority_snapshots.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    assert verify_sealed_evidence_root(output).passed is False


def test_duplicate_bar_interval_identity_fails_closed(tmp_path: Path):
    bars = _write_parquet(
        tmp_path / "bars.parquet",
        {"interval_end_epoch": [1785821460.0, 1785821460.0]},
    )
    with pytest.raises(AuditError, match="DUPLICATE_BAR_INTERVAL_IDENTITIES"):
        read_bar_intervals(bars)
