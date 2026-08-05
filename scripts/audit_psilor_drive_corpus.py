#!/usr/bin/env python3
"""Fail-closed audit of a sealed PSILOR/Drive market-data corpus.

This auditor intentionally avoids reading Parquet row data. It verifies the
sealed session manifest, normalized chunk manifest, validation reports, and
embedded Parquet schema metadata that are already available. Equality-only
local-sequence findings are not silently accepted: they require a row-level tie
audit before normalized rows may be admitted.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

ISSUE_RE = re.compile(
    r"Non-monotonic local sequence\s+(?P<previous>\d+)\s*->\s*(?P<current>\d+)\s+in\s+(?P<file>.+)$"
)
PANDAS_METADATA_RE = re.compile(
    rb'(\{"index_columns".*?"pandas_version"\s*:\s*"[^"]+"\})', re.DOTALL
)
PARTITION_RE = re.compile(
    r"asset_class=(?P<asset>[^/]+)/trade_date=(?P<date>[^/]+)/provider=(?P<provider>[^/]+)/instrument_family=(?P<family>[^/]+)/hour=(?P<hour>[^/]+)"
)


class AuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class SequenceIssueSummary:
    total: int
    equal: int
    backward: int
    forward_or_unknown: int
    unparsed: int
    affected_files: int


@dataclass(frozen=True)
class ManifestIntegrity:
    chunk_entries: int
    chunk_rows: int
    chunk_bytes: int
    unique_paths: int
    unique_hashes: int
    missing_from_sealed_manifest: int
    hash_mismatches: int
    duplicate_paths: int
    duplicate_hashes: int
    nonpositive_row_files: int
    nonpositive_size_files: int
    chunk_sequence_groups: int
    chunk_sequence_anomaly_groups: int


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"Unable to read JSON {path}: {exc}") from exc


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AuditError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
                if not isinstance(value, dict):
                    raise AuditError(f"Expected object at {path}:{line_no}")
                rows.append(value)
    except OSError as exc:
        raise AuditError(f"Unable to read JSONL {path}: {exc}") from exc
    return rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract_pandas_schema(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AuditError(f"Unable to read Parquet schema source {path}: {exc}") from exc
    matches = PANDAS_METADATA_RE.findall(data)
    if not matches:
        return {"status": "NO_EMBEDDED_PANDAS_METADATA", "columns": []}
    try:
        metadata = json.loads(matches[-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Embedded pandas metadata is invalid in {path}: {exc}") from exc
    columns = [
        {
            "name": item.get("name"),
            "pandas_type": item.get("pandas_type"),
            "numpy_type": item.get("numpy_type"),
        }
        for item in metadata.get("columns", [])
    ]
    names = {item["name"] for item in columns}
    quote_columns = {"bid_price", "ask_price"}
    return {
        "status": "PRESENT",
        "columns": columns,
        "quote_schema": (
            "BID_ASK_COLUMNS_PRESENT_VALUES_NOT_AUDITED"
            if quote_columns.issubset(names)
            else "BID_ASK_COLUMNS_NOT_PROVEN"
        ),
    }


def summarize_sequence_issues(issues: Iterable[Any]) -> SequenceIssueSummary:
    equal = backward = forward_or_unknown = unparsed = 0
    files: set[str] = set()
    total = 0
    for issue in issues:
        total += 1
        if not isinstance(issue, str):
            unparsed += 1
            continue
        match = ISSUE_RE.fullmatch(issue.strip())
        if not match:
            unparsed += 1
            continue
        previous = int(match.group("previous"))
        current = int(match.group("current"))
        files.add(match.group("file"))
        if current == previous:
            equal += 1
        elif current < previous:
            backward += 1
        else:
            forward_or_unknown += 1
    return SequenceIssueSummary(
        total=total,
        equal=equal,
        backward=backward,
        forward_or_unknown=forward_or_unknown,
        unparsed=unparsed,
        affected_files=len(files),
    )


def audit_manifests(
    session_manifest: dict[str, Any], chunks: list[dict[str, Any]]
) -> tuple[ManifestIntegrity, dict[str, Any]]:
    sealed = session_manifest.get("checksums")
    if not isinstance(sealed, dict):
        raise AuditError("session_manifest.checksums must be an object")

    path_counts: collections.Counter[str] = collections.Counter()
    hash_counts: collections.Counter[str] = collections.Counter()
    missing: list[str] = []
    mismatches: list[dict[str, str]] = []
    nonpositive_rows: list[str] = []
    nonpositive_sizes: list[str] = []
    groups: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    assets: dict[tuple[str, str], dict[str, Any]] = collections.defaultdict(
        lambda: {
            "files": 0,
            "rows": 0,
            "bytes": 0,
            "first_source_timestamp": None,
            "last_source_timestamp": None,
        }
    )

    for index, row in enumerate(chunks):
        required = {
            "run_id",
            "partition",
            "chunk_sequence",
            "relative_path",
            "row_count",
            "size_bytes",
            "sha256",
        }
        absent = sorted(required.difference(row))
        if absent:
            raise AuditError(f"Chunk {index} missing fields: {absent}")
        path = str(row["relative_path"])
        digest = str(row["sha256"])
        path_counts[path] += 1
        hash_counts[digest] += 1
        if int(row["row_count"]) <= 0:
            nonpositive_rows.append(path)
        if int(row["size_bytes"]) <= 0:
            nonpositive_sizes.append(path)
        sealed_digest = sealed.get(path)
        if sealed_digest is None:
            missing.append(path)
        elif sealed_digest != digest:
            mismatches.append(
                {"path": path, "sealed_sha256": str(sealed_digest), "chunk_sha256": digest}
            )
        key = (str(row["run_id"]), str(row["partition"]))
        groups[key].append(int(row["chunk_sequence"]))

        partition_match = PARTITION_RE.fullmatch(str(row["partition"]))
        asset_key = (
            partition_match.group("asset"),
            partition_match.group("family"),
        ) if partition_match else ("UNKNOWN", "UNKNOWN")
        summary = assets[asset_key]
        summary["files"] += 1
        summary["rows"] += int(row["row_count"])
        summary["bytes"] += int(row["size_bytes"])
        first = row.get("first_source_timestamp")
        last = row.get("last_source_timestamp")
        if isinstance(first, int):
            current = summary["first_source_timestamp"]
            summary["first_source_timestamp"] = first if current is None else min(current, first)
        if isinstance(last, int):
            current = summary["last_source_timestamp"]
            summary["last_source_timestamp"] = last if current is None else max(current, last)

    sequence_anomalies: list[dict[str, Any]] = []
    for (run_id, partition), sequences in groups.items():
        counts = collections.Counter(sequences)
        duplicates = sorted(value for value, count in counts.items() if count > 1)
        minimum = min(sequences)
        maximum = max(sequences)
        missing_sequences = sorted(set(range(minimum, maximum + 1)).difference(counts))
        if minimum != 1 or duplicates or missing_sequences:
            sequence_anomalies.append(
                {
                    "run_id": run_id,
                    "partition": partition,
                    "minimum": minimum,
                    "maximum": maximum,
                    "duplicates": duplicates,
                    "missing": missing_sequences,
                }
            )

    integrity = ManifestIntegrity(
        chunk_entries=len(chunks),
        chunk_rows=sum(int(row["row_count"]) for row in chunks),
        chunk_bytes=sum(int(row["size_bytes"]) for row in chunks),
        unique_paths=len(path_counts),
        unique_hashes=len(hash_counts),
        missing_from_sealed_manifest=len(missing),
        hash_mismatches=len(mismatches),
        duplicate_paths=sum(count - 1 for count in path_counts.values() if count > 1),
        duplicate_hashes=sum(count - 1 for count in hash_counts.values() if count > 1),
        nonpositive_row_files=len(nonpositive_rows),
        nonpositive_size_files=len(nonpositive_sizes),
        chunk_sequence_groups=len(groups),
        chunk_sequence_anomaly_groups=len(sequence_anomalies),
    )
    detail = {
        "asset_inventory": {
            f"{asset}:{family}": summary for (asset, family), summary in sorted(assets.items())
        },
        "missing_paths": missing,
        "hash_mismatches": mismatches,
        "nonpositive_row_paths": nonpositive_rows,
        "nonpositive_size_paths": nonpositive_sizes,
        "chunk_sequence_anomalies": sequence_anomalies,
    }
    return integrity, detail


def classify(
    session_manifest: dict[str, Any],
    validation_report: dict[str, Any],
    partition_report: dict[str, Any],
    integrity: ManifestIntegrity,
    sequence: SequenceIssueSummary,
) -> dict[str, Any]:
    manifest_pass = all(
        value == 0
        for value in (
            integrity.missing_from_sealed_manifest,
            integrity.hash_mismatches,
            integrity.duplicate_paths,
            integrity.duplicate_hashes,
            integrity.nonpositive_row_files,
            integrity.nonpositive_size_files,
            integrity.chunk_sequence_anomaly_groups,
        )
    )
    raw_valid = validation_report.get("raw_valid") is True
    partition_pass = partition_report.get("status") == "PASS" and not partition_report.get("errors")
    normalized_flag = validation_report.get("normalized_valid") is True

    if not manifest_pass or not raw_valid or not partition_pass:
        reuse = "REBUILD_FROM_RAW_OR_REJECT"
    elif sequence.backward or sequence.forward_or_unknown or sequence.unparsed:
        reuse = "REBUILD_FROM_RAW_REQUIRED"
    elif normalized_flag and sequence.total == 0:
        reuse = "REUSE_DIRECTLY_AFTER_MATERIALIZATION"
    elif sequence.total and sequence.equal == sequence.total:
        reuse = "NORMALIZED_REUSE_REQUIRES_EQUAL_SEQUENCE_TIE_AUDIT"
    else:
        reuse = "NORMALIZED_REUSE_NOT_ADMITTED"

    return {
        "manifest_integrity": "PASS" if manifest_pass else "FAIL",
        "raw_authority": "PASS" if raw_valid else "FAIL",
        "partition_validation": "PASS" if partition_pass else "FAIL",
        "normalized_reported_valid": normalized_flag,
        "normalized_reuse_verdict": reuse,
        "historical_session_admission": "NO",
        "data_ready_for_dorl_only": False,
        "data_ready_for_psilor_proxy_validation": False,
        "formal_extraction_approved": False,
        "reason": (
            "The corpus covers one partial live session. Equality-only local-sequence findings "
            "must be resolved using row identity/source-frame ties; they are not evidence of a "
            "backward sequence regression, but cannot be silently accepted."
        ),
        "sealed_total_files": session_manifest.get("total_files"),
        "sealed_total_bytes": session_manifest.get("total_bytes"),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    session_manifest = load_json(args.session_manifest)
    validation_report = load_json(args.validation_report)
    partition_report = load_json(args.partition_validation_report)
    chunks = load_jsonl(args.chunk_manifest)

    integrity, detail = audit_manifests(session_manifest, chunks)
    sequence = summarize_sequence_issues(validation_report.get("issues", []))
    result = {
        "audit_version": 1,
        "session": {
            key: session_manifest.get(key)
            for key in ("run_id", "date", "sealed_at_utc", "total_files", "total_bytes")
        },
        "manifest_integrity": asdict(integrity),
        "sequence_issues": asdict(sequence),
        "detail": detail,
        "classification": classify(
            session_manifest, validation_report, partition_report, integrity, sequence
        ),
    }
    if args.sample_parquet:
        result["sample_parquet"] = {
            "path": str(args.sample_parquet),
            "sha256": sha256_file(args.sample_parquet),
            **extract_pandas_schema(args.sample_parquet),
        }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-manifest", type=Path, required=True)
    parser.add_argument("--chunk-manifest", type=Path, required=True)
    parser.add_argument("--validation-report", type=Path, required=True)
    parser.add_argument("--partition-validation-report", type=Path, required=True)
    parser.add_argument("--sample-parquet", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except AuditError as exc:
        print(f"AUDIT_FAILED={exc}")
        return 2
    print(f"AUDIT_OUTPUT={args.output}")
    print(f"NORMALIZED_REUSE_VERDICT={result['classification']['normalized_reuse_verdict']}")
    print(f"DATA_READY_FOR_DORL_ONLY={str(result['classification']['data_ready_for_dorl_only']).upper()}")
    print(
        "DATA_READY_FOR_PSILOR_PROXY_VALIDATION="
        f"{str(result['classification']['data_ready_for_psilor_proxy_validation']).upper()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
