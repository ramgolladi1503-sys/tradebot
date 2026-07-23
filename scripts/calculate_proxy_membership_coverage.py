#!/usr/bin/env python3
"""Compute point-in-time constituent coverage for each decision state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.constituent_lead_lag.proxy_weights import validate_normalized_proxy


def calculate(
    states_path: Path,
    bars_path: Path,
    weights_path: Path,
    ticker_resolution: Path,
    output_dir: Path,
    start_date: str,
    end_date: str,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    states = pd.read_parquet(states_path)
    bars = pd.read_parquet(bars_path)
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    weights = validate_normalized_proxy(
        pd.read_csv(weights_path),
        evaluation_start=start_date,
        evaluation_end=end_date,
        allow_community_reconstructed_proxy=True,
    )
    resolution = pd.read_csv(ticker_resolution)
    resolved = set(resolution["proxy_ticker"].astype(str).str.upper())
    day_by_session = {
        str(session): group[["timestamp", "symbol"]].sort_values("timestamp")
        for session, group in bars.groupby("session", sort=False)
    }
    active_by_session: dict[str, pd.DataFrame] = {}
    for session in states["session"].astype(str).unique():
        session_date = pd.Timestamp(session).date()
        effective_to = pd.to_datetime(weights["effective_to"], errors="coerce")
        active_by_session[session] = weights[
            (weights["effective_from"] <= session_date)
            & (
                effective_to.isna()
                | pd.Series(
                    [value.date() >= session_date if pd.notna(value) else False for value in effective_to],
                    index=weights.index,
                )
            )
        ].copy()
    rows = []
    for state in states.itertuples(index=False):
        session = str(state.session)
        cutoff = pd.Timestamp(state.decision_timestamp)
        active = active_by_session[session]
        active_symbols = set(active["constituent_symbol"].astype(str).str.upper())
        resolved_symbols = active_symbols & resolved
        day = day_by_session.get(session, pd.DataFrame(columns=["timestamp", "symbol"]))
        day_bars = day[day["timestamp"] <= cutoff]
        with_bars = set(day_bars["symbol"].astype(str).str.upper()) & resolved_symbols
        missing = sorted(active_symbols - with_bars)
        active_weight = float(active["weight"].sum()) if len(active) else 0.0
        available_weight = float(active.loc[active["constituent_symbol"].isin(with_bars), "weight"].sum()) if len(active) else 0.0
        count_coverage = len(with_bars) / len(active_symbols) if active_symbols else 0.0
        weight_coverage = available_weight / active_weight if active_weight else 0.0
        rows.append({
            "session": session,
            "decision_time": state.decision_time,
            "active_point_in_time_constituents": len(active_symbols),
            "resolved_active_constituents": len(resolved_symbols),
            "active_constituents_with_valid_bars": len(with_bars),
            "count_coverage": count_coverage,
            "active_snapshot_weight": active_weight,
            "available_snapshot_weight": available_weight,
            "weight_coverage": weight_coverage,
            "missing_constituents": missing,
            "passes_count_coverage": count_coverage >= 0.80,
            "passes_weight_coverage": weight_coverage >= 0.80,
        })
    coverage = pd.DataFrame(rows)
    coverage.to_parquet(output_dir / "membership_coverage.parquet", index=False)
    low = coverage[(~coverage["passes_count_coverage"]) | (~coverage["passes_weight_coverage"])]
    low.to_parquet(output_dir / "low_coverage_states.parquet", index=False)
    summary = {
        "states": int(len(coverage)),
        "count_coverage_min": float(coverage["count_coverage"].min()) if len(coverage) else None,
        "count_coverage_median": float(coverage["count_coverage"].median()) if len(coverage) else None,
        "weight_coverage_min": float(coverage["weight_coverage"].min()) if len(coverage) else None,
        "weight_coverage_median": float(coverage["weight_coverage"].median()) if len(coverage) else None,
        "low_count_coverage_states": int((~coverage["passes_count_coverage"]).sum()) if len(coverage) else 0,
        "low_weight_coverage_states": int((~coverage["passes_weight_coverage"]).sum()) if len(coverage) else 0,
        "both_gates_pass_rate": float((coverage["passes_count_coverage"] & coverage["passes_weight_coverage"]).mean()) if len(coverage) else 0.0,
    }
    (output_dir / "membership_coverage_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--ticker-resolution", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2025-08-29")
    args = parser.parse_args()
    print(json.dumps(calculate(args.states, args.bars, args.weights, args.ticker_resolution, args.output_dir, args.start_date, args.end_date), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
