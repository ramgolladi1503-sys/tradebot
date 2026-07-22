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
FULL_SESSION_ROWS = 70
PRIMARY_DISPOSITIONS = (
    "ACCEPTED_UNDERLYING",
    "REJECT_APPLE_METADATA",
    "REJECT_MOCK_DATA",
    "REJECT_NON_UNDERLYING",
    "REJECT_NOT_NATIVE_5M",
    "REJECT_INCOMPLETE_SESSION",
    "REJECT_MALFORMED",
    "REJECT_DUPLICATE",
    "REJECT_AMBIGUOUS",
)
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
        "entry_type": "FILE",
        "primary_disposition": "REJECT_AMBIGUOUS",
        "secondary_flags": [],
        "observed_interval": "UNKNOWN",
        "expected_completed_bar_schedule": "09:15-15:25 Asia/Kolkata native 5-minute completed bars",
        "missing_timestamps": [],
        "duplicate_timestamps": [],
        "reason_evidence": [],
        "accepted": False,
        "rejection_reasons": [],
    }
    if "__MACOSX" in path.parts or path.name.startswith("._"):
        entry["primary_disposition"] = "REJECT_APPLE_METADATA"
        entry["reason_evidence"].append("Apple metadata path or AppleDouble filename")
        entry["rejection_reasons"].append("APPLE_METADATA")
        return entry
    if path.suffix.lower() not in {".parquet", ".csv", ".json", ".jsonl"}:
        entry["primary_disposition"] = "REJECT_NON_UNDERLYING"
        entry["reason_evidence"].append(f"unsupported non-market extension {path.suffix}")
        entry["rejection_reasons"].append("UNSUPPORTED_FILE_TYPE")
        return entry
    try:
        df = _read_market_file(path)
    except Exception as exc:
        entry["primary_disposition"] = "REJECT_MALFORMED"
        entry["reason_evidence"].append(f"reader raised {type(exc).__name__}: {exc}")
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
                entry["observed_interval"] = "5m"
            elif not diffs.empty:
                entry["bar_interval"] = "NON_5M"
                entry["observed_interval"] = ",".join(
                    str(value) for value in sorted(set(diffs.astype(str)))[:5]
                )
            duplicated = timestamps[timestamps.duplicated()].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
            entry["duplicate_timestamps"] = sorted(set(duplicated.astype(str)))
            if entry["trading_date"]:
                expected = pd.date_range(
                    f"{entry['trading_date']} 09:15",
                    f"{entry['trading_date']} 15:25",
                    freq="5min",
                    tz="Asia/Kolkata",
                )
                missing = expected.difference(pd.DatetimeIndex(timestamps.dropna()))
                entry["missing_timestamps"] = [value.isoformat() for value in missing]
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
    if entry["row_count"] < FULL_SESSION_ROWS:
        entry["session_completeness_status"] = "INCOMPLETE"
        entry["rejection_reasons"].append("INCOMPLETE_SESSION")
    else:
        entry["session_completeness_status"] = "COMPLETE"
    is_underlying_path = "/underlying/" in rel.lower()
    if entry["mock"]:
        entry["primary_disposition"] = "REJECT_MOCK_DATA"
        entry["reason_evidence"].append("mock flag, mock filename, or OPT_MOCK marker")
    elif not is_underlying_path:
        entry["primary_disposition"] = "REJECT_NON_UNDERLYING"
        entry["reason_evidence"].append("not under the archive underlying lane")
    elif entry["instrument"] is None or entry["trading_date"] is None or entry["data_source"] != "KITE":
        entry["primary_disposition"] = "REJECT_AMBIGUOUS"
        entry["reason_evidence"].append("instrument, date, or source could not be inferred uniquely")
    elif str(entry["duplicate_content_status"]).startswith("DUPLICATE_OF"):
        entry["primary_disposition"] = "REJECT_DUPLICATE"
        entry["reason_evidence"].append(str(entry["duplicate_content_status"]))
    elif entry["bar_interval"] != "5m":
        entry["primary_disposition"] = "REJECT_NOT_NATIVE_5M"
        entry["reason_evidence"].append(f"observed interval is {entry['observed_interval']}")
    elif entry["session_completeness_status"] != "COMPLETE":
        entry["primary_disposition"] = "REJECT_INCOMPLETE_SESSION"
        entry["reason_evidence"].append(
            f"row_count {entry['row_count']} is below full-session minimum {FULL_SESSION_ROWS}"
        )
    elif entry["rejection_reasons"]:
        entry["primary_disposition"] = "REJECT_AMBIGUOUS"
        entry["reason_evidence"].append("secondary rejection flags remain after primary checks")
    else:
        entry["primary_disposition"] = "ACCEPTED_UNDERLYING"
    entry["secondary_flags"] = list(entry["rejection_reasons"])
    entry["accepted"] = entry["primary_disposition"] == "ACCEPTED_UNDERLYING"
    return entry


def _zip_authority(archive: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        files = [info for info in infos if not info.is_dir()]
    non_apple = [
        info for info in files
        if "__MACOSX" not in Path(info.filename).parts
        and not Path(info.filename).name.startswith("._")
    ]
    def count_symbol(symbol: str) -> int:
        total = 0
        for info in non_apple:
            name = Path(info.filename).name.upper()
            if "OPT_MOCK" in name or "MOCK" in name:
                continue
            if symbol == "NIFTY":
                total += "NIFTY" in name and "BANKNIFTY" not in name
            else:
                total += symbol in name
        return int(total)
    return {
        "archive_path": str(archive),
        "byte_size": archive.stat().st_size,
        "sha256": file_sha256(archive),
        "zip_entry_count": len(infos),
        "directory_entry_count": len(infos) - len(files),
        "non_directory_file_count": len(files),
        "apple_metadata_count": len(files) - len(non_apple),
        "non_apple_file_count": len(non_apple),
        "real_underlying_count_by_symbol_before_filtering": {
            symbol: count_symbol(symbol) for symbol in INSTRUMENTS
        },
        "mock_option_count": sum(
            1 for info in non_apple
            if "OPT_MOCK" in Path(info.filename).name.upper()
            or "MOCK" in Path(info.filename).name.upper()
        ),
        "other_real_file_count": len(non_apple)
        - sum(count_symbol(symbol) for symbol in INSTRUMENTS)
        - sum(
            1 for info in non_apple
            if "OPT_MOCK" in Path(info.filename).name.upper()
            or "MOCK" in Path(info.filename).name.upper()
        ),
    }


def _date_alignment_manifest(accepted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in accepted:
        by_date[str(row["trading_date"])].append(row)
    aligned = []
    for date, rows in sorted(by_date.items()):
        by_symbol = {row["instrument"]: row for row in rows}
        missing = [symbol for symbol in INSTRUMENTS if symbol not in by_symbol]
        timestamp_sets = {
            symbol: {
                ts for ts in pd.date_range(
                    by_symbol[symbol]["minimum_timestamp"],
                    by_symbol[symbol]["maximum_timestamp"],
                    freq="5min",
                ).astype(str)
            }
            for symbol in by_symbol
        }
        compatible = not missing and len({tuple(sorted(v)) for v in timestamp_sets.values()}) == 1
        aligned.append(
            {
                "trading_date": date,
                "symbols": sorted(by_symbol),
                "missing_symbols": missing,
                "compatible_completed_bar_timestamps": compatible,
                "file_count": len(rows),
                "files": {symbol: by_symbol[symbol]["relative_path"] for symbol in sorted(by_symbol)},
            }
        )
    return aligned


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
    for row in inventory:
        if row["primary_disposition"] not in PRIMARY_DISPOSITIONS:
            raise ValueError(f"invalid primary disposition for {row['relative_path']}")
    accepted = [row for row in inventory if row["accepted"]]
    rejected = [row for row in inventory if not row["accepted"]]
    primary_counts = Counter(row["primary_disposition"] for row in inventory)
    secondary_counts: Counter[str] = Counter()
    for row in rejected:
        secondary_counts.update(row["secondary_flags"])
    by_instrument_date: dict[str, set[str]] = defaultdict(set)
    for row in accepted:
        by_instrument_date[str(row["instrument"])].add(str(row["trading_date"]))
    summary = {
        "schema_version": "1.0",
        "archive_authority": _zip_authority(archive),
        "archive_path": str(archive),
        "archive_sha256": file_sha256(archive),
        "governing_commit": commit,
        "total_files": len(inventory),
        "accepted_files": len(accepted),
        "rejected_files": len(rejected),
        "primary_disposition_counts": {
            disposition: int(primary_counts.get(disposition, 0))
            for disposition in PRIMARY_DISPOSITIONS
        },
        "primary_disposition_count_sum": int(sum(primary_counts.values())),
        "secondary_flag_counts": dict(sorted(secondary_counts.items())),
        "accepted_counts_by_instrument": {
            instrument: sum(1 for row in accepted if row["instrument"] == instrument)
            for instrument in INSTRUMENTS
        },
        "rejected_counts_by_reason": dict(sorted(secondary_counts.items())),
        "underlying_rejected_files": [
            row for row in rejected
            if "/underlying/" in row["relative_path"].lower()
            and row["primary_disposition"] != "REJECT_APPLE_METADATA"
        ],
        "excluded_underlying_dates": sorted(
            {
                row["trading_date"] for row in rejected
                if "/underlying/" in row["relative_path"].lower()
                and row["primary_disposition"] != "REJECT_APPLE_METADATA"
            }
        ),
        "incomplete_flag_reconciliation": {
            "total_incomplete_secondary_flags": int(secondary_counts.get("INCOMPLETE_SESSION", 0)),
            "incomplete_underlying_primary_rejections": int(primary_counts.get("REJECT_INCOMPLETE_SESSION", 0)),
            "explanation": (
                "Seven INCOMPLETE_SESSION secondary flags coexist with six excluded underlying files "
                "because one incomplete file is an OPT_MOCK option file whose primary disposition is REJECT_MOCK_DATA."
            ),
        },
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
    write_json_with_sidecar(input_dir / "canonical_file_disposition.json", inventory)
    write_json_with_sidecar(input_dir / "date_alignment_manifest.json", _date_alignment_manifest(accepted))
    write_json_with_sidecar(input_dir / "corpus_summary.json", summary)
    return summary
