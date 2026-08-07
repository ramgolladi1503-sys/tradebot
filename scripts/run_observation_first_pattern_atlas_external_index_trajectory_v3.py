#!/usr/bin/env python3
"""Disk-safe authoritative continuous-index trajectory for Pattern Atlas V1.

Reads one already-downloaded physical Parquet directly from an external path
(e.g. the shared Git LFS object store). The file is hashed and schema-inspected
in place, so no LFS checkout or runtime copy is required inside the research
worktree.

No future return, outcome label, trade direction, entry, exit, stop, target,
P&L, validation outcome, or holdout outcome is read or calculated.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

V2_PATH = Path(__file__).with_name(
    "run_observation_first_pattern_atlas_index_trajectory_v2.py"
)
SPEC = importlib.util.spec_from_file_location("pattern_atlas_index_trajectory_v2", V2_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load v2 trajectory module: {V2_PATH}")
V2 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V2
SPEC.loader.exec_module(V2)
BASE = V2.BASE

CAMPAIGN = "observation_first_pattern_atlas_v1"
STAGE = "external_authoritative_continuous_index_trajectory_v3"
DEFAULT_NIFTY_SOURCE_SHA256 = V2.DEFAULT_NIFTY_SOURCE_SHA256
DEFAULT_NIFTY_SOURCE_SIZE = 47_788_672


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def inspect_external_parquet(
    path: Path,
    expected_sha256: str,
    expected_size: int,
    logical_basename: str,
) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"External authoritative source is not a file: {resolved}")

    size = int(resolved.stat().st_size)
    if expected_size > 0 and size != expected_size:
        raise ValueError(
            f"Authoritative source size mismatch: expected={expected_size} actual={size}"
        )

    actual_sha256 = sha256_file(resolved)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "Authoritative source SHA-256 mismatch: "
            f"expected={expected_sha256} actual={actual_sha256}"
        )

    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyarrow is required for external Parquet inspection") from exc

    parquet = pq.ParquetFile(resolved)
    columns = [str(value) for value in parquet.schema_arrow.names]
    forbidden = sorted(column for column in columns if BASE.denied(column))
    if forbidden:
        raise ValueError(f"Authoritative source contains outcome-like columns: {forbidden}")

    return {
        "path": str(resolved),
        "logical_basename": logical_basename,
        "sha256": actual_sha256,
        "size_bytes": size,
        "rows": int(parquet.metadata.num_rows),
        "row_groups": int(parquet.metadata.num_row_groups),
        "columns": columns,
        "outcome_like_columns": [],
        "schema_error": None,
        "storage_mode": "shared_external_physical_file",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-sha256", default=DEFAULT_NIFTY_SOURCE_SHA256)
    parser.add_argument("--source-size", type=int, default=DEFAULT_NIFTY_SOURCE_SIZE)
    parser.add_argument("--source-basename", default="constituent_index_5m.parquet")
    parser.add_argument("--index-symbol", default="NIFTY")
    parser.add_argument("--minimum-source-sessions", type=int, default=120)
    parser.add_argument("--minimum-median-price", type=float, default=10000.0)
    parser.add_argument("--grid-points", type=int, default=96)
    parser.add_argument("--minimum-native-coverage", type=float, default=0.90)
    parser.add_argument("--maximum-staleness-multiple", type=float, default=1.25)
    parser.add_argument("--naive-timezone", default=BASE.TZ)
    args = parser.parse_args()

    source = inspect_external_parquet(
        args.source_file,
        args.source_sha256,
        args.source_size,
        args.source_basename,
    )
    selected_columns = BASE.allowed_columns("constituent", source["columns"])
    if BASE.first(selected_columns, BASE.TS) is None:
        raise ValueError("Authoritative source has no allowed timestamp column")
    if BASE.first(selected_columns, BASE.PRICE) is None:
        raise ValueError("Authoritative source has no allowed price column")

    raw = BASE.read_parquet(Path(source["path"]), selected_columns)
    index_raw, selection_diagnostics = V2.select_exact_index_rows(
        raw,
        args.index_symbol,
        args.minimum_source_sessions,
        args.minimum_median_price,
    )
    clean = BASE.canonicalize(
        index_raw,
        source["logical_basename"],
        "constituent",
        args.naive_timezone,
    )
    clean["instrument"] = args.index_symbol

    cadence = V2.infer_native_cadence(clean)
    minute = BASE.resample_minutes(clean).merge(
        cadence,
        on=["instrument", "session_date"],
        how="left",
        validate="many_to_one",
    )
    causal = BASE.add_causal_features(minute)
    accepted, rejected = V2.build_cadence_aware_vectors(
        causal,
        args.grid_points,
        args.minimum_native_coverage,
        args.maximum_staleness_multiple,
    )

    output = args.output_root.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    causal.to_parquet(output / "causal_minute_trajectory.parquet", index=False)
    BASE.stable_write(output / "completed_session_vectors.json", {"sessions": accepted})
    BASE.stable_write(output / "rejected_sessions.json", {"sessions": rejected})

    authority = {
        "campaign": CAMPAIGN,
        "stage": STAGE,
        "source_path": source["path"],
        "source_logical_basename": source["logical_basename"],
        "source_sha256": source["sha256"],
        "source_size_bytes": source["size_bytes"],
        "source_rows": source["rows"],
        "source_row_groups": source["row_groups"],
        "source_storage_mode": source["storage_mode"],
        "index_symbol": args.index_symbol,
        "selection": selection_diagnostics,
        "policy": {
            "exact_physical_sha_required": True,
            "exact_physical_size_required": True,
            "external_source_read_in_place": True,
            "worktree_source_copy_required": False,
            "exact_continuous_symbol_required": True,
            "option_contracts_excluded": True,
            "native_cadence_quality": True,
            "outcomes_read": False,
            "allowed_for_live_execution": False,
        },
    }
    authority["semantic_sha256"] = BASE.digest(authority)
    BASE.stable_write(output / "source_authority.json", authority)

    contract = {
        "schema_version": 3,
        "campaign": CAMPAIGN,
        "stage": STAGE,
        "source_authority_sha256": authority["semantic_sha256"],
        "market_timezone": BASE.TZ,
        "cas_start_date": BASE.CAS_START.isoformat(),
        "grid_points": args.grid_points,
        "minimum_native_coverage": args.minimum_native_coverage,
        "maximum_staleness_multiple": args.maximum_staleness_multiple,
        "causal_features": list(BASE.CAUSAL),
        "vector_features": list(BASE.VECTOR),
        "policy": {
            "causal_minute_representation": True,
            "whole_session_vectors_post_close_only": True,
            "external_source_read_in_place": True,
            "runtime_inside_worktree_required": False,
            "outcomes_read": False,
            "future_returns_calculated": False,
            "pnl_calculated": False,
            "direction_selected": False,
            "holdout_opened": False,
            "allowed_for_live_execution": False,
        },
    }
    contract["semantic_sha256"] = BASE.digest(contract)
    BASE.stable_write(output / "trajectory_contract.json", contract)

    summary = {
        "principal_verdict": (
            "AUTHORITATIVE_EXTERNAL_INDEX_TRAJECTORY_READY_FOR_OUTCOME_BLIND_CLUSTERING"
            if accepted
            else "NO_AUTHORITATIVE_EXTERNAL_INDEX_SESSION_PASSED_QUALITY_GATES"
        ),
        "source_path": source["path"],
        "source_sha256": source["sha256"],
        "source_storage_mode": source["storage_mode"],
        "instrument": args.index_symbol,
        "source_sessions": selection_diagnostics["selected_sessions"],
        "causal_minute_rows": int(len(causal)),
        "accepted_session_vectors": int(len(accepted)),
        "rejected_sessions": int(len(rejected)),
        "regimes": sorted({item["regime"] for item in accepted}),
        "worktree_source_copy_required": False,
        "outcomes_read": False,
        "allowed_for_live_execution": False,
    }
    summary["semantic_sha256"] = BASE.digest(summary)
    BASE.stable_write(output / "trajectory_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
