from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

_SECRET_RE = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9\-\._~\+/=]{20,}|[A-Za-z0-9]{20,}\.[A-Za-z0-9\-\._~\+/=]{10,}|[A-Za-z0-9_\-]{32,})"
)

_PROVENANCE_COLUMNS = ("data_origin", "provider", "source_endpoint", "source")


@dataclass(frozen=True)
class NiftyFuturesIngestionReport:
    artifact_path: str
    artifact_type: str
    sha256: str
    validation_status: str
    blockers: tuple[str, ...]
    row_count: int
    timestamp_min: str | None
    timestamp_max: str | None
    duplicate_timestamps: int
    vwap_formula: str
    vwap: float | None
    provenance_fields: tuple[str, ...]
    instrument_key_redacted: str | None
    source: str
    public_safe: bool
    metadata_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_candle_frame(path: Path) -> tuple[pd.DataFrame, str]:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path), "parquet"
    if suffix == ".csv":
        return pd.read_csv(path), "csv"
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True), "jsonl"
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame(payload), "json"
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    return pd.DataFrame(value), "json"
            return pd.DataFrame([payload]), "json"
        raise ValueError("unsupported_json_payload")
    raise ValueError(f"unsupported_artifact_type:{suffix}")


def validate_candle_artifact(path: str | Path, output_path: str | Path | None = None) -> NiftyFuturesIngestionReport:
    artifact_path = Path(path).expanduser()
    if not artifact_path.exists():
        raise FileNotFoundError(str(artifact_path))

    frame, artifact_type = load_candle_frame(artifact_path)
    sha256 = sha256_file(artifact_path)
    blockers: list[str] = []
    provenance_fields = tuple(col for col in _PROVENANCE_COLUMNS if col in frame.columns)
    if not provenance_fields:
        blockers.append("MISSING_PROVENANCE")

    ts_col = _first_present_column(frame.columns, ("timestamp", "ts", "datetime", "date", "time"))
    if ts_col is None:
        blockers.append("MISSING_TIMESTAMP")
        parsed_ts = pd.Series(dtype="datetime64[ns, UTC]")
    else:
        parsed_ts = pd.to_datetime(frame[ts_col], errors="coerce", utc=True)
        if parsed_ts.isna().any():
            blockers.append("INVALID_TIMESTAMP")

    row_count = int(len(frame))
    if row_count == 0:
        blockers.append("EMPTY_DATASET")

    if ts_col is not None and not parsed_ts.empty:
        if parsed_ts.duplicated().any():
            blockers.append("DUPLICATE_TIMESTAMP")
        if not parsed_ts.is_monotonic_increasing:
            blockers.append("OUT_OF_ORDER_TIMESTAMP")
        ts_min = parsed_ts.min().isoformat().replace("+00:00", "Z")
        ts_max = parsed_ts.max().isoformat().replace("+00:00", "Z")
    else:
        ts_min = None
        ts_max = None

    ohlc_blockers = _validate_ohlc(frame)
    blockers.extend(ohlc_blockers)
    volume_col = _first_present_column(frame.columns, ("volume", "vol"))
    if volume_col is None:
        blockers.append("MISSING_VOLUME")
        vwap = None
    else:
        volume = pd.to_numeric(frame[volume_col], errors="coerce")
        if volume.isna().any():
            blockers.append("INVALID_VOLUME")
        if volume.fillna(0).sum() <= 0:
            blockers.append("ZERO_VOLUME")
            vwap = None
        else:
            close_col = _first_present_column(frame.columns, ("close", "c"))
            if close_col is None:
                blockers.append("MISSING_CLOSE_FOR_VWAP")
                vwap = None
            else:
                close = pd.to_numeric(frame[close_col], errors="coerce")
                if close.isna().any():
                    blockers.append("INVALID_CLOSE_FOR_VWAP")
                    vwap = None
                else:
                    vwap = float((close * volume.fillna(0)).sum() / volume.fillna(0).sum())

    instrument_key_redacted = _redact(_first_non_empty_value(frame, ("instrument_key", "instrument_token", "tradingsymbol", "symbol", "underlying")))
    validation_status = "PASS" if not blockers else "BLOCKED"
    report = NiftyFuturesIngestionReport(
        artifact_path=str(artifact_path),
        artifact_type=artifact_type,
        sha256=sha256,
        validation_status=validation_status,
        blockers=tuple(dict.fromkeys(blockers)),
        row_count=row_count,
        timestamp_min=ts_min,
        timestamp_max=ts_max,
        duplicate_timestamps=int(parsed_ts.duplicated().sum()) if not parsed_ts.empty else 0,
        vwap_formula="close_volume_weighted: sum(close * volume) / sum(volume)",
        vwap=vwap,
        provenance_fields=provenance_fields,
        instrument_key_redacted=instrument_key_redacted,
        source="local_validation_scaffold",
        public_safe=True,
    )
    if output_path is not None:
        metadata_path = Path(output_path).expanduser()
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = _public_report(report)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        report = NiftyFuturesIngestionReport(**{**report.to_dict(), "metadata_path": str(metadata_path)})
    return report


def _public_report(report: NiftyFuturesIngestionReport) -> dict[str, Any]:
    payload = report.to_dict()
    payload["instrument_key_redacted"] = _redact(payload.get("instrument_key_redacted"))
    payload["source"] = _redact(payload.get("source"))
    payload["artifact_path"] = str(payload.get("artifact_path"))
    payload["metadata_path"] = str(payload.get("metadata_path") or "")
    payload["provenance_fields"] = list(payload.get("provenance_fields") or ())
    payload["blockers"] = list(payload.get("blockers") or ())
    return _sanitize_strings(payload)


def _validate_ohlc(frame: pd.DataFrame) -> list[str]:
    blockers: list[str] = []
    required = ("open", "high", "low", "close")
    missing = [col for col in required if col not in frame.columns]
    if missing:
        return ["MISSING_OHLC"]
    numeric = {col: pd.to_numeric(frame[col], errors="coerce") for col in required}
    if any(series.isna().any() for series in numeric.values()):
        blockers.append("INVALID_OHLC")
        return blockers
    if (numeric["high"] < numeric["low"]).any():
        blockers.append("INVALID_OHLC")
    if (numeric["high"] < numeric["open"]).any() or (numeric["high"] < numeric["close"]).any():
        blockers.append("INVALID_OHLC")
    if (numeric["low"] > numeric["open"]).any() or (numeric["low"] > numeric["close"]).any():
        blockers.append("INVALID_OHLC")
    return blockers


def _first_present_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    lower_map = {str(col).lower().strip(): str(col) for col in columns}
    for name in candidates:
        if name in lower_map:
            return lower_map[name]
    return None


def _first_non_empty_value(frame: pd.DataFrame, candidates: Iterable[str]) -> Any:
    col = _first_present_column(frame.columns, candidates)
    if col is None:
        return None
    series = frame[col].dropna()
    if series.empty:
        return None
    return series.iloc[0]


def _redact(value: Any) -> str | None:
    if value in (None, "", "None"):
        return None
    text = str(value)
    if _SECRET_RE.search(text):
        return "[REDACTED]"
    return text


def _sanitize_strings(payload: Any, *, key: str | None = None) -> Any:
    if isinstance(payload, dict):
        return {dict_key: _sanitize_strings(value, key=dict_key) for dict_key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize_strings(value, key=key) for value in payload]
    if isinstance(payload, tuple):
        return tuple(_sanitize_strings(value, key=key) for value in payload)
    if isinstance(payload, str):
        if key in {"sha256", "artifact_path", "metadata_path", "validation_status", "vwap_formula", "instrument_key_redacted", "source"}:
            return payload
        return _redact(payload)
    return payload


def write_public_metadata(report: NiftyFuturesIngestionReport, output_path: str | Path) -> Path:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    return path
