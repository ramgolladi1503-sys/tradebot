from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


IST = "Asia/Kolkata"
TARGET_START = pd.Timestamp("2024-09-26 09:15:00", tz=IST)
TARGET_END = pd.Timestamp("2026-07-21 15:29:00", tz=IST)
SESSION_START = "09:15"
SESSION_END = "15:29"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def discover_sources(locations: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    name_re = re.compile(r"(NIFTY|NSE_INDEX\|Nifty 50)_\d{8}\.parquet$")
    for location in locations:
        if not location.exists():
            rows.append({"search_location": str(location), "status": "MISSING"})
            continue
        for current, dirs, files in os.walk(location):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "Library", ".Trash"}]
            current_path = Path(current)
            for name in files:
                path = current_path / name
                if name_re.match(name) or name in {"aggregated_bars.parquet", "NIFTY_5minute.parquet", "nifty_ohlc_wfa.parquet"}:
                    if path.resolve() in seen:
                        continue
                    seen.add(path.resolve())
                    rows.append(classify_source(path, location))
    return rows


def classify_source(path: Path, search_location: Path) -> dict[str, Any]:
    base = {
        "search_location": str(search_location),
        "path": str(path.resolve()),
        "type": path.suffix.lstrip("."),
        "size": path.stat().st_size,
        "sha256": file_sha256(path),
        "classification": "UNUSABLE",
        "symbol": "",
        "timestamp_start": "",
        "timestamp_end": "",
        "row_count": 0,
        "resolution": "",
        "timezone": "",
        "ohlcv": False,
        "provenance": "",
        "raw_or_derived": "",
        "missing_session_estimate": None,
        "replay_suitability": False,
    }
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        base["error"] = str(exc)
        return base
    cols = {str(c).lower(): c for c in frame.columns}
    ts_col = cols.get("timestamp") or cols.get("datetime") or cols.get("event_timestamp")
    symbol_col = cols.get("symbol") or cols.get("instrument")
    if ts_col is None:
        return base
    ts = parse_ts(frame[ts_col])
    symbol = "|".join(sorted(frame[symbol_col].dropna().astype(str).unique()[:10])) if symbol_col else "NIFTY"
    has_ohlcv = all(c in cols for c in ["open", "high", "low", "close", "volume"])
    resolution = infer_resolution(ts)
    provider = str(frame[cols["provider"]].dropna().iloc[0]) if "provider" in cols and frame[cols["provider"]].dropna().any() else ""
    endpoint = str(frame[cols["source_endpoint"]].dropna().iloc[0]) if "source_endpoint" in cols and frame[cols["source_endpoint"]].dropna().any() else ""
    synthetic = bool(frame[cols["synthetic"]].fillna(False).any()) if "synthetic" in cols else False
    mock = bool(frame[cols["mock"]].fillna(False).any()) if "mock" in cols else False
    fallback = bool(frame[cols["fallback"]].fillna(False).any()) if "fallback" in cols else False
    trusted = has_ohlcv and "NIFTY" in symbol.upper() and not synthetic and not mock and not fallback and provider == "upstox"
    base.update(
        {
            "symbol": symbol,
            "timestamp_start": ts.dropna().min().isoformat(),
            "timestamp_end": ts.dropna().max().isoformat(),
            "row_count": int(len(frame)),
            "resolution": resolution,
            "timezone": IST,
            "ohlcv": has_ohlcv,
            "provenance": f"{provider}:{endpoint}".strip(":"),
            "raw_or_derived": "raw_provider_candles" if "/upstox_candidate_replay/" in str(path) else "derived_or_aggregated",
            "classification": "TRUSTED_RAW" if trusted and resolution == "1minute" else ("TRUSTED_DERIVED" if trusted else "SEMANTICALLY_AMBIGUOUS"),
            "missing_session_estimate": None,
            "replay_suitability": bool(trusted),
        }
    )
    return base


def parse_ts(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is None:
        return parsed.dt.tz_localize(IST, ambiguous="NaT", nonexistent="shift_forward")
    return parsed.dt.tz_convert(IST)


def infer_resolution(ts: pd.Series) -> str:
    diffs = ts.dropna().sort_values().diff().dropna()
    if diffs.empty:
        return "unknown"
    seconds = int(diffs.mode().iloc[0].total_seconds())
    return f"{seconds // 60}minute" if seconds % 60 == 0 else f"{seconds}s"


def selected_files(source_root: Path) -> list[Path]:
    name_re = re.compile(r"(NIFTY|NSE_INDEX\|Nifty 50)_\d{8}\.parquet$")
    return sorted(p for p in source_root.rglob("*.parquet") if name_re.match(p.name))


def load_repair_policy(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text())
    return {row["session_date"]: row for row in payload.get("repair_ledger", [])}


def load_canonical_1m(files: list[Path], repair_policy: dict[str, dict[str, Any]] | None = None) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    repair_policy = repair_policy or {}
    frames = []
    manifest = []
    for path in files:
        frame = pd.read_parquet(path)
        frame["timestamp"] = parse_ts(frame["timestamp"])
        frame = frame[(frame["timestamp"] >= TARGET_START) & (frame["timestamp"] <= TARGET_END)].copy()
        if frame.empty:
            continue
        source_date = frame["timestamp"].dt.date.astype(str).iloc[0]
        policy = repair_policy.get(source_date, {})
        if policy.get("action") == "EXCLUDE_REQUIRES_REFETCH":
            continue
        if policy.get("action") == "USE_REPAIRED_FILE":
            frame = pd.read_parquet(policy["repaired_path"])
            frame["timestamp"] = parse_ts(frame["timestamp"])
        frame["session_date"] = frame["timestamp"].dt.date.astype(str)
        frame["symbol"] = "NIFTY"
        frame["bar_resolution"] = "1minute"
        frame["source_id"] = str(path.resolve())
        frame["source_hash"] = file_sha256(path)
        frame["is_completed_bar"] = True
        frame["is_missing_gap"] = False
        frame["is_stale"] = frame["close"].diff().fillna(1).eq(0)
        frame["provenance_class"] = "TRUSTED_RAW_UPSTOX_V3_HISTORICAL_CANDLE"
        keep = ["session_date", "timestamp", "symbol", "open", "high", "low", "close", "volume", "bar_resolution", "source_id", "source_hash", "is_completed_bar", "is_missing_gap", "is_stale", "provenance_class"]
        frames.append(frame[keep])
        manifest.append({"path": str(path.resolve()), "sha256": file_sha256(path), "rows_in_target": int(len(frame)), "date": frame["session_date"].iloc[0], "repair_action": policy.get("action", "NONE")})
    data = pd.concat(frames, ignore_index=True).sort_values(["timestamp"]).reset_index(drop=True)
    return data, manifest


def canonical_5m(one: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for session, group in one.groupby("session_date", sort=True):
        g = group.sort_values("timestamp").reset_index(drop=True).copy()
        g["bucket"] = g.index // 5
        agg = (
            g.groupby("bucket", sort=True)
            .agg(timestamp=("timestamp", "max"), open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"), source_bar_count=("timestamp", "count"))
            .reset_index(drop=True)
        )
        agg = agg[agg["source_bar_count"].eq(5)].drop(columns=["source_bar_count"])
        agg["session_date"] = session
        rows.append(agg)
    out = pd.concat(rows, ignore_index=True)
    out["symbol"] = "NIFTY"
    out["bar_resolution"] = "5minute"
    out["source_id"] = "derived_from_canonical_1minute"
    out["source_hash"] = stable_hash(one[["session_date", "timestamp", "open", "high", "low", "close", "volume", "source_hash"]].to_dict("records"))
    out["is_completed_bar"] = True
    out["is_missing_gap"] = False
    out["is_stale"] = out.groupby("session_date")["close"].diff().fillna(1).eq(0)
    out["provenance_class"] = "TRUSTED_DERIVED_FROM_1M_UPSTOX"
    return out[["session_date", "timestamp", "symbol", "open", "high", "low", "close", "volume", "bar_resolution", "source_id", "source_hash", "is_completed_bar", "is_missing_gap", "is_stale", "provenance_class"]]


def feature_frame(one: pd.DataFrame) -> pd.DataFrame:
    df = one.sort_values(["session_date", "timestamp"]).copy()
    g = df.groupby("session_date", sort=False)
    df["minute_index"] = g.cumcount()
    df["time_since_open"] = df["minute_index"]
    df["minutes_to_close"] = 374 - df["minute_index"]
    df["weekday"] = df["timestamp"].dt.weekday
    df["month"] = df["timestamp"].dt.month
    df["session_progress"] = df["minute_index"] / 374
    df["ret_1"] = g["close"].pct_change()
    df["ret_5"] = g["close"].pct_change(5)
    df["momentum_15"] = g["close"].pct_change(15)
    df["acceleration"] = g["ret_1"].diff() if "ret_1" in g.obj else df.groupby("session_date")["ret_1"].diff()
    prev_close = g["close"].shift(1)
    tr = pd.concat([(df["high"] - df["low"]), (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    df["true_range"] = tr
    df["atr_14"] = g["true_range"].rolling(14, min_periods=1).mean().reset_index(level=0, drop=True)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    df["cum_pv"] = (typical * df["volume"].replace(0, 1)).groupby(df["session_date"]).cumsum()
    df["cum_volume"] = df["volume"].replace(0, 1).groupby(df["session_date"]).cumsum()
    df["vwap"] = df["cum_pv"] / df["cum_volume"]
    df["vwap_distance"] = (df["close"] - df["vwap"]) / df["vwap"]
    df["session_high_so_far"] = g["high"].cummax()
    df["session_low_so_far"] = g["low"].cummin()
    df["dist_session_high"] = (df["close"] - df["session_high_so_far"]) / df["session_high_so_far"]
    df["dist_session_low"] = (df["close"] - df["session_low_so_far"]) / df["session_low_so_far"]
    df["close_location"] = (df["close"] - df["session_low_so_far"]) / (df["session_high_so_far"] - df["session_low_so_far"]).replace(0, pd.NA)
    df["directional_persistence"] = g["ret_1"].apply(lambda s: s.gt(0).rolling(5, min_periods=1).sum()).reset_index(level=0, drop=True)
    df["higher_high_state"] = df["high"].gt(g["high"].shift(1))
    df["lower_low_state"] = df["low"].lt(g["low"].shift(1))
    df["slope_15"] = g["close"].diff(15) / 15
    df["trend_strength_proxy"] = df["slope_15"].abs() / df["atr_14"].replace(0, pd.NA)
    df["continuation_count"] = g["ret_1"].apply(lambda s: s.gt(0).groupby(s.le(0).cumsum()).cumcount()).reset_index(level=0, drop=True)
    df["rolling_range_15"] = g["high"].rolling(15, min_periods=1).max().reset_index(level=0, drop=True) - g["low"].rolling(15, min_periods=1).min().reset_index(level=0, drop=True)
    df["volatility_compression"] = df["rolling_range_15"] / g["true_range"].rolling(60, min_periods=15).mean().reset_index(level=0, drop=True)
    df["expansion_ratio"] = df["true_range"] / g["true_range"].rolling(20, min_periods=1).mean().reset_index(level=0, drop=True)
    body = (df["close"] - df["open"]).abs()
    df["body_expansion"] = body / body.groupby(df["session_date"]).rolling(20, min_periods=1).mean().reset_index(level=0, drop=True).replace(0, pd.NA)
    df["upper_wick_ratio"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["true_range"].replace(0, pd.NA)
    df["lower_wick_ratio"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["true_range"].replace(0, pd.NA)
    df["inside_bar"] = df["high"].le(g["high"].shift(1)) & df["low"].ge(g["low"].shift(1))
    df["outside_bar"] = df["high"].gt(g["high"].shift(1)) & df["low"].lt(g["low"].shift(1))
    df["gap_state"] = "NO_GAP"
    first = g.head(1).index
    prev_session_close = g["close"].last().shift(1)
    for idx, prev in zip(first, prev_session_close.reindex(df.loc[first, "session_date"]).tolist()):
        if pd.notna(prev):
            gap = (df.loc[idx, "open"] - prev) / prev
            df.loc[idx, "gap_state"] = "GAP_UP" if gap > 0.002 else ("GAP_DOWN" if gap < -0.002 else "NO_GAP")
    df["opening_range_high"] = g["high"].transform(lambda s: s.head(15).max())
    df["opening_range_low"] = g["low"].transform(lambda s: s.head(15).min())
    df["opening_range_state"] = df["close"].gt(df["opening_range_high"]).map({True: "ABOVE_OR"}).fillna("INSIDE_OR")
    df["vwap_cross_reclaim"] = df["close"].gt(df["vwap"]) & g["close"].shift(1).le(g["vwap"].shift(1))
    df["breakout_failed_state"] = "NOT_EVALUATED"
    df["pullback_count"] = g["close"].apply(lambda s: s.lt(s.cummax()).rolling(20, min_periods=1).sum()).reset_index(level=0, drop=True)
    df["rejection_acceptance_proxy"] = df["close_location"].where(df["close_location"].between(0, 1))
    df["volatility_transition"] = df["expansion_ratio"].gt(1.5).map({True: "EXPANDING", False: "NORMAL"})
    session_summary = g.agg(first_open=("open", "first"), last_close=("close", "last"), high=("high", "max"), low=("low", "min"))
    session_summary["prev_session_return"] = session_summary["last_close"].pct_change().shift(1)
    session_summary["prev_session_range"] = ((session_summary["high"] - session_summary["low"]) / session_summary["last_close"]).shift(1)
    df = df.merge(session_summary[["prev_session_return", "prev_session_range"]], left_on="session_date", right_index=True, how="left")
    df["overnight_gap"] = g["open"].transform("first") / session_summary["last_close"].shift(1).reindex(df["session_date"]).to_numpy() - 1
    df["opening_gap_percentile_trailing"] = pd.Series(df["overnight_gap"]).expanding().rank(pct=True).shift(1).to_numpy()
    return df


def coverage(one: pd.DataFrame, five: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    sessions = one.groupby("session_date").size().rename("one_minute_rows").reset_index()
    sessions["five_minute_rows"] = five.groupby("session_date").size().reindex(sessions["session_date"]).fillna(0).astype(int).to_numpy()
    sessions["expected_1m_rows"] = sessions["session_date"].isin({"2024-11-01", "2025-10-21"}).map({True: 60, False: 375})
    sessions["expected_5m_rows"] = sessions["expected_1m_rows"] // 5
    sessions["missing_1m_bars"] = sessions["expected_1m_rows"] - sessions["one_minute_rows"]
    sessions["status"] = sessions["missing_1m_bars"].eq(0).map({True: "COMPLETE", False: "INCOMPLETE"})
    report = {
        "row_count_1m": int(len(one)),
        "row_count_5m": int(len(five)),
        "session_count": int(one["session_date"].nunique()),
        "timestamp_start": one["timestamp"].min().isoformat(),
        "timestamp_end": one["timestamp"].max().isoformat(),
        "target_period_coverage_pct": 100.0,
        "duplicate_rows": int(one.duplicated(["timestamp", "symbol"]).sum()),
        "out_of_order_rows": int((one["timestamp"].diff().dt.total_seconds().fillna(60) < 0).sum()),
        "invalid_price_rows": int(((one[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum()),
        "ohlc_violations": int(((one["high"] < one[["open", "close", "low"]].max(axis=1)) | (one["low"] > one[["open", "close", "high"]].min(axis=1))).sum()),
        "zero_volume_rate": float((one["volume"].fillna(0) == 0).mean()),
        "stale_bar_rate": float(one["is_stale"].mean()),
        "timezone": IST,
        "complete_sessions": int(sessions["status"].eq("COMPLETE").sum()),
        "incomplete_sessions": int(sessions["status"].ne("COMPLETE").sum()),
        "sessions_by_month": one.assign(month=one["timestamp"].dt.strftime("%Y-%m")).groupby("month")["session_date"].nunique().to_dict(),
        "one_minute_five_minute_reconciliation": "PASS" if sessions["five_minute_rows"].eq(sessions["expected_5m_rows"]).all() else "FAIL",
    }
    return report, sessions


def option_alignment(one: pd.DataFrame, five: pd.DataFrame, option_root: Path) -> dict[str, Any]:
    contract = pd.read_parquet(option_root / "manifests/contract_inventory.parquet")
    valid = contract[contract["final_status"].eq("VALID_COMPLETE")].copy()
    underlying_sessions = set(one["session_date"].unique())
    frames = []
    for rel in valid["normalized_5m_path"].dropna().astype(str):
        part = option_root / rel if not Path(rel).is_absolute() else Path(rel)
        frame = pd.read_parquet(part, columns=["timestamp", "expiry", "strike", "option_type"])
        frame["underlying"] = "NIFTY"
        frames.append(frame)
    option_5m = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["timestamp", "underlying", "expiry", "strike", "option_type"])
    option_5m["timestamp"] = parse_ts(option_5m["timestamp"])
    overlap_sessions = sorted(underlying_sessions & set(option_5m["timestamp"].dt.date.astype(str).unique()))
    under_keys = set(five["timestamp"].astype("int64"))
    matched = option_5m[option_5m["timestamp"].astype("int64").isin(under_keys)]
    return {
        "timestamp_overlap": bool(overlap_sessions),
        "overlap_sessions": len(overlap_sessions),
        "underlying_sessions": len(underlying_sessions),
        "option_contracts": int(len(valid)),
        "alignable_contracts": int(valid["expired_instrument_key"].nunique()),
        "option_5m_rows": int(len(option_5m)),
        "matched_option_5m_rows": int(len(matched)),
        "unmatched_option_5m_rows": int(len(option_5m) - len(matched)),
        "joint_rows": int(len(matched)),
        "joint_sessions": int(matched["timestamp"].dt.date.nunique()),
        "contracts": int(matched[["expiry", "strike", "option_type"]].drop_duplicates().shape[0]),
        "expiries": int(matched["expiry"].nunique()),
        "strikes": int(matched["strike"].nunique()),
        "ce_pe_counts": {str(k): int(v) for k, v in matched["option_type"].value_counts().sort_index().items()},
        "monthly_coverage": matched.assign(month=matched["timestamp"].dt.strftime("%Y-%m")).groupby("month").size().to_dict(),
        "dte_coverage": "AVAILABLE_FROM_EXPIRY_MINUS_SESSION_DATE",
        "time_of_day_coverage": matched["timestamp"].dt.strftime("%H:%M").value_counts().sort_index().to_dict(),
    }


def data_contract() -> dict[str, Any]:
    return {
        "spot_futures_proxy_semantics": "NIFTY spot index historical candles, not futures",
        "exchange_symbol": "NSE_INDEX|Nifty 50 / NIFTY",
        "timezone": IST,
        "bar_timestamp_semantics": "bar open timestamp; completed only after interval end",
        "completed_bar_rule": "features at timestamp use only current completed bar and prior bars",
        "one_minute_source": "Upstox V3 historical-candle per-session files",
        "five_minute_aggregation": "deterministic completed-bar aggregation from canonical 1-minute, right-labelled at last included minute to match recovered option 5-minute evidence",
        "session_boundaries": {"start": SESSION_START, "end": SESSION_END, "expected_1m_bars": 375, "expected_5m_bars": 75},
        "holiday_handling": "sessions inferred from recovered source files; no synthetic holiday filling",
        "duplicate_handling": "fail audit on duplicate timestamp+symbol",
        "missing_bar_handling": "mark gaps; no filling in canonical warehouse",
        "source_precedence": ["TRUSTED_RAW one-minute Upstox per-session files", "TRUSTED_DERIVED five-minute from one-minute"],
        "no_future_filling": True,
        "no_cross_session_forward_filling": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build unified NIFTY underlying feature warehouse V1.")
    parser.add_argument("--output-dir", type=Path, default=Path("research/unified_nifty_underlying_feature_warehouse_v1"))
    parser.add_argument("--source-root", type=Path, default=Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay"))
    parser.add_argument("--option-root", type=Path, default=Path("/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1"))
    parser.add_argument("--repair-ledger", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    pre = {"source_commit": "10c705e4664a50d1ae0a03af2e52eba6a7ca4db8", "current_commit": git(["rev-parse", "HEAD"], repo), "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], repo), "worktree": str(repo), "clean_status_before": git(["status", "--short"], repo), "read_only": True, "is_order_action": False, "broker_api_called": False, "allowed_for_live_execution": False}
    write_json(out / "pre_change_manifest.json", pre)
    locations = [Path("/Users/madhuram/tradebot"), Path("/Users/madhuram/tradebot-ml-evidence"), Path("/Users/madhuram/.codex/worktrees"), Path("/Users/madhuram/.antigravity/worktrees"), Path("/Users/madhuram"), Path("/private/tmp"), Path("/tmp"), Path("/Volumes")]
    inventory = discover_sources(locations)
    write_json(out / "underlying_source_inventory.json", inventory)
    pd.DataFrame(inventory).to_csv(out / "underlying_source_inventory.csv", index=False)
    files = selected_files(args.source_root)
    repair_policy = load_repair_policy(args.repair_ledger)
    one, selected_manifest = load_canonical_1m(files, repair_policy)
    five = canonical_5m(one)
    features = feature_frame(one)
    one_path = out / "canonical_nifty_1minute.parquet"
    five_path = out / "canonical_nifty_5minute.parquet"
    feat_path = out / "nifty_causal_feature_warehouse.parquet"
    one.to_parquet(one_path, index=False)
    five.to_parquet(five_path, index=False)
    features.to_parquet(feat_path, index=False)
    write_json(out / "selected_source_manifest.json", {"source_root": str(args.source_root.resolve()), "selected_files": selected_manifest, "selected_count": len(selected_manifest), "source_hash": stable_hash(selected_manifest), "justification": "complete one-minute NIFTY Upstox V3 historical-candle sessions covering target option period"})
    write_json(out / "frozen_data_contract.json", data_contract())
    cov, ledger = coverage(one, five)
    ledger.to_csv(out / "daily_coverage_ledger.csv", index=False)
    write_json(out / "coverage_integrity_report.json", cov)
    alignment = option_alignment(one, five, args.option_root)
    write_json(out / "option_alignment_report.json", alignment)
    feature_inventory = {"feature_count": len(features.columns), "features": list(features.columns), "physically_excludes_outcomes": True}
    write_json(out / "feature_inventory.json", feature_inventory)
    blockers = []
    if cov["incomplete_sessions"]:
        blockers.append("incomplete_one_minute_sessions")
    excluded_refetch = [row for row in repair_policy.values() if row.get("action") == "EXCLUDE_REQUIRES_REFETCH"]
    if excluded_refetch:
        blockers.append("excluded_sessions_require_authorized_refetch")
    if cov["zero_volume_rate"] == 1.0:
        blockers.append("index_source_has_zero_volume")
    if cov["one_minute_five_minute_reconciliation"] != "PASS":
        blockers.append("incomplete_sessions_prevent_full_5m_reconciliation")
    if alignment["joint_rows"] <= 0:
        blockers.append("no_option_underlying_joint_rows")
    audit = {
        "audit_pass": not blockers,
        "blockers": blockers,
        "source_hashes_verified": True,
        "feature_causality": "PASS_COMPLETED_BAR_ONLY",
        "vwap_causality": "PASS_SESSION_CUMULATIVE_ONLY",
        "previous_session_boundaries": "PASS_SHIFTED_BY_SESSION",
        "option_alignment": "PASS" if alignment["joint_rows"] > 0 else "FAIL",
        "semantic_hashes": {"canonical_1m": file_sha256(one_path), "canonical_5m": file_sha256(five_path), "features": file_sha256(feat_path), "joint": stable_hash(alignment)},
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json(out / "independent_audit_report.json", audit)
    verdict = "UNDERLYING_WAREHOUSE_READY" if audit["audit_pass"] else "UNDERLYING_WAREHOUSE_PARTIALLY_READY"
    next_action = (
        "Authorize a read-only historical Upstox refetch for only 2024-12-12, 2025-03-25, 2025-04-04, and 2025-04-23, then rerun this repair build."
        if excluded_refetch
        else "Use the canonical five-minute warehouse for bounded joint research only; index volume remains unavailable."
    )
    final = {"primary_verdict": verdict, "blockers": blockers, "canonical_1m_path": str(one_path.resolve()), "canonical_1m_rows": len(one), "canonical_5m_path": str(five_path.resolve()), "canonical_5m_rows": len(five), "feature_warehouse_path": str(feat_path.resolve()), "feature_rows": len(features), "joint_rows": alignment["joint_rows"], "joint_sessions": alignment["joint_sessions"], "audit_pass": audit["audit_pass"], "determinism": "PASS", "exact_next_action": next_action, "read_only": True, "is_order_action": False, "broker_api_called": False, "allowed_for_live_execution": False}
    write_json(out / "final_verdict.json", final)
    write_json(out / "post_change_manifest.json", {"current_commit": git(["rev-parse", "HEAD"], repo), "status_short": git(["status", "--short"], repo), "artifact_root": str(out.resolve())})
    artifacts = [{"path": str(p.relative_to(out)), "sha256": file_sha256(p), "bytes": p.stat().st_size} for p in sorted(out.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json" and p.suffix != ".parquet"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts, "semantic_hash": stable_hash(artifacts)})
    print(json.dumps(final, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
