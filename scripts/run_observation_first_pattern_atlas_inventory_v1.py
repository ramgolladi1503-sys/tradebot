#!/usr/bin/env python3
"""Inventory historical market evidence for observation-first pattern discovery.

This stage intentionally does not calculate returns, labels, P&L, direction,
entries, exits, targets, or stops. It profiles Parquet schema and metadata,
detects outcome-like fields, records timestamp coverage where metadata permits,
and enforces a hard pre-/post-CAS regime boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import pyarrow.parquet as pq

CAMPAIGN = "observation_first_pattern_atlas_v1"
CAS_START_DATE = date(2026, 8, 3)

TIMESTAMP_CANDIDATES = (
    "event_timestamp",
    "timestamp",
    "datetime",
    "date_time",
    "exchange_timestamp",
    "last_trade_time",
    "candle_timestamp",
    "time",
)

SESSION_CANDIDATES = (
    "session_id",
    "session",
    "trade_date",
    "date",
)

OUTCOME_PATTERNS = (
    re.compile(r"(^|_)(future|forward|fwd)(_|$)", re.IGNORECASE),
    re.compile(r"(^|_)(target|stop|entry|exit)(_|$)", re.IGNORECASE),
    re.compile(r"(^|_)(pnl|profit|loss|expectancy|drawdown|sharpe)(_|$)", re.IGNORECASE),
    re.compile(r"(^|_)(label|outcome|winner|win_rate|hit_target)(_|$)", re.IGNORECASE),
    re.compile(r"(^|_)(mfe|mae)(_|$)", re.IGNORECASE),
)

OBSERVATION_HINTS = {
    "underlying": {
        "open", "high", "low", "close", "volume", "vwap",
        "ret_1", "atr_14", "session_progress",
    },
    "option": {
        "option_type", "strike", "premium_mean", "premium_velocity",
        "open_interest", "open_interest_sum",
    },
    "constituent": {
        "symbol", "close", "volume", "session",
    },
    "tick": {
        "ltp", "last_price", "bid_price", "ask_price", "exchange_timestamp",
    },
}


@dataclass(frozen=True)
class FileInventory:
    path: str
    size_bytes: int
    sha256: str
    rows: int | None
    row_groups: int | None
    columns: list[str]
    timestamp_column: str | None
    session_column: str | None
    min_timestamp_metadata: str | None
    max_timestamp_metadata: str | None
    observation_family: str
    outcome_like_columns: list[str]
    schema_error: str | None


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def find_first(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    lookup = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def outcome_like_columns(columns: Iterable[str]) -> list[str]:
    result: list[str] = []
    for column in columns:
        if any(pattern.search(column) for pattern in OUTCOME_PATTERNS):
            result.append(column)
    return sorted(result)


def classify_family(path: Path, columns: Sequence[str]) -> str:
    lowered = {column.lower() for column in columns}
    path_text = str(path).lower()

    scores: dict[str, int] = {}
    for family, hints in OBSERVATION_HINTS.items():
        scores[family] = len(lowered.intersection(hints))

    path_boosts = {
        "option": ("option", "nse_fo", "strike", "ce", "pe"),
        "constituent": ("constituent", "breadth"),
        "tick": ("tick", "depth", "websocket", "market_data"),
        "underlying": ("underlying", "candle", "nifty", "sensex"),
    }
    for family, tokens in path_boosts.items():
        scores[family] += sum(token in path_text for token in tokens)

    family, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    return family if score > 0 else "unknown"


def _stat_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return str(value)
    except Exception:
        return None


def timestamp_stats_from_metadata(
    parquet: pq.ParquetFile,
    timestamp_column: str | None,
) -> tuple[str | None, str | None]:
    if not timestamp_column:
        return None, None

    schema_names = parquet.schema_arrow.names
    try:
        column_index = schema_names.index(timestamp_column)
    except ValueError:
        return None, None

    mins: list[Any] = []
    maxs: list[Any] = []
    metadata = parquet.metadata
    if metadata is None:
        return None, None

    for row_group_index in range(metadata.num_row_groups):
        column = metadata.row_group(row_group_index).column(column_index)
        stats = column.statistics
        if stats is None or not stats.has_min_max:
            continue
        mins.append(stats.min)
        maxs.append(stats.max)

    if not mins or not maxs:
        return None, None

    try:
        minimum = min(mins)
        maximum = max(maxs)
    except TypeError:
        return None, None

    return _stat_to_iso(minimum), _stat_to_iso(maximum)


def inspect_parquet(path: Path, repo_root: Path) -> FileInventory:
    try:
        parquet = pq.ParquetFile(path)
        columns = list(parquet.schema_arrow.names)
        timestamp_column = find_first(columns, TIMESTAMP_CANDIDATES)
        session_column = find_first(columns, SESSION_CANDIDATES)
        min_ts, max_ts = timestamp_stats_from_metadata(parquet, timestamp_column)
        metadata = parquet.metadata
        return FileInventory(
            path=str(path.relative_to(repo_root)),
            size_bytes=path.stat().st_size,
            sha256=sha256(path),
            rows=metadata.num_rows if metadata is not None else None,
            row_groups=metadata.num_row_groups if metadata is not None else None,
            columns=columns,
            timestamp_column=timestamp_column,
            session_column=session_column,
            min_timestamp_metadata=min_ts,
            max_timestamp_metadata=max_ts,
            observation_family=classify_family(path, columns),
            outcome_like_columns=outcome_like_columns(columns),
            schema_error=None,
        )
    except Exception as exc:
        return FileInventory(
            path=str(path.relative_to(repo_root)),
            size_bytes=path.stat().st_size if path.exists() else 0,
            sha256=sha256(path) if path.exists() and path.is_file() else "",
            rows=None,
            row_groups=None,
            columns=[],
            timestamp_column=None,
            session_column=None,
            min_timestamp_metadata=None,
            max_timestamp_metadata=None,
            observation_family="unknown",
            outcome_like_columns=[],
            schema_error=f"{type(exc).__name__}: {exc}",
        )


def parse_date_from_text(text: str) -> date | None:
    patterns = (
        r"(?<!\d)(20\d{2})[-_/](\d{2})[-_/](\d{2})(?!\d)",
        r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            continue
    return None


def regime_for_path(path: str) -> str:
    detected = parse_date_from_text(path)
    if detected is None:
        return "UNRESOLVED"
    return "POST_CAS" if detected >= CAS_START_DATE else "PRE_CAS"


def inventory_summary(files: Sequence[FileInventory]) -> dict[str, Any]:
    families: dict[str, int] = {}
    regimes: dict[str, int] = {}
    total_rows = 0
    rows_known = 0

    for item in files:
        families[item.observation_family] = families.get(item.observation_family, 0) + 1
        regime = regime_for_path(item.path)
        regimes[regime] = regimes.get(regime, 0) + 1
        if item.rows is not None:
            total_rows += item.rows
            rows_known += 1

    return {
        "file_count": len(files),
        "total_size_bytes": sum(item.size_bytes for item in files),
        "files_with_known_row_count": rows_known,
        "known_total_rows": total_rows,
        "families": dict(sorted(families.items())),
        "regimes_by_path_date": dict(sorted(regimes.items())),
        "schema_errors": sum(item.schema_error is not None for item in files),
        "files_with_outcome_like_columns": sum(bool(item.outcome_like_columns) for item in files),
        "files_without_timestamp_column": sum(item.timestamp_column is None for item in files),
    }


def build_readiness_markdown(
    summary: dict[str, Any],
    files: Sequence[FileInventory],
) -> str:
    schema_errors = [item for item in files if item.schema_error]
    forbidden = [item for item in files if item.outcome_like_columns]
    unknown_regime = [item for item in files if regime_for_path(item.path) == "UNRESOLVED"]

    verdict = (
        "READY_FOR_OBSERVATION_WAREHOUSE_DESIGN"
        if files and not schema_errors
        else "DATA_INVENTORY_REQUIRES_REPAIR"
    )

    lines = [
        "# Observation-First Pattern Atlas V1 — Data Readiness",
        "",
        f"Principal verdict: `{verdict}`",
        "",
        "This stage did not calculate returns, labels, direction, entries, exits, targets, stops, P&L, or performance.",
        "",
        "## Corpus summary",
        "",
        f"- Parquet files: `{summary['file_count']}`",
        f"- Known rows: `{summary['known_total_rows']}` across `{summary['files_with_known_row_count']}` files",
        f"- Schema errors: `{summary['schema_errors']}`",
        f"- Files containing outcome-like columns: `{summary['files_with_outcome_like_columns']}`",
        f"- Files with unresolved regime date: `{len(unknown_regime)}`",
        "",
        "## Family counts",
        "",
    ]
    for family, count in summary["families"].items():
        lines.append(f"- `{family}`: `{count}`")

    lines.extend(["", "## Governance findings", ""])
    if forbidden:
        lines.append("- Outcome-like columns exist and must be excluded by an explicit pre-outcome allowlist:")
        for item in forbidden[:25]:
            lines.append(f"  - `{item.path}`: {', '.join(item.outcome_like_columns)}")
    else:
        lines.append("- No outcome-like columns were detected by the inventory denylist.")

    if schema_errors:
        lines.append("- Files with schema errors:")
        for item in schema_errors[:25]:
            lines.append(f"  - `{item.path}`: {item.schema_error}")
    else:
        lines.append("- No Parquet schema errors were detected.")

    lines.extend(
        [
            "",
            "## Next stage",
            "",
            "Build the normalized, pre-outcome trajectory warehouse with explicit session coverage and hard PRE_CAS/POST_CAS partitioning.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--search-root",
        type=Path,
        default=Path("research/local_evidence_consolidation_v1"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/research/observation_first_pattern_atlas_v1/inventory"),
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    search_root = args.search_root
    if not search_root.is_absolute():
        search_root = repo_root / search_root
    output_root = args.output_root
    if not output_root.is_absolute():
        output_root = repo_root / output_root

    if not search_root.exists():
        raise FileNotFoundError(f"Search root does not exist: {search_root}")

    parquet_paths = sorted(path for path in search_root.rglob("*.parquet") if path.is_file())
    if not parquet_paths:
        raise FileNotFoundError(f"No Parquet files found below: {search_root}")

    inventory = [inspect_parquet(path, repo_root) for path in parquet_paths]
    summary = inventory_summary(inventory)

    contract = {
        "schema_version": 1,
        "campaign": CAMPAIGN,
        "stage": "corpus_inventory",
        "repo_root": str(repo_root),
        "search_root": str(search_root),
        "cas_start_date": CAS_START_DATE.isoformat(),
        "policy": {
            "schema_and_metadata_only": True,
            "outcomes_read": False,
            "returns_calculated": False,
            "pnl_calculated": False,
            "direction_selected": False,
            "entry_exit_defined": False,
            "validation_opened": False,
            "holdout_opened": False,
            "allowed_for_live_execution": False,
        },
        "timestamp_candidates": list(TIMESTAMP_CANDIDATES),
        "session_candidates": list(SESSION_CANDIDATES),
        "outcome_column_denylist_patterns": [
            pattern.pattern for pattern in OUTCOME_PATTERNS
        ],
    }
    contract["semantic_sha256"] = semantic_hash(contract)

    cas_inventory = {
        "cas_start_date": CAS_START_DATE.isoformat(),
        "rule": "path-derived dates before CAS start are PRE_CAS; on/after are POST_CAS; unresolved dates remain isolated",
        "counts": summary["regimes_by_path_date"],
        "files": [
            {
                "path": item.path,
                "regime": regime_for_path(item.path),
                "min_timestamp_metadata": item.min_timestamp_metadata,
                "max_timestamp_metadata": item.max_timestamp_metadata,
            }
            for item in inventory
        ],
    }
    cas_inventory["semantic_sha256"] = semantic_hash(cas_inventory)

    output_root.mkdir(parents=True, exist_ok=True)
    stable_write(output_root / "observation_contract.json", contract)
    stable_write(
        output_root / "corpus_inventory.json",
        {
            "summary": summary,
            "files": [asdict(item) for item in inventory],
            "semantic_sha256": semantic_hash([asdict(item) for item in inventory]),
        },
    )
    stable_write(output_root / "cas_regime_inventory.json", cas_inventory)
    (output_root / "DATA_READINESS.md").write_text(
        build_readiness_markdown(summary, inventory),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
