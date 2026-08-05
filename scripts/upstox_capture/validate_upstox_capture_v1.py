#!/usr/bin/env python3
"""Fail-closed integrity validation for an Upstox capture session."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import struct
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import zstandard as zstd

sys.path.append(str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate_capture")

IDENTITY_COLUMNS = ("connection_id", "local_sequence", "instrument_key")
NON_IDENTITY_COLUMNS = (
    "source_exchange_ts",
    "provider_current_ts",
    "provider_last_trade_ts",
    "receive_wall_ts_utc",
    "receive_monotonic_ns",
    "ltp",
    "volume",
    "open_interest",
)


def validate_raw_frames(run_dir: Path) -> dict[str, Any]:
    raw_dir = run_dir / "raw"
    if not raw_dir.exists():
        return {"status": "MISSING_RAW_DATA", "error": "Raw folder missing"}

    bin_files = list(raw_dir.glob("**/*.bin.zst"))
    issues: list[str] = []
    total_index_rows = 0
    total_bin_records = 0

    for bin_file in bin_files:
        index_file = bin_file.parent / f"{bin_file.name.split('.')[0]}.index.parquet"
        if not index_file.exists():
            issues.append(f"Index file missing for {bin_file.name}")
            continue

        try:
            with bin_file.open("rb") as fh:
                dctx = zstd.ZstdDecompressor()
                with dctx.stream_reader(fh) as reader:
                    while True:
                        len_bytes = reader.read(4)
                        if not len_bytes:
                            break
                        if len(len_bytes) < 4:
                            issues.append(f"Truncated frame length header in {bin_file.name}")
                            break
                        length = struct.unpack(">I", len_bytes)[0]
                        payload = reader.read(length)
                        if len(payload) < length:
                            issues.append(f"Truncated frame payload in {bin_file.name}")
                            break
                        total_bin_records += 1
        except Exception as exc:  # pragma: no cover - provider/file dependent
            issues.append(f"Zstd corruption or read error in {bin_file.name}: {exc}")

        try:
            total_index_rows += len(pq.read_table(index_file).to_pandas())
        except Exception as exc:  # pragma: no cover - provider/file dependent
            issues.append(f"Failed to read index parquet {index_file.name}: {exc}")

    return {
        "total_bin_records": total_bin_records,
        "total_index_rows": total_index_rows,
        "raw_issues": issues,
        "success": len(issues) == 0 and total_bin_records == total_index_rows,
    }


def _normalize_identity_value(value: Any) -> Any:
    return None if pd.isna(value) else value


def find_local_sequence_issues(df: pd.DataFrame, file_name: str) -> dict[str, Any]:
    """Validate frame sequence without rejecting valid multi-instrument frame ties.

    The capture increments ``local_sequence`` once per websocket frame and emits
    one normalized row per instrument contained in that frame. Therefore equal
    sequence values across different instrument keys are expected. A lower
    sequence within the same connection is a regression. Repeated
    ``(connection_id, local_sequence, instrument_key)`` identities are either
    exact duplicates requiring dedupe or conflicting duplicates requiring
    rejection.
    """
    required = set(IDENTITY_COLUMNS)
    missing = sorted(required.difference(df.columns))
    if missing:
        return {
            "issues": [f"Missing sequence identity columns {missing} in {file_name}"],
            "equal_frame_ties": 0,
            "backward_regressions": 0,
            "exact_duplicate_events": 0,
            "conflicting_duplicate_events": 0,
        }

    issues: list[str] = []
    equal_frame_ties = 0
    backward_regressions = 0
    exact_duplicates = 0
    conflicting_duplicates = 0

    for connection_id, group in df.groupby("connection_id", dropna=False, sort=False):
        sequences = pd.to_numeric(group["local_sequence"], errors="coerce")
        previous: int | None = None
        previous_instrument: Any = None
        for row_index, (sequence, instrument_key) in enumerate(
            zip(sequences.tolist(), group["instrument_key"].tolist())
        ):
            if pd.isna(sequence):
                issues.append(
                    f"Null/non-numeric local sequence at row {row_index} in {file_name}"
                )
                continue
            current = int(sequence)
            if previous is not None:
                if current < previous:
                    backward_regressions += 1
                    issues.append(
                        "Backward local sequence regression "
                        f"{previous} -> {current} for connection {connection_id} in {file_name}"
                    )
                elif current == previous and instrument_key != previous_instrument:
                    equal_frame_ties += 1
            previous = current
            previous_instrument = instrument_key

    identity_groups = df.groupby(list(IDENTITY_COLUMNS), dropna=False, sort=False)
    compare_columns = [column for column in NON_IDENTITY_COLUMNS if column in df.columns]
    for identity, group in identity_groups:
        if len(group) <= 1:
            continue
        normalized_identity = tuple(_normalize_identity_value(value) for value in identity)
        comparable = group[compare_columns].copy() if compare_columns else group.copy()
        comparable = comparable.astype(object).where(pd.notna(comparable), None)
        unique_rows = comparable.drop_duplicates()
        duplicate_count = len(group) - 1
        if len(unique_rows) == 1:
            exact_duplicates += duplicate_count
            issues.append(
                f"Exact duplicate normalized event {normalized_identity} x{len(group)} "
                f"in {file_name}; deterministic dedupe required"
            )
        else:
            conflicting_duplicates += duplicate_count
            issues.append(
                f"Conflicting duplicate normalized event {normalized_identity} x{len(group)} "
                f"in {file_name}"
            )

    return {
        "issues": issues,
        "equal_frame_ties": equal_frame_ties,
        "backward_regressions": backward_regressions,
        "exact_duplicate_events": exact_duplicates,
        "conflicting_duplicate_events": conflicting_duplicates,
    }


def validate_normalized_ticks(run_dir: Path) -> dict[str, Any]:
    normalized_dir = run_dir / "normalized"
    if not normalized_dir.exists():
        return {"status": "MISSING_NORMALIZED_DATA", "error": "Normalized folder missing"}

    parquet_files = list(normalized_dir.glob("**/*.parquet"))
    issues: list[str] = []
    total_rows = 0
    equal_frame_ties = 0
    backward_regressions = 0
    exact_duplicate_events = 0
    conflicting_duplicate_events = 0

    for file_path in parquet_files:
        try:
            df = pq.read_table(file_path, partitioning=None).to_pandas()
            total_rows += len(df)

            expected_cols = [
                "ltp",
                "volume",
                "open_interest",
                "receive_wall_ts_utc",
                "receive_monotonic_ns",
                "connection_id",
                "instrument_key",
                "local_sequence",
            ]
            for column in expected_cols:
                if column not in df.columns:
                    issues.append(
                        f"Missing expected schema column {column} in {file_path.name}"
                    )

            sequence = find_local_sequence_issues(df, file_path.name)
            issues.extend(sequence["issues"])
            equal_frame_ties += sequence["equal_frame_ties"]
            backward_regressions += sequence["backward_regressions"]
            exact_duplicate_events += sequence["exact_duplicate_events"]
            conflicting_duplicate_events += sequence["conflicting_duplicate_events"]

            if "receive_wall_ts_utc" in df.columns:
                timestamps = pd.to_datetime(
                    df["receive_wall_ts_utc"], format="ISO8601", utc=True, errors="coerce"
                )
                invalid = timestamps.isna().sum()
                if invalid:
                    issues.append(
                        f"Detected {int(invalid)} invalid receive timestamps in {file_path.name}"
                    )
                now_ts = pd.Timestamp.now(tz="UTC")
                future_ticks = timestamps[timestamps > now_ts + pd.Timedelta(seconds=60)]
                if not future_ticks.empty:
                    issues.append(
                        f"Detected {len(future_ticks)} ticks with future timestamp in {file_path.name}"
                    )

        except Exception as exc:  # pragma: no cover - provider/file dependent
            issues.append(f"Failed to validate normalized file {file_path.name}: {exc}")

    return {
        "total_normalized_rows": total_rows,
        "normalized_issues": issues,
        "equal_frame_ties": equal_frame_ties,
        "backward_regressions": backward_regressions,
        "exact_duplicate_events": exact_duplicate_events,
        "conflicting_duplicate_events": conflicting_duplicate_events,
        "success": len(issues) == 0,
    }


def calculate_sha256(filepath: Path) -> str:
    digest = hashlib.sha256()
    with filepath.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Capture run root directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        logger.error("Run directory %s does not exist.", run_dir)
        raise SystemExit(1)

    logger.info("Starting integrity verification of capture session: %s", run_dir)
    raw_results = validate_raw_frames(run_dir)
    normalized_results = validate_normalized_ticks(run_dir)
    all_issues = raw_results.get("raw_issues", []) + normalized_results.get(
        "normalized_issues", []
    )

    report = {
        "run_dir": str(run_dir),
        "raw_valid": raw_results.get("success", False),
        "normalized_valid": normalized_results.get("success", False),
        "total_raw_frames": raw_results.get("total_bin_records", 0),
        "total_normalized_rows": normalized_results.get("total_normalized_rows", 0),
        "equal_frame_ties": normalized_results.get("equal_frame_ties", 0),
        "backward_regressions": normalized_results.get("backward_regressions", 0),
        "exact_duplicate_events": normalized_results.get("exact_duplicate_events", 0),
        "conflicting_duplicate_events": normalized_results.get(
            "conflicting_duplicate_events", 0
        ),
        "issues_count": len(all_issues),
        "issues": all_issues,
    }

    report_path = run_dir / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    logger.info("Verification complete. Issues found: %s", len(all_issues))
    for issue in all_issues[:10]:
        logger.warning("Issue: %s", issue)
    if len(all_issues) > 10:
        logger.warning("... and %s more issues.", len(all_issues) - 10)
    logger.info("Report saved to %s", report_path)

    if all_issues:
        raise SystemExit(1)
    logger.info("Session verified successfully (REPLAY_QUALITY_CERTIFIED).")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
