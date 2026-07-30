from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

REQUIRED_COLUMNS = ("ts", "instrument_key", "ltp")
OPTIONAL_COLUMNS = ("bid_price", "ask_price", "delta", "theta", "gamma", "vega", "iv", "volume", "oi")
READ_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
OPTION_PREFIXES = {"BSE_FO", "NSE_FO", "NFO", "BFO"}


class HistoricalReplayError(ValueError):
    """Raised when real-artifact replay inputs are missing or unsafe."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parquet_module():
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:  # pragma: no cover - pyarrow is a TradeBot dependency
        raise RuntimeError("pyarrow_required_for_historical_replay") from exc
    return parquet


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _schema_fingerprint(schema: Any) -> str:
    fields = [{"name": field.name, "type": str(field.type), "nullable": bool(field.nullable)} for field in schema]
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _discover(path: Path) -> tuple[Path, ...]:
    if path.is_file():
        return (path.resolve(),)
    if not path.is_dir():
        return ()
    return tuple(sorted({item.resolve() for pattern in ("*.parquet", "*.parquet.bin") for item in path.rglob(pattern) if item.is_file()}))


def _json_object(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    target = Path(path)
    if not target.is_file():
        raise HistoricalReplayError(f"json_file_not_found:{target}")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HistoricalReplayError(f"json_file_invalid:{target}") from exc
    if not isinstance(payload, Mapping):
        raise HistoricalReplayError(f"json_object_required:{target}")
    return dict(payload)


def _safe_manifest_count(manifest: Mapping[str, Any], field: str) -> int:
    value = manifest.get(field, 0)
    try:
        count = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise HistoricalReplayError(f"collector_manifest_invalid_integer:{field}") from exc
    if count < 0:
        raise HistoricalReplayError(f"collector_manifest_negative_integer:{field}")
    return count


def _provenance_failures(files: Iterable[Path], provenance: Mapping[str, Any]) -> list[str]:
    if not provenance:
        return []
    if provenance.get("synthetic") is not False or provenance.get("mock") is not False or provenance.get("fallback") is not False:
        return ["PROVENANCE_NOT_REAL_ONLY"]
    entries = provenance.get("files")
    if not isinstance(entries, list):
        return ["PROVENANCE_FILES_INVALID"]
    by_name = {str(item.get("fixture_name") or item.get("original_name") or ""): item for item in entries if isinstance(item, Mapping)}
    failures: list[str] = []
    for path in files:
        entry = by_name.get(path.name)
        if entry is None:
            failures.append(f"PROVENANCE_ENTRY_MISSING:{path.name}")
            continue
        if int(entry.get("size_bytes") or -1) != path.stat().st_size:
            failures.append(f"PROVENANCE_SIZE_MISMATCH:{path.name}")
        if str(entry.get("sha256") or "").lower() != sha256_file(path):
            failures.append(f"PROVENANCE_SHA256_MISMATCH:{path.name}")
    return failures


def analyze_parquet_partition(path: str | Path, *, batch_size: int = 65_536) -> dict[str, Any]:
    """Stream one immutable parquet partition and produce deterministic quality evidence."""
    target = Path(path).resolve()
    result: dict[str, Any] = {
        "path": str(target), "file_name": target.name, "exists": target.is_file(),
        "status": "REAL_ARTIFACT_REPLAY_FAIL", "hard_failures": [], "warnings": [],
    }
    if batch_size <= 0:
        raise HistoricalReplayError("batch_size_must_be_positive")
    if not target.is_file():
        result["hard_failures"].append("PARQUET_FILE_NOT_FOUND")
        return result
    result.update(size_bytes=target.stat().st_size, sha256=sha256_file(target))
    try:
        with target.open("rb") as handle:
            head = handle.read(4)
            handle.seek(-4, 2)
            tail = handle.read(4)
    except OSError as exc:
        result["hard_failures"].append(f"PARQUET_FILE_READ_FAILED:{type(exc).__name__}")
        return result
    result["parquet_magic_valid"] = head == b"PAR1" and tail == b"PAR1"
    if not result["parquet_magic_valid"]:
        result["hard_failures"].append("PARQUET_MAGIC_INVALID")
        return result

    try:
        parquet_file = _parquet_module().ParquetFile(target)
    except Exception as exc:
        result["hard_failures"].append(f"PARQUET_OPEN_FAILED:{type(exc).__name__}")
        return result
    schema = parquet_file.schema_arrow
    available = tuple(schema.names)
    missing = [column for column in REQUIRED_COLUMNS if column not in available]
    result.update(
        created_by=parquet_file.metadata.created_by,
        metadata_row_count=int(parquet_file.metadata.num_rows),
        row_group_count=int(parquet_file.metadata.num_row_groups),
        columns=list(available), required_columns=list(REQUIRED_COLUMNS),
        missing_required_columns=missing, schema_fingerprint=_schema_fingerprint(schema),
    )
    if missing:
        result["hard_failures"].append("REQUIRED_COLUMNS_MISSING")
        return result

    selected = [column for column in READ_COLUMNS if column in available]
    counters = {
        "streamed_row_count": 0, "valid_timestamp_rows": 0, "invalid_timestamp_rows": 0,
        "timestamp_order_violations": 0, "instrument_key_missing_rows": 0,
        "ltp_valid_rows": 0, "ltp_missing_rows": 0, "ltp_zero_rows": 0,
        "ltp_negative_rows": 0, "quote_complete_rows": 0, "crossed_market_rows": 0,
        "nonnegative_spread_rows": 0, "greeks_complete_rows": 0,
    }
    optional_nulls = {column: 0 for column in OPTIONAL_COLUMNS if column in available}
    keys: set[str] = set()
    prefixes: dict[str, int] = {}
    timestamp_min = timestamp_max = previous_timestamp = None
    spread_sum = 0.0
    spread_max = None
    try:
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=selected):
            columns = {name: batch.column(index).to_pylist() for index, name in enumerate(selected)}
            empty = [None] * int(batch.num_rows)
            counters["streamed_row_count"] += int(batch.num_rows)
            for offset in range(int(batch.num_rows)):
                timestamp = _finite(columns["ts"][offset])
                if timestamp is None:
                    counters["invalid_timestamp_rows"] += 1
                else:
                    counters["valid_timestamp_rows"] += 1
                    timestamp_min = timestamp if timestamp_min is None else min(timestamp_min, timestamp)
                    timestamp_max = timestamp if timestamp_max is None else max(timestamp_max, timestamp)
                    if previous_timestamp is not None and timestamp < previous_timestamp:
                        counters["timestamp_order_violations"] += 1
                    previous_timestamp = timestamp

                raw_key = columns["instrument_key"][offset]
                key = str(raw_key).strip() if raw_key is not None else ""
                if not key:
                    counters["instrument_key_missing_rows"] += 1
                else:
                    keys.add(key)
                    prefix = key.split("|", 1)[0]
                    prefixes[prefix] = prefixes.get(prefix, 0) + 1

                ltp = _finite(columns["ltp"][offset])
                if ltp is None:
                    counters["ltp_missing_rows"] += 1
                else:
                    counters["ltp_valid_rows"] += 1
                    counters["ltp_zero_rows"] += int(ltp == 0)
                    counters["ltp_negative_rows"] += int(ltp < 0)

                for column in optional_nulls:
                    optional_nulls[column] += int(columns[column][offset] is None)
                bid = _finite(columns.get("bid_price", empty)[offset])
                ask = _finite(columns.get("ask_price", empty)[offset])
                if bid is not None and ask is not None:
                    counters["quote_complete_rows"] += 1
                    spread = ask - bid
                    if spread < 0:
                        counters["crossed_market_rows"] += 1
                    else:
                        counters["nonnegative_spread_rows"] += 1
                        spread_sum += spread
                        spread_max = spread if spread_max is None else max(spread_max, spread)
                greeks = [_finite(columns.get(name, empty)[offset]) for name in ("delta", "theta", "gamma", "vega", "iv")]
                counters["greeks_complete_rows"] += int(all(value is not None for value in greeks))
    except Exception as exc:
        result["hard_failures"].append(f"PARQUET_STREAM_FAILED:{type(exc).__name__}")
        return result

    rows = counters["streamed_row_count"]
    option_rows = sum(count for prefix, count in prefixes.items() if prefix in OPTION_PREFIXES)
    result.update(counters)
    result.update(
        row_count_matches_metadata=rows == int(parquet_file.metadata.num_rows),
        timestamp_min_epoch=timestamp_min, timestamp_max_epoch=timestamp_max,
        duration_seconds=(timestamp_max - timestamp_min) if timestamp_min is not None and timestamp_max is not None else None,
        instrument_count=len(keys), instrument_prefix_counts=dict(sorted(prefixes.items())),
        option_row_count=option_rows,
        quote_complete_ratio=counters["quote_complete_rows"] / rows if rows else 0.0,
        mean_nonnegative_spread=spread_sum / counters["nonnegative_spread_rows"] if counters["nonnegative_spread_rows"] else None,
        max_nonnegative_spread=spread_max,
        greeks_complete_ratio=counters["greeks_complete_rows"] / rows if rows else 0.0,
        optional_null_counts=optional_nulls,
        artifact_class="OPTION_CHAIN_TICK_PARTITION" if option_rows else "INDEX_ONLY_TICK_PARTITION",
    )
    hard_conditions = (
        (rows == 0, "PARQUET_HAS_NO_ROWS"),
        (not result["row_count_matches_metadata"], "PARQUET_ROW_COUNT_MISMATCH"),
        (counters["valid_timestamp_rows"] == 0, "NO_VALID_TIMESTAMPS"),
        (counters["ltp_valid_rows"] == 0, "NO_VALID_LTP_VALUES"),
        (not keys, "NO_VALID_INSTRUMENT_KEYS"),
        (counters["ltp_negative_rows"] > 0, "NEGATIVE_LTP_OBSERVED"),
    )
    warning_conditions = (
        (counters["invalid_timestamp_rows"], "INVALID_TIMESTAMP_ROWS_OBSERVED"),
        (counters["timestamp_order_violations"], "TIMESTAMP_ORDER_VIOLATIONS_OBSERVED"),
        (counters["instrument_key_missing_rows"], "MISSING_INSTRUMENT_KEYS_OBSERVED"),
        (counters["ltp_missing_rows"], "MISSING_LTP_ROWS_OBSERVED"),
        (counters["ltp_zero_rows"], "ZERO_LTP_ROWS_OBSERVED"),
        (counters["crossed_market_rows"], "CROSSED_MARKET_ROWS_OBSERVED"),
        (option_rows and counters["quote_complete_rows"] == 0, "OPTION_ROWS_WITHOUT_COMPLETE_QUOTES"),
        (not option_rows, "INDEX_ONLY_PARTITION_NO_OPTION_ANALYTICS"),
    )
    result["hard_failures"].extend(code for condition, code in hard_conditions if condition)
    result["warnings"].extend(code for condition, code in warning_conditions if condition)
    result["status"] = "REAL_ARTIFACT_REPLAY_FAIL" if result["hard_failures"] else (
        "REAL_ARTIFACT_REPLAY_PASS_WITH_WARNINGS" if result["warnings"] else "REAL_ARTIFACT_REPLAY_PASS"
    )
    return result


def replay_historical_market_data(
    input_path: str | Path, *, collector_manifest_path: str | Path | None = None,
    provenance_path: str | Path | None = None, output_dir: str | Path | None = None,
    batch_size: int = 65_536,
) -> dict[str, Any]:
    """Replay real parquet files without inventing candidate or trade evidence."""
    source = Path(input_path).resolve()
    files = _discover(source)
    manifest = _json_object(collector_manifest_path)
    provenance = _json_object(provenance_path)
    provenance_failures = _provenance_failures(files, provenance)
    partitions = [analyze_parquet_partition(path, batch_size=batch_size) for path in files]
    hard_file_count = sum(bool(item.get("hard_failures")) for item in partitions)
    fingerprints = sorted({str(item["schema_fingerprint"]) for item in partitions if item.get("schema_fingerprint")})
    manifest_warnings: list[str] = []
    if manifest:
        if _safe_manifest_count(manifest, "dropped_messages"):
            manifest_warnings.append("COLLECTOR_DROPPED_MESSAGES_REPORTED")
        if _safe_manifest_count(manifest, "parse_failures"):
            manifest_warnings.append("COLLECTOR_PARSE_FAILURES_REPORTED")
    if len(fingerprints) > 1:
        manifest_warnings.append("PARQUET_SCHEMA_DRIFT_OBSERVED")
    warnings = sum(len(item.get("warnings") or []) for item in partitions) + len(manifest_warnings)
    if not files or hard_file_count or provenance_failures:
        verdict = "REAL_ARTIFACT_REPLAY_FAIL"
    elif warnings:
        verdict = "REAL_ARTIFACT_REPLAY_PASS_WITH_WARNINGS"
    else:
        verdict = "REAL_ARTIFACT_REPLAY_PASS"
    limitations = []
    if not files:
        limitations.append("No parquet artifacts were discovered at the requested input path.")
    limitations.extend([
        "This replay certifies real parquet compatibility and market-data artifact quality only.",
        "Raw tick parquet does not contain candidate lineage, approvals, rejections, executions, or terminal trade outcomes.",
        "Candidate decision analytics remain unverified until real candidate-lineage and trade-log artifacts are replayed.",
        "This replay does not certify profitability, structural edge, strategy thresholds, or unique market causality.",
    ])
    report = {
        "schema_version": 1, "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "input_path": str(source), "verdict": verdict,
        "certification_scope": "REAL_MARKET_DATA_PARQUET_COMPATIBILITY",
        "real_artifact_replay_executed": bool(files), "synthetic_data_used": False,
        "candidate_lifecycle_replay_eligible": False, "file_count": len(files),
        "hard_failure_file_count": hard_file_count, "warning_count": warnings,
        "total_rows": sum(int(item.get("streamed_row_count") or 0) for item in partitions),
        "schema_fingerprint_count": len(fingerprints), "schema_fingerprints": fingerprints,
        "collector_manifest": manifest, "collector_manifest_warnings": manifest_warnings,
        "provenance": provenance, "provenance_failures": provenance_failures,
        "partitions": partitions, "limitations": limitations,
    }
    if output_dir is not None:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "historical_real_artifact_replay.json"
        markdown_path = target / "historical_real_artifact_replay.md"
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
        markdown_path.write_text(render_historical_replay_markdown(report), encoding="utf-8")
        report.update(json_path=str(json_path), markdown_path=str(markdown_path))
    return report


def render_historical_replay_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TradeBot AI Reliability Agent — Historical Real-Artifact Replay", "",
        f"- Verdict: `{report.get('verdict')}`", f"- Scope: `{report.get('certification_scope')}`",
        f"- Files: `{report.get('file_count')}`", f"- Rows: `{report.get('total_rows')}`",
        f"- Synthetic data used: `{report.get('synthetic_data_used')}`",
        f"- Candidate-lifecycle replay eligible: `{report.get('candidate_lifecycle_replay_eligible')}`", "",
        "## Partitions", "",
    ]
    for item in report.get("partitions") or []:
        lines.extend([
            f"### {item.get('file_name')}", f"- Status: `{item.get('status')}`",
            f"- SHA-256: `{item.get('sha256')}`", f"- Rows: `{item.get('streamed_row_count', 0)}`",
            f"- Class: `{item.get('artifact_class', 'UNCLASSIFIED')}`",
            f"- Instruments: `{item.get('instrument_count', 0)}`",
            f"- Timestamp order violations: `{item.get('timestamp_order_violations', 0)}`",
            f"- Crossed market rows: `{item.get('crossed_market_rows', 0)}`",
            f"- Hard failures: `{', '.join(item.get('hard_failures') or []) or 'none'}`",
            f"- Warnings: `{', '.join(item.get('warnings') or []) or 'none'}`", "",
        ])
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {item}" for item in report.get("limitations") or [])
    return "\n".join(lines) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay real TradeBot market-data parquet artifacts")
    parser.add_argument("--input", required=True)
    parser.add_argument("--collector-manifest")
    parser.add_argument("--provenance")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--batch-size", type=int, default=65_536)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = replay_historical_market_data(
        args.input, collector_manifest_path=args.collector_manifest,
        provenance_path=args.provenance, output_dir=args.output_dir, batch_size=args.batch_size,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return int(report["verdict"] == "REAL_ARTIFACT_REPLAY_FAIL")
