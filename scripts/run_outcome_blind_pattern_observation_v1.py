#!/usr/bin/env python3
"""Outcome-blind market pattern observation V1.

Stage 0 profiles the physical historical evidence and explicitly separates
pre-outcome fields from future/entry/outcome fields. It does not calculate P&L,
rank trading ideas, select CE/PE direction, or inspect later validation/holdout
outcomes. Research-only and never executable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

CAMPAIGN = "outcome_blind_pattern_observation_v1"
FORBIDDEN_PATTERNS = (
    r"(^|_)future($|_)",
    r"(^|_)forward($|_)",
    r"(^|_)next($|_)",
    r"(^|_)entry($|_)",
    r"(^|_)exit($|_)",
    r"(^|_)outcome($|_)",
    r"(^|_)target($|_)",
    r"(^|_)label($|_)",
    r"(^|_)pnl($|_)",
    r"(^|_)profit($|_)",
    r"(^|_)payoff($|_)",
    r"(^|_)winner($|_)",
    r"(^|_)holdout($|_)",
)
IDENTIFIER_PATTERNS = (
    r"(^|_)id($|_)",
    r"(^|_)key($|_)",
    r"(^|_)symbol($|_)",
    r"(^|_)token($|_)",
    r"(^|_)name($|_)",
    r"(^|_)path($|_)",
    r"(^|_)sha($|_)",
    r"(^|_)hash($|_)",
)
TIMESTAMP_CANDIDATES = (
    "timestamp",
    "ts",
    "datetime",
    "signal_ts",
    "bar_ts",
    "bar_end_ts",
    "source_bar_end",
    "source_bar_end_ts",
)
SESSION_CANDIDATES = ("session", "session_id", "trade_date", "date")


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_forbidden(name: str) -> bool:
    lowered = name.lower()
    return any(re.search(pattern, lowered) for pattern in FORBIDDEN_PATTERNS)


def is_identifier(name: str) -> bool:
    lowered = name.lower()
    return any(re.search(pattern, lowered) for pattern in IDENTIFIER_PATTERNS)


def choose_timestamp(columns: list[str]) -> str | None:
    lower_map = {column.lower(): column for column in columns}
    for candidate in TIMESTAMP_CANDIDATES:
        if candidate in lower_map:
            return lower_map[candidate]
    for column in columns:
        lowered = column.lower()
        if "timestamp" in lowered or lowered.endswith("_ts"):
            return column
    return None


def choose_session(columns: list[str]) -> str | None:
    lower_map = {column.lower(): column for column in columns}
    for candidate in SESSION_CANDIDATES:
        if candidate in lower_map:
            return lower_map[candidate]
    return None


def parquet_summary(path: Path, repo: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    columns = [field.name for field in schema]
    dtypes = {field.name: str(field.type) for field in schema}
    numeric = [field.name for field in schema if str(field.type).startswith(("int", "uint", "float", "double", "decimal"))]
    forbidden = sorted(column for column in columns if is_forbidden(column))
    identifiers = sorted(column for column in columns if is_identifier(column))
    allowed_numeric = sorted(column for column in numeric if column not in forbidden and column not in identifiers)
    timestamp_column = choose_timestamp(columns)
    session_column = choose_session(columns)

    selected = []
    for column in [timestamp_column, session_column, *allowed_numeric]:
        if column and column not in selected:
            selected.append(column)
    selected = selected[:42]
    table = pq.read_table(path, columns=selected) if selected else None
    frame = table.to_pandas() if table is not None else pd.DataFrame()

    numeric_profile: dict[str, Any] = {}
    for column in allowed_numeric:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        finite = values[np.isfinite(values)]
        if finite.empty:
            numeric_profile[column] = {"non_null": 0}
            continue
        numeric_profile[column] = {
            "non_null": int(finite.size),
            "unique": int(finite.nunique(dropna=True)),
            "min": float(finite.min()),
            "p01": float(finite.quantile(0.01)),
            "p25": float(finite.quantile(0.25)),
            "median": float(finite.quantile(0.50)),
            "p75": float(finite.quantile(0.75)),
            "p99": float(finite.quantile(0.99)),
            "max": float(finite.max()),
        }

    temporal: dict[str, Any] = {}
    if timestamp_column and timestamp_column in frame.columns:
        ts = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True)
        temporal["timestamp_column"] = timestamp_column
        temporal["timestamp_non_null"] = int(ts.notna().sum())
        if ts.notna().any():
            temporal["timestamp_min"] = ts.min().isoformat()
            temporal["timestamp_max"] = ts.max().isoformat()
    if session_column and session_column in frame.columns:
        sessions = frame[session_column].dropna().astype(str)
        temporal["session_column"] = session_column
        temporal["session_count"] = int(sessions.nunique())
        if not sessions.empty:
            ordered = sorted(sessions.unique().tolist())
            temporal["first_sessions"] = ordered[:5]
            temporal["last_sessions"] = ordered[-5:]

    return {
        "path": str(path.relative_to(repo)),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "rows": parquet.metadata.num_rows,
        "row_groups": parquet.metadata.num_row_groups,
        "columns": len(columns),
        "schema": dtypes,
        "forbidden_future_or_outcome_columns": forbidden,
        "identifier_columns": identifiers,
        "allowed_numeric_preoutcome_candidates": allowed_numeric,
        "numeric_profile": numeric_profile,
        "temporal": temporal,
    }


def locate(repo: Path, name: str) -> list[Path]:
    root = repo / "research" / "local_evidence_consolidation_v1"
    return sorted(path for path in root.rglob(name) if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-root", type=Path, default=Path("runtime/research/outcome_blind_pattern_observation_v1"))
    parser.add_argument("--stage", choices=("profile",), default="profile")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    output = args.output_root if args.output_root.is_absolute() else repo / args.output_root
    output.mkdir(parents=True, exist_ok=True)

    event_universes = locate(repo, "event_universe_5m.parquet")
    repaired = locate(repo, "repaired_joint_underlying_option_warehouse.parquet")
    constituents = locate(repo, "constituent_index_5m.parquet")

    report: dict[str, Any] = {
        "schema_version": 1,
        "campaign": CAMPAIGN,
        "stage": "profile_only",
        "research_only": True,
        "allowed_for_live_execution": False,
        "outcomes_read": False,
        "pnl_calculated": False,
        "hypothesis_named": False,
        "direction_selected": False,
        "holdout_opened": False,
        "selection_policy": "no motif, feature, direction, or strategy selection in profile stage",
        "event_universe_candidates": len(event_universes),
        "repaired_joint_candidates": len(repaired),
        "constituent_candidates": len(constituents),
        "event_universes": [parquet_summary(path, repo) for path in event_universes[:3]],
        "repaired_joint_warehouses": [parquet_summary(path, repo) for path in repaired[:2]],
        "constituent_panels": [parquet_summary(path, repo) for path in constituents[:2]],
    }
    blockers: list[str] = []
    if not repaired:
        blockers.append("missing_repaired_joint_warehouse")
    if not constituents:
        blockers.append("missing_constituent_panel")
    if not event_universes:
        blockers.append("missing_event_universe_5m")
    report["blockers"] = blockers
    report["principal_verdict"] = "OUTCOME_BLIND_OBSERVATION_UNIVERSE_PROFILED" if not blockers else "OBSERVATION_UNIVERSE_PROFILE_BLOCKED"
    stable_write(output / "schema_profile.json", report)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
