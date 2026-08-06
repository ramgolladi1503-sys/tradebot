#!/usr/bin/env python3
"""Outcome-blind normalized trajectory warehouse for Pattern Atlas V1.

Outputs causal minute rows and completed-session vectors. No future return,
trade label, direction, entry/exit, target/stop or P&L is read or calculated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import date, time
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

CAMPAIGN = "observation_first_pattern_atlas_v1"
CAS_START = date(2026, 8, 3)
TZ = "Asia/Kolkata"
TS = ("event_timestamp", "timestamp", "datetime", "date_time", "exchange_timestamp", "candle_timestamp", "time")
SESSION = ("session_id", "session", "trade_date", "date")
INSTRUMENT = ("instrument_family", "tradingsymbol", "trading_symbol", "symbol", "instrument_key", "instrument_token", "underlying")
PRICE = ("close", "ltp", "last_price", "premium_mean", "price")
VOLUME = ("volume", "volume_sum", "last_traded_quantity", "ltq")
VWAP = ("vwap", "average_price")
DENY = tuple(re.compile(value, re.I) for value in (
    r"(^|_)(future|forward|fwd)(_|$)", r"(^|_)(target|stop|entry|exit)(_|$)",
    r"(^|_)(pnl|profit|loss|expectancy|drawdown|sharpe)(_|$)",
    r"(^|_)(label|outcome|winner|win_rate|hit_target|mfe|mae)(_|$)",
))
ALLOW = {
    "underlying": (*TS, *SESSION, *INSTRUMENT, "open", "high", "low", "close", "volume", "vwap", "average_price", "is_completed_bar", "is_stale", "stale_price_flag", "underlying_completed_bar", "underlying_sparse_bar_flag", "underlying_stale_flag"),
    "constituent": (*TS, *SESSION, *INSTRUMENT, "open", "high", "low", "close", "volume", "vwap", "average_price", "fallback", "mock", "synthetic"),
    "tick": (*TS, *SESSION, *INSTRUMENT, "ltp", "last_price", "price", "volume", "last_traded_quantity", "ltq", "vwap", "average_price", "is_stale", "stale_price_flag"),
    "option": (*TS, *SESSION, *INSTRUMENT, "option_type", "strike", "expiry", "close", "ltp", "last_price", "premium_mean", "volume", "volume_sum", "open_interest", "open_interest_sum", "vwap", "average_price", "is_completed_bar", "is_stale", "stale_price_flag", "certified_for_replay"),
}
CAUSAL = ("return_from_open", "log_return_1", "rolling_volatility_15", "directional_efficiency_15", "expanding_range_pct", "expanding_range_position", "vwap_distance", "prior_atr14_distance", "session_progress")
VECTOR = ("return_from_open", "rolling_volatility_15", "directional_efficiency_15", "expanding_range_position", "vwap_distance")


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def first(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    lookup = {str(value).lower(): str(value) for value in columns}
    return next((lookup[value.lower()] for value in candidates if value.lower() in lookup), None)


def denied(column: str) -> bool:
    return any(pattern.search(str(column)) for pattern in DENY)


def allowed_columns(family: str, available: Iterable[str]) -> list[str]:
    if family not in ALLOW:
        raise ValueError(f"Unsupported family: {family}")
    lookup = {str(value).lower(): str(value) for value in available}
    result: list[str] = []
    for requested in ALLOW[family]:
        actual = lookup.get(requested.lower())
        if actual and not denied(actual) and actual not in result:
            result.append(actual)
    return result


def regime(session_date: date) -> str:
    return "POST_CAS" if session_date >= CAS_START else "PRE_CAS"


def window(value: str) -> tuple[time, time]:
    if value == "PRE_CAS":
        return time(9, 15), time(15, 30)
    if value == "POST_CAS":
        return time(9, 15), time(15, 40)
    raise ValueError(value)


def normalize_timestamps(values: pd.Series, naive_timezone: str = TZ) -> pd.Series:
    output = []
    for raw in values:
        try:
            stamp = pd.Timestamp(raw)
            if pd.isna(stamp):
                raise ValueError
            if stamp.tzinfo is None:
                stamp = stamp.tz_localize(naive_timezone, ambiguous="NaT", nonexistent="NaT")
            output.append(stamp.tz_convert(TZ))
        except Exception:
            output.append(pd.NaT)
    return pd.Series(output, index=values.index, dtype=f"datetime64[ns, {TZ}]")


def quality_mask(frame: pd.DataFrame) -> pd.Series:
    lookup = {str(value).lower(): str(value) for value in frame.columns}
    mask = pd.Series(True, index=frame.index)
    for name in ("is_completed_bar", "underlying_completed_bar", "certified_for_replay"):
        if name in lookup:
            mask &= frame[lookup[name]].fillna(False).astype(bool)
    for name in ("is_stale", "stale_price_flag", "underlying_sparse_bar_flag", "underlying_stale_flag", "fallback", "mock", "synthetic"):
        if name in lookup:
            mask &= ~frame[lookup[name]].fillna(True).astype(bool)
    return mask


def canonicalize(frame: pd.DataFrame, source: str, family: str, naive_timezone: str = TZ) -> pd.DataFrame:
    leaked = sorted(value for value in frame.columns if denied(str(value)))
    if leaked:
        raise ValueError(f"Outcome-like columns reached trajectory stage: {leaked}")
    timestamp, price = first(frame.columns, TS), first(frame.columns, PRICE)
    if timestamp is None or price is None:
        raise ValueError("Timestamp or price column missing")
    session, instrument = first(frame.columns, SESSION), first(frame.columns, INSTRUMENT)
    volume, vwap = first(frame.columns, VOLUME), first(frame.columns, VWAP)
    result = pd.DataFrame(index=frame.index)
    result["timestamp"] = normalize_timestamps(frame[timestamp], naive_timezone)
    result["session_date"] = pd.to_datetime(frame[session], errors="coerce").dt.date if session else result["timestamp"].dt.date
    result["instrument"] = frame[instrument].astype(str) if instrument else Path(source).stem
    result["price"] = pd.to_numeric(frame[price], errors="coerce")
    result["volume"] = pd.to_numeric(frame[volume], errors="coerce").clip(lower=0) if volume else np.nan
    result["source_vwap"] = pd.to_numeric(frame[vwap], errors="coerce") if vwap else np.nan
    result = result.loc[quality_mask(frame)].copy()
    result = result.loc[result["timestamp"].notna() & result["session_date"].notna() & result["price"].gt(0)].copy()
    result["regime"] = result["session_date"].map(regime)
    local = result["timestamp"].dt.time
    keep = pd.Series(False, index=result.index)
    for name in ("PRE_CAS", "POST_CAS"):
        start, end = window(name)
        keep |= result["regime"].eq(name) & local.between(start, end, inclusive="both")
    result = result.loc[keep].copy()
    result["source_path"] = source
    result["source_family"] = family
    return result.sort_values(["instrument", "session_date", "timestamp"], kind="mergesort").drop_duplicates(["instrument", "session_date", "timestamp"], keep="last").reset_index(drop=True)


def resample_minutes(frame: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for (instrument, session_date), group in frame.groupby(["instrument", "session_date"], sort=True):
        name = regime(session_date)
        start_time, end_time = window(name)
        start = pd.Timestamp.combine(session_date, start_time).tz_localize(TZ)
        end = pd.Timestamp.combine(session_date, end_time).tz_localize(TZ)
        grid = pd.date_range(start, end, freq="1min")
        values = group.set_index("timestamp")[["price", "volume", "source_vwap"]].resample("1min").last().reindex(grid)
        observed = values["price"].notna()
        values["price"] = values["price"].ffill()
        values["source_vwap"] = values["source_vwap"].ffill()
        values["volume"] = values["volume"].fillna(0.0)
        values["observed_this_minute"] = observed
        values["minutes_since_observation"] = observed.groupby(observed.cumsum()).cumcount().astype(float)
        values = values.loc[values["price"].notna()].copy()
        values["timestamp"], values["instrument"], values["session_date"], values["regime"] = values.index, instrument, session_date, name
        values["session_start"], values["session_end"] = start, end
        parts.append(values.reset_index(drop=True))
    return pd.concat(parts, ignore_index=True).sort_values(["instrument", "session_date", "timestamp"], kind="mergesort") if parts else pd.DataFrame()


def divide(left: pd.Series, right: pd.Series) -> pd.Series:
    return left.div(right.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def add_prior_atr(frame: pd.DataFrame) -> pd.DataFrame:
    daily = frame.groupby(["instrument", "session_date"], observed=True).agg(high=("price", "max"), low=("price", "min"), close=("price", "last")).reset_index().sort_values(["instrument", "session_date"])
    daily["previous_close"] = daily.groupby("instrument", observed=True)["close"].shift()
    daily["true_range"] = pd.concat([daily["high"] - daily["low"], (daily["high"] - daily["previous_close"]).abs(), (daily["low"] - daily["previous_close"]).abs()], axis=1).max(axis=1)
    daily["prior_atr14"] = daily.groupby("instrument", observed=True)["true_range"].transform(lambda values: values.shift().rolling(14, min_periods=5).mean())
    return frame.merge(daily[["instrument", "session_date", "previous_close", "prior_atr14"]], on=["instrument", "session_date"], how="left", validate="many_to_one")


def add_causal_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = add_prior_atr(frame).sort_values(["instrument", "session_date", "timestamp"], kind="mergesort").copy()
    group = result.groupby(["instrument", "session_date"], observed=True, sort=False)
    result["session_open"] = group["price"].transform("first")
    result["return_from_open"] = divide(result["price"], result["session_open"]) - 1
    log_price = np.log(result["price"])
    result["log_return_1"] = group["price"].transform(lambda values: np.log(values).diff())
    high, low = group["price"].cummax(), group["price"].cummin()
    result["expanding_range_pct"] = divide(high - low, result["session_open"])
    result["expanding_range_position"] = divide(result["price"] - low, high - low).fillna(0.5).clip(0, 1)
    result["rolling_volatility_15"] = group["log_return_1"].transform(lambda values: values.rolling(15, min_periods=5).std(ddof=0))
    absolute_path = group["log_return_1"].transform(lambda values: values.abs().rolling(15, min_periods=2).sum())
    net_move = log_price.groupby([result["instrument"], result["session_date"]]).diff(14).abs()
    result["directional_efficiency_15"] = divide(net_move, absolute_path).clip(0, 1)
    price_volume = result["price"] * result["volume"].fillna(0)
    cumulative_volume = group["volume"].cumsum()
    cumulative_pv = price_volume.groupby([result["instrument"], result["session_date"]]).cumsum()
    calculated_vwap = divide(cumulative_pv, cumulative_volume)
    result["causal_vwap"] = result["source_vwap"].where(result["source_vwap"].gt(0), calculated_vwap).fillna(result["session_open"])
    result["vwap_distance"] = divide(result["price"], result["causal_vwap"]) - 1
    result["prior_atr14_distance"] = divide(result["price"] - result["session_open"], result["prior_atr14"])
    elapsed = (result["timestamp"] - result["session_start"]).dt.total_seconds() / 60
    duration = (result["session_end"] - result["session_start"]).dt.total_seconds() / 60
    result["session_progress"] = divide(elapsed, duration).clip(0, 1)
    return result


def prefix_invariant(full: pd.DataFrame, rows: int) -> bool:
    left, right = add_causal_features(full).iloc[:rows], add_causal_features(full.iloc[:rows].copy())
    return all(np.allclose(pd.to_numeric(left[column], errors="coerce"), pd.to_numeric(right[column], errors="coerce"), atol=1e-12, rtol=0, equal_nan=True) for column in CAUSAL)


def vector(group: pd.DataFrame, points: int) -> dict[str, Any]:
    ordered = group.sort_values("session_progress")
    x = pd.to_numeric(ordered["session_progress"], errors="coerce").to_numpy(float)
    unique = ~pd.Series(x).duplicated(keep="last").to_numpy()
    x, target = x[unique], np.linspace(0, 1, points)
    payload = {"instrument": str(ordered["instrument"].iloc[0]), "session_date": str(ordered["session_date"].iloc[0]), "regime": str(ordered["regime"].iloc[0]), "grid_points": points, "features": {}}
    for feature in VECTOR:
        y = pd.to_numeric(ordered.loc[unique, feature], errors="coerce").to_numpy(float)
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < 2:
            values = [None] * points
        else:
            interpolated = np.interp(target, x[valid], y[valid])
            interpolated[(target < x[valid].min()) | (target > x[valid].max())] = np.nan
            values = [None if not math.isfinite(value) else float(value) for value in interpolated]
        payload["features"][feature] = values
    payload["semantic_sha256"] = digest(payload)
    return payload


def build_vectors(frame: pd.DataFrame, points: int, min_coverage: float, max_staleness: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted, rejected = [], []
    for (instrument, session_date), group in frame.groupby(["instrument", "session_date"], sort=True):
        observed, stale = float(group["observed_this_minute"].mean()), float(group["minutes_since_observation"].max())
        start, end = float(group["session_progress"].min()), float(group["session_progress"].max())
        reasons = []
        if observed < min_coverage: reasons.append("observed_minute_share_below_threshold")
        if stale > max_staleness: reasons.append("staleness_exceeds_threshold")
        if start > 0.02: reasons.append("session_start_missing")
        if end < 0.98: reasons.append("session_end_missing")
        if reasons:
            rejected.append({"instrument": str(instrument), "session_date": str(session_date), "regime": regime(session_date), "observed_minute_share": observed, "max_minutes_since_observation": stale, "first_progress": start, "last_progress": end, "reasons": reasons})
        else:
            accepted.append(vector(group, points))
    return accepted, rejected


def read_parquet(path: Path, columns: Sequence[str]) -> pd.DataFrame:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyarrow is required for physical Parquet execution") from exc
    return pq.read_table(path, columns=list(columns)).to_pandas()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--inventory-json", type=Path, default=Path("runtime/research/observation_first_pattern_atlas_v1/inventory/corpus_inventory.json"))
    parser.add_argument("--output-root", type=Path, default=Path("runtime/research/observation_first_pattern_atlas_v1/trajectory"))
    parser.add_argument("--family", choices=sorted(ALLOW), default="underlying")
    parser.add_argument("--naive-timezone", default=TZ)
    parser.add_argument("--grid-points", type=int, default=96)
    parser.add_argument("--min-session-coverage", type=float, default=0.90)
    parser.add_argument("--max-staleness-minutes", type=float, default=5.0)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    inventory_path = args.inventory_json if args.inventory_json.is_absolute() else repo / args.inventory_json
    output = args.output_root if args.output_root.is_absolute() else repo / args.output_root
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    candidates = []
    for item in inventory.get("files", []):
        if item.get("observation_family") != args.family or item.get("schema_error"): continue
        selected = allowed_columns(args.family, item.get("columns", []))
        if first(selected, TS) and first(selected, PRICE): candidates.append({**item, "selected_columns": selected})
    parts, diagnostics = [], []
    for item in sorted(candidates, key=lambda value: value["path"]):
        try:
            raw = read_parquet(repo / item["path"], item["selected_columns"])
            clean = canonicalize(raw, item["path"], args.family, args.naive_timezone)
            parts.append(clean)
            diagnostics.append({"path": item["path"], "status": "ACCEPTED", "raw_rows": len(raw), "canonical_rows": len(clean), "selected_columns": item["selected_columns"]})
        except Exception as exc:
            diagnostics.append({"path": item["path"], "status": "REJECTED", "error": f"{type(exc).__name__}: {exc}", "selected_columns": item["selected_columns"]})
    if not parts: raise ValueError("No physical file was accepted")
    causal = add_causal_features(resample_minutes(pd.concat(parts, ignore_index=True)))
    accepted, rejected = build_vectors(causal, args.grid_points, args.min_session_coverage, args.max_staleness_minutes)
    output.mkdir(parents=True, exist_ok=True)
    causal.to_parquet(output / "causal_minute_trajectory.parquet", index=False)
    stable_write(output / "completed_session_vectors.json", {"sessions": accepted})
    stable_write(output / "rejected_sessions.json", {"sessions": rejected})
    stable_write(output / "file_diagnostics.json", {"files": diagnostics})
    contract = {"schema_version": 1, "campaign": CAMPAIGN, "stage": "normalized_trajectory_warehouse_v1", "cas_start_date": CAS_START.isoformat(), "market_timezone": TZ, "family": args.family, "grid_points": args.grid_points, "causal_features": list(CAUSAL), "vector_features": list(VECTOR), "policy": {"explicit_allowlist": True, "outcomes_read": False, "future_returns_calculated": False, "pnl_calculated": False, "direction_selected": False, "whole_day_vectors_allowed_intraday": False, "allowed_for_live_execution": False}}
    contract["semantic_sha256"] = digest(contract)
    stable_write(output / "trajectory_contract.json", contract)
    summary = {"principal_verdict": "TRAJECTORY_WAREHOUSE_READY_FOR_OUTCOME_BLIND_CLUSTERING" if accepted else "NO_SESSION_PASSED_TRAJECTORY_QUALITY_GATES", "candidate_files": len(candidates), "accepted_files": sum(value["status"] == "ACCEPTED" for value in diagnostics), "rejected_files": sum(value["status"] == "REJECTED" for value in diagnostics), "causal_minute_rows": len(causal), "instruments": int(causal["instrument"].nunique()), "sessions": int(causal[["instrument", "session_date"]].drop_duplicates().shape[0]), "accepted_session_vectors": len(accepted), "rejected_sessions": len(rejected), "outcomes_read": False, "allowed_for_live_execution": False}
    summary["semantic_sha256"] = digest(summary)
    stable_write(output / "trajectory_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
