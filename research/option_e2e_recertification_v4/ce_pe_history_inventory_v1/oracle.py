from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    OPERATIONAL_EXCLUSIONS,
)

_OPTION_RE = re.compile(r"(?:^|[^A-Z0-9])(CE|PE)(?:[^A-Z0-9]|$)", re.IGNORECASE)
_DENIED = (
    "outcome",
    "pnl",
    "profit",
    "loss",
    "holdout",
    "future_return",
    "forward_return",
    "post_trade",
)
_TIME = (
    "timestamp",
    "ts",
    "local_ts",
    "exchange_timestamp",
    "quote_timestamp",
    "quote_ts",
)
_ID = {"instrument_key", "instrument_token", "symbol", "trading_symbol", "tradingsymbol"}
_BID = {"bid", "bid_price", "best_bid"}
_ASK = {"ask", "ask_price", "best_ask"}
_OPTION_TYPE = {"option_type", "instrument_type", "type"}
_STRIKE = {"strike", "strike_price"}
_EXPIRY = {"expiry", "expiry_date"}
_NORMALIZED = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "bid",
    "ask",
    "quote_timestamp",
    "underlying",
    "option_type",
    "strike",
    "expiry",
    "provider",
    "dataset_hash",
    "bar_interval",
}
MAX_ZIP_PARQUET_MEMBER_BYTES = 128 * 1024 * 1024


def _denied(value: str) -> bool:
    text = value.casefold().replace("-", "_").replace(" ", "_")
    return any(token in text for token in _DENIED)


def _archive_metadata(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(path.parts and path.parts[0] == "__MACOSX")
        or path.name.startswith("._")
        or path.name == ".DS_Store"
    )


def _option_name(value: str) -> bool:
    name = PurePosixPath(value).name.replace("_", " ").replace("-", " ")
    return bool(_OPTION_RE.search(name))


def _path_date(value: str) -> str | None:
    for part in PurePosixPath(value).parts:
        if len(part) == 8 and part.isdigit():
            try:
                return datetime.strptime(part, "%Y%m%d").date().isoformat()
            except ValueError:
                return None
    return None


def _to_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            ).date().isoformat()
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        number = float(value)
        magnitude = abs(number)
        divisor = (
            1e9
            if magnitude >= 1e17
            else 1e6
            if magnitude >= 1e14
            else 1e3
            if magnitude >= 1e11
            else 1.0
        )
        try:
            return datetime.fromtimestamp(number / divisor, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _footer(source: Any, path_hint: str) -> dict[str, Any]:
    import pyarrow.parquet as pq

    try:
        parquet = pq.ParquetFile(source)
    except Exception as exc:
        return {
            "columns": [],
            "session_dates": [],
            "session_date_evidence": f"PARQUET_FOOTER_REJECTED:{type(exc).__name__}",
        }
    metadata = parquet.metadata
    columns = [str(name) for name in parquet.schema_arrow.names]
    timestamp_column = next((name for name in _TIME if name in columns), None)
    dates: set[str] = set()
    if timestamp_column:
        for group_index in range(metadata.num_row_groups):
            group = metadata.row_group(group_index)
            for column_index in range(group.num_columns):
                column = group.column(column_index)
                if column.path_in_schema != timestamp_column:
                    continue
                stats = column.statistics
                if stats is None or not stats.has_min_max:
                    continue
                minimum = _to_date(stats.min)
                maximum = _to_date(stats.max)
                if minimum:
                    dates.add(minimum)
                if maximum:
                    dates.add(maximum)
    if len(dates) == 1:
        session_dates = sorted(dates)
        evidence = "PARQUET_FOOTER_STATISTICS"
    elif dates:
        session_dates = []
        evidence = "MULTI_DATE_FOOTER_REQUIRES_DEEP_REVIEW"
    else:
        hinted = _path_date(path_hint)
        session_dates = [hinted] if hinted else []
        evidence = "PATH_HINT_ONLY" if hinted else "NOT_ESTABLISHED"
    return {
        "columns": columns,
        "session_dates": session_dates,
        "session_date_evidence": evidence,
    }


def _relevant(columns: list[str], path_hint: str) -> bool:
    values = set(columns)
    if _NORMALIZED.issubset(values):
        return True
    if values & set(_TIME) and values & _ID and values & _BID and values & _ASK:
        return True
    if (
        values & set(_TIME)
        and values & _OPTION_TYPE
        and values & _STRIKE
        and values & _EXPIRY
    ):
        return True
    return bool(
        values & set(_TIME)
        and {"open", "high", "low", "close"}.issubset(values)
        and _option_name(path_hint)
    )


def oracle_inventory(machine_manifest: Path) -> dict[str, Any]:
    payload = json.loads(machine_manifest.read_text(encoding="utf-8"))
    candidate_ids: list[str] = []
    session_dates: set[str] = set()
    denied_count = 0
    files_visited = 0
    parquet_metadata_inspected = 0
    zip_members_inspected = 0
    archive_metadata_members = 0
    oversized_option_members = 0

    for root in sorted(
        payload.get("roots", []), key=lambda row: str(row["current_root_id"])
    ):
        root_id = str(root["current_root_id"])
        root_path = Path(root["absolute_path"])
        if root_path.is_symlink() or not root_path.is_dir():
            raise ValueError(f"oracle_invalid_root:{root_id}")
        root_path = root_path.resolve(strict=True)

        for directory, dirnames, filenames in os.walk(root_path, followlinks=False):
            retained: list[str] = []
            for name in sorted(dirnames):
                child = Path(directory) / name
                if name in OPERATIONAL_EXCLUSIONS:
                    continue
                if child.is_symlink():
                    raise ValueError(
                        f"oracle_symlink_directory:{root_id}:"
                        f"{child.relative_to(root_path).as_posix()}"
                    )
                retained.append(name)
            dirnames[:] = retained

            for filename in sorted(filenames):
                path = Path(directory) / filename
                relative = path.relative_to(root_path).as_posix()
                files_visited += 1
                if path.is_symlink():
                    raise ValueError(f"oracle_symlink_file:{root_id}:{relative}")
                if stat.S_IFMT(path.lstat().st_mode) != stat.S_IFREG or not path.is_file():
                    raise ValueError(f"oracle_non_regular_file:{root_id}:{relative}")
                if _denied(relative):
                    denied_count += 1
                    continue

                if path.suffix.casefold() == ".parquet":
                    footer = _footer(path, relative)
                    parquet_metadata_inspected += 1
                    if _relevant(footer["columns"], relative):
                        candidate_ids.append(f"{root_id}:{relative}")
                        session_dates.update(footer["session_dates"])
                    continue
                if path.suffix.casefold() != ".zip":
                    continue

                with zipfile.ZipFile(path) as archive:
                    for info in sorted(
                        archive.infolist(), key=lambda item: item.filename
                    ):
                        zip_members_inspected += 1
                        name = PurePosixPath(info.filename).as_posix()
                        if _archive_metadata(name):
                            archive_metadata_members += 1
                            continue
                        if (
                            info.is_dir()
                            or _denied(name)
                            or not name.casefold().endswith(".parquet")
                            or not _option_name(name)
                        ):
                            continue
                        if info.file_size > MAX_ZIP_PARQUET_MEMBER_BYTES:
                            oversized_option_members += 1
                            continue
                        with archive.open(info) as handle:
                            content = handle.read(MAX_ZIP_PARQUET_MEMBER_BYTES + 1)
                        if len(content) != info.file_size:
                            raise ValueError(
                                f"oracle_archive_member_size_mismatch:{name}"
                            )
                        footer = _footer(io.BytesIO(content), name)
                        parquet_metadata_inspected += 1
                        if _relevant(footer["columns"], name):
                            candidate_ids.append(f"{root_id}:{relative}!{name}")
                            session_dates.update(footer["session_dates"])

    candidate_ids.sort()
    digest = hashlib.sha256(
        "".join(f"{candidate_id}\n" for candidate_id in candidate_ids).encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "schema_version": "ce_pe_history_inventory_oracle_v1",
        "candidate_ids": candidate_ids,
        "candidate_identity_manifest_sha256": digest,
        "candidate_count": len(candidate_ids),
        "session_dates": sorted(session_dates),
        "files_visited": files_visited,
        "parquet_metadata_inspected": parquet_metadata_inspected,
        "zip_members_inspected": zip_members_inspected,
        "archive_metadata_members": archive_metadata_members,
        "oversized_option_members_not_opened": oversized_option_members,
        "zip_member_read_limit_bytes": MAX_ZIP_PARQUET_MEMBER_BYTES,
        "denied_metadata_only_count": denied_count,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
