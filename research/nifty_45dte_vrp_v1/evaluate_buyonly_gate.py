#!/usr/bin/env python3
"""Evaluate the frozen 45-DTE VRP context gate on a BUY-only baseline.

Backward as-of joins guarantee state_timestamp <= entry_timestamp. This module
cannot create/reverse trades or authorize paper/live execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"UNSUPPORTED_TABLE_FORMAT:{path.suffix.lower()}")


def _to_ist(series: pd.Series, *, assume_ist: bool, field: str) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise ValueError(f"{field.upper()}_PARSE_FAILED")
    if getattr(ts.dt, "tz", None) is None:
        if not assume_ist:
            raise ValueError(f"NAIVE_{field.upper()}_REQUIRES_EXPLICIT_ASSUME_IST")
        return ts.dt.tz_localize("Asia/Kolkata", ambiguous="raise", nonexistent="raise")
    return ts.dt.tz_convert("Asia/Kolkata")


def _max_drawdown(values: pd.Series) -> float | None:
    if values.empty:
        return None
    cumulative = values.astype(float).cumsum().to_numpy()
    equity = np.concatenate(([0.0], cumulative))
    peaks = np.maximum.accumulate(equity)
    return float(np.min(equity - peaks))


def _metrics(df: pd.DataFrame, *, pnl_column: str) -> dict:
    if df.empty:
        return {"trades": 0, "mean": None, "median": None, "win_rate": None, "p05": None, "total": None, "max_drawdown": None}
    pnl = df[pnl_column].astype(float)
    return {
        "trades": int(len(df)),
        "mean": float(pnl.mean()),
        "median": float(pnl.median()),
        "win_rate": float((pnl > 0).mean()),
        "p05": float(pnl.quantile(0.05)),
        "total": float(pnl.sum()),
        "max_drawdown": _max_drawdown(pnl),
    }


def _bootstrap_incremental_mean(available: pd.DataFrame, *, pnl_column: str, gate_column: str, reps: int = 20000, seed: int = 20260824) -> list[float] | None:
    if len(available) < 2 or int(available[gate_column].sum()) < 2:
        return None
    pnl = available[pnl_column].astype(float).to_numpy()
    gate = available[gate_column].astype(bool).to_numpy()
    rng = np.random.default_rng(seed)
    diffs: list[float] = []
    n = len(available)
    for _ in range(reps):
        idx = rng.integers(0, n, size=n)
        sampled_gate = gate[idx]
        if sampled_gate.any():
            sampled_pnl = pnl[idx]
            diffs.append(float(sampled_pnl[sampled_gate].mean() - sampled_pnl.mean()))
    if len(diffs) < max(100, reps // 10):
        return None
    lo, hi = np.quantile(np.asarray(diffs), [0.025, 0.975])
    return [float(lo), float(hi)]


def evaluate(
    baseline: pd.DataFrame,
    states: pd.DataFrame,
    *,
    entry_timestamp_column: str,
    pnl_column: str,
    assume_ist_baseline: bool,
    assume_ist_states: bool,
) -> tuple[pd.DataFrame, dict]:
    if entry_timestamp_column not in baseline.columns:
        raise ValueError(f"BASELINE_ENTRY_COLUMN_MISSING:{entry_timestamp_column}")
    if pnl_column not in baseline.columns:
        raise ValueError(f"BASELINE_PNL_COLUMN_MISSING:{pnl_column}")
    missing = sorted({"state_timestamp", "vrp_zscore", "primary_gate_admit"} - set(states.columns))
    if missing:
        raise ValueError("STATE_COLUMNS_MISSING:" + ",".join(missing))

    b = baseline.copy()
    b[entry_timestamp_column] = _to_ist(b[entry_timestamp_column], assume_ist=assume_ist_baseline, field="baseline_entry_timestamp")
    b[pnl_column] = pd.to_numeric(b[pnl_column], errors="coerce")
    if b[pnl_column].isna().any():
        raise ValueError("BASELINE_PNL_NON_NUMERIC")
    b = b.sort_values(entry_timestamp_column).reset_index(drop=False).rename(columns={"index": "_original_order"})

    s = states.copy()
    s["state_timestamp"] = _to_ist(s["state_timestamp"], assume_ist=assume_ist_states, field="state_timestamp")
    s["vrp_zscore"] = pd.to_numeric(s["vrp_zscore"], errors="coerce")
    if s["primary_gate_admit"].dtype != bool:
        s["primary_gate_admit"] = s["primary_gate_admit"].astype(str).str.strip().str.lower().map({"true": True, "false": False})
    if s["primary_gate_admit"].isna().any():
        raise ValueError("STATE_GATE_BOOLEAN_INVALID")
    s = s.sort_values("state_timestamp").drop_duplicates("state_timestamp", keep="last")

    joined = pd.merge_asof(
        b,
        s[["state_timestamp", "vrp_zscore", "primary_gate_admit"]],
        left_on=entry_timestamp_column,
        right_on="state_timestamp",
        direction="backward",
        allow_exact_matches=True,
    )
    bad = joined.loc[joined["state_timestamp"].notna() & (joined["state_timestamp"] > joined[entry_timestamp_column])]
    if not bad.empty:
        raise ValueError("ASOF_JOIN_LOOKAHEAD_DETECTED")
    joined["vrp_state_available"] = joined["state_timestamp"].notna() & joined["vrp_zscore"].notna()
    joined["vrp_gate_admit"] = joined["vrp_state_available"] & joined["primary_gate_admit"].fillna(False)

    available = joined.loc[joined["vrp_state_available"]].copy()
    gated = available.loc[available["vrp_gate_admit"]].copy()
    base_metrics = _metrics(available, pnl_column=pnl_column)
    gated_metrics = _metrics(gated, pnl_column=pnl_column)
    incremental = None if base_metrics["mean"] is None or gated_metrics["mean"] is None else float(gated_metrics["mean"] - base_metrics["mean"])
    coverage = None if available.empty else float(len(gated) / len(available))

    by_year: dict[str, dict] = {}
    for year, grp in available.groupby(available[entry_timestamp_column].dt.year) if not available.empty else []:
        gated_grp = grp.loc[grp["vrp_gate_admit"]]
        bm = _metrics(grp, pnl_column=pnl_column); gm = _metrics(gated_grp, pnl_column=pnl_column)
        by_year[str(int(year))] = {
            "available_baseline": bm,
            "gated": gm,
            "coverage_retained": float(len(gated_grp) / len(grp)),
            "incremental_mean": None if bm["mean"] is None or gm["mean"] is None else float(gm["mean"] - bm["mean"]),
        }
    return joined, {
        "state_available_baseline": base_metrics,
        "primary_gated": gated_metrics,
        "incremental_mean": incremental,
        "coverage_retained": coverage,
        "bootstrap_95pct_incremental_mean_ci": _bootstrap_incremental_mean(available, pnl_column=pnl_column, gate_column="vrp_gate_admit"),
        "by_entry_year": by_year,
        "total_input_trades": int(len(joined)),
        "trades_without_usable_prior_state": int((~joined["vrp_state_available"]).sum()),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("baseline", type=Path); p.add_argument("states", type=Path); p.add_argument("--output-dir", type=Path, required=True); p.add_argument("--baseline-candidate-sha", required=True)
    p.add_argument("--expected-baseline-sha256"); p.add_argument("--expected-states-sha256"); p.add_argument("--entry-timestamp-column", default="entry_timestamp"); p.add_argument("--pnl-column", default="net_pnl")
    p.add_argument("--assume-ist-baseline", action="store_true"); p.add_argument("--assume-ist-states", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "buyonly_gate_summary.json"; joined_path = args.output_dir / "buyonly_gate_joined_ledger.csv"
    governance = {"edge_certified": False, "broker_api_called": False, "order_authority": False, "paper_authorized": False, "live_authorized": False, "holdout_accessed": False}
    try:
        if not GIT_SHA_RE.fullmatch(args.baseline_candidate_sha):
            raise ValueError("EXACT_BASELINE_CANDIDATE_SHA_REQUIRED")
        baseline_sha = sha256_file(args.baseline); states_sha = sha256_file(args.states)
        if args.expected_baseline_sha256 and baseline_sha != args.expected_baseline_sha256:
            raise ValueError("BASELINE_SHA256_MISMATCH")
        if args.expected_states_sha256 and states_sha != args.expected_states_sha256:
            raise ValueError("STATES_SHA256_MISMATCH")
        joined, metrics = evaluate(load_table(args.baseline), load_table(args.states), entry_timestamp_column=args.entry_timestamp_column, pnl_column=args.pnl_column, assume_ist_baseline=args.assume_ist_baseline, assume_ist_states=args.assume_ist_states)
        joined.to_csv(joined_path, index=False)
        result = {"schema_version": "nifty_45dte_vrp_buyonly_gate_eval_v2", "candidate_id": "NIFTY_45DTE_VRP_TRANSLATOR_BUYONLY_V1", "status": "DESCRIPTIVE_GATE_EVAL_COMPLETE", "baseline_candidate_sha": args.baseline_candidate_sha, "baseline_file_sha256": baseline_sha, "states_file_sha256": states_sha, "entry_timestamp_column": args.entry_timestamp_column, "pnl_column": args.pnl_column, "primary_rule": "admit baseline trade iff latest available vrp_zscore <= 0", "availability_rule": "state_timestamp <= entry_timestamp via backward as-of join", "metrics": metrics, "artifacts": {"joined_ledger": str(joined_path), "summary": str(summary_path)}, "governance": governance}
    except Exception as exc:
        result = {"schema_version": "nifty_45dte_vrp_buyonly_gate_eval_v2", "candidate_id": "NIFTY_45DTE_VRP_TRANSLATOR_BUYONLY_V1", "status": "GATE_EVAL_FAILED", "error": f"{type(exc).__name__}:{exc}", "governance": governance}
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result["status"] == "DESCRIPTIVE_GATE_EVAL_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
