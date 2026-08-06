#!/usr/bin/env python3
"""Build the authoritative continuous-index trajectory for Pattern Atlas V1.

This corrected lane selects one pinned physical source and one continuous index
symbol before constructing trajectories. It uses native-cadence-aware quality
gates while retaining the causal one-minute feature representation.

No future return, outcome label, trade direction, entry, exit, stop, target,
P&L, validation outcome, or holdout outcome is read or calculated.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE_PATH = Path(__file__).with_name("run_observation_first_pattern_atlas_trajectory_v1.py")
SPEC = importlib.util.spec_from_file_location("pattern_atlas_trajectory_base_v1", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load base trajectory module: {BASE_PATH}")
BASE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BASE
SPEC.loader.exec_module(BASE)

CAMPAIGN = "observation_first_pattern_atlas_v1"
STAGE = "authoritative_continuous_index_trajectory_v2"
DEFAULT_NIFTY_SOURCE_SHA256 = "ae9645a83cb555899145e04ebe5a961fd130df25cba88a8fc8fd43b986bbfad0"


def select_authoritative_source(
    inventory: dict[str, Any],
    expected_sha256: str,
    expected_basename: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in inventory.get("files", [])
        if item.get("sha256") == expected_sha256
        and Path(str(item.get("path", ""))).name == expected_basename
        and not item.get("schema_error")
    ]
    if len(matches) != 1:
        raise ValueError(
            "Expected exactly one authoritative source "
            f"for sha={expected_sha256} basename={expected_basename}; found={len(matches)}"
        )
    source = matches[0]
    forbidden = list(source.get("outcome_like_columns") or [])
    if forbidden:
        raise ValueError(f"Authoritative source contains outcome-like columns: {forbidden}")
    return source


def select_exact_index_rows(
    frame: pd.DataFrame,
    symbol: str,
    minimum_sessions: int,
    minimum_median_price: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    instrument_column = BASE.first(frame.columns, BASE.INSTRUMENT)
    session_column = BASE.first(frame.columns, BASE.SESSION)
    price_column = BASE.first(frame.columns, BASE.PRICE)
    if instrument_column is None or price_column is None:
        raise ValueError("Authoritative source lacks instrument or price column")

    normalized = frame[instrument_column].astype(str).str.strip().str.upper()
    selected = frame.loc[normalized.eq(symbol.strip().upper())].copy()
    if selected.empty:
        examples = sorted(normalized.dropna().unique().tolist())[:25]
        raise ValueError(f"Exact index symbol {symbol!r} not found; examples={examples}")

    prices = pd.to_numeric(selected[price_column], errors="coerce")
    median_price = float(prices.median())
    if session_column:
        session_count = int(pd.Series(selected[session_column]).astype(str).nunique())
        first_session = str(pd.Series(selected[session_column]).astype(str).min())
        last_session = str(pd.Series(selected[session_column]).astype(str).max())
    else:
        timestamp_column = BASE.first(frame.columns, BASE.TS)
        if timestamp_column is None:
            raise ValueError("No session or timestamp column for coverage audit")
        dates = BASE.normalize_timestamps(selected[timestamp_column]).dt.date
        session_count = int(dates.nunique())
        first_session = str(dates.min())
        last_session = str(dates.max())

    if session_count < minimum_sessions:
        raise ValueError(
            f"Continuous index source has only {session_count} sessions; "
            f"minimum required is {minimum_sessions}"
        )
    if not math.isfinite(median_price) or median_price < minimum_median_price:
        raise ValueError(
            f"Median index price {median_price} is below authority floor {minimum_median_price}"
        )

    diagnostics = {
        "selected_symbol": symbol,
        "selected_rows": int(len(selected)),
        "selected_sessions": session_count,
        "first_session": first_session,
        "last_session": last_session,
        "median_price": median_price,
        "instrument_column": instrument_column,
        "session_column": session_column,
        "price_column": price_column,
    }
    return selected, diagnostics


def infer_native_cadence(clean: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for (instrument, session_date), group in clean.groupby(
        ["instrument", "session_date"], sort=True
    ):
        timestamps = (
            pd.to_datetime(group["timestamp"], errors="coerce")
            .dropna()
            .sort_values()
            .drop_duplicates()
        )
        deltas = timestamps.diff().dt.total_seconds().div(60.0)
        finite = deltas[(deltas > 0) & np.isfinite(deltas)]
        if finite.empty:
            cadence = np.nan
        else:
            cadence = float(finite.median())
        records.append(
            {
                "instrument": str(instrument),
                "session_date": session_date,
                "native_cadence_minutes": cadence,
                "source_observations": int(len(timestamps)),
            }
        )
    return pd.DataFrame(records)


def cadence_quality_metrics(group: pd.DataFrame) -> dict[str, float]:
    cadence_values = pd.to_numeric(
        group["native_cadence_minutes"], errors="coerce"
    ).dropna()
    if cadence_values.empty:
        cadence = float("nan")
    else:
        cadence = float(cadence_values.median())

    observed_minute_share = float(group["observed_this_minute"].mean())
    max_minutes_since_observation = float(group["minutes_since_observation"].max())
    if math.isfinite(cadence) and cadence > 0:
        native_coverage = min(1.0, observed_minute_share * cadence)
        staleness_multiple = max_minutes_since_observation / cadence
    else:
        native_coverage = 0.0
        staleness_multiple = float("inf")

    return {
        "native_cadence_minutes": cadence,
        "observed_minute_share": observed_minute_share,
        "native_bar_coverage": native_coverage,
        "max_minutes_since_observation": max_minutes_since_observation,
        "staleness_multiple": staleness_multiple,
    }


def build_cadence_aware_vectors(
    frame: pd.DataFrame,
    points: int,
    minimum_native_coverage: float,
    maximum_staleness_multiple: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for (instrument, session_date), group in frame.groupby(
        ["instrument", "session_date"], sort=True
    ):
        metrics = cadence_quality_metrics(group)
        first_progress = float(group["session_progress"].min())
        last_progress = float(group["session_progress"].max())
        reasons: list[str] = []
        cadence = metrics["native_cadence_minutes"]

        if not math.isfinite(cadence) or not 1.0 <= cadence <= 15.0:
            reasons.append("unsupported_native_cadence")
        if metrics["native_bar_coverage"] < minimum_native_coverage:
            reasons.append("native_bar_coverage_below_threshold")
        if metrics["staleness_multiple"] > maximum_staleness_multiple:
            reasons.append("native_gap_exceeds_threshold")
        if first_progress > 0.02:
            reasons.append("session_start_missing")
        if last_progress < 0.98:
            reasons.append("session_end_missing")

        evidence = {
            "instrument": str(instrument),
            "session_date": str(session_date),
            "regime": BASE.regime(session_date),
            **metrics,
            "first_progress": first_progress,
            "last_progress": last_progress,
        }
        if reasons:
            rejected.append({**evidence, "reasons": reasons})
        else:
            payload = BASE.vector(group, points)
            payload["quality"] = evidence
            payload["semantic_sha256"] = BASE.digest(payload)
            accepted.append(payload)
    return accepted, rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--inventory-json",
        type=Path,
        default=Path(
            "runtime/research/observation_first_pattern_atlas_v1/"
            "inventory/corpus_inventory_deduplicated.json"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            "runtime/research/observation_first_pattern_atlas_v1/"
            "index_trajectory_v2"
        ),
    )
    parser.add_argument("--source-sha256", default=DEFAULT_NIFTY_SOURCE_SHA256)
    parser.add_argument("--source-basename", default="constituent_index_5m.parquet")
    parser.add_argument("--index-symbol", default="NIFTY")
    parser.add_argument("--minimum-source-sessions", type=int, default=120)
    parser.add_argument("--minimum-median-price", type=float, default=10000.0)
    parser.add_argument("--grid-points", type=int, default=96)
    parser.add_argument("--minimum-native-coverage", type=float, default=0.90)
    parser.add_argument("--maximum-staleness-multiple", type=float, default=1.25)
    parser.add_argument("--naive-timezone", default=BASE.TZ)
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    inventory_path = (
        args.inventory_json
        if args.inventory_json.is_absolute()
        else repo / args.inventory_json
    )
    output = (
        args.output_root if args.output_root.is_absolute() else repo / args.output_root
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    source = select_authoritative_source(
        inventory,
        args.source_sha256,
        args.source_basename,
    )
    selected_columns = BASE.allowed_columns("constituent", source.get("columns", []))
    if BASE.first(selected_columns, BASE.TS) is None:
        raise ValueError("Authoritative source has no allowed timestamp column")
    if BASE.first(selected_columns, BASE.PRICE) is None:
        raise ValueError("Authoritative source has no allowed price column")

    raw = BASE.read_parquet(repo / source["path"], selected_columns)
    index_raw, selection_diagnostics = select_exact_index_rows(
        raw,
        args.index_symbol,
        args.minimum_source_sessions,
        args.minimum_median_price,
    )
    clean = BASE.canonicalize(
        index_raw,
        source["path"],
        "constituent",
        args.naive_timezone,
    )
    clean["instrument"] = args.index_symbol

    cadence = infer_native_cadence(clean)
    minute = BASE.resample_minutes(clean).merge(
        cadence,
        on=["instrument", "session_date"],
        how="left",
        validate="many_to_one",
    )
    causal = BASE.add_causal_features(minute)
    accepted, rejected = build_cadence_aware_vectors(
        causal,
        args.grid_points,
        args.minimum_native_coverage,
        args.maximum_staleness_multiple,
    )

    output.mkdir(parents=True, exist_ok=True)
    causal.to_parquet(output / "causal_minute_trajectory.parquet", index=False)
    BASE.stable_write(output / "completed_session_vectors.json", {"sessions": accepted})
    BASE.stable_write(output / "rejected_sessions.json", {"sessions": rejected})

    authority = {
        "campaign": CAMPAIGN,
        "stage": STAGE,
        "source_path": source["path"],
        "source_sha256": source["sha256"],
        "source_rows": source.get("rows"),
        "source_timestamp_min": source.get("min_timestamp_metadata"),
        "source_timestamp_max": source.get("max_timestamp_metadata"),
        "index_symbol": args.index_symbol,
        "selection": selection_diagnostics,
        "policy": {
            "exact_physical_sha_required": True,
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
        "schema_version": 2,
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
            "AUTHORITATIVE_INDEX_TRAJECTORY_READY_FOR_OUTCOME_BLIND_CLUSTERING"
            if accepted
            else "NO_AUTHORITATIVE_INDEX_SESSION_PASSED_QUALITY_GATES"
        ),
        "source_path": source["path"],
        "source_sha256": source["sha256"],
        "instrument": args.index_symbol,
        "source_sessions": selection_diagnostics["selected_sessions"],
        "causal_minute_rows": int(len(causal)),
        "accepted_session_vectors": int(len(accepted)),
        "rejected_sessions": int(len(rejected)),
        "regimes": sorted({item["regime"] for item in accepted}),
        "outcomes_read": False,
        "allowed_for_live_execution": False,
    }
    summary["semantic_sha256"] = BASE.digest(summary)
    BASE.stable_write(output / "trajectory_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
