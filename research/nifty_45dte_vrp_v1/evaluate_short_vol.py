#!/usr/bin/env python3
"""Mechanical descriptive replay for NIFTY_45DTE_VRP_V1.

Research only. Requires real executable-side quotes, uses one monthly expiry
position, sells at bid and buys back at ask. A valid 21-DTE management snapshot
is mandatory: profit targets observed after that point can never rescue a trade.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from audit_data import (  # noqa: E402
    _contains_synthetic_source,
    _monthly_expiry_dates,
    _nearest_snapshot_for_day,
    load_frame,
    normalize_frame,
    sha256_file,
)


def _select_leg(snapshot: pd.DataFrame, *, option_type: str, target_abs_delta: float, delta_tolerance: float) -> pd.Series:
    leg = snapshot.loc[snapshot["type"] == option_type].copy()
    if leg.empty:
        raise ValueError(f"ENTRY_LEG_MISSING:{option_type}")
    leg["_delta_distance"] = (leg["delta"].abs() - target_abs_delta).abs()
    leg["_abs_delta"] = leg["delta"].abs()
    leg["_spread"] = leg["ask"] - leg["bid"]
    leg = leg.loc[leg["_delta_distance"] <= delta_tolerance]
    if leg.empty:
        raise ValueError(f"ENTRY_DELTA_NOT_AVAILABLE:{option_type}")
    return leg.sort_values(["_delta_distance", "_abs_delta", "_spread", "strike"]).iloc[0]


def _find_entry(
    exp_df: pd.DataFrame,
    *,
    expiry_date,
    min_dte: int,
    max_dte: int,
    snapshot_ist: str,
    snapshot_tolerance_minutes: int,
    target_abs_delta: float,
    delta_tolerance: float,
) -> dict | None:
    work = exp_df.copy()
    work["trade_date"] = work["timestamp"].dt.date
    for trade_date, day_df in work.groupby("trade_date", sort=True):
        dte = (expiry_date - trade_date).days
        if not min_dte <= dte <= max_dte:
            continue
        snap = _nearest_snapshot_for_day(day_df, target_hhmm=snapshot_ist, tolerance_minutes=snapshot_tolerance_minutes)
        if snap is None:
            continue
        try:
            ce = _select_leg(snap, option_type="CE", target_abs_delta=target_abs_delta, delta_tolerance=delta_tolerance)
            pe = _select_leg(snap, option_type="PE", target_abs_delta=target_abs_delta, delta_tolerance=delta_tolerance)
        except ValueError:
            continue
        return {
            "entry_timestamp": pd.Timestamp(snap["timestamp"].iloc[0]),
            "entry_trade_date": trade_date,
            "entry_dte": int(dte),
            "ce_strike": float(ce["strike"]),
            "pe_strike": float(pe["strike"]),
            "ce_delta": float(ce["delta"]),
            "pe_delta": float(pe["delta"]),
            "ce_bid": float(ce["bid"]),
            "ce_ask": float(ce["ask"]),
            "pe_bid": float(pe["bid"]),
            "pe_ask": float(pe["ask"]),
        }
    return None


def _synchronized_close_path(exp_df: pd.DataFrame, *, entry_timestamp: pd.Timestamp, ce_strike: float, pe_strike: float) -> pd.DataFrame:
    ce = exp_df.loc[
        (exp_df["type"] == "CE") & (exp_df["strike"] == ce_strike) & (exp_df["timestamp"] > entry_timestamp),
        ["timestamp", "ask", "bid", "delta"],
    ].copy()
    pe = exp_df.loc[
        (exp_df["type"] == "PE") & (exp_df["strike"] == pe_strike) & (exp_df["timestamp"] > entry_timestamp),
        ["timestamp", "ask", "bid", "delta"],
    ].copy()
    if ce.empty or pe.empty:
        return pd.DataFrame()
    ce = ce.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    pe = pe.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    path = ce.merge(pe, on="timestamp", how="inner", suffixes=("_ce", "_pe"))
    if path.empty:
        return path
    path["close_debit"] = path["ask_ce"] + path["ask_pe"]
    path["trade_date"] = path["timestamp"].dt.date
    return path.sort_values("timestamp").reset_index(drop=True)


def _time_exit_row(
    path: pd.DataFrame,
    *,
    expiry_date,
    time_exit_dte: int,
    snapshot_ist: str,
    snapshot_tolerance_minutes: int,
) -> pd.Series | None:
    eligible = path.loc[path["trade_date"].map(lambda d: 0 <= (expiry_date - d).days <= time_exit_dte)].copy()
    if eligible.empty:
        return None
    first_date = eligible["trade_date"].min()
    day_df = eligible.loc[eligible["trade_date"] == first_date].copy()
    hh, mm = (int(x) for x in snapshot_ist.split(":"))
    target = pd.Timestamp(year=first_date.year, month=first_date.month, day=first_date.day, hour=hh, minute=mm, tz="Asia/Kolkata")
    day_df["_distance_sec"] = (day_df["timestamp"] - target).abs().dt.total_seconds()
    row = day_df.sort_values(["_distance_sec", "timestamp"]).iloc[0]
    if float(row["_distance_sec"]) > snapshot_tolerance_minutes * 60:
        return None
    return row


def evaluate_expiry(
    exp_df: pd.DataFrame,
    *,
    expiry_date,
    min_dte: int,
    max_dte: int,
    snapshot_ist: str,
    snapshot_tolerance_minutes: int,
    target_abs_delta: float,
    delta_tolerance: float,
    profit_target_fraction: float,
    time_exit_dte: int,
    extra_round_trip_cost_points: float,
) -> dict | None:
    entry = _find_entry(
        exp_df,
        expiry_date=expiry_date,
        min_dte=min_dte,
        max_dte=max_dte,
        snapshot_ist=snapshot_ist,
        snapshot_tolerance_minutes=snapshot_tolerance_minutes,
        target_abs_delta=target_abs_delta,
        delta_tolerance=delta_tolerance,
    )
    if entry is None:
        return None
    initial_credit = float(entry["ce_bid"] + entry["pe_bid"])
    if initial_credit <= 0:
        return None
    path = _synchronized_close_path(
        exp_df,
        entry_timestamp=entry["entry_timestamp"],
        ce_strike=entry["ce_strike"],
        pe_strike=entry["pe_strike"],
    )
    if path.empty:
        return None

    # Fail closed: without an executable snapshot at the frozen management point,
    # this expiry has insufficient path coverage. Never accept a later winner.
    time_row = _time_exit_row(
        path,
        expiry_date=expiry_date,
        time_exit_dte=time_exit_dte,
        snapshot_ist=snapshot_ist,
        snapshot_tolerance_minutes=snapshot_tolerance_minutes,
    )
    if time_row is None:
        return None

    target_debit = initial_credit * (1.0 - profit_target_fraction)
    cutoff = pd.Timestamp(time_row["timestamp"])
    target_hits = path.loc[(path["timestamp"] <= cutoff) & (path["close_debit"] <= target_debit)]
    if not target_hits.empty:
        chosen = target_hits.iloc[0]
        reason = "PROFIT_TARGET"
    else:
        chosen = time_row
        reason = "TIME_EXIT"

    close_debit = float(chosen["close_debit"])
    gross_pnl_points = initial_credit - close_debit
    net_pnl_points = gross_pnl_points - float(extra_round_trip_cost_points)
    observed = path.loc[path["timestamp"] <= chosen["timestamp"]]
    max_close_debit = float(observed["close_debit"].max())
    min_close_debit = float(observed["close_debit"].min())
    return {
        "expiry": str(expiry_date),
        **entry,
        "initial_credit_points": initial_credit,
        "target_close_debit_points": float(target_debit),
        "exit_timestamp": pd.Timestamp(chosen["timestamp"]),
        "exit_trade_date": chosen["trade_date"],
        "exit_dte": int((expiry_date - chosen["trade_date"]).days),
        "exit_reason": reason,
        "close_debit_points": close_debit,
        "gross_pnl_points": float(gross_pnl_points),
        "extra_round_trip_cost_points": float(extra_round_trip_cost_points),
        "net_pnl_points": float(net_pnl_points),
        "gross_pnl_over_credit": float(gross_pnl_points / initial_credit),
        "net_pnl_over_credit": float(net_pnl_points / initial_credit),
        "max_adverse_debit_excursion_points": float(max_close_debit - initial_credit),
        "max_favorable_debit_excursion_points": float(initial_credit - min_close_debit),
        "exit_ce_ask": float(chosen["ask_ce"]),
        "exit_pe_ask": float(chosen["ask_pe"]),
        "exit_ce_delta": float(chosen["delta_ce"]),
        "exit_pe_delta": float(chosen["delta_pe"]),
    }


def _max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return math.nan
    cumulative = values.astype(float).cumsum().to_numpy()
    equity = np.concatenate(([0.0], cumulative))
    peaks = np.maximum.accumulate(equity)
    return float(np.min(equity - peaks))


def _loss_concentration(values: pd.Series, n: int) -> float | None:
    losses = -values[values < 0].sort_values()
    total = float(losses.sum())
    return None if total <= 0 else float(losses.head(n).sum() / total)


def _bootstrap_mean_ci(values: np.ndarray, *, seed: int = 20260824, reps: int = 20000) -> list[float] | None:
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(reps, len(values)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return [float(lo), float(hi)]


def summarize(ledger: pd.DataFrame, *, dataset_sha256: str, config: dict) -> dict:
    governance = {"edge_certified": False, "paper_authorized": False, "live_authorized": False, "order_authority": False, "broker_api_called": False, "holdout_accessed": False}
    if ledger.empty:
        return {"schema_version": "nifty_45dte_vrp_primary_eval_v2", "candidate_id": "NIFTY_45DTE_VRP_V1", "status": "PRIMARY_EVAL_NO_TRADES", "dataset_sha256": dataset_sha256, "config": config, "governance": governance}
    pnl = ledger["net_pnl_points"].astype(float)
    by_year = {}
    for year, grp in ledger.groupby(ledger["entry_timestamp"].dt.year):
        gpnl = grp["net_pnl_points"].astype(float)
        by_year[str(int(year))] = {"trades": int(len(grp)), "mean_net_pnl_points": float(gpnl.mean()), "median_net_pnl_points": float(gpnl.median()), "win_rate": float((gpnl > 0).mean()), "total_net_pnl_points": float(gpnl.sum()), "worst_trade_points": float(gpnl.min())}
    return {
        "schema_version": "nifty_45dte_vrp_primary_eval_v2",
        "candidate_id": "NIFTY_45DTE_VRP_V1",
        "status": "DESCRIPTIVE_PRIMARY_EVAL_COMPLETE" if len(ledger) >= 24 else "DESCRIPTIVE_PRIMARY_EVAL_INSUFFICIENT_SAMPLE",
        "dataset_sha256": dataset_sha256,
        "config": config,
        "sample_count": int(len(ledger)),
        "metrics": {
            "total_net_pnl_points": float(pnl.sum()), "mean_net_pnl_points": float(pnl.mean()), "median_net_pnl_points": float(pnl.median()), "win_rate": float((pnl > 0).mean()),
            "p05_net_pnl_points": float(pnl.quantile(0.05)), "p95_net_pnl_points": float(pnl.quantile(0.95)), "worst_trade_points": float(pnl.min()), "best_trade_points": float(pnl.max()),
            "max_drawdown_points": _max_drawdown(pnl), "worst_1_loss_share": _loss_concentration(pnl, 1), "worst_3_loss_share": _loss_concentration(pnl, 3),
            "bootstrap_95pct_mean_ci_points": _bootstrap_mean_ci(pnl.to_numpy()), "profit_target_hit_rate": float((ledger["exit_reason"] == "PROFIT_TARGET").mean()),
        },
        "exit_reason_counts": {str(k): int(v) for k, v in ledger["exit_reason"].value_counts().items()},
        "by_entry_year": by_year,
        "interpretation_guardrails": ["Positive descriptive P&L is not structural-edge certification.", "Undefined-risk short-vol capital/margin normalization is not supplied by this evaluator.", "Bid/ask is executable-side; statutory charges need separate evidence.", "The direct strategy conflicts with TradeBot BUY_ONLY production policy."],
        "governance": governance,
    }


def run(dataset: Path, *, output_dir: Path, expected_sha256: str | None, assume_ist: bool, min_dte: int, max_dte: int, snapshot_ist: str, snapshot_tolerance_minutes: int, target_abs_delta: float, delta_tolerance: float, profit_target_fraction: float, time_exit_dte: int, extra_round_trip_cost_points: float) -> dict:
    dataset_sha = sha256_file(dataset)
    if expected_sha256 and dataset_sha != expected_sha256:
        raise ValueError("DATASET_SHA256_MISMATCH")
    raw = load_frame(dataset)
    hits = _contains_synthetic_source(raw)
    if hits:
        raise ValueError("SYNTHETIC_SOURCE_REJECTED:" + ",".join(hits))
    df = normalize_frame(raw, assume_ist=assume_ist)
    monthly, monthly_method = _monthly_expiry_dates(df)
    config = {"entry_dte_window": [min_dte, max_dte], "expiry_cycle": "MONTHLY", "monthly_expiry_identification": monthly_method, "snapshot_ist": snapshot_ist, "snapshot_tolerance_minutes": snapshot_tolerance_minutes, "target_abs_delta": target_abs_delta, "delta_tolerance": delta_tolerance, "profit_target_fraction_initial_credit": profit_target_fraction, "time_exit_dte": time_exit_dte, "entry_execution": "SELL_AT_BID", "exit_execution": "BUY_TO_CLOSE_AT_ASK", "extra_round_trip_cost_points": extra_round_trip_cost_points}
    rows = []
    for expiry_date, exp_df in df.groupby("expiry_date", sort=True):
        if expiry_date not in monthly:
            continue
        row = evaluate_expiry(exp_df, expiry_date=expiry_date, min_dte=min_dte, max_dte=max_dte, snapshot_ist=snapshot_ist, snapshot_tolerance_minutes=snapshot_tolerance_minutes, target_abs_delta=target_abs_delta, delta_tolerance=delta_tolerance, profit_target_fraction=profit_target_fraction, time_exit_dte=time_exit_dte, extra_round_trip_cost_points=extra_round_trip_cost_points)
        if row is not None:
            rows.append(row)
    ledger = pd.DataFrame(rows)
    if not ledger.empty:
        for col in ("entry_timestamp", "exit_timestamp"):
            ledger[col] = pd.to_datetime(ledger[col])
        ledger = ledger.sort_values("entry_timestamp").reset_index(drop=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "trade_ledger.csv"
    summary_path = output_dir / "primary_eval_summary.json"
    ledger.to_csv(ledger_path, index=False)
    summary = summarize(ledger, dataset_sha256=dataset_sha, config=config)
    summary["artifacts"] = {"trade_ledger": str(ledger_path), "summary": str(summary_path)}
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("dataset", type=Path); p.add_argument("--output-dir", type=Path, required=True); p.add_argument("--expected-sha256"); p.add_argument("--assume-ist", action="store_true")
    p.add_argument("--min-dte", type=int, default=42); p.add_argument("--max-dte", type=int, default=48); p.add_argument("--snapshot-ist", default="15:00"); p.add_argument("--snapshot-tolerance-minutes", type=int, default=15)
    p.add_argument("--target-delta", type=float, default=0.16); p.add_argument("--delta-tolerance", type=float, default=0.03); p.add_argument("--profit-target", type=float, default=0.50); p.add_argument("--time-exit-dte", type=int, default=21); p.add_argument("--extra-round-trip-cost-points", type=float, default=0.0)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run(args.dataset, output_dir=args.output_dir, expected_sha256=args.expected_sha256, assume_ist=args.assume_ist, min_dte=args.min_dte, max_dte=args.max_dte, snapshot_ist=args.snapshot_ist, snapshot_tolerance_minutes=args.snapshot_tolerance_minutes, target_abs_delta=args.target_delta, delta_tolerance=args.delta_tolerance, profit_target_fraction=args.profit_target, time_exit_dte=args.time_exit_dte, extra_round_trip_cost_points=args.extra_round_trip_cost_points)
        print(json.dumps(result, indent=2, sort_keys=True)); return 0
    except Exception as exc:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        result = {"schema_version": "nifty_45dte_vrp_primary_eval_v2", "candidate_id": "NIFTY_45DTE_VRP_V1", "status": "PRIMARY_EVAL_FAILED", "error": f"{type(exc).__name__}:{exc}", "governance": {"edge_certified": False, "paper_authorized": False, "live_authorized": False, "order_authority": False, "broker_api_called": False, "holdout_accessed": False}}
        (args.output_dir / "primary_eval_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
