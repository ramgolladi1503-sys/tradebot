from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
import sqlite3
from typing import Any

from .models import CoverageWindow, DataFormat, HistoricalDataSourceRecord, HistoricalSourceType

_CSV_TS_CANDIDATES = ("timestamp", "datetime", "ts", "date")
_CSV_SYMBOL_CANDIDATES = ("symbol", "underlying", "index_symbol", "tradingsymbol")
_CSV_EXPIRY_CANDIDATES = ("expiry", "expiry_date")
_CSV_STRIKE_CANDIDATES = ("strike", "strike_price")
_CSV_INTERVAL_CANDIDATES = ("interval", "timeframe", "granularity")

_UNDERLYING_REQUIRED = frozenset({"timestamp", "symbol", "open", "high", "low", "close", "volume"})
_FUTURES_REQUIRED = frozenset({"timestamp", "symbol", "expiry", "open", "high", "low", "close", "volume", "oi"})
_OPTION_INTRADAY_REQUIRED = frozenset(
    {"timestamp", "underlying", "expiry", "strike", "option_type", "open", "high", "low", "close"}
)
_OPTION_EOD_REQUIRED = frozenset(
    {"date", "underlying", "expiry", "strike", "option_type", "open", "high", "low", "close"}
)
_OPTION_CHAIN_REQUIRED = frozenset({"timestamp", "underlying", "expiry", "strike"})
_OPTION_INTRADAY_WARNING_FIELDS = ("volume", "oi", "bid", "ask")
_OPTION_EOD_WARNING_FIELDS = ("volume", "oi", "settlement")


class HistoricalDataSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class SourceScanSummary:
    columns: tuple[str, ...]
    row_count: int
    symbols: tuple[str, ...]
    expiries: tuple[str, ...]
    strikes: tuple[str, ...]
    intervals: tuple[str, ...]
    coverage: CoverageWindow


def detect_source_format(path: str | Path) -> DataFormat:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return DataFormat.CSV
    if suffix in {".sqlite", ".db"}:
        return DataFormat.SQLITE
    if suffix in {".parquet", ".pq"}:
        return DataFormat.PARQUET
    return DataFormat.UNKNOWN


def load_historical_source(
    path: str | Path,
    *,
    source_type: HistoricalSourceType,
    provenance: str,
    parquet_enabled: bool = True,
) -> HistoricalDataSourceRecord:
    source_path = Path(path).expanduser()
    data_format = detect_source_format(source_path)
    warnings: list[str] = []
    missing_required_fields: tuple[str, ...] = ()
    optional_fields_present: tuple[str, ...] = ()
    metadata: dict[str, Any] = {}

    try:
        if data_format == DataFormat.CSV:
            summary = _scan_csv(source_path)
        elif data_format == DataFormat.SQLITE:
            summary = load_sqlite_runtime_source(source_path)
        elif data_format == DataFormat.PARQUET:
            if not parquet_enabled:
                raise HistoricalDataSchemaError("parquet_disabled_by_config")
            summary = _scan_parquet(source_path)
        else:
            raise HistoricalDataSchemaError(f"unsupported_format:{source_path.suffix.lower()}")
        _validate_schema(columns=summary.columns, source_type=source_type)
        optional_fields_present = tuple(_optional_fields_present(summary.columns, source_type))
        warnings.extend(_warning_messages(summary.columns, source_type))
        schema_valid = True
    except HistoricalDataSchemaError as exc:
        summary = SourceScanSummary(
            columns=(),
            row_count=0,
            symbols=(),
            expiries=(),
            strikes=(),
            intervals=(),
            coverage=CoverageWindow(start_date=None, end_date=None, span_days=0, row_count=0),
        )
        schema_valid = False
        missing_required_fields = _extract_missing_fields(str(exc))
        warnings.append(str(exc))
    except FileNotFoundError:
        raise

    if source_type == HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA:
        metadata["runtime_replay_only"] = True

    return HistoricalDataSourceRecord(
        source_type=source_type,
        path=str(source_path),
        data_format=data_format,
        provenance=provenance,
        schema_valid=schema_valid,
        coverage=summary.coverage,
        symbols=summary.symbols,
        expiries=summary.expiries,
        strikes=summary.strikes,
        intervals=summary.intervals,
        missing_required_fields=missing_required_fields,
        optional_fields_present=optional_fields_present,
        warnings=tuple(warnings),
        eight_year_coverage=summary.coverage.span_days >= 2890,
        metadata=metadata,
    )


def scan_source_path(
    root: str | Path,
    *,
    source_type: HistoricalSourceType,
    provenance: str,
    parquet_enabled: bool = True,
) -> list[HistoricalDataSourceRecord]:
    base = Path(root).expanduser()
    if not base.exists():
        return []
    if base.is_file():
        return [
            load_historical_source(
                base,
                source_type=source_type,
                provenance=provenance,
                parquet_enabled=parquet_enabled,
            )
        ]
    records: list[HistoricalDataSourceRecord] = []
    for path in sorted(base.rglob("*")):
        if path.is_dir():
            continue
        if detect_source_format(path) == DataFormat.UNKNOWN:
            continue
        records.append(
            load_historical_source(
                path,
                source_type=source_type,
                provenance=provenance,
                parquet_enabled=parquet_enabled,
            )
        )
    return records


def validate_underlying_index_schema(columns: list[str] | tuple[str, ...]) -> None:
    _require_columns(columns, _UNDERLYING_REQUIRED)


def validate_option_intraday_schema(columns: list[str] | tuple[str, ...]) -> None:
    _require_columns(columns, _OPTION_INTRADAY_REQUIRED)


def validate_option_eod_schema(columns: list[str] | tuple[str, ...]) -> None:
    _require_columns(columns, _OPTION_EOD_REQUIRED)


def summarize_source_coverage(records: list[HistoricalDataSourceRecord]) -> dict[str, Any]:
    symbols = sorted({symbol for record in records for symbol in record.symbols})
    expiries = sorted({expiry for record in records for expiry in record.expiries})
    strikes = sorted({strike for record in records for strike in record.strikes})
    intervals = sorted({interval for record in records for interval in record.intervals})
    start_dates = [record.coverage.start_date for record in records if record.coverage.start_date]
    end_dates = [record.coverage.end_date for record in records if record.coverage.end_date]
    return {
        "record_count": len(records),
        "symbols": symbols,
        "expiries": expiries,
        "strikes": strikes,
        "intervals": intervals,
        "start_date": min(start_dates) if start_dates else None,
        "end_date": max(end_dates) if end_dates else None,
    }


def load_sqlite_runtime_source(path: str | Path) -> SourceScanSummary:
    db_path = Path(path).expanduser()
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        if not tables:
            raise HistoricalDataSchemaError("sqlite_source_has_no_tables")
        selected = None
        selected_columns: list[str] = []
        for table in tables:
            columns = [row[1] for row in cursor.execute(f"PRAGMA table_info('{table}')")]
            if any(name in columns for name in _CSV_TS_CANDIDATES):
                selected = table
                selected_columns = columns
                break
        if selected is None:
            raise HistoricalDataSchemaError("sqlite_source_missing_timestamp_like_column")
        rows = cursor.execute(f"SELECT * FROM '{selected}'").fetchall()
        row_count = len(rows)
        ts_index = _find_column_index(selected_columns, _CSV_TS_CANDIDATES)
        symbol_index = _find_column_index(selected_columns, _CSV_SYMBOL_CANDIDATES)
        expiry_index = _find_column_index(selected_columns, _CSV_EXPIRY_CANDIDATES)
        strike_index = _find_column_index(selected_columns, _CSV_STRIKE_CANDIDATES)
        interval_index = _find_column_index(selected_columns, _CSV_INTERVAL_CANDIDATES)
        timestamps: list[date] = []
        symbols: set[str] = set()
        expiries: set[str] = set()
        strikes: set[str] = set()
        intervals: set[str] = set()
        for row in rows:
            ts_value = row[ts_index] if ts_index is not None else None
            parsed = _parse_temporal_value(ts_value)
            if parsed is not None:
                timestamps.append(parsed)
            if symbol_index is not None and row[symbol_index] not in (None, ""):
                symbols.add(str(row[symbol_index]).strip().upper())
            if expiry_index is not None and row[expiry_index] not in (None, ""):
                expiries.add(str(row[expiry_index]).strip())
            if strike_index is not None and row[strike_index] not in (None, ""):
                strikes.add(str(row[strike_index]).strip())
            if interval_index is not None and row[interval_index] not in (None, ""):
                intervals.add(str(row[interval_index]).strip())
        coverage = _build_coverage(timestamps=timestamps, row_count=row_count)
        return SourceScanSummary(
            columns=tuple(selected_columns),
            row_count=row_count,
            symbols=tuple(sorted(symbols)),
            expiries=tuple(sorted(expiries)),
            strikes=tuple(sorted(strikes)),
            intervals=tuple(sorted(intervals)),
            coverage=coverage,
        )


def _scan_csv(path: Path) -> SourceScanSummary:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        if not fieldnames:
            raise HistoricalDataSchemaError("csv_source_has_no_header")
        timestamps: list[date] = []
        symbols: set[str] = set()
        expiries: set[str] = set()
        strikes: set[str] = set()
        intervals: set[str] = set()
        row_count = 0
        for row in reader:
            row_count += 1
            parsed = _parse_temporal_value(_first_present(row, _CSV_TS_CANDIDATES))
            if parsed is not None:
                timestamps.append(parsed)
            symbol = _first_present(row, _CSV_SYMBOL_CANDIDATES)
            if symbol:
                symbols.add(str(symbol).strip().upper())
            expiry = _first_present(row, _CSV_EXPIRY_CANDIDATES)
            if expiry:
                expiries.add(str(expiry).strip())
            strike = _first_present(row, _CSV_STRIKE_CANDIDATES)
            if strike:
                strikes.add(str(strike).strip())
            interval = _first_present(row, _CSV_INTERVAL_CANDIDATES)
            if interval:
                intervals.add(str(interval).strip())
    return SourceScanSummary(
        columns=fieldnames,
        row_count=row_count,
        symbols=tuple(sorted(symbols)),
        expiries=tuple(sorted(expiries)),
        strikes=tuple(sorted(strikes)),
        intervals=tuple(sorted(intervals)),
        coverage=_build_coverage(timestamps=timestamps, row_count=row_count),
    )


def _scan_parquet(path: Path) -> SourceScanSummary:
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover
        raise HistoricalDataSchemaError("parquet_reader_unavailable") from exc
    frame = pd.read_parquet(path)
    columns = tuple(str(column) for column in frame.columns)
    timestamps = [_parse_temporal_value(value) for value in frame.get("timestamp", [])]
    timestamps = [value for value in timestamps if value is not None]
    symbols = tuple(sorted({str(value).strip().upper() for value in frame.get("symbol", []) if str(value).strip()}))
    expiries = tuple(sorted({str(value).strip() for value in frame.get("expiry", []) if str(value).strip()}))
    strikes = tuple(sorted({str(value).strip() for value in frame.get("strike", []) if str(value).strip()}))
    intervals = tuple(sorted({str(value).strip() for value in frame.get("interval", []) if str(value).strip()}))
    return SourceScanSummary(
        columns=columns,
        row_count=int(len(frame.index)),
        symbols=symbols,
        expiries=expiries,
        strikes=strikes,
        intervals=intervals,
        coverage=_build_coverage(timestamps=timestamps, row_count=int(len(frame.index))),
    )


def _validate_schema(*, columns: tuple[str, ...], source_type: HistoricalSourceType) -> None:
    if source_type == HistoricalSourceType.UNDERLYING_INDEX_CANDLES:
        validate_underlying_index_schema(columns)
        return
    if source_type == HistoricalSourceType.FUTURES_CANDLES:
        _require_columns(columns, _FUTURES_REQUIRED)
        return
    if source_type == HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY:
        validate_option_intraday_schema(columns)
        return
    if source_type == HistoricalSourceType.OPTION_CONTRACT_EOD:
        validate_option_eod_schema(columns)
        return
    if source_type == HistoricalSourceType.OPTION_CHAIN_SNAPSHOT:
        _require_columns(columns, _OPTION_CHAIN_REQUIRED)
        return
    if source_type == HistoricalSourceType.RUNTIME_CAPTURED_LIVE_DATA:
        _require_columns(columns, {"timestamp"})
        return
    raise HistoricalDataSchemaError(f"unknown_source_type:{source_type.value}")


def _optional_fields_present(columns: tuple[str, ...], source_type: HistoricalSourceType) -> list[str]:
    present = set(columns)
    if source_type == HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY:
        return sorted(field for field in _OPTION_INTRADAY_WARNING_FIELDS if field in present)
    if source_type == HistoricalSourceType.OPTION_CONTRACT_EOD:
        return sorted(field for field in (*_OPTION_EOD_WARNING_FIELDS, "last") if field in present)
    return []


def _warning_messages(columns: tuple[str, ...], source_type: HistoricalSourceType) -> list[str]:
    present = set(columns)
    warnings: list[str] = []
    if source_type == HistoricalSourceType.OPTION_CONTRACT_CANDLES_INTRADAY:
        for field in _OPTION_INTRADAY_WARNING_FIELDS:
            if field not in present:
                warnings.append(f"missing_recommended_field:{field}")
    if source_type == HistoricalSourceType.OPTION_CONTRACT_EOD:
        for field in _OPTION_EOD_WARNING_FIELDS:
            if field not in present:
                warnings.append(f"missing_recommended_field:{field}")
    return warnings


def _require_columns(columns: list[str] | tuple[str, ...], required: set[str] | frozenset[str]) -> None:
    missing = sorted(field for field in required if field not in set(columns))
    if missing:
        raise HistoricalDataSchemaError("missing_required_fields:" + ",".join(missing))


def _extract_missing_fields(error: str) -> tuple[str, ...]:
    prefix = "missing_required_fields:"
    if error.startswith(prefix):
        return tuple(part for part in error[len(prefix) :].split(",") if part)
    return ()


def _build_coverage(*, timestamps: list[date], row_count: int) -> CoverageWindow:
    if not timestamps:
        return CoverageWindow(start_date=None, end_date=None, span_days=0, row_count=row_count)
    start_value = min(timestamps)
    end_value = max(timestamps)
    return CoverageWindow(
        start_date=start_value.isoformat(),
        end_date=end_value.isoformat(),
        span_days=max((end_value - start_value).days, 0),
        row_count=row_count,
    )


def _first_present(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _find_column_index(columns: list[str], names: tuple[str, ...]) -> int | None:
    for name in names:
        if name in columns:
            return columns.index(name)
    return None


def _parse_temporal_value(value: Any) -> date | None:
    if value in (None, "", "None"):
        return None
    if isinstance(value, (int, float)) and value > 1_000_000_000:
        try:
            return datetime.fromtimestamp(float(value), tz=UTC).date()
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10 and text.count("-") == 2:
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None
