#!/usr/bin/env python3
"""Build leakage-safe NIFTY 45-DTE volatility-risk-premium state.

Research only. No network/broker/order calls.

Primary state at each session's 15:00 IST snapshot:
- choose real NIFTY option quotes with 35-55 calendar DTE,
- estimate each expiry's near-ATM IV from CE/PE closest to |delta|=0.50,
- linearly interpolate to 45 DTE when expiries bracket 45; otherwise use the
  nearest expiry only when it is within 5 calendar days of 45,
- compute RV20 from the PRIOR 20 completed NIFTY close-to-close returns,
- VRP proxy = IV45^2 - RV20^2,
- z-score current VRP against PRIOR state observations only (shifted expanding
  mean/std, minimum 60 observations).

The emitted `state_timestamp` is the exact information-availability timestamp.
Downstream gates must as-of join using state_timestamp <= trade entry timestamp.
Thus a 09:15 trade cannot consume the same day's 15:00 state.
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

from audit_data import _contains_synthetic_source, load_frame, sha256_file  # noqa: E402

OPTION_REQUIRED = {"timestamp", "symbol", "expiry", "type", "delta", "iv"}
UNDERLYING_REQUIRED = {"timestamp", "close"}


def _to_ist(series: pd.Series, *, assume_ist: bool, field: str) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise ValueError(f"{field.upper()}_PARSE_FAILED")
    if getattr(ts.dt, "tz", None) is None:
        if not assume_ist:
            raise ValueError(f"NAIVE_{field.upper()}_REQUIRES_EXPLICIT_ASSUME_IST")
        return ts.dt.tz_localize("Asia/Kolkata", ambiguous="raise", nonexistent="raise")
    return ts.dt.tz_convert("Asia/Kolkata")


def normalize_options(df: pd.DataFrame, *, assume_ist: bool, iv_unit: str) -> pd.DataFrame:
    missing = sorted(OPTION_REQUIRED - set(df.columns))
    if missing:
        raise ValueError("MISSING_OPTION_COLUMNS:" + ",".join(missing))
    hits = _contains_synthetic_source(df)
    if hits:
        raise ValueError("SYNTHETIC_SOURCE_REJECTED:" + ",".join(hits))

    out = df.copy()
    out["timestamp"] = _to_ist(out["timestamp"], assume_ist=assume_ist, field="timestamp")
    expiry = pd.to_datetime(out["expiry"], errors="coerce")
    if expiry.isna().any():
        raise ValueError("EXPIRY_PARSE_FAILED")
    out["expiry_date"] = expiry.dt.date
    out["symbol"] = out["symbol"].astype(str).str.upper()
    if set(out["symbol"].dropna().unique()) != {"NIFTY"}:
        raise ValueError("ONLY_NIFTY_SUPPORTED")
    out["type"] = out["type"].astype(str).str.upper().replace({"CALL": "CE", "PUT": "PE"})
    if not out["type"].isin({"CE", "PE"}).all():
        raise ValueError("UNSUPPORTED_OPTION_TYPE")
    out["delta"] = pd.to_numeric(out["delta"], errors="coerce")
    out["iv"] = pd.to_numeric(out["iv"], errors="coerce")
    if out[["delta", "iv"]].isna().any().any():
        raise ValueError("NON_NUMERIC_DELTA_OR_IV")
    if iv_unit == "percent":
        out["iv"] = out["iv"] / 100.0
    elif iv_unit != "decimal":
        raise ValueError("IV_UNIT_MUST_BE_DECIMAL_OR_PERCENT")
    if not out["iv"].between(0.01, 3.0).all():
        raise ValueError("IV_OUT_OF_RANGE")
    if not out.loc[out["type"] == "CE", "delta"].between(0.0, 1.0).all():
        raise ValueError("INVALID_CALL_DELTA")
    if not out.loc[out["type"] == "PE", "delta"].between(-1.0, 0.0).all():
        raise ValueError("INVALID_PUT_DELTA")
    return out.sort_values(["timestamp", "expiry_date", "type", "delta"]).reset_index(drop=True)


def normalize_underlying(df: pd.DataFrame, *, assume_ist: bool) -> pd.DataFrame:
    missing = sorted(UNDERLYING_REQUIRED - set(df.columns))
    if missing:
        raise ValueError("MISSING_UNDERLYING_COLUMNS:" + ",".join(missing))
    out = df.copy()
    out["timestamp"] = _to_ist(out["timestamp"], assume_ist=assume_ist, field="underlying_timestamp")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    if out["close"].isna().any() or (out["close"] <= 0).any():
        raise ValueError("INVALID_UNDERLYING_CLOSE")
    out["session_date"] = out["timestamp"].dt.date
    daily = (
        out.sort_values("timestamp")
        .groupby("session_date", as_index=False)
        .agg(close=("close", "last"), close_timestamp=("timestamp", "last"))
        .sort_values("session_date")
        .reset_index(drop=True)
    )
    daily["log_return"] = np.log(daily["close"] / daily["close"].shift(1))
    # RV20 for state date D must not consume D's close because the state exists at 15:00.
    # Shift first, then rolling 20 prior completed returns.
    daily["rv20_prior"] = (
        daily["log_return"].shift(1).rolling(20, min_periods=20).std(ddof=1) * math.sqrt(252.0)
    )
    return daily


def _snapshot_near_time(day_df: pd.DataFrame, *, hhmm: str, tolerance_minutes: int) -> pd.DataFrame | None:
    if day_df.empty:
        return None
    hh, mm = [int(x) for x in hhmm.split(":")]
    date = day_df["timestamp"].iloc[0].date()
    target = pd.Timestamp(date).tz_localize("Asia/Kolkata") + pd.Timedelta(hours=hh, minutes=mm)
    unique_ts = pd.Series(day_df["timestamp"].drop_duplicates().sort_values())
    distance = (unique_ts - target).abs().dt.total_seconds()
    idx = int(distance.idxmin())
    if float(distance.loc[idx]) > tolerance_minutes * 60:
        return None
    chosen = unique_ts.loc[idx]
    return day_df.loc[day_df["timestamp"] == chosen].copy()


def _near_atm_iv_for_expiry(exp_df: pd.DataFrame, *, target_abs_delta: float = 0.50) -> float | None:
    vals: list[float] = []
    for opt_type in ("CE", "PE"):
        leg = exp_df.loc[exp_df["type"] == opt_type].copy()
        if leg.empty:
            return None
        leg["distance"] = (leg["delta"].abs() - target_abs_delta).abs()
        row = leg.sort_values(["distance", "iv"]).iloc[0]
        vals.append(float(row["iv"]))
    return float(np.mean(vals))


def _iv45_from_snapshot(
    snapshot: pd.DataFrame,
    *,
    state_date,
    min_dte: int,
    max_dte: int,
    target_dte: int,
    nearest_tolerance_days: int,
) -> tuple[float, str, list[dict]] | None:
    rows: list[dict] = []
    for expiry_date, exp_df in snapshot.groupby("expiry_date", sort=True):
        dte = int((expiry_date - state_date).days)
        if dte < min_dte or dte > max_dte:
            continue
        iv = _near_atm_iv_for_expiry(exp_df)
        if iv is not None:
            rows.append({"expiry": str(expiry_date), "dte": dte, "atm_iv": iv})
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r["dte"])

    lower = [r for r in rows if r["dte"] <= target_dte]
    upper = [r for r in rows if r["dte"] >= target_dte]
    if lower and upper:
        lo = lower[-1]
        hi = upper[0]
        if lo["dte"] == hi["dte"]:
            return float(lo["atm_iv"]), "EXACT_DTE", rows
        weight = (target_dte - lo["dte"]) / (hi["dte"] - lo["dte"])
        iv45 = lo["atm_iv"] + weight * (hi["atm_iv"] - lo["atm_iv"])
        return float(iv45), "LINEAR_DTE_INTERPOLATION", rows

    nearest = min(rows, key=lambda r: abs(r["dte"] - target_dte))
    if abs(nearest["dte"] - target_dte) <= nearest_tolerance_days:
        return float(nearest["atm_iv"]), "NEAREST_WITHIN_TOLERANCE", rows
    return None


def build_states(
    option_df: pd.DataFrame,
    underlying_daily: pd.DataFrame,
    *,
    snapshot_ist: str = "15:00",
    snapshot_tolerance_minutes: int = 15,
    min_dte: int = 35,
    max_dte: int = 55,
    target_dte: int = 45,
    nearest_tolerance_days: int = 5,
    zscore_min_history: int = 60,
) -> pd.DataFrame:
    rv_map = underlying_daily.set_index("session_date")["rv20_prior"].to_dict()
    work = option_df.copy()
    work["session_date"] = work["timestamp"].dt.date
    states: list[dict] = []

    for state_date, day_df in work.groupby("session_date", sort=True):
        rv20 = rv_map.get(state_date)
        if rv20 is None or pd.isna(rv20):
            continue
        snap = _snapshot_near_time(day_df, hhmm=snapshot_ist, tolerance_minutes=snapshot_tolerance_minutes)
        if snap is None:
            continue
        iv_result = _iv45_from_snapshot(
            snap,
            state_date=state_date,
            min_dte=min_dte,
            max_dte=max_dte,
            target_dte=target_dte,
            nearest_tolerance_days=nearest_tolerance_days,
        )
        if iv_result is None:
            continue
        iv45, method, components = iv_result
        state_ts = pd.Timestamp(snap["timestamp"].iloc[0])
        vrp = float(iv45 * iv45 - float(rv20) * float(rv20))
        states.append(
            {
                "state_timestamp": state_ts,
                "state_date": str(state_date),
                "iv45": float(iv45),
                "rv20_prior": float(rv20),
                "vrp_proxy": vrp,
                "iv45_method": method,
                "iv45_components_json": json.dumps(components, sort_keys=True),
            }
        )

    out = pd.DataFrame(states)
    if out.empty:
        return out
    out = out.sort_values("state_timestamp").reset_index(drop=True)
    prior_mean = out["vrp_proxy"].expanding(min_periods=zscore_min_history).mean().shift(1)
    prior_std = out["vrp_proxy"].expanding(min_periods=zscore_min_history).std(ddof=1).shift(1)
    out["vrp_prior_mean"] = prior_mean
    out["vrp_prior_std"] = prior_std
    out["vrp_zscore"] = (out["vrp_proxy"] - prior_mean) / prior_std
    out.loc[prior_std <= 0, "vrp_zscore"] = np.nan
    out["primary_gate_admit"] = out["vrp_zscore"].le(0.0) & out["vrp_zscore"].notna()
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("options", type=Path)
    p.add_argument("underlying", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--expected-options-sha256")
    p.add_argument("--expected-underlying-sha256")
    p.add_argument("--assume-ist-options", action="store_true")
    p.add_argument("--assume-ist-underlying", action="store_true")
    p.add_argument("--iv-unit", choices=["decimal", "percent"], default="decimal")
    p.add_argument("--snapshot-ist", default="15:00")
    p.add_argument("--snapshot-tolerance-minutes", type=int, default=15)
    p.add_argument("--min-dte", type=int, default=35)
    p.add_argument("--max-dte", type=int, default=55)
    p.add_argument("--target-dte", type=int, default=45)
    p.add_argument("--nearest-tolerance-days", type=int, default=5)
    p.add_argument("--zscore-min-history", type=int, default=60)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        options_sha = sha256_file(args.options)
        underlying_sha = sha256_file(args.underlying)
        if args.expected_options_sha256 and options_sha != args.expected_options_sha256:
            raise ValueError("OPTIONS_SHA256_MISMATCH")
        if args.expected_underlying_sha256 and underlying_sha != args.expected_underlying_sha256:
            raise ValueError("UNDERLYING_SHA256_MISMATCH")
        options = normalize_options(
            load_frame(args.options), assume_ist=args.assume_ist_options, iv_unit=args.iv_unit
        )
        underlying = normalize_underlying(
            load_frame(args.underlying), assume_ist=args.assume_ist_underlying
        )
        states = build_states(
            options,
            underlying,
            snapshot_ist=args.snapshot_ist,
            snapshot_tolerance_minutes=args.snapshot_tolerance_minutes,
            min_dte=args.min_dte,
            max_dte=args.max_dte,
            target_dte=args.target_dte,
            nearest_tolerance_days=args.nearest_tolerance_days,
            zscore_min_history=args.zscore_min_history,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        states.to_csv(args.output, index=False)
        usable = int(states["vrp_zscore"].notna().sum()) if not states.empty else 0
        admitted = int(states["primary_gate_admit"].sum()) if not states.empty else 0
        result = {
            "schema_version": "nifty_45dte_vrp_state_v1",
            "candidate_id": "NIFTY_45DTE_VRP_TRANSLATOR_BUYONLY_V1",
            "status": "VRP_STATE_BUILT" if usable > 0 else "VRP_STATE_INSUFFICIENT_HISTORY",
            "options_sha256": options_sha,
            "underlying_sha256": underlying_sha,
            "state_rows": int(len(states)),
            "usable_zscore_rows": usable,
            "primary_gate_admitted_state_rows": admitted,
            "availability_rule": "state_timestamp <= downstream trade entry timestamp",
            "lookahead_guard": "RV20 uses prior completed sessions; zscore moments are shifted by one state",
            "output": str(args.output),
            "governance": {
                "broker_api_called": False,
                "order_authority": False,
                "paper_authorized": False,
                "live_authorized": False,
                "holdout_accessed": False,
                "edge_certified": False,
            },
        }
    except Exception as exc:
        result = {
            "schema_version": "nifty_45dte_vrp_state_v1",
            "candidate_id": "NIFTY_45DTE_VRP_TRANSLATOR_BUYONLY_V1",
            "status": "VRP_STATE_BUILD_FAILED",
            "error": f"{type(exc).__name__}:{exc}",
            "governance": {
                "broker_api_called": False,
                "order_authority": False,
                "paper_authorized": False,
                "live_authorized": False,
                "holdout_accessed": False,
                "edge_certified": False,
            },
        }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "VRP_STATE_BUILT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
