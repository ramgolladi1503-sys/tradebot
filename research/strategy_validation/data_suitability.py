from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


DATA_SUITABILITY_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_BASENAME = "four_strategy_dataset_manifest_v1.json"
DEFAULT_SUPPORTED_SUFFIXES = {".parquet", ".csv", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}
DEFAULT_EXCLUDED_DIR_NAMES = {"manifests"}
DEFAULT_STRATEGY_IDS = (
    "opening_range_retest_v1",
    "compression_breakout_v1",
    "trend_pullback_v1",
    "vwap_reclaim_rejection_v1",
)


@dataclass(frozen=True)
class FieldCoverage:
    field: str
    status: str
    source_columns: tuple[str, ...]
    evidence: str
    notes: str


@dataclass(frozen=True)
class StrategyCoverage:
    strategy_id: str
    status: str
    required_inputs: tuple[FieldCoverage, ...]
    optional_inputs: tuple[FieldCoverage, ...]
    blocking_required_fields: tuple[str, ...]
    satisfied_required_fields: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class SessionIntegrity:
    status: str
    cadence_minutes: int | None
    expected_rows: int | None
    observed_rows: int
    duplicate_timestamp_rows: int
    missing_timestamp_rows: int
    out_of_order_rows: int
    missing_bar_count: int | None
    session_start: str | None
    session_end: str | None
    session_date: str | None


@dataclass(frozen=True)
class DatasetInspection:
    absolute_path: str
    relative_path: str
    source_root: str
    file_format: str
    file_size_bytes: int
    sha256: str
    row_count: int
    schema_columns: tuple[dict[str, str], ...]
    timestamp_field: str | None
    timestamp_timezone: str | None
    timestamp_min: str | None
    timestamp_max: str | None
    symbol_values: tuple[str, ...]
    instrument_tokens: tuple[str, ...]
    bar_interval: str | None
    duplicate_rows_exact: int
    duplicate_rows_natural_key: int
    null_counts: dict[str, int]
    volume_sum: float | None
    volume_nonzero_rows: int | None
    volume_truth_status: str
    data_kind: str
    provenance: str
    session_integrity: SessionIntegrity
    field_coverage: tuple[FieldCoverage, ...]
    strategy_coverage: tuple[StrategyCoverage, ...]
    inspection_error: str
    suitability_status: str
    exclusion_reason: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_source_roots() -> tuple[Path, ...]:
    root = project_root()
    return (
        root / "runtime" / "upstox_candidate_replay",
        root / ".runtime" / "market_data",
    )


def load_frozen_contract_bundle(bundle_path: Path | None = None) -> dict[str, Any]:
    bundle_path = bundle_path or (project_root() / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v1.json")
    sidecar_path = bundle_path.with_suffix(bundle_path.suffix + ".sha256")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    if sidecar_path.exists():
        expected = sidecar_path.read_text(encoding="utf-8").split()[0]
        actual = sha256_file(bundle_path)
        if expected != actual:
            raise ValueError(
                f"bundle_sha256_mismatch:{bundle_path.name}:expected={expected}:actual={actual}"
            )
    return payload


def discover_candidate_datasets(
    roots: Iterable[Path] | None = None,
    *,
    supported_suffixes: set[str] | None = None,
) -> list[Path]:
    suffixes = supported_suffixes or DEFAULT_SUPPORTED_SUFFIXES
    discovered: list[Path] = []
    seen: set[Path] = set()
    for root in roots or default_source_roots():
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = sorted(
                p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes and not _excluded_path(p)
            )
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            discovered.append(path)
    return sorted(discovered, key=lambda p: str(p))


def build_four_strategy_dataset_manifest(
    *,
    roots: Iterable[Path] | None = None,
    bundle_path: Path | None = None,
    code_commit: str | None = None,
) -> dict[str, Any]:
    bundle = load_frozen_contract_bundle(bundle_path)
    dataset_paths = discover_candidate_datasets(roots)
    inspections: list[DatasetInspection] = []
    for path in dataset_paths:
        try:
            inspections.append(inspect_dataset(path, bundle=bundle))
        except Exception as exc:
            inspections.append(_error_inspection(path, reason=repr(exc), bundle=bundle))
    strategy_summary = _build_strategy_summary(inspections, bundle)
    corpus_status = _corpus_status(strategy_summary)
    manifest = {
        "schema_version": DATA_SUITABILITY_SCHEMA_VERSION,
        "code_commit": code_commit or _current_git_commit(),
        "architecture_decision": bundle.get("architecture_decision"),
        "bundle_path": str((bundle_path or _default_bundle_path()).resolve()),
        "bundle_sha256": sha256_file(bundle_path or _default_bundle_path()),
        "selected_roots": [str(Path(root).resolve()) for root in (roots or default_source_roots())],
        "discovery_filters": {
            "supported_suffixes": sorted(DEFAULT_SUPPORTED_SUFFIXES),
            "excluded_dir_names": sorted(DEFAULT_EXCLUDED_DIR_NAMES),
        },
        "dataset_count": len(inspections),
        "dataset_records": [asdict(item) for item in inspections],
        "strategy_summary": strategy_summary,
        "corpus_status": corpus_status,
        "corpus_blockers": _corpus_blockers(strategy_summary),
        "provenance_policy": {
            "file_hash": "sha256(bytes)",
            "serialization": "canonical_json_sorted_keys",
            "data_slicing": "read_only_inspection_only",
            "resampling": "not_applied",
            "timezone_normalization": "preserve_source_encoding",
        },
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_feed_used": False,
    }
    return manifest


def inspect_dataset(path: Path, *, bundle: dict[str, Any] | None = None) -> DatasetInspection:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    bundle = bundle or load_frozen_contract_bundle()
    file_format = path.suffix.lower().lstrip(".") or "unknown"
    file_size = path.stat().st_size
    file_hash = sha256_file(path)
    df = _read_dataset(path)
    row_count = int(len(df))
    schema_columns = tuple({"name": str(col), "dtype": str(dtype)} for col, dtype in df.dtypes.items())
    timestamp_field = _detect_timestamp_field(df)
    timestamp_timezone = _timestamp_timezone(df, timestamp_field)
    timestamp_min, timestamp_max = _timestamp_range(df, timestamp_field)
    symbol_values = _collect_unique_values(df, ("symbol", "instrument", "underlying", "tradingsymbol"))
    instrument_tokens = _collect_unique_values(df, ("instrument_token", "token", "instrument_id"))
    bar_interval = _detect_interval(df)
    duplicate_rows_exact = int(df.duplicated().sum())
    duplicate_rows_natural_key = int(df.duplicated(subset=_natural_key_columns(df), keep=False).sum()) if _natural_key_columns(df) else duplicate_rows_exact
    null_counts = {str(col): int(df[col].isna().sum()) for col in df.columns}
    volume_sum, volume_nonzero_rows, volume_truth_status = _volume_truth(df)
    data_kind = _detect_data_kind(df)
    provenance = _detect_provenance(df)
    session_integrity = _session_integrity(df, timestamp_field, bar_interval)
    field_coverage = _field_coverage_for_dataset(df, timestamp_field, bar_interval, volume_truth_status)
    strategy_coverage = tuple(
        _strategy_coverage(strategy, df, timestamp_field, bar_interval, volume_truth_status, field_coverage)
        for strategy in _strategy_requirements(bundle)
    )
    suitability_status = "SUITABLE" if all(item.status == "SUITABLE" for item in strategy_coverage) else "INVALID_DUE_TO_DATA"
    exclusion_reason = "" if suitability_status == "SUITABLE" else _first_blocking_reason(strategy_coverage)
    return DatasetInspection(
        absolute_path=str(path.resolve()),
        relative_path=_relative_path(path),
        source_root=_source_root_label(path),
        file_format=file_format,
        file_size_bytes=file_size,
        sha256=file_hash,
        row_count=row_count,
        schema_columns=schema_columns,
        timestamp_field=timestamp_field,
        timestamp_timezone=timestamp_timezone,
        timestamp_min=timestamp_min,
        timestamp_max=timestamp_max,
        symbol_values=symbol_values,
        instrument_tokens=instrument_tokens,
        bar_interval=bar_interval,
        duplicate_rows_exact=duplicate_rows_exact,
        duplicate_rows_natural_key=duplicate_rows_natural_key,
        null_counts=null_counts,
        volume_sum=volume_sum,
        volume_nonzero_rows=volume_nonzero_rows,
        volume_truth_status=volume_truth_status,
        data_kind=data_kind,
        provenance=provenance,
        session_integrity=session_integrity,
        field_coverage=field_coverage,
        strategy_coverage=strategy_coverage,
        inspection_error="",
        suitability_status=suitability_status,
        exclusion_reason=exclusion_reason,
    )


def write_manifest_and_sidecar(manifest: dict[str, Any], *, output_path: Path) -> tuple[Path, Path]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n"
    output_path.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    sidecar_path = output_path.with_suffix(output_path.suffix + ".sha256")
    sidecar_path.write_text(f"{sha}  {output_path.name}\n", encoding="utf-8")
    return output_path, sidecar_path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_bundle_path() -> Path:
    return project_root() / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v1.json"


def _current_git_commit() -> str:
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root(),
            capture_output=True,
            check=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _excluded_path(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & DEFAULT_EXCLUDED_DIR_NAMES)


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root()))
    except Exception:
        return str(path.resolve())


def _source_root_label(path: Path) -> str:
    resolved = path.resolve()
    root = project_root()
    for candidate in default_source_roots():
        try:
            resolved.relative_to(candidate.resolve())
            return str(candidate.resolve())
        except Exception:
            continue
    try:
        return str(resolved.relative_to(root))
    except Exception:
        return str(resolved)


def _read_dataset(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    if suffix == ".json":
        try:
            return pd.read_json(path)
        except ValueError:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return pd.DataFrame(payload)
            if isinstance(payload, dict):
                return pd.DataFrame([payload])
            return pd.DataFrame()
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return _read_sqlite(path)
    raise ValueError(f"unsupported_format:{suffix}")


def _read_sqlite(path: Path) -> pd.DataFrame:
    with sqlite3.connect(str(path)) as conn:
        tables = pd.read_sql_query("select name from sqlite_master where type='table' order by name", conn)
        frames: list[pd.DataFrame] = []
        for table in tables["name"].tolist():
            safe_name = str(table).replace('"', '""')
            try:
                frame = pd.read_sql_query(f'select * from "{safe_name}"', conn)
            except Exception:
                continue
            frame["_sqlite_table"] = table
            frames.append(frame)
        return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _detect_timestamp_field(df: pd.DataFrame) -> str | None:
    for field in ("timestamp", "date", "ts", "datetime", "time"):
        if field in df.columns:
            return field
    return None


def _timestamp_timezone(df: pd.DataFrame, field: str | None) -> str | None:
    if field is None or field not in df.columns or df.empty:
        return None
    series = df[field]
    if isinstance(series.dtype, pd.DatetimeTZDtype):
        return str(series.dt.tz)
    if pd.api.types.is_datetime64_any_dtype(series):
        return "naive"
    if pd.api.types.is_numeric_dtype(series):
        return "epoch_seconds_utc_assumed"
    return "unparsed"


def _timestamp_range(df: pd.DataFrame, field: str | None) -> tuple[str | None, str | None]:
    if field is None or field not in df.columns or df.empty:
        return None, None
    series = _normalize_timestamp_series(df[field])
    if series.empty:
        return None, None
    return series.min().isoformat(), series.max().isoformat()


def _normalize_timestamp_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        parsed = pd.to_datetime(series, unit="s", errors="coerce")
    else:
        parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        return parsed
    return parsed.dt.tz_convert("Asia/Kolkata")


def _collect_unique_values(df: pd.DataFrame, columns: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for column in columns:
        if column not in df.columns:
            continue
        values.extend(str(item) for item in df[column].dropna().astype(str).unique().tolist()[:50])
    return tuple(sorted(dict.fromkeys(values)))


def _detect_interval(df: pd.DataFrame) -> str | None:
    for field in ("interval", "timeframe", "granularity"):
        if field in df.columns:
            values = [str(v) for v in df[field].dropna().astype(str).unique().tolist()]
            if values:
                return values[0]
    return None


def _natural_key_columns(df: pd.DataFrame) -> list[str]:
    preferred = ["timestamp", "date", "ts", "symbol", "instrument", "underlying", "interval"]
    return [column for column in preferred if column in df.columns]


def _volume_truth(df: pd.DataFrame) -> tuple[float | None, int | None, str]:
    for field in ("volume", "vol"):
        if field not in df.columns:
            continue
        volume = pd.to_numeric(df[field], errors="coerce")
        nonzero_rows = int((volume.fillna(0) != 0).sum())
        total = float(volume.fillna(0).sum())
        if volume.isna().all():
            return None, None, "NO_VOLUME_TRUTH"
        if nonzero_rows == 0:
            return total, nonzero_rows, "ZERO_VOLUME"
        if volume.isna().any():
            return total, nonzero_rows, "PARTIAL_VOLUME"
        return total, nonzero_rows, "HAS_VOLUME"
    return None, None, "NO_VOLUME_COLUMN"


def _detect_data_kind(df: pd.DataFrame) -> str:
    columns = {str(col).lower() for col in df.columns}
    has_ohlc = {"open", "high", "low", "close"}.issubset(columns)
    has_ltp = "ltp" in columns or "last_price" in columns or "last_traded_price" in columns
    has_quote = {"bid", "ask"}.intersection(columns)
    has_depth = "depth" in columns or "market_depth" in columns
    if has_ohlc:
        return "CANDLE_OHLCV" if "volume" in columns or "vol" in columns else "CANDLE_OHLC"
    if has_ltp and (has_quote or has_depth or "vol" in columns or "volume" in columns):
        if has_depth:
            return "TICK_WITH_DEPTH"
        if has_quote:
            return "TICK_QUOTE"
        return "TICK_STREAM"
    if has_ltp:
        return "LTP_ONLY"
    return "UNKNOWN"


def _detect_provenance(df: pd.DataFrame) -> str:
    for field in ("data_origin", "provider", "source", "fetch_source"):
        if field in df.columns:
            values = [str(v) for v in df[field].dropna().astype(str).unique().tolist()]
            if values:
                return "|".join(sorted(dict.fromkeys(values))[:5])
    return "UNKNOWN"


def _session_integrity(df: pd.DataFrame, timestamp_field: str | None, interval: str | None) -> SessionIntegrity:
    if timestamp_field is None or timestamp_field not in df.columns or df.empty:
        return SessionIntegrity(
            status="NOT_APPLICABLE",
            cadence_minutes=None,
            expected_rows=None,
            observed_rows=int(len(df)),
            duplicate_timestamp_rows=0,
            missing_timestamp_rows=0,
            out_of_order_rows=0,
            missing_bar_count=None,
            session_start=None,
            session_end=None,
            session_date=None,
        )
    ts = _normalize_timestamp_series(df[timestamp_field]).dropna()
    if ts.empty:
        return SessionIntegrity(
            status="INVALID",
            cadence_minutes=None,
            expected_rows=None,
            observed_rows=int(len(df)),
            duplicate_timestamp_rows=0,
            missing_timestamp_rows=int(df[timestamp_field].isna().sum()),
            out_of_order_rows=0,
            missing_bar_count=None,
            session_start=None,
            session_end=None,
            session_date=None,
        )
    duplicate_timestamp_rows = int(ts.duplicated().sum())
    out_of_order_rows = int((ts.diff().dropna() < pd.Timedelta(0)).sum())
    cadence_minutes = 1 if (interval or "").lower() in {"1minute", "1m", "minute", "1min"} else None
    missing_bar_count = None
    expected_rows = None
    status = "NOT_APPLICABLE"
    if cadence_minutes == 1:
        expected_index = pd.date_range(ts.min(), ts.max(), freq="1min")
        missing_bar_count = int(len(expected_index.difference(pd.DatetimeIndex(ts))))
        expected_rows = int(len(expected_index))
        status = "COMPLETE" if duplicate_timestamp_rows == 0 and missing_bar_count == 0 and out_of_order_rows == 0 else "INCOMPLETE"
    elif pd.api.types.is_datetime64_any_dtype(ts) or isinstance(ts.dtype, pd.DatetimeTZDtype):
        status = "ORDERED" if duplicate_timestamp_rows == 0 and out_of_order_rows == 0 else "INCOMPLETE"
    session_date = None
    try:
        session_date = str(ts.iloc[0].date())
    except Exception:
        session_date = None
    return SessionIntegrity(
        status=status,
        cadence_minutes=cadence_minutes,
        expected_rows=expected_rows,
        observed_rows=int(len(df)),
        duplicate_timestamp_rows=duplicate_timestamp_rows,
        missing_timestamp_rows=int(df[timestamp_field].isna().sum()),
        out_of_order_rows=out_of_order_rows,
        missing_bar_count=missing_bar_count,
        session_start=ts.min().isoformat(),
        session_end=ts.max().isoformat(),
        session_date=session_date,
    )


def _field_coverage_for_dataset(
    df: pd.DataFrame,
    timestamp_field: str | None,
    bar_interval: str | None,
    volume_truth_status: str,
) -> tuple[FieldCoverage, ...]:
    cols = {str(col).lower(): str(col) for col in df.columns}
    has_ohlc = all(name in cols for name in ("open", "high", "low", "close"))
    candle_complete = has_ohlc and _session_integrity(df, timestamp_field, bar_interval).status == "COMPLETE"
    coverage: list[FieldCoverage] = []
    coverage.append(
        FieldCoverage(
            field="completed_bar_history",
            status="DIRECT" if candle_complete else "UNAVAILABLE",
            source_columns=tuple(c for c in (timestamp_field, "open", "high", "low", "close", "volume") if c and c in df.columns),
            evidence="completed 1m bar history" if candle_complete else "no completed 1m bar history",
            notes="1m completed bar history present" if candle_complete else "candles absent or incomplete",
        )
    )
    coverage.append(
        FieldCoverage(
            field="spot_ltp",
            status="DIRECT" if "ltp" in cols else ("DERIVABLE" if has_ohlc else "UNAVAILABLE"),
            source_columns=tuple(c for c in ("ltp", "close") if c in df.columns),
            evidence="ltp present" if "ltp" in cols else ("close present" if has_ohlc else "missing"),
            notes="ticks provide spot ltp directly; candles provide latest close only as derivation",
        )
    )
    vwap_status = "DIRECT" if "vwap" in cols else "DERIVABLE" if volume_truth_status == "HAS_VOLUME" and "ltp" in cols else "UNAVAILABLE"
    coverage.append(
        FieldCoverage(
            field="vwap",
            status=vwap_status,
            source_columns=tuple(c for c in ("vwap", "ltp", "volume", "vol") if c in df.columns),
            evidence="explicit vwap column" if "vwap" in cols else ("tick volume truth exists" if vwap_status == "DERIVABLE" else "no exact vwap truth"),
            notes="candles without an explicit vwap column are treated as insufficient for exact VWAP truth",
        )
    )
    coverage.append(
        FieldCoverage(
            field="range_width_pct",
            status="DERIVABLE" if candle_complete and has_ohlc else "UNAVAILABLE",
            source_columns=tuple(c for c in ("open", "high", "low", "close", "timestamp") if c in df.columns),
            evidence="session OHLC present" if candle_complete and has_ohlc else "not enough candle history",
            notes="requires completed candle history",
        )
    )
    for field_name, min_bars in (("atr_short", 5), ("atr_long", 30)):
        coverage.append(
            FieldCoverage(
                field=field_name,
                status="DERIVABLE" if candle_complete and has_ohlc and len(df) >= min_bars else "UNAVAILABLE",
                source_columns=tuple(c for c in ("high", "low", "close", "timestamp") if c in df.columns),
                evidence=f"{min_bars}+ completed bars" if candle_complete and has_ohlc and len(df) >= min_bars else "insufficient completed bars",
                notes="requires ordered completed bars with exact bar history",
            )
        )
    coverage.extend(
        [
            FieldCoverage(
                field="nearest_support",
                status="DERIVABLE" if candle_complete and has_ohlc else "UNAVAILABLE",
                source_columns=tuple(c for c in ("low", "open", "close", "timestamp") if c in df.columns),
                evidence="session low/support anchor available" if candle_complete and has_ohlc else "not available",
                notes="support anchor may be derived from completed candles when the strategy permits it",
            ),
            FieldCoverage(
                field="nearest_resistance",
                status="DERIVABLE" if candle_complete and has_ohlc else "UNAVAILABLE",
                source_columns=tuple(c for c in ("high", "open", "close", "timestamp") if c in df.columns),
                evidence="session high/resistance anchor available" if candle_complete and has_ohlc else "not available",
                notes="resistance anchor may be derived from completed candles when the strategy permits it",
            ),
            FieldCoverage(
                field="previous_completed_close",
                status="DERIVABLE" if candle_complete and has_ohlc else "UNAVAILABLE",
                source_columns=tuple(c for c in ("close", "timestamp") if c in df.columns),
                evidence="ordered prior close exists" if candle_complete and has_ohlc else "not available",
                notes="requires a causal completed-bar prefix",
            ),
            FieldCoverage(
                field="vwap_slope",
                status="DERIVABLE" if vwap_status in {"DIRECT", "DERIVABLE"} and candle_complete and has_ohlc else "UNAVAILABLE",
                source_columns=tuple(c for c in ("vwap", "ltp", "close", "timestamp") if c in df.columns),
                evidence="vwap series available" if vwap_status in {"DIRECT", "DERIVABLE"} and candle_complete and has_ohlc else "not available",
                notes="requires an exact VWAP series, not a close-price proxy",
            ),
            FieldCoverage(
                field="volume_z",
                status="DERIVABLE" if volume_truth_status == "HAS_VOLUME" else "UNAVAILABLE",
                source_columns=tuple(c for c in ("volume", "vol", "timestamp") if c in df.columns),
                evidence="nonzero volume truth" if volume_truth_status == "HAS_VOLUME" else volume_truth_status,
                notes="zero-volume candles are not sufficient for a truthful volume z-score",
            ),
        ]
    )
    return tuple(coverage)


def _strategy_requirements(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    strategies = []
    for entry in bundle.get("strategies", []):
        strategies.append(entry)
    return strategies


def _strategy_coverage(
    strategy: dict[str, Any],
    df: pd.DataFrame,
    timestamp_field: str | None,
    bar_interval: str | None,
    volume_truth_status: str,
    field_coverage: tuple[FieldCoverage, ...],
) -> StrategyCoverage:
    required_fields = [item for item in strategy.get("required_inputs", []) if item.get("required")]
    optional_fields = [item for item in strategy.get("required_inputs", []) if not item.get("required")]
    coverage_map = {item.field: item for item in field_coverage}
    required_cov = tuple(
        _coverage_for_required_input(item, df, coverage_map, timestamp_field, bar_interval, volume_truth_status)
        for item in required_fields
    )
    optional_cov = tuple(
        _coverage_for_optional_input(item, df, coverage_map, timestamp_field, bar_interval, volume_truth_status)
        for item in optional_fields
    )
    blocking = tuple(sorted(c.field for c in required_cov if c.status == "UNAVAILABLE"))
    satisfied = tuple(sorted(c.field for c in required_cov if c.status in {"DIRECT", "DERIVABLE"}))
    if blocking:
        status = "INVALID_DUE_TO_DATA"
    elif any(c.status == "UNAVAILABLE" for c in optional_cov):
        status = "SUITABLE_WITH_GAPS"
    else:
        status = "SUITABLE"
    notes = _strategy_notes(strategy, required_cov, optional_cov)
    return StrategyCoverage(
        strategy_id=str(strategy.get("runtime_strategy_id") or strategy.get("canonical_strategy_id") or "UNKNOWN"),
        status=status,
        required_inputs=required_cov,
        optional_inputs=optional_cov,
        blocking_required_fields=blocking,
        satisfied_required_fields=satisfied,
        notes=notes,
    )


def _coverage_for_required_input(
    requirement: dict[str, Any],
    df: pd.DataFrame,
    coverage_map: dict[str, FieldCoverage],
    timestamp_field: str | None,
    bar_interval: str | None,
    volume_truth_status: str,
) -> FieldCoverage:
    field = str(requirement.get("field"))
    if field in coverage_map:
        return coverage_map[field]
    columns = tuple(c for c in (timestamp_field, "open", "high", "low", "close", "volume", "vol", "ltp") if c and c in df.columns)
    data_kind = _detect_data_kind(df)
    status = "UNAVAILABLE"
    evidence = "missing"
    notes = str(requirement.get("missing_data_behavior") or "")
    if field == "completed_bar_history" and data_kind.startswith("CANDLE") and _session_integrity(df, timestamp_field, bar_interval).status == "COMPLETE":
        status = "DIRECT"
        evidence = "completed candle history available"
    elif field == "spot_ltp":
        if "ltp" in df.columns:
            status = "DIRECT"
            evidence = "ltp column present"
        elif {"open", "high", "low", "close"}.issubset({str(c).lower() for c in df.columns}):
            status = "DERIVABLE"
            evidence = "latest close available"
    elif field == "vwap":
        if "vwap" in df.columns:
            status = "DIRECT"
            evidence = "vwap column present"
        elif "ltp" in df.columns and volume_truth_status == "HAS_VOLUME" and not data_kind.startswith("CANDLE"):
            status = "DERIVABLE"
            evidence = "tick volume truth present"
        else:
            status = "UNAVAILABLE"
            evidence = "no exact VWAP truth"
    elif field == "range_width_pct" and data_kind.startswith("CANDLE") and _session_integrity(df, timestamp_field, bar_interval).status == "COMPLETE":
        status = "DERIVABLE"
        evidence = "completed candles provide session range"
    elif field in {"atr_short", "atr_long"} and data_kind.startswith("CANDLE") and _session_integrity(df, timestamp_field, bar_interval).status == "COMPLETE":
        min_bars = 5 if field == "atr_short" else 30
        if len(df) >= min_bars:
            status = "DERIVABLE"
            evidence = f"completed candles >= {min_bars}"
    elif field in {"nearest_support", "nearest_resistance", "previous_completed_close"} and data_kind.startswith("CANDLE") and _session_integrity(df, timestamp_field, bar_interval).status == "COMPLETE":
        status = "DERIVABLE"
        evidence = "completed candle history provides ordered session context"
    elif field == "vwap_slope" and "vwap" in df.columns:
        status = "DERIVABLE"
        evidence = "explicit vwap series present"
    elif field == "volume_z" and volume_truth_status == "HAS_VOLUME":
        status = "DERIVABLE"
        evidence = "nonzero volume truth available"
    return FieldCoverage(
        field=field,
        status=status,
        source_columns=columns,
        evidence=evidence,
        notes=notes,
    )


def _coverage_for_optional_input(
    requirement: dict[str, Any],
    df: pd.DataFrame,
    coverage_map: dict[str, FieldCoverage],
    timestamp_field: str | None,
    bar_interval: str | None,
    volume_truth_status: str,
) -> FieldCoverage:
    field = str(requirement.get("field"))
    if field in coverage_map:
        return coverage_map[field]
    return _coverage_for_required_input(requirement, df, coverage_map, timestamp_field, bar_interval, volume_truth_status)


def _strategy_notes(strategy: dict[str, Any], required_cov: tuple[FieldCoverage, ...], optional_cov: tuple[FieldCoverage, ...]) -> str:
    blocking = [item.field for item in required_cov if item.status == "UNAVAILABLE"]
    if blocking:
        return f"missing_required_inputs:{','.join(blocking)}"
    missing_optional = [item.field for item in optional_cov if item.status == "UNAVAILABLE"]
    if missing_optional:
        return f"optional_inputs_unavailable:{','.join(missing_optional)}"
    return "all_required_inputs_present"


def _build_strategy_summary(
    inspections: list[DatasetInspection],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    strategies = _strategy_requirements(bundle)
    for strategy in strategies:
        strategy_id = str(strategy.get("runtime_strategy_id") or strategy.get("canonical_strategy_id") or "UNKNOWN")
        relevant = [item for item in inspections if any(c.strategy_id == strategy_id and c.status == "SUITABLE" for c in item.strategy_coverage)]
        partial = [item for item in inspections if any(c.strategy_id == strategy_id and c.status != "SUITABLE" for c in item.strategy_coverage)]
        blocking_fields = sorted({field for item in inspections for cov in item.strategy_coverage if cov.strategy_id == strategy_id for field in cov.blocking_required_fields})
        summary[strategy_id] = {
            "status": "SUITABLE" if relevant else "INVALID_DUE_TO_DATA",
            "suitable_dataset_count": len(relevant),
            "partial_dataset_count": len(partial),
            "suitable_dataset_paths": [item.absolute_path for item in relevant],
            "blocking_required_fields": blocking_fields,
            "notes": _strategy_summary_notes(strategy_id, inspections, blocking_fields),
        }
    return summary


def _strategy_summary_notes(strategy_id: str, inspections: list[DatasetInspection], blocking_fields: list[str]) -> str:
    if not inspections:
        return "no datasets discovered"
    if strategy_id == "opening_range_retest_v1":
        return "1m candle files provide completed history, but they carry zero volume and do not provide exact VWAP truth"
    if strategy_id == "trend_pullback_v1":
        return "1m candle files provide completed history, but they carry zero volume and do not provide exact VWAP truth"
    if strategy_id == "compression_breakout_v1":
        return "1m candle files provide range/ATR history, but they carry zero volume and do not provide exact VWAP truth"
    if strategy_id == "vwap_reclaim_rejection_v1":
        return "tick files provide real volume on some sessions, but they do not provide completed bar history in the required 1m candle contract"
    if blocking_fields:
        return f"blocking_required_fields:{','.join(blocking_fields)}"
    return "unknown"


def _corpus_status(strategy_summary: dict[str, Any]) -> str:
    return "SUITABLE" if strategy_summary and all(item.get("status") == "SUITABLE" for item in strategy_summary.values()) else "INVALID_DUE_TO_DATA"


def _corpus_blockers(strategy_summary: dict[str, Any]) -> list[str]:
    blockers = sorted({field for item in strategy_summary.values() for field in item.get("blocking_required_fields", [])})
    if not blockers:
        return ["INSUFFICIENT_DATA"]
    return blockers


def _first_blocking_reason(strategy_coverage: tuple[StrategyCoverage, ...]) -> str:
    for coverage in strategy_coverage:
        if coverage.blocking_required_fields:
            return f"{coverage.strategy_id}:{','.join(coverage.blocking_required_fields)}"
    return "none"


def _error_inspection(path: Path, *, reason: str, bundle: dict[str, Any] | None = None) -> DatasetInspection:
    return DatasetInspection(
        absolute_path=str(path.resolve()),
        relative_path=_relative_path(path),
        source_root=_source_root_label(path),
        file_format=path.suffix.lower().lstrip(".") or "unknown",
        file_size_bytes=path.stat().st_size if path.exists() else 0,
        sha256=sha256_file(path) if path.exists() and path.is_file() else "",
        row_count=0,
        schema_columns=(),
        timestamp_field=None,
        timestamp_timezone=None,
        timestamp_min=None,
        timestamp_max=None,
        symbol_values=(),
        instrument_tokens=(),
        bar_interval=None,
        duplicate_rows_exact=0,
        duplicate_rows_natural_key=0,
        null_counts={},
        volume_sum=None,
        volume_nonzero_rows=None,
        volume_truth_status="INVALID_OR_UNVERIFIABLE",
        data_kind="INVALID_OR_UNVERIFIABLE",
        provenance="UNKNOWN",
        session_integrity=SessionIntegrity(
            status="INVALID",
            cadence_minutes=None,
            expected_rows=None,
            observed_rows=0,
            duplicate_timestamp_rows=0,
            missing_timestamp_rows=0,
            out_of_order_rows=0,
            missing_bar_count=None,
            session_start=None,
            session_end=None,
            session_date=None,
        ),
        field_coverage=(),
        strategy_coverage=tuple(
            StrategyCoverage(
                strategy_id=str(strategy.get("runtime_strategy_id") or strategy.get("canonical_strategy_id") or "UNKNOWN"),
                status="INVALID_DUE_TO_DATA",
                required_inputs=(),
                optional_inputs=(),
                blocking_required_fields=(),
                satisfied_required_fields=(),
                notes=f"read_error:{reason}",
            )
            for strategy in _strategy_requirements(bundle or load_frozen_contract_bundle())
        ),
        inspection_error=reason,
        suitability_status="INVALID_OR_UNVERIFIABLE",
        exclusion_reason=f"read_error:{reason}",
    )
