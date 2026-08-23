#!/usr/bin/env python3
"""Fail-closed data-capability audit for NIFTY_45DTE_VRP_V1.

This module does not call brokers, networks, or order APIs. It only inspects a
local CSV/Parquet historical option dataset and emits a JSON readiness artifact.
Synthetic/"realish" option chains are never accepted for edge certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

REQUIRED_COLUMNS = {
    "timestamp",
    "expiry",
    "strike",
    "type",
    "bid",
    "ask",
    "delta",
}
SYNTHETIC_MARKERS = ("synthetic", "realish", "simulated", "mock", "fixture")
SOURCE_COLUMNS = ("chain_source", "quote_source", "price_source", "option_ltp_source")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"UNSUPPORTED_DATASET_FORMAT:{suffix}")


def _contains_synthetic_source(df: pd.DataFrame) -> list[str]:
    hits: list[str] = []
    for col in SOURCE_COLUMNS:
        if col not in df.columns:
            continue
        values = df[col].dropna().astype(str).str.lower()
        for marker in SYNTHETIC_MARKERS:
            if values.str.contains(marker, regex=False).any():
                hits.append(f"{col}:{marker}")
    return sorted(set(hits))


def normalize_frame(df: pd.DataFrame, *, assume_ist: bool) -> pd.DataFrame:
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"MISSING_REQUIRED_COLUMNS:{','.join(missing)}")

    out = df.copy()
    ts = pd.to_datetime(out["timestamp"], errors="coerce")
    if ts.isna().any():
        raise ValueError("TIMESTAMP_PARSE_FAILED")
    if getattr(ts.dt, "tz", None) is None:
        if not assume_ist:
            raise ValueError("NAIVE_TIMESTAMP_REQUIRES_EXPLICIT_ASSUME_IST")
        ts = ts.dt.tz_localize("Asia/Kolkata", ambiguous="raise", nonexistent="raise")
    else:
        ts = ts.dt.tz_convert("Asia/Kolkata")
    out["timestamp"] = ts

    expiry = pd.to_datetime(out["expiry"], errors="coerce")
    if expiry.isna().any():
        raise ValueError("EXPIRY_PARSE_FAILED")
    out["expiry_date"] = expiry.dt.date

    out["type"] = out["type"].astype(str).str.upper().replace({"CALL": "CE", "PUT": "PE"})
    if not out["type"].isin({"CE", "PE"}).all():
        raise ValueError("UNSUPPORTED_OPTION_TYPE")

    for col in ("strike", "bid", "ask", "delta"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
        if out[col].isna().any():
            raise ValueError(f"NON_NUMERIC_REQUIRED_FIELD:{col}")

    if (out["bid"] <= 0).any() or (out["ask"] <= 0).any():
        raise ValueError("NON_POSITIVE_QUOTES")
    if (out["ask"] < out["bid"]).any():
        raise ValueError("CROSSED_QUOTES")
    if not out.loc[out["type"] == "CE", "delta"].between(0.0, 1.0).all():
        raise ValueError("INVALID_CALL_DELTA")
    if not out.loc[out["type"] == "PE", "delta"].between(-1.0, 0.0).all():
        raise ValueError("INVALID_PUT_DELTA")

    if "symbol" in out.columns:
        symbols = set(out["symbol"].dropna().astype(str).str.upper().unique())
        if symbols and symbols != {"NIFTY"}:
            raise ValueError(f"NON_NIFTY_SYMBOLS_PRESENT:{sorted(symbols)}")

    return out.sort_values(["expiry_date", "timestamp", "strike", "type"]).reset_index(drop=True)


def _nearest_snapshot_for_day(
    day_df: pd.DataFrame,
    *,
    target_hhmm: str,
    tolerance_minutes: int,
) -> pd.DataFrame | None:
    if day_df.empty:
        return None
    hh, mm = (int(x) for x in target_hhmm.split(":"))
    day = day_df["timestamp"].iloc[0].date()
    target = pd.Timestamp(
        year=day.year,
        month=day.month,
        day=day.day,
        hour=hh,
        minute=mm,
        tz="Asia/Kolkata",
    )
    unique_ts = pd.Index(day_df["timestamp"].drop_duplicates())
    if unique_ts.empty:
        return None
    distances = pd.Series([abs((x - target).total_seconds()) for x in unique_ts], index=unique_ts)
    best_ts = distances.idxmin()
    if distances.loc[best_ts] > tolerance_minutes * 60:
        return None
    return day_df.loc[day_df["timestamp"] == best_ts].copy()


def _has_delta_pair(snapshot: pd.DataFrame, target_delta: float, tolerance: float) -> bool:
    ce = snapshot[snapshot["type"] == "CE"]
    pe = snapshot[snapshot["type"] == "PE"]
    if ce.empty or pe.empty:
        return False
    ce_dist = (ce["delta"].abs() - target_delta).abs().min()
    pe_dist = (pe["delta"].abs() - target_delta).abs().min()
    return bool(ce_dist <= tolerance and pe_dist <= tolerance)


def eligible_expiries(
    df: pd.DataFrame,
    *,
    min_dte: int,
    max_dte: int,
    target_delta: float,
    delta_tolerance: float,
    snapshot_ist: str,
    snapshot_tolerance_minutes: int,
) -> list[dict]:
    results: list[dict] = []
    for expiry_date, exp_df in df.groupby("expiry_date", sort=True):
        work = exp_df.copy()
        work["trade_date"] = work["timestamp"].dt.date
        found = None
        for trade_date, day_df in work.groupby("trade_date", sort=True):
            dte = (expiry_date - trade_date).days
            if dte < min_dte or dte > max_dte:
                continue
            snap = _nearest_snapshot_for_day(
                day_df,
                target_hhmm=snapshot_ist,
                tolerance_minutes=snapshot_tolerance_minutes,
            )
            if snap is None or not _has_delta_pair(snap, target_delta, delta_tolerance):
                continue
            exit_cover = work[
                work["trade_date"].map(lambda d: (expiry_date - d).days <= 21)
                & work["trade_date"].map(lambda d: (expiry_date - d).days >= 0)
            ]
            found = {
                "expiry": str(expiry_date),
                "entry_trade_date": str(trade_date),
                "entry_dte": int(dte),
                "entry_snapshot": snap["timestamp"].iloc[0].isoformat(),
                "has_21dte_or_later_quotes": bool(not exit_cover.empty),
            }
            break
        if found is not None:
            results.append(found)
    return results


def build_audit(
    path: Path,
    *,
    assume_ist: bool,
    expected_sha256: str | None,
    min_eligible_expiries: int,
    required_years: Iterable[int],
    min_per_required_year: int,
    target_delta: float,
    delta_tolerance: float,
    min_dte: int,
    max_dte: int,
    snapshot_ist: str,
    snapshot_tolerance_minutes: int,
) -> dict:
    actual_sha = sha256_file(path)
    if expected_sha256 and actual_sha != expected_sha256:
        raise ValueError("DATASET_SHA256_MISMATCH")

    raw = load_frame(path)
    synthetic_hits = _contains_synthetic_source(raw)
    if synthetic_hits:
        raise ValueError("SYNTHETIC_SOURCE_REJECTED:" + ",".join(synthetic_hits))

    df = normalize_frame(raw, assume_ist=assume_ist)
    elig = eligible_expiries(
        df,
        min_dte=min_dte,
        max_dte=max_dte,
        target_delta=target_delta,
        delta_tolerance=delta_tolerance,
        snapshot_ist=snapshot_ist,
        snapshot_tolerance_minutes=snapshot_tolerance_minutes,
    )

    by_year: dict[str, int] = {}
    eligible_with_exit = [row for row in elig if row["has_21dte_or_later_quotes"]]
    for row in eligible_with_exit:
        year = row["entry_trade_date"][:4]
        by_year[year] = by_year.get(year, 0) + 1

    required_years = [int(y) for y in required_years]
    year_gate = all(by_year.get(str(y), 0) >= min_per_required_year for y in required_years)
    count_gate = len(eligible_with_exit) >= min_eligible_expiries
    status = "DATA_READY_FOR_PRIMARY_EVAL" if count_gate and year_gate else "DATA_INSUFFICIENT_FOR_PRIMARY_EVAL"

    return {
        "schema_version": "nifty_45dte_vrp_data_audit_v1",
        "candidate_id": "NIFTY_45DTE_VRP_V1",
        "status": status,
        "dataset": {
            "path": str(path),
            "sha256": actual_sha,
            "rows": int(len(df)),
            "first_timestamp": df["timestamp"].min().isoformat(),
            "last_timestamp": df["timestamp"].max().isoformat(),
            "expiry_count": int(df["expiry_date"].nunique()),
        },
        "rules": {
            "dte_window": [min_dte, max_dte],
            "target_abs_delta": target_delta,
            "delta_tolerance": delta_tolerance,
            "snapshot_ist": snapshot_ist,
            "snapshot_tolerance_minutes": snapshot_tolerance_minutes,
            "minimum_eligible_expiries": min_eligible_expiries,
            "required_years": required_years,
            "minimum_per_required_year": min_per_required_year,
        },
        "eligible_expiries_total": len(elig),
        "eligible_expiries_with_21dte_quote_coverage": len(eligible_with_exit),
        "eligible_entries_by_year": by_year,
        "eligible_expiries": eligible_with_exit,
        "governance": {
            "synthetic_data_accepted": False,
            "broker_api_called": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
            "holdout_accessed": False,
        },
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("dataset", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--expected-sha256")
    p.add_argument("--assume-ist", action="store_true")
    p.add_argument("--min-eligible-expiries", type=int, default=24)
    p.add_argument("--required-years", default="2024,2025,2026")
    p.add_argument("--min-per-required-year", type=int, default=4)
    p.add_argument("--target-delta", type=float, default=0.16)
    p.add_argument("--delta-tolerance", type=float, default=0.03)
    p.add_argument("--min-dte", type=int, default=42)
    p.add_argument("--max-dte", type=int, default=48)
    p.add_argument("--snapshot-ist", default="15:00")
    p.add_argument("--snapshot-tolerance-minutes", type=int, default=15)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    years = [int(x.strip()) for x in args.required_years.split(",") if x.strip()]
    try:
        result = build_audit(
            args.dataset,
            assume_ist=args.assume_ist,
            expected_sha256=args.expected_sha256,
            min_eligible_expiries=args.min_eligible_expiries,
            required_years=years,
            min_per_required_year=args.min_per_required_year,
            target_delta=args.target_delta,
            delta_tolerance=args.delta_tolerance,
            min_dte=args.min_dte,
            max_dte=args.max_dte,
            snapshot_ist=args.snapshot_ist,
            snapshot_tolerance_minutes=args.snapshot_tolerance_minutes,
        )
    except Exception as exc:
        result = {
            "schema_version": "nifty_45dte_vrp_data_audit_v1",
            "candidate_id": "NIFTY_45DTE_VRP_V1",
            "status": "DATA_AUDIT_FAILED",
            "error": f"{type(exc).__name__}:{exc}",
            "governance": {
                "broker_api_called": False,
                "order_authority": False,
                "paper_authorized": False,
                "live_authorized": False,
                "holdout_accessed": False,
            },
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "DATA_READY_FOR_PRIMARY_EVAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
