from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import OPERATIONAL_EXCLUSIONS

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
_TIME = {
    "timestamp",
    "ts",
    "local_ts",
    "exchange_timestamp",
    "quote_timestamp",
    "quote_ts",
}
_ID = {"instrument_key", "instrument_token", "symbol", "trading_symbol", "tradingsymbol"}
_BID = {"bid", "bid_price", "best_bid"}
_ASK = {"ask", "ask_price", "best_ask"}
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


def _denied(value: str) -> bool:
    text = value.casefold().replace("-", "_").replace(" ", "_")
    return any(token in text for token in _DENIED)


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


def _footer(source: Any) -> list[str]:
    import pyarrow.parquet as pq

    return [str(name) for name in pq.ParquetFile(source).schema_arrow.names]


def _relevant(columns: list[str], path_hint: str) -> bool:
    values = set(columns)
    if _NORMALIZED.issubset(values):
        return True
    if values & _TIME and values & _ID and values & _BID and values & _ASK:
        return True
    return bool(
        values & _TIME
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
    for root in sorted(payload.get("roots", []), key=lambda row: str(row["current_root_id"])):
        root_id = str(root["current_root_id"])
        root_path = Path(root["absolute_path"]).resolve(strict=True)
        for directory, dirnames, filenames in os.walk(root_path, followlinks=False):
            dirnames[:] = sorted(
                name for name in dirnames if name not in OPERATIONAL_EXCLUSIONS
            )
            for filename in sorted(filenames):
                path = Path(directory) / filename
                relative = path.relative_to(root_path).as_posix()
                files_visited += 1
                if _denied(relative):
                    denied_count += 1
                    continue
                if path.suffix.casefold() == ".parquet":
                    columns = _footer(path)
                    parquet_metadata_inspected += 1
                    if _relevant(columns, relative):
                        candidate_ids.append(f"{root_id}:{relative}")
                    continue
                if path.suffix.casefold() != ".zip":
                    continue
                with zipfile.ZipFile(path) as archive:
                    for info in sorted(archive.infolist(), key=lambda item: item.filename):
                        zip_members_inspected += 1
                        name = PurePosixPath(info.filename).as_posix()
                        if (
                            info.is_dir()
                            or _denied(name)
                            or not name.casefold().endswith(".parquet")
                            or not _option_name(name)
                        ):
                            continue
                        with archive.open(info) as handle:
                            content = handle.read()
                        columns = _footer(io.BytesIO(content))
                        parquet_metadata_inspected += 1
                        if _relevant(columns, name):
                            candidate_ids.append(f"{root_id}:{relative}!{name}")
                            found = _path_date(name)
                            if found:
                                session_dates.add(found)
    candidate_ids.sort()
    digest = hashlib.sha256(
        "".join(f"{candidate_id}\n" for candidate_id in candidate_ids).encode("utf-8")
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
        "denied_metadata_only_count": denied_count,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
