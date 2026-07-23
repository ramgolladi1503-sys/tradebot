#!/usr/bin/env python3
"""Compute exact-bar point-in-time constituent coverage for each decision state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.constituent_lead_lag.bar_grid import symbols_with_exact_window
from research.constituent_lead_lag.proxy_weights import validate_normalized_proxy


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported table type: {path}")


def calculate_frame(states: pd.DataFrame, bars: pd.DataFrame, weights: pd.DataFrame,
                    resolution: pd.DataFrame, start_date: str, end_date: str) -> tuple[pd.DataFrame, dict[str, object]]:
    states = states.copy()
    bars = bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars["symbol"] = bars["symbol"].astype(str).str.upper()
    weights = validate_normalized_proxy(
        weights,
        evaluation_start=start_date,
        evaluation_end=end_date,
        allow_community_reconstructed_proxy=True,
    )
    resolved = set(resolution["proxy_ticker"].astype(str).str.upper())
    day_by_session = {
        str(session): {symbol: group.sort_values("timestamp") for symbol, group in day.groupby("symbol", sort=False)}
        for session, day in bars.groupby("session", sort=False)
    }
    rows: list[dict[str, object]] = []
    for state in states.itertuples(index=False):
        session = str(state.session)
        session_date = pd.Timestamp(session).date()
        active_to = weights["effective_to"].apply(
            lambda value: pd.isna(value) or pd.Timestamp(value).date() >= session_date
        )
        active = weights[
            (weights["effective_from"] <= session_date)
            & active_to
        ].copy()
        active_symbols = set(active["constituent_symbol"].astype(str).str.upper())
        resolved_symbols = active_symbols & resolved
        cutoff = pd.Timestamp(state.decision_timestamp)
        exact, missing_by_symbol = symbols_with_exact_window(day_by_session.get(session, {}), sorted(resolved_symbols), cutoff)
        with_bars = set(exact)
        unresolved = sorted(active_symbols - resolved_symbols)
        stale_or_missing = sorted(resolved_symbols - with_bars)
        active_weight = float(active["weight"].sum()) if len(active) else 0.0
        available_weight = float(active.loc[active["constituent_symbol"].isin(with_bars), "weight"].sum()) if len(active) else 0.0
        count_coverage = len(with_bars) / len(active_symbols) if active_symbols else 0.0
        weight_coverage = available_weight / active_weight if active_weight else 0.0
        state_count = float(getattr(state, "count_coverage", count_coverage))
        state_weight = float(getattr(state, "weight_coverage", weight_coverage))
        rows.append({
            "session": session,
            "decision_time": str(state.decision_time),
            "decision_timestamp": str(state.decision_timestamp),
            "active_point_in_time_constituents": len(active_symbols),
            "resolved_active_constituents": len(resolved_symbols),
            "exact_bar_valid_constituents": len(with_bars),
            "count_coverage": count_coverage,
            "active_snapshot_weight": active_weight,
            "available_snapshot_weight": available_weight,
            "weight_coverage": weight_coverage,
            "unresolved_constituents": unresolved,
            "stale_or_missing_constituents": stale_or_missing,
            "missing_timestamps_by_constituent": json.dumps({k: list(v) for k, v in sorted(missing_by_symbol.items())}, sort_keys=True),
            "passes_count_coverage": count_coverage >= 0.80,
            "passes_weight_coverage": weight_coverage >= 0.80,
            "state_count_coverage_matches": abs(state_count - count_coverage) <= 1e-12,
            "state_weight_coverage_matches": abs(state_weight - weight_coverage) <= 1e-12,
        })
    coverage = pd.DataFrame(rows)
    both = coverage["passes_count_coverage"] & coverage["passes_weight_coverage"] if len(coverage) else pd.Series(dtype=bool)
    summary = {
        "states": int(len(coverage)),
        "count_coverage_min": float(coverage["count_coverage"].min()) if len(coverage) else None,
        "count_coverage_median": float(coverage["count_coverage"].median()) if len(coverage) else None,
        "weight_coverage_min": float(coverage["weight_coverage"].min()) if len(coverage) else None,
        "weight_coverage_median": float(coverage["weight_coverage"].median()) if len(coverage) else None,
        "low_count_coverage_states": int((~coverage["passes_count_coverage"]).sum()) if len(coverage) else 0,
        "low_weight_coverage_states": int((~coverage["passes_weight_coverage"]).sum()) if len(coverage) else 0,
        "both_gates_pass_rate": float(both.mean()) if len(coverage) else 0.0,
        "state_count_coverage_mismatches": int((~coverage["state_count_coverage_matches"]).sum()) if len(coverage) else 0,
        "state_weight_coverage_mismatches": int((~coverage["state_weight_coverage_matches"]).sum()) if len(coverage) else 0,
        "coverage_contract": "exact_T_Tminus5_Tminus10_v1",
    }
    return coverage, summary


def calculate(states_path: Path, bars_path: Path, weights_path: Path, ticker_resolution: Path,
              output_dir: Path, start_date: str, end_date: str) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage, summary = calculate_frame(
        read_table(states_path), read_table(bars_path), read_table(weights_path),
        read_table(ticker_resolution), start_date, end_date,
    )
    coverage.to_parquet(output_dir / "membership_coverage.parquet", index=False)
    coverage[(~coverage["passes_count_coverage"]) | (~coverage["passes_weight_coverage"])].to_parquet(
        output_dir / "low_coverage_states.parquet", index=False
    )
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
