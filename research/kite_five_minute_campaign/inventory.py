from __future__ import annotations

import re
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .common import file_sha256, write_json_with_sidecar

INSTRUMENTS = ("BANKNIFTY", "NIFTY", "SENSEX")
DATA_ROOT = Path("research/kite_five_minute_campaign/input/extracted")


def _safe_extract(archive: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = Path(info.filename)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError(f"unsafe archive member: {info.filename}")
            target = (destination / name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise ValueError(f"archive member escapes destination: {info.filename}")
            zf.extract(info, destination)


def _instrument(path: Path) -> str | None:
    upper = path.name.upper()
    for instrument in INSTRUMENTS:
        if instrument in upper:
            return instrument
    return None


def _date(path: Path) -> str | None:
    text = "/".join(path.parts)
    match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", text)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _flag(path: Path, df: pd.DataFrame | None, name: str) -> bool:
    text = str(path).lower()
    if name in text:
        return True
    if df is None:
        return False
    for col in df.columns:
        if col.lower() == name and bool(df[col].astype(bool).any()):
            return True
    return False


def _time_column(df: pd.DataFrame) -> str | None:
    for col in ("timestamp", "datetime", "date", "time"):
        if col in df.columns:
            return col
    return None


def _read_market_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".json", ".jsonl"}:
        return pd.read_json(path, lines=path.suffix.lower() == ".jsonl")
    raise ValueError(f"unsupported market file type: {path.suffix}")


def _classify_file(root: Path, path: Path, content_seen: dict[str, str]) -> dict[str, Any]:
    rel = path.relative_to(root).as_posix()
    entry: dict[str, Any] = {
        "relative_path": rel,
        "filename": path.name,
        "instrument": _instrument(path),
        "trading_date": _date(path),
        "data_source": "KITE" if "kite" in rel.lower() else "UNKNOWN",
        "bar_interval": "UNKNOWN",
        "row_count": 0,
        "minimum_timestamp": None,
        "maximum_timestamp": None,
        "columns": [],
        "dtypes": {},
        "file_size": path.stat().st_size,
        "sha256": file_sha256(path),
        "synthetic": False,
        "fallback": False,
        "mock": False,
        "duplicate_content_status": "UNIQUE",
        "session_completeness_status": "UNKNOWN",
        "accepted": False,
        "rejection_reasons": [],
    }
    if "__MACOSX" in path.parts or path.name.startswith("._"):
        entry["rejection_reasons"].append("APPLE_METADATA")
        return entry
    if path.suffix.lower() not in {".parquet", ".csv", ".json", ".jsonl"}:
        entry["rejection_reasons"].append("UNSUPPORTED_FILE_TYPE")
        return entry
    try:
        df = _read_market_file(path)
    except Exception as exc:
        entry["rejection_reasons"].append(f"MALFORMED:{type(exc).__name__}")
        return entry
    entry["row_count"] = int(len(df))
    entry["columns"] = [str(col) for col in df.columns]
    entry["dtypes"] = {str(col): str(dtype) for col, dtype in df.dtypes.items()}
    entry["synthetic"] = _flag(path, df, "synthetic")
    entry["fallback"] = _flag(path, df, "fallback")
    entry["mock"] = _flag(path, df, "mock") or "OPT_MOCK" in rel.upper()
    ts_col = _time_column(df)
    if ts_col:
        timestamps = pd.to_datetime(df[ts_col], errors="coerce")
        if timestamps.notna().any():
            timestamps = timestamps.dt.tz_localize(
                "Asia/Kolkata", nonexistent="shift_forward", ambiguous="NaT"
            ) if timestamps.dt.tz is None else timestamps.dt.tz_convert("Asia/Kolkata")
            entry["minimum_timestamp"] = timestamps.min().isoformat()
            entry["maximum_timestamp"] = timestamps.max().isoformat()
            diffs = timestamps.sort_values().diff().dropna()
            if not diffs.empty and (diffs == pd.Timedelta(minutes=5)).all():
                entry["bar_interval"] = "5m"
            elif not diffs.empty:
                entry["bar_interval"] = "NON_5M"
    first_for_hash = content_seen.setdefault(entry["sha256"], rel)
    if first_for_hash != rel:
        entry["duplicate_content_status"] = f"DUPLICATE_OF:{first_for_hash}"
    required_cols = {"open", "high", "low", "close"}
    lower_cols = {col.lower() for col in entry["columns"]}
    if entry["instrument"] is None:
        entry["rejection_reasons"].append("AMBIGUOUS_INSTRUMENT")
    if entry["trading_date"] is None:
        entry["rejection_reasons"].append("AMBIGUOUS_TRADING_DATE")
    if entry["data_source"] != "KITE":
        entry["rejection_reasons"].append("AMBIGUOUS_DATA_SOURCE")
    if entry["mock"]:
        entry["rejection_reasons"].append("MOCK_DATA")
    if entry["synthetic"]:
        entry["rejection_reasons"].append("SYNTHETIC_DATA")
    if entry["fallback"]:
        entry["rejection_reasons"].append("FALLBACK_DATA")
    if not required_cols.issubset(lower_cols):
        entry["rejection_reasons"].append("MISSING_OHLC")
    if entry["bar_interval"] != "5m":
        entry["rejection_reasons"].append("NOT_NATIVE_5M")
    if str(entry["duplicate_content_status"]).startswith("DUPLICATE_OF"):
        entry["rejection_reasons"].append("DUPLICATE_CONTENT")
    if entry["row_count"] < 70:
        entry["session_completeness_status"] = "INCOMPLETE"
        entry["rejection_reasons"].append("INCOMPLETE_SESSION")
    else:
        entry["session_completeness_status"] = "COMPLETE"
    entry["accepted"] = not entry["rejection_reasons"]
    return entry


def certify_archive(archive: str | Path, output_root: str | Path, *, commit: str) -> dict[str, Any]:
    archive = Path(archive).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"Kite archive not found: {archive}")
    extract_root = output_root / DATA_ROOT
    _safe_extract(archive, extract_root)
    files = [path for path in extract_root.rglob("*") if path.is_file()]
    content_seen: dict[str, str] = {}
    inventory = [_classify_file(extract_root, path, content_seen) for path in sorted(files)]
    accepted = [row for row in inventory if row["accepted"]]
    rejected = [row for row in inventory if not row["accepted"]]
    by_reason: Counter[str] = Counter()
    for row in rejected:
        by_reason.update(row["rejection_reasons"])
    by_instrument_date: dict[str, set[str]] = defaultdict(set)
    for row in accepted:
        by_instrument_date[str(row["instrument"])].add(str(row["trading_date"]))
    summary = {
        "schema_version": "1.0",
        "archive_path": str(archive),
        "archive_sha256": file_sha256(archive),
        "governing_commit": commit,
        "total_files": len(inventory),
        "accepted_files": len(accepted),
        "rejected_files": len(rejected),
        "accepted_counts_by_instrument": {
            instrument: sum(1 for row in accepted if row["instrument"] == instrument)
            for instrument in INSTRUMENTS
        },
        "rejected_counts_by_reason": dict(sorted(by_reason.items())),
        "date_coverage": {
            "minimum_date": min((row["trading_date"] for row in accepted), default=None),
            "maximum_date": max((row["trading_date"] for row in accepted), default=None),
            "unique_dates": len({row["trading_date"] for row in accepted}),
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    input_dir = output_root / "research/kite_five_minute_campaign/input"
    write_json_with_sidecar(input_dir / "full_inventory.json", inventory)
    write_json_with_sidecar(input_dir / "accepted_underlying_manifest.json", accepted)
    write_json_with_sidecar(input_dir / "rejected_files.json", rejected)
    write_json_with_sidecar(input_dir / "corpus_summary.json", summary)
    return summary
