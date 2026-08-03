from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .historical_replay import (
    HistoricalReplayError,
    _discover,
    _json_object,
    _parquet_module,
    _provenance_failures,
    _schema_fingerprint,
)

CANDLE_REQUIRED_COLUMNS = ("timestamp", "symbol", "open", "high", "low", "close")
CANDLE_OPTIONAL_COLUMNS = (
    "volume",
    "oi",
    "source",
    "interval",
    "fetch_timestamp",
    "fetch_start_date",
    "fetch_end_date",
    "data_origin",
    "synthetic",
    "mock",
    "fallback",
    "provider",
    "source_endpoint",
)
CANDLE_READ_COLUMNS = CANDLE_REQUIRED_COLUMNS + CANDLE_OPTIONAL_COLUMNS


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _timestamp_epoch(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return normalized.timestamp()
    method = getattr(value, "timestamp", None)
    if callable(method):
        try:
            return _finite(method())
        except (TypeError, ValueError, OverflowError, OSError):
            return None
    number = _finite(value)
    if number is None:
        return None
    if abs(number) > 10_000_000_000_000_000:
        return number / 1_000_000_000.0
    if abs(number) > 10_000_000_000_000:
        return number / 1_000_000.0
    if abs(number) > 10_000_000_000:
        return number / 1_000.0
    return number


def _manifest_failures(manifest: Mapping[str, Any]) -> list[str]:
    if not manifest:
        return ["CANDLE_MANIFEST_REQUIRED"]
    failures: list[str] = []
    expected = {
        "provider": "upstox",
        "fetch_status": "UPSTOX_FETCH_SUCCEEDED_REAL_CANDLES",
        "data_origin": "upstox_api",
        "synthetic": False,
        "mock": False,
        "fallback": False,
        "certification_eligible": True,
        "deprecated_endpoint": False,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            failures.append(f"CANDLE_MANIFEST_INVALID:{field}")
    return failures


def analyze_historical_candle_partition(
    path: str | Path,
    *,
    batch_size: int = 65_536,
) -> dict[str, Any]:
    target = Path(path).resolve()
    result: dict[str, Any] = {
        "path": str(target),
        "file_name": target.name,
        "exists": target.is_file(),
        "parquet_profile": "HISTORICAL_CANDLE",
        "artifact_class": "HISTORICAL_CANDLE_PARTITION",
        "status": "REAL_CANDLE_REPLAY_FAIL",
        "hard_failures": [],
        "warnings": [],
    }
    if batch_size <= 0:
        raise HistoricalReplayError("batch_size_must_be_positive")
    if not target.is_file():
        result["hard_failures"].append("PARQUET_FILE_NOT_FOUND")
        return result

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
    missing = [column for column in CANDLE_REQUIRED_COLUMNS if column not in available]
    result.update(
        metadata_row_count=int(parquet_file.metadata.num_rows),
        row_group_count=int(parquet_file.metadata.num_row_groups),
        created_by=parquet_file.metadata.created_by,
        columns=list(available),
        required_columns=list(CANDLE_REQUIRED_COLUMNS),
        missing_required_columns=missing,
        schema_fingerprint=_schema_fingerprint(schema),
        size_bytes=target.stat().st_size,
    )
    if missing:
        result["hard_failures"].append("CANDLE_REQUIRED_COLUMNS_MISSING")
        return result

    selected = [column for column in CANDLE_READ_COLUMNS if column in available]
    counters = {
        "streamed_row_count": 0,
        "valid_timestamp_rows": 0,
        "invalid_timestamp_rows": 0,
        "timestamp_order_violations": 0,
        "duplicate_symbol_timestamp_rows": 0,
        "symbol_missing_rows": 0,
        "complete_ohlc_rows": 0,
        "missing_ohlc_rows": 0,
        "nonpositive_ohlc_rows": 0,
        "ohlc_invariant_violations": 0,
        "negative_volume_rows": 0,
        "negative_oi_rows": 0,
        "synthetic_true_rows": 0,
        "mock_true_rows": 0,
        "fallback_true_rows": 0,
        "provenance_flag_missing_rows": 0,
        "cadence_gap_rows": 0,
    }
    symbols: set[str] = set()
    intervals: set[str] = set()
    providers: set[str] = set()
    origins: set[str] = set()
    sources: set[str] = set()
    endpoints: set[str] = set()
    seen: set[tuple[str, float]] = set()
    timestamp_min = timestamp_max = previous_timestamp = None

    try:
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=selected):
            columns = {name: batch.column(index).to_pylist() for index, name in enumerate(selected)}
            empty = [None] * int(batch.num_rows)
            counters["streamed_row_count"] += int(batch.num_rows)
            for offset in range(int(batch.num_rows)):
                timestamp = _timestamp_epoch(columns["timestamp"][offset])
                raw_symbol = columns["symbol"][offset]
                symbol = str(raw_symbol).strip() if raw_symbol is not None else ""
                if timestamp is None:
                    counters["invalid_timestamp_rows"] += 1
                else:
                    counters["valid_timestamp_rows"] += 1
                    timestamp_min = timestamp if timestamp_min is None else min(timestamp_min, timestamp)
                    timestamp_max = timestamp if timestamp_max is None else max(timestamp_max, timestamp)
                    if previous_timestamp is not None:
                        if timestamp < previous_timestamp:
                            counters["timestamp_order_violations"] += 1
                        elif timestamp - previous_timestamp > 60.5:
                            counters["cadence_gap_rows"] += 1
                    previous_timestamp = timestamp
                    identity = (symbol, timestamp)
                    if identity in seen:
                        counters["duplicate_symbol_timestamp_rows"] += 1
                    else:
                        seen.add(identity)

                if not symbol:
                    counters["symbol_missing_rows"] += 1
                else:
                    symbols.add(symbol)

                prices = {name: _finite(columns[name][offset]) for name in ("open", "high", "low", "close")}
                if any(value is None for value in prices.values()):
                    counters["missing_ohlc_rows"] += 1
                else:
                    counters["complete_ohlc_rows"] += 1
                    values = [float(prices[name]) for name in ("open", "high", "low", "close")]
                    counters["nonpositive_ohlc_rows"] += int(any(value <= 0 for value in values))
                    open_price, high_price, low_price, close_price = values
                    invalid_ohlc = (
                        high_price < max(open_price, close_price, low_price)
                        or low_price > min(open_price, close_price, high_price)
                    )
                    counters["ohlc_invariant_violations"] += int(invalid_ohlc)

                volume = _finite(columns.get("volume", empty)[offset])
                oi = _finite(columns.get("oi", empty)[offset])
                counters["negative_volume_rows"] += int(volume is not None and volume < 0)
                counters["negative_oi_rows"] += int(oi is not None and oi < 0)

                flags_present = True
                for field, counter in (
                    ("synthetic", "synthetic_true_rows"),
                    ("mock", "mock_true_rows"),
                    ("fallback", "fallback_true_rows"),
                ):
                    if field not in columns or columns[field][offset] is None:
                        flags_present = False
                    elif columns[field][offset] is not False:
                        counters[counter] += 1
                counters["provenance_flag_missing_rows"] += int(not flags_present)

                for field, values in (
                    ("interval", intervals),
                    ("provider", providers),
                    ("data_origin", origins),
                    ("source", sources),
                    ("source_endpoint", endpoints),
                ):
                    raw = columns.get(field, empty)[offset]
                    text = str(raw).strip() if raw is not None else ""
                    if text:
                        values.add(text)
    except Exception as exc:
        result["hard_failures"].append(f"PARQUET_STREAM_FAILED:{type(exc).__name__}")
        return result

    rows = counters["streamed_row_count"]
    result.update(counters)
    result.update(
        row_count_matches_metadata=rows == int(parquet_file.metadata.num_rows),
        timestamp_min_epoch=timestamp_min,
        timestamp_max_epoch=timestamp_max,
        duration_seconds=(timestamp_max - timestamp_min)
        if timestamp_min is not None and timestamp_max is not None else None,
        symbol_count=len(symbols),
        symbols=sorted(symbols),
        intervals=sorted(intervals),
        providers=sorted(providers),
        data_origins=sorted(origins),
        sources=sorted(sources),
        source_endpoints=sorted(endpoints),
        real_only_row_flags=(
            counters["synthetic_true_rows"] == 0
            and counters["mock_true_rows"] == 0
            and counters["fallback_true_rows"] == 0
            and counters["provenance_flag_missing_rows"] == 0
        ),
    )
    hard_conditions = (
        (rows == 0, "PARQUET_HAS_NO_ROWS"),
        (not result["row_count_matches_metadata"], "PARQUET_ROW_COUNT_MISMATCH"),
        (counters["valid_timestamp_rows"] == 0, "NO_VALID_TIMESTAMPS"),
        (not symbols, "NO_VALID_SYMBOLS"),
        (counters["complete_ohlc_rows"] == 0, "NO_COMPLETE_OHLC_ROWS"),
        (counters["nonpositive_ohlc_rows"] > 0, "NONPOSITIVE_OHLC_OBSERVED"),
        (counters["ohlc_invariant_violations"] > 0, "OHLC_INVARIANT_VIOLATION"),
        (counters["synthetic_true_rows"] > 0, "SYNTHETIC_ROWS_OBSERVED"),
        (counters["mock_true_rows"] > 0, "MOCK_ROWS_OBSERVED"),
        (counters["fallback_true_rows"] > 0, "FALLBACK_ROWS_OBSERVED"),
    )
    warning_conditions = (
        (counters["invalid_timestamp_rows"], "INVALID_TIMESTAMP_ROWS_OBSERVED"),
        (counters["timestamp_order_violations"], "TIMESTAMP_ORDER_VIOLATIONS_OBSERVED"),
        (counters["duplicate_symbol_timestamp_rows"], "DUPLICATE_SYMBOL_TIMESTAMPS_OBSERVED"),
        (counters["symbol_missing_rows"], "MISSING_SYMBOL_ROWS_OBSERVED"),
        (counters["missing_ohlc_rows"], "MISSING_OHLC_ROWS_OBSERVED"),
        (counters["negative_volume_rows"], "NEGATIVE_VOLUME_ROWS_OBSERVED"),
        (counters["negative_oi_rows"], "NEGATIVE_OI_ROWS_OBSERVED"),
        (counters["provenance_flag_missing_rows"], "ROW_PROVENANCE_FLAGS_MISSING"),
        (counters["cadence_gap_rows"], "ONE_MINUTE_CADENCE_GAPS_OBSERVED"),
        (len(symbols) > 1, "MULTIPLE_SYMBOLS_IN_PARTITION"),
        (len(intervals) > 1, "MULTIPLE_INTERVALS_IN_PARTITION"),
        (len(providers) > 1, "MULTIPLE_PROVIDERS_IN_PARTITION"),
        (len(origins) > 1, "MULTIPLE_DATA_ORIGINS_IN_PARTITION"),
    )
    result["hard_failures"].extend(code for condition, code in hard_conditions if condition)
    result["warnings"].extend(code for condition, code in warning_conditions if condition)
    result["status"] = "REAL_CANDLE_REPLAY_FAIL" if result["hard_failures"] else (
        "REAL_CANDLE_REPLAY_PASS_WITH_WARNINGS" if result["warnings"] else "REAL_CANDLE_REPLAY_PASS"
    )
    return result


def replay_historical_candles(
    input_path: str | Path,
    *,
    fetch_manifest_path: str | Path,
    provenance_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    batch_size: int = 65_536,
) -> dict[str, Any]:
    source = Path(input_path).resolve()
    files = _discover(source)
    manifest = _json_object(fetch_manifest_path)
    provenance = _json_object(provenance_path)
    manifest_failures = _manifest_failures(manifest)
    provenance_failures = _provenance_failures(files, provenance)
    partitions = [analyze_historical_candle_partition(path, batch_size=batch_size) for path in files]
    hard_partition_count = sum(bool(item.get("hard_failures")) for item in partitions)
    warnings = sum(len(item.get("warnings") or []) for item in partitions)
    if not files or manifest_failures or provenance_failures or hard_partition_count:
        verdict = "REAL_HISTORICAL_CANDLE_REPLAY_FAIL"
    elif warnings:
        verdict = "REAL_HISTORICAL_CANDLE_REPLAY_PASS_WITH_WARNINGS"
    else:
        verdict = "REAL_HISTORICAL_CANDLE_REPLAY_PASS"
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "input_path": str(source),
        "verdict": verdict,
        "certification_scope": "REAL_UPSTOX_HISTORICAL_CANDLE_COMPATIBILITY",
        "real_artifact_replay_executed": bool(files),
        "synthetic_data_used": False,
        "candidate_lifecycle_replay_eligible": False,
        "file_count": len(files),
        "total_rows": sum(int(item.get("streamed_row_count") or 0) for item in partitions),
        "hard_failure_partition_count": hard_partition_count,
        "warning_count": warnings,
        "manifest": manifest,
        "manifest_failures": manifest_failures,
        "provenance": provenance,
        "provenance_failures": provenance_failures,
        "partitions": partitions,
        "limitations": [
            "These files contain real historical underlying candles, not recorded TradeBot candidate decisions.",
            "Strategy generation, rejection, approval, ranking, execution, and terminal outcome replay remain pending.",
            "This replay does not certify profitability, structural edge, strategy thresholds, or unique causality.",
        ],
    }
    if output_dir is not None:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "historical_candle_real_artifact_replay.json"
        md_path = target / "historical_candle_real_artifact_replay.md"
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
        md_path.write_text(render_historical_candle_replay_markdown(report), encoding="utf-8")
        report.update(json_path=str(json_path), markdown_path=str(md_path))
    return report


def render_historical_candle_replay_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# TradeBot AI Reliability Agent — Real Historical Candle Replay",
        "",
        f"- Verdict: `{report.get('verdict')}`",
        f"- Scope: `{report.get('certification_scope')}`",
        f"- Files: `{report.get('file_count')}`",
        f"- Rows: `{report.get('total_rows')}`",
        f"- Candidate-lifecycle replay eligible: `{report.get('candidate_lifecycle_replay_eligible')}`",
        "",
        "## Partitions",
        "",
    ]
    for item in report.get("partitions") or []:
        lines.extend([
            f"### {item.get('file_name')}",
            f"- Status: `{item.get('status')}`",
            f"- Rows: `{item.get('streamed_row_count', 0)}`",
            f"- Symbols: `{', '.join(item.get('symbols') or [])}`",
            f"- OHLC violations: `{item.get('ohlc_invariant_violations', 0)}`",
            f"- Provenance flags real-only: `{item.get('real_only_row_flags')}`",
            f"- Hard failures: `{', '.join(item.get('hard_failures') or []) or 'none'}`",
            f"- Warnings: `{', '.join(item.get('warnings') or []) or 'none'}`",
            "",
        ])
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {item}" for item in report.get("limitations") or [])
    return "\n".join(lines) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay real Upstox historical candle parquet artifacts")
    parser.add_argument("--input", required=True)
    parser.add_argument("--fetch-manifest", required=True)
    parser.add_argument("--provenance")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--batch-size", type=int, default=65_536)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = replay_historical_candles(
        args.input,
        fetch_manifest_path=args.fetch_manifest,
        provenance_path=args.provenance,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return int(report["verdict"] == "REAL_HISTORICAL_CANDLE_REPLAY_FAIL")
