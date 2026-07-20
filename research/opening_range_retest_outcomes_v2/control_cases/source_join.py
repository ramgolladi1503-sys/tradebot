from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from research.opening_range_retest_outcomes_v2.control_protocol import MutationSpec, RawExecution
from research.opening_range_retest_outcomes_v2.contract import INPUT_SOURCE_HASH, sha256_bytes, sha256_file
from research.opening_range_retest_outcomes_v2.engine import measure_candidate
from research.opening_range_retest_outcomes_v2.oracle import join_failure, source_path, validate_frame

SOURCE_JOIN_CATEGORY = "source_join"


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")


def digest(payload: Any) -> str:
    return sha256_bytes(canonical_bytes(payload))


def source_join_specs() -> tuple[MutationSpec, ...]:
    return (
        MutationSpec("S3_SOURCE_RECORD_MISSING_FROM_MANIFEST_JOIN", SOURCE_JOIN_CATEGORY, "missing_manifest_join", {}, "oracle.join_failure"),
        MutationSpec("S3_SOURCE_MISSING_PHYSICAL_FILE", SOURCE_JOIN_CATEGORY, "missing_physical_file", {}, "oracle.source_path"),
        MutationSpec("S3_SOURCE_SHA_MISMATCH", SOURCE_JOIN_CATEGORY, "sha_mismatch", {}, "oracle.source_path"),
        MutationSpec("S3_SOURCE_SIZE_MISMATCH", SOURCE_JOIN_CATEGORY, "size_mismatch", {}, "oracle.source_path"),
        MutationSpec("S3_SOURCE_ABSOLUTE_PATH", SOURCE_JOIN_CATEGORY, "absolute_path", {}, "oracle.source_path"),
        MutationSpec("S3_SOURCE_TRAVERSAL_PATH", SOURCE_JOIN_CATEGORY, "traversal_path", {}, "oracle.source_path"),
        MutationSpec("S3_SOURCE_SYMLINK_FILE", SOURCE_JOIN_CATEGORY, "symlink_file", {}, "oracle.source_path"),
        MutationSpec("S3_SOURCE_SYMLINK_ANCESTOR", SOURCE_JOIN_CATEGORY, "symlink_ancestor", {}, "oracle.source_path"),
        MutationSpec("S3_SOURCE_SCHEMA_ORDER", SOURCE_JOIN_CATEGORY, "schema_order", {}, "oracle.validate_frame"),
        MutationSpec("S3_SOURCE_SCHEMA_MISSING_COLUMN", SOURCE_JOIN_CATEGORY, "schema_missing_column", {}, "oracle.validate_frame"),
        MutationSpec("S3_SOURCE_SYMBOL_MISMATCH", SOURCE_JOIN_CATEGORY, "frame_symbol_mismatch", {}, "oracle.validate_frame"),
        MutationSpec("S3_SOURCE_SESSION_MISMATCH", SOURCE_JOIN_CATEGORY, "frame_session_mismatch", {}, "oracle.validate_frame"),
        MutationSpec("S3_SOURCE_OHLC_NON_POSITIVE", SOURCE_JOIN_CATEGORY, "ohlc_non_positive", {}, "oracle.validate_frame"),
        MutationSpec("S3_SOURCE_OHLC_NAN", SOURCE_JOIN_CATEGORY, "ohlc_nan", {}, "oracle.validate_frame"),
        MutationSpec("S3_SOURCE_OHLC_INFINITE", SOURCE_JOIN_CATEGORY, "ohlc_infinite", {}, "oracle.validate_frame"),
        MutationSpec("S3_SOURCE_OHLC_BOUNDS", SOURCE_JOIN_CATEGORY, "ohlc_bounds", {}, "oracle.validate_frame"),
        MutationSpec("S3_JOIN_RECORD_ID_MISMATCH", SOURCE_JOIN_CATEGORY, "join_record_id", {}, "oracle.join_failure"),
        MutationSpec("S3_JOIN_PATH_MISMATCH", SOURCE_JOIN_CATEGORY, "join_path", {}, "oracle.join_failure"),
        MutationSpec("S3_JOIN_SHA_MISMATCH", SOURCE_JOIN_CATEGORY, "join_sha", {}, "oracle.join_failure"),
        MutationSpec("S3_JOIN_MANIFEST_HASH_MISMATCH", SOURCE_JOIN_CATEGORY, "join_manifest_hash", {}, "oracle.join_failure"),
        MutationSpec("S3_JOIN_MANIFEST_VERSION_MISMATCH", SOURCE_JOIN_CATEGORY, "join_manifest_version", {}, "oracle.join_failure"),
        MutationSpec("S3_JOIN_PROVENANCE_SYMBOL_MISMATCH", SOURCE_JOIN_CATEGORY, "join_provenance_symbol", {}, "oracle.join_failure"),
        MutationSpec("S3_JOIN_PROVENANCE_SESSION_MISMATCH", SOURCE_JOIN_CATEGORY, "join_provenance_session", {}, "oracle.join_failure"),
        MutationSpec("S3_JOIN_CORE_SYMBOL_MISMATCH", SOURCE_JOIN_CATEGORY, "join_core_symbol", {}, "oracle.join_failure"),
        MutationSpec("S3_JOIN_CORE_SESSION_MISMATCH", SOURCE_JOIN_CATEGORY, "join_core_session", {}, "oracle.join_failure"),
        MutationSpec("S3_SOURCE_VALIDATION_BLOCKS_MEASURED", SOURCE_JOIN_CATEGORY, "source_validation_blocking", {}, "engine.measure_candidate"),
    )


def execute_source_join_spec(spec: MutationSpec) -> RawExecution:
    executors = {
        "missing_manifest_join": _exec_missing_manifest_join,
        "missing_physical_file": _exec_source_path,
        "sha_mismatch": _exec_source_path,
        "size_mismatch": _exec_source_path,
        "absolute_path": _exec_source_path,
        "traversal_path": _exec_source_path,
        "symlink_file": _exec_source_path,
        "symlink_ancestor": _exec_source_path,
        "schema_order": _exec_frame_validation,
        "schema_missing_column": _exec_frame_validation,
        "frame_symbol_mismatch": _exec_frame_validation,
        "frame_session_mismatch": _exec_frame_validation,
        "ohlc_non_positive": _exec_frame_validation,
        "ohlc_nan": _exec_frame_validation,
        "ohlc_infinite": _exec_frame_validation,
        "ohlc_bounds": _exec_frame_validation,
        "join_record_id": _exec_join,
        "join_path": _exec_join,
        "join_sha": _exec_join,
        "join_manifest_hash": _exec_join,
        "join_manifest_version": _exec_join,
        "join_provenance_symbol": _exec_join,
        "join_provenance_session": _exec_join,
        "join_core_symbol": _exec_join,
        "join_core_session": _exec_join,
        "source_validation_blocking": _exec_source_validation_blocking,
    }
    return executors[spec.mutation_kind](spec)


def _exec_missing_manifest_join(spec: MutationSpec) -> RawExecution:
    candidate = _candidate()
    before = {"candidate": candidate, "source": _source_record()}
    failures = _failures(join_failure(candidate, None))
    after = {"candidate": candidate, "source": None}
    return _raw(failures, before, after)


def _exec_source_path(spec: MutationSpec) -> RawExecution:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = _source_record(root)
        parquet = root / source["logical_path"]
        before = {"source": dict(source), "path_exists": parquet.exists(), "path_is_symlink": parquet.is_symlink()}
        if spec.mutation_kind == "missing_physical_file":
            parquet.unlink()
        elif spec.mutation_kind == "sha_mismatch":
            source["actual_sha256"] = "0" * 64
        elif spec.mutation_kind == "size_mismatch":
            source["byte_size"] = int(source["byte_size"]) + 1
        elif spec.mutation_kind == "absolute_path":
            source["logical_path"] = "/tmp/orb_s3_source_join_outside.parquet"
        elif spec.mutation_kind == "traversal_path":
            source["logical_path"] = "runtime/upstox_candidate_replay/../outside.parquet"
        elif spec.mutation_kind == "symlink_file":
            parquet.unlink()
            parquet.symlink_to(root / "missing-target.parquet")
        elif spec.mutation_kind == "symlink_ancestor":
            shutil.rmtree(root / "runtime" / "upstox_candidate_replay")
            outside = root / "outside"
            outside.mkdir()
            (root / "runtime" / "upstox_candidate_replay").symlink_to(outside)
        after = {"source": dict(source), "path_exists": (root / str(source["logical_path"])).exists()}
        try:
            source_path(source, root)
            failures = ()
        except ValueError as exc:
            failures = (str(exc),)
    return _raw(failures, before, after)


def _exec_frame_validation(spec: MutationSpec) -> RawExecution:
    source = _source_record()
    frame = _frame()
    before = _frame_snapshot(frame)
    if spec.mutation_kind == "schema_order":
        frame = frame[list(reversed(frame.columns))]
    elif spec.mutation_kind == "schema_missing_column":
        frame = frame.drop(columns=["provider"])
    elif spec.mutation_kind == "frame_symbol_mismatch":
        frame.loc[0, "symbol"] = "BANKNIFTY"
    elif spec.mutation_kind == "frame_session_mismatch":
        frame["timestamp"] = frame["timestamp"] + pd.Timedelta(days=1)
    elif spec.mutation_kind == "ohlc_non_positive":
        frame.loc[0, "open"] = 0.0
    elif spec.mutation_kind == "ohlc_nan":
        frame.loc[0, "close"] = float("nan")
    elif spec.mutation_kind == "ohlc_infinite":
        frame.loc[0, "high"] = float("inf")
    elif spec.mutation_kind == "ohlc_bounds":
        frame.loc[0, "high"] = frame.loc[0, "low"] - 1.0
    failures = _failures(validate_frame(frame, source))
    return _raw(failures, before, _frame_snapshot(frame))


def _exec_join(spec: MutationSpec) -> RawExecution:
    source = _source_record()
    candidate = _candidate(source)
    before = {"candidate": json.loads(json.dumps(candidate)), "source": dict(source)}
    if spec.mutation_kind == "join_record_id":
        candidate["source_provenance"]["source_record_id"] = "other-source"
    elif spec.mutation_kind == "join_path":
        candidate["source_provenance"]["source_logical_path"] = "runtime/upstox_candidate_replay/20260706/underlying/OTHER.parquet"
    elif spec.mutation_kind == "join_sha":
        candidate["source_provenance"]["source_actual_sha256"] = "0" * 64
    elif spec.mutation_kind == "join_manifest_hash":
        candidate["source_provenance"]["source_manifest_semantic_hash"] = "0" * 64
    elif spec.mutation_kind == "join_manifest_version":
        candidate["source_provenance"]["source_manifest_version"] = "v1"
    elif spec.mutation_kind == "join_provenance_symbol":
        candidate["source_provenance"]["source_symbol"] = "BANKNIFTY"
    elif spec.mutation_kind == "join_provenance_session":
        candidate["source_provenance"]["source_session_date"] = "2026-07-07"
    elif spec.mutation_kind == "join_core_symbol":
        candidate["candidate_core"]["symbol"] = "BANKNIFTY"
    elif spec.mutation_kind == "join_core_session":
        candidate["candidate_core"]["session_date"] = "2026-07-07"
    after = {"candidate": candidate, "source": dict(source)}
    return _raw(_failures(join_failure(candidate, source)), before, after)


def _exec_source_validation_blocking(spec: MutationSpec) -> RawExecution:
    source = _source_record()
    candidate = _candidate(source)
    frame = _frame().drop(columns=["provider"])
    before = {"candidate": candidate, "source": source, "frame": "schema_missing_column"}
    outcome = measure_candidate(candidate, source, frame, "contract", source_failure="SOURCE_SCHEMA_MISMATCH")
    after = {"terminal_reason": outcome["terminal_reason"], "terminal_detail": outcome["terminal_detail"]}
    return _raw((outcome["terminal_reason"],), before, after)


def _raw(failures: tuple[str, ...], before: Any, after: Any) -> RawExecution:
    return RawExecution(
        observed_failures=failures,
        target_invoked=True,
        mutation_applied=digest(before) != digest(after),
        fixture_hash_before=digest(before),
        fixture_hash_after=digest(after),
        target_output_hash=digest(failures),
    )


def _failures(code: str | None) -> tuple[str, ...]:
    return () if code is None else (code,)


def _source_record(root: Path | None = None) -> dict[str, Any]:
    logical_path = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    record = {
        "source_record_id": "source-nifty-20260706",
        "logical_path": logical_path,
        "actual_sha256": "a" * 64,
        "byte_size": 1,
        "session_date": "2026-07-06",
        "symbol": "NIFTY",
    }
    if root is not None:
        parquet = root / logical_path
        parquet.parent.mkdir(parents=True)
        _frame().to_parquet(parquet, index=False)
        record["actual_sha256"] = sha256_file(parquet)
        record["byte_size"] = parquet.stat().st_size
    return record


def _candidate(source: dict[str, Any] | None = None) -> dict[str, Any]:
    source = source or _source_record()
    return {
        "candidate_id": "candidate-nifty-20260706",
        "candidate_core": {
            "strategy_id": "opening_range_retest_v1",
            "symbol": "NIFTY",
            "direction": "BUY_CALL",
            "status": "RAW_CANDIDATE",
            "raw_score": 1.0,
            "entry_trigger": "entry",
            "invalid_if": "invalid",
            "rank_reason": "rank",
            "proposal_ready_at_iso": "2026-07-06T09:20:00+05:30",
            "setup_id": "setup",
            "history_hash": "history",
            "session_date": "2026-07-06",
        },
        "source_provenance": {
            "source_record_id": source["source_record_id"],
            "source_logical_path": source["logical_path"],
            "source_actual_sha256": source["actual_sha256"],
            "source_manifest_semantic_hash": INPUT_SOURCE_HASH,
            "source_manifest_version": "v2",
            "source_session_date": source["session_date"],
            "source_symbol": source["symbol"],
        },
    }


def _frame() -> pd.DataFrame:
    timestamps = pd.date_range("2026-07-06 09:15", periods=375, freq="min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": ["NIFTY"] * len(timestamps),
            "open": [100.0 + idx for idx in range(len(timestamps))],
            "high": [101.0 + idx for idx in range(len(timestamps))],
            "low": [99.0 + idx for idx in range(len(timestamps))],
            "close": [100.5 + idx for idx in range(len(timestamps))],
            "volume": [1] * len(timestamps),
            "oi": [0] * len(timestamps),
            "source": ["fixture"] * len(timestamps),
            "interval": ["1minute"] * len(timestamps),
            "fetch_timestamp": ["2026-07-06T16:00:00+05:30"] * len(timestamps),
            "fetch_start_date": ["2026-07-06"] * len(timestamps),
            "fetch_end_date": ["2026-07-06"] * len(timestamps),
            "data_origin": ["fixture"] * len(timestamps),
            "synthetic": [False] * len(timestamps),
            "mock": [False] * len(timestamps),
            "fallback": [False] * len(timestamps),
            "provider": ["upstox"] * len(timestamps),
            "source_endpoint": ["historical-candle"] * len(timestamps),
        }
    )


def _frame_snapshot(frame: pd.DataFrame) -> dict[str, Any]:
    return {"columns": list(frame.columns), "rows": frame.head(5).to_dict("records"), "row_count": len(frame)}
