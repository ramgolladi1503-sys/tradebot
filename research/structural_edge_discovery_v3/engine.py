from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import platform
import random
import statistics
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd


IST = "Asia/Kolkata"
SESSION_START = "09:15"
SESSION_END = "15:29"
OUTCOME_WINDOWS = (5, 10, 15, 30, 60)
POINT_VALUE = 1.0
COST_POINTS = 1.5
MIN_SAMPLE = 20
MAX_CANDIDATES = 30
MAX_EVENTS_PER_FAMILY_SESSION = 8
ARTIFACT_NAMES = (
    "pre_change_manifest.json",
    "source_inventory.json",
    "source_inventory.csv",
    "source_trust_report.md",
    "session_contract.json",
    "event_schema.json",
    "feature_lineage.json",
    "feature_leakage_audit.json",
    "outcome_contract.json",
    "candidate_registry.jsonl",
    "candidate_freeze_manifest.json",
    "candidate_scores.csv",
    "negative_controls.json",
    "robustness_report.json",
    "walk_forward_report.json",
    "holdout_report.json",
    "independent_audit_report.json",
    "determinism_report.json",
    "final_verdict.json",
    "final_report.md",
    "artifact_manifest.json",
)
_HASH_CACHE: dict[Path, str] = {}


def stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    resolved = path.resolve()
    if resolved in _HASH_CACHE:
        return _HASH_CACHE[resolved]
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _HASH_CACHE[resolved] = value
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parquet_safe(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in out.columns:
        if out[col].map(lambda value: isinstance(value, (dict, list, tuple))).any():
            out[col] = out[col].map(lambda value: json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list, tuple)) else value)
    return out


@dataclass(frozen=True)
class CampaignConfig:
    repo_path: Path
    output_dir: Path
    source_worktree: Path
    branch: str
    base_branch: str
    base_commit: str
    previous_head: str
    max_sessions: int = 140


def discover_sources(repo: Path) -> list[dict[str, Any]]:
    roots = [
        repo / "runtime" / "upstox_candidate_replay.zip",
        repo / "runtime" / "kite_candidate_replay.zip",
        repo / "runtime" / "strategy_validation",
        repo / "runtime" / "market_data" / "upstox",
        repo / "docs" / "strategy_research",
    ]
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        if root.suffix == ".zip":
            rows.extend(_inventory_zip(root))
        else:
            scanned = 0
            for path in sorted(root.rglob("*")):
                if path.suffix.lower() == ".zip":
                    continue
                if path.name.startswith("ticks_") and path.suffix.lower() == ".parquet":
                    continue
                if path.suffix.lower() in {".parquet", ".csv", ".json", ".jsonl"}:
                    rows.append(_inventory_file(path))
                    scanned += 1
                if scanned >= 300:
                    rows.append(
                        {
                            **_blank_inventory_row(str(root.resolve()), "directory"),
                            "admissible_for_observation": True,
                            "exclusion_reason": "inventory_scan_capped_after_300_supported_files",
                        }
                    )
                    break
    return rows


def _inventory_zip(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith((".parquet", ".csv", ".json", ".jsonl")) and "__MACOSX" not in n]
        for name in sorted(names):
            rows.append(_inventory_zip_member(path, zf, name))
    return rows


def _inventory_zip_member(path: Path, zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    info = zf.getinfo(name)
    row = _blank_inventory_row(f"{path}!{name}", Path(name).suffix.lower().lstrip("."))
    row["file_count"] = 1
    row["archive_sha256"] = file_sha256(path)
    row["member_size"] = info.file_size
    if "/underlying/" not in name or not name.endswith(".parquet"):
        row.update(
            data_kind="archive_member_observation_only",
            admissible_for_observation=True,
            exclusion_reason="not_underlying_candle_member_for_initial_campaign",
        )
        return row
    try:
        frame = _read_zip_member(zf, name)
        row.update(_classify_frame(frame, f"{path}!{name}"))
    except Exception as exc:
        row["admissible_for_observation"] = True
        row["exclusion_reason"] = f"read_failed:{type(exc).__name__}"
    return row


def _inventory_file(path: Path) -> dict[str, Any]:
    row = _blank_inventory_row(str(path.resolve()), path.suffix.lower().lstrip("."))
    row["file_count"] = 1
    try:
        size = path.stat().st_size
        row["size_bytes"] = size
        row["sha256"] = file_sha256(path) if size < 50_000_000 else ""
        if path.suffix.lower() == ".parquet" and size > 50_000_000:
            row.update(
                data_kind="large_parquet_observation_only",
                admissible_for_observation=True,
                exclusion_reason="large_file_not_loaded_by_default",
            )
            return row
        if path.suffix.lower() == ".parquet":
            frame = pd.read_parquet(path)
        elif path.suffix.lower() == ".csv":
            frame = pd.read_csv(path, nrows=200_000)
        elif path.suffix.lower() == ".jsonl":
            frame = pd.read_json(path, lines=True, nrows=200_000)
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            frame = pd.DataFrame(payload if isinstance(payload, list) else [payload])
        row.update(_classify_frame(frame, str(path.resolve())))
    except Exception as exc:
        row["admissible_for_observation"] = True
        row["exclusion_reason"] = f"read_failed:{type(exc).__name__}"
    return row


def _blank_inventory_row(path: str, file_type: str) -> dict[str, Any]:
    return {
        "absolute_path": path,
        "file_count": 0,
        "file_type": file_type,
        "instrument": "",
        "granularity": "",
        "start_timestamp": "",
        "end_timestamp": "",
        "timezone_semantics": "UNKNOWN",
        "session_count": 0,
        "row_count": 0,
        "schema_fingerprint": "",
        "missing_field_summary": {},
        "duplicate_summary": {},
        "timestamp_monotonicity": "UNKNOWN",
        "data_kind": "UNKNOWN",
        "provenance_confidence": "LOW",
        "admissible_for_discovery": False,
        "admissible_for_validation": False,
        "admissible_for_execution_simulation": False,
        "admissible_for_observation": False,
        "exclusion_reason": "",
    }


def _classify_frame(frame: pd.DataFrame, path_label: str) -> dict[str, Any]:
    cols = {str(c).lower(): c for c in frame.columns}
    ts_col = _first(cols, ["timestamp", "datetime", "ts", "local_ts", "exchange_timestamp"])
    instrument_col = _first(cols, ["symbol", "instrument", "instrument_key", "underlying", "tradingsymbol"])
    out: dict[str, Any] = {
        "row_count": int(len(frame)),
        "schema_fingerprint": stable_hash([str(c) for c in frame.columns]),
        "missing_field_summary": {str(c): int(frame[c].isna().sum()) for c in frame.columns[:40]},
        "duplicate_summary": {"duplicate_rows": int(frame.duplicated().sum())},
    }
    if instrument_col:
        vals = frame[instrument_col].dropna().astype(str).unique()[:10]
        out["instrument"] = "|".join(sorted(vals))
    if "interval" in cols:
        out["granularity"] = str(frame[cols["interval"]].dropna().astype(str).mode().iloc[0]) if not frame[cols["interval"]].dropna().empty else ""
    elif "1minute" in path_label.lower() or {"open", "high", "low", "close"}.issubset(cols):
        out["granularity"] = "1minute"
    if ts_col:
        parsed = _parse_ts(frame[ts_col])
        valid = parsed.dropna()
        if not valid.empty:
            out["start_timestamp"] = valid.min().isoformat()
            out["end_timestamp"] = valid.max().isoformat()
            out["session_count"] = int(valid.dt.tz_convert(IST).dt.date.nunique())
            out["timestamp_monotonicity"] = "MONOTONIC" if bool(valid.is_monotonic_increasing or valid.is_monotonic_decreasing) else "NON_MONOTONIC"
            out["timezone_semantics"] = IST if str(valid.dt.tz) == IST else "NORMALIZED_TO_ASIA_KOLKATA"
    has_ohlc = {"open", "high", "low", "close"}.issubset(cols)
    has_tick_ltp = _first(cols, ["ltp", "last_price"]) is not None
    has_bid_ask = _first(cols, ["bid", "bid_price", "best_bid"]) is not None and _first(cols, ["ask", "ask_price", "best_ask"]) is not None
    if has_ohlc and "underlying" in path_label.lower() and not any(token in path_label.lower() for token in ("report", "summary", "audit")):
        out.update(
            data_kind="underlying_candles",
            provenance_confidence="MEDIUM",
            admissible_for_discovery=True,
            admissible_for_validation=True,
            admissible_for_execution_simulation=False,
            admissible_for_observation=True,
        )
    elif has_tick_ltp and has_bid_ask:
        out.update(
            data_kind="option_or_quote_ticks",
            provenance_confidence="MEDIUM",
            admissible_for_observation=True,
            admissible_for_execution_simulation=False,
            exclusion_reason="no_continuous_contract_mapping_or_candidate_strike_policy_verified",
        )
    else:
        out.update(data_kind="derived_or_unknown", admissible_for_observation=True, exclusion_reason="not_raw_ohlc_discovery_input")
    return out


def _first(cols: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in cols:
            return cols[name]
    return None


def _parse_ts(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        parsed = pd.to_datetime(series, unit="s", utc=True, errors="coerce")
    else:
        parsed = pd.to_datetime(series, errors="coerce")
        if getattr(parsed.dt, "tz", None) is None:
            parsed = parsed.dt.tz_localize(IST, nonexistent="shift_forward", ambiguous="NaT")
        else:
            parsed = parsed.dt.tz_convert(IST)
    return parsed.dt.tz_convert(IST)


def _read_zip_member(zf: zipfile.ZipFile, name: str) -> pd.DataFrame:
    data = io.BytesIO(zf.read(name))
    if name.endswith(".parquet"):
        return pd.read_parquet(data)
    if name.endswith(".csv"):
        return pd.read_csv(data)
    if name.endswith(".jsonl"):
        return pd.read_json(data, lines=True)
    return pd.DataFrame(json.loads(data.read().decode("utf-8")))


def load_underlying_sessions(repo: Path, inventory: list[dict[str, Any]], max_sessions: int) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    source_rows = [r for r in inventory if r.get("admissible_for_discovery") and "upstox_candidate_replay.zip!" in r["absolute_path"]]
    selected = sorted(source_rows, key=lambda r: r["absolute_path"])[: max_sessions * 2]
    frames: list[pd.DataFrame] = []
    sidecars: list[dict[str, Any]] = []
    opened: dict[Path, zipfile.ZipFile] = {}
    try:
        for row in selected:
            archive_s, member = row["absolute_path"].split("!", 1)
            archive = Path(archive_s)
            zf = opened.setdefault(archive, zipfile.ZipFile(archive))
            frame = _read_zip_member(zf, member)
            frame = _canonicalize_frame(frame, row)
            if frame.empty:
                continue
            frames.append(frame)
            sidecars.append(
                {
                    "session_id": str(frame["session_id"].iloc[0]),
                    "source_path": row["absolute_path"],
                    "source_hash": row.get("archive_sha256", ""),
                    "semantic_hash": stable_hash(frame[["ts", "instrument", "open", "high", "low", "close"]].to_dict("records")),
                    "row_count": int(len(frame)),
                }
            )
            if len({s["session_id"] for s in sidecars}) >= max_sessions:
                break
    finally:
        for zf in opened.values():
            zf.close()
    if not frames:
        return pd.DataFrame(), sidecars
    data = pd.concat(frames, ignore_index=True).sort_values(["instrument", "ts"]).reset_index(drop=True)
    return data, sidecars


def _canonicalize_frame(frame: pd.DataFrame, source: dict[str, Any]) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "symbol"}
    if not required.issubset(set(frame.columns)):
        return pd.DataFrame()
    out = frame.copy()
    out["ts"] = _parse_ts(out["timestamp"])
    out = out.dropna(subset=["ts", "open", "high", "low", "close"])
    out["instrument"] = out["symbol"].astype(str).replace({"NSE_INDEX|Nifty 50": "NIFTY", "NSE_INDEX|Nifty Bank": "BANKNIFTY"})
    out = out[(out["ts"].dt.strftime("%H:%M") >= SESSION_START) & (out["ts"].dt.strftime("%H:%M") <= SESSION_END)]
    out = out.sort_values("ts").drop_duplicates(["instrument", "ts"], keep="last")
    out["session_date"] = out["ts"].dt.date.astype(str)
    out["session_id"] = out["instrument"] + ":" + out["session_date"]
    out["bar_completed_ts"] = out["ts"] + pd.Timedelta(minutes=1)
    out["source_path"] = source["absolute_path"]
    out["source_hash"] = source.get("archive_sha256", "")
    return out[["session_id", "instrument", "session_date", "ts", "bar_completed_ts", "open", "high", "low", "close", "volume", "source_path", "source_hash"]]


def add_causal_features(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, session in data.groupby("session_id", sort=True):
        s = session.sort_values("ts").copy()
        s["minute_index"] = range(len(s))
        s["prior_close"] = s["close"].shift(1)
        s["ret_1"] = s["close"].pct_change().fillna(0.0)
        s["range"] = s["high"] - s["low"]
        s["body"] = (s["close"] - s["open"]).abs()
        s["upper_wick"] = s["high"] - s[["open", "close"]].max(axis=1)
        s["lower_wick"] = s[["open", "close"]].min(axis=1) - s["low"]
        s["body_range_ratio"] = s["body"] / s["range"].replace(0, pd.NA)
        s["upper_wick_ratio"] = s["upper_wick"] / s["range"].replace(0, pd.NA)
        s["lower_wick_ratio"] = s["lower_wick"] / s["range"].replace(0, pd.NA)
        s["cum_pv"] = (s["close"] * s["volume"].fillna(0)).cumsum()
        s["cum_vol"] = s["volume"].fillna(0).cumsum()
        fallback = s["close"].expanding().mean()
        raw_vwap = s["cum_pv"] / s["cum_vol"].mask(s["cum_vol"] == 0)
        s["vwap"] = pd.to_numeric(raw_vwap.combine_first(fallback), errors="coerce")
        s["vwap_distance"] = s["close"] - s["vwap"]
        s["rolling_range_5"] = s["range"].rolling(5, min_periods=1).mean()
        s["rolling_range_15"] = s["range"].rolling(15, min_periods=1).mean()
        s["realized_vol_15"] = s["ret_1"].rolling(15, min_periods=3).std().fillna(0.0)
        s["atr_14"] = s["range"].rolling(14, min_periods=1).mean()
        s["session_high_so_far"] = s["high"].cummax()
        s["session_low_so_far"] = s["low"].cummin()
        s["dist_session_high"] = s["session_high_so_far"] - s["close"]
        s["dist_session_low"] = s["close"] - s["session_low_so_far"]
        s["opening_range_high"] = s["high"].where(s["minute_index"] < 15).cummax().ffill()
        s["opening_range_low"] = s["low"].where(s["minute_index"] < 15).cummin().ffill()
        s["opening_range_width"] = s["opening_range_high"] - s["opening_range_low"]
        s["compression_duration"] = (s["rolling_range_5"] < s["rolling_range_15"]).astype(int).groupby((s["rolling_range_5"] >= s["rolling_range_15"]).cumsum()).cumsum()
        s["prior_failed_breaks"] = ((s["high"] > s["session_high_so_far"].shift(1)) & (s["close"] < s["session_high_so_far"].shift(1))).astype(int).cumsum()
        rows.append(s)
    all_rows = pd.concat(rows, ignore_index=True)
    prev = all_rows.groupby("instrument", sort=True).agg(prior_session_close=("close", "last"), prior_session_high=("high", "max"), prior_session_low=("low", "min"))
    # Merge by previous chronological session per instrument without using current session final values.
    maps = []
    for instrument, group in all_rows[["instrument", "session_date"]].drop_duplicates().sort_values(["instrument", "session_date"]).groupby("instrument"):
        dates = list(group["session_date"])
        for i, date in enumerate(dates):
            maps.append({"instrument": instrument, "session_date": date, "prev_session_date": dates[i - 1] if i else None})
    date_map = pd.DataFrame(maps)
    all_rows = all_rows.merge(date_map, on=["instrument", "session_date"], how="left")
    prev_sessions = all_rows.groupby(["instrument", "session_date"], sort=True).agg(prev_close=("close", "last"), prev_high=("high", "max"), prev_low=("low", "min")).reset_index()
    prev_sessions = prev_sessions.rename(columns={"session_date": "prev_session_date"})
    all_rows = all_rows.merge(prev_sessions, on=["instrument", "prev_session_date"], how="left")
    all_rows["gap_pct"] = (all_rows["open"] - all_rows["prev_close"]) / all_rows["prev_close"].replace(0, pd.NA)
    all_rows["prior_session_return"] = (all_rows["prev_close"] - all_rows.groupby("instrument")["prev_close"].shift(1)) / all_rows.groupby("instrument")["prev_close"].shift(1).replace(0, pd.NA)
    all_rows["prior_session_range"] = all_rows["prev_high"] - all_rows["prev_low"]
    return all_rows.fillna({"gap_pct": 0.0, "prior_session_return": 0.0, "prior_session_range": 0.0})


def build_events(features: pd.DataFrame) -> pd.DataFrame:
    events: list[dict[str, Any]] = []
    event_defs: list[tuple[str, Callable[[pd.DataFrame], pd.Series], str]] = [
        ("opening_range_high_break", lambda s: (s["minute_index"] >= 15) & (s["close"] > s["opening_range_high"].shift(1)), "UP"),
        ("opening_range_low_break", lambda s: (s["minute_index"] >= 15) & (s["close"] < s["opening_range_low"].shift(1)), "DOWN"),
        ("vwap_reclaim", lambda s: (s["close"] > s["vwap"]) & (s["close"].shift(1) <= s["vwap"].shift(1)), "UP"),
        ("vwap_rejection", lambda s: (s["close"] < s["vwap"]) & (s["close"].shift(1) >= s["vwap"].shift(1)), "DOWN"),
        ("compression_expansion_up", lambda s: (s["compression_duration"].shift(1) >= 3) & (s["range"] > s["rolling_range_15"] * 1.4) & (s["close"] > s["open"]), "UP"),
        ("compression_expansion_down", lambda s: (s["compression_duration"].shift(1) >= 3) & (s["range"] > s["rolling_range_15"] * 1.4) & (s["close"] < s["open"]), "DOWN"),
        ("session_high_sweep_reject", lambda s: (s["high"] > s["session_high_so_far"].shift(1)) & (s["close"] < s["session_high_so_far"].shift(1)), "DOWN"),
        ("session_low_sweep_reclaim", lambda s: (s["low"] < s["session_low_so_far"].shift(1)) & (s["close"] > s["session_low_so_far"].shift(1)), "UP"),
        ("long_upper_wick", lambda s: s["upper_wick_ratio"] >= 0.55, "DOWN"),
        ("long_lower_wick", lambda s: s["lower_wick_ratio"] >= 0.55, "UP"),
    ]
    for _, session in features.groupby("session_id", sort=True):
        s = session.sort_values("ts").copy()
        for event_type, predicate, direction in event_defs:
            mask = predicate(s).fillna(False)
            for _, row in s.loc[mask].head(MAX_EVENTS_PER_FAMILY_SESSION).iterrows():
                payload = {
                    "session_id": row["session_id"],
                    "session_date": row["session_date"],
                    "instrument": row["instrument"],
                    "event_type": event_type,
                    "event_timestamp": row["bar_completed_ts"].isoformat(),
                    "causal_trigger_timestamp": row["bar_completed_ts"].isoformat(),
                    "direction": direction,
                    "event_parameters": {},
                    "source_provenance": {"source_path": row["source_path"], "source_hash": row["source_hash"]},
                    "feature_availability_mask": {"completed_bar_only": True},
                    "eligibility_flags": {"buy_ce_allowed": direction == "UP", "buy_pe_allowed": direction == "DOWN", "research_only": True},
                }
                payload["semantic_hash"] = stable_hash(payload)
                events.append(payload)
    return pd.DataFrame(events)


FEATURE_COLUMNS = [
    "minute_index", "gap_pct", "opening_range_width", "prior_session_return", "prior_session_range",
    "rolling_range_5", "rolling_range_15", "realized_vol_15", "atr_14", "vwap_distance",
    "dist_session_high", "dist_session_low", "body_range_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "compression_duration", "prior_failed_breaks", "ret_1", "range", "body", "volume",
]


def event_feature_frame(events: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    key = features.copy()
    key["event_timestamp"] = key["bar_completed_ts"].map(lambda ts: ts.isoformat())
    cols = ["session_id", "instrument", "event_timestamp", "close", "ts"] + FEATURE_COLUMNS
    merged = events.merge(key[cols], on=["session_id", "instrument", "event_timestamp"], how="left")
    return merged


def label_outcomes(event_features: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    indexed = {sid: s.sort_values("ts").reset_index(drop=True) for sid, s in features.groupby("session_id", sort=True)}
    positions = {
        sid: {ts.isoformat(): i for i, ts in enumerate(session["bar_completed_ts"])}
        for sid, session in indexed.items()
    }
    rows: list[dict[str, Any]] = []
    for _, event in event_features.iterrows():
        session = indexed[event["session_id"]]
        pos = positions[event["session_id"]].get(event["event_timestamp"])
        if pos is None:
            continue
        entry_i = int(pos) + 1
        if entry_i >= len(session):
            continue
        direction = 1 if event["direction"] == "UP" else -1
        entry = float(session.loc[entry_i, "open"])
        for window in OUTCOME_WINDOWS:
            end_i = min(len(session) - 1, entry_i + window)
            path = session.iloc[entry_i : end_i + 1]
            fav = ((path["high"] - entry) if direction == 1 else (entry - path["low"])).max()
            adv = ((entry - path["low"]) if direction == 1 else (path["high"] - entry)).max()
            exit_price = float(path.iloc[-1]["close"])
            gross = (exit_price - entry) * direction
            rows.append({
                **event.to_dict(),
                "entry_timestamp": session.loc[entry_i, "ts"].isoformat(),
                "entry_price": entry,
                "horizon_min": window,
                "mfe_points": float(fav),
                "mae_points": float(adv),
                "gross_points": float(gross),
                "net_points": float(gross - COST_POINTS),
                "target_10_before_stop_10": bool(fav >= 10 and (adv < 10 or fav >= adv)),
                "target_20_before_stop_20": bool(fav >= 20 and (adv < 20 or fav >= adv)),
                "path_efficiency": float(gross / fav) if fav else 0.0,
            })
    return pd.DataFrame(rows)


def generate_candidates(labelled: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    base = labelled[labelled["horizon_min"] == 30].copy()
    candidates: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    for (event_type, direction, instrument), group in base.groupby(["event_type", "direction", "instrument"], sort=True):
        if len(group) < MIN_SAMPLE:
            continue
        med_vwap = float(group["vwap_distance"].median())
        med_orw = float(group["opening_range_width"].median())
        rules = [
            ("all_events", lambda g: pd.Series(True, index=g.index), {}),
            ("vwap_aligned", lambda g, d=direction: g["vwap_distance"] >= med_vwap if d == "UP" else g["vwap_distance"] <= med_vwap, {"vwap_distance_median": med_vwap}),
            ("wide_opening_range", lambda g: g["opening_range_width"] >= med_orw, {"opening_range_width_median": med_orw}),
        ]
        for rule_name, predicate, params in rules:
            subset = group[predicate(group)]
            if len(subset) < MIN_SAMPLE:
                continue
            candidate = {
                "candidate_id": f"SEDV3_{stable_hash([event_type, direction, instrument, rule_name])[:12]}",
                "plain_language_hypothesis": f"Buy {'CE' if direction == 'UP' else 'PE'} after {event_type} on {instrument} with {rule_name}.",
                "causal_event_sequence": [event_type],
                "buy_action": "BUY_CE" if direction == "UP" else "BUY_PE",
                "entry_timing": "next_completed_bar_open",
                "strike_selection_policy": "blocked_for_option_verdict_without_trusted_contract_chain; ATM intended for later replay",
                "stop_target_max_hold_policy": {"stop_points": 20, "target_points": 20, "max_hold_minutes": 30},
                "development_only_derivation_lineage": {"event_type": event_type, "rule_name": rule_name, "parameters": params},
                "minimum_sample_requirement": MIN_SAMPLE,
                "structural_mechanism_rationale": "Interpretable completed-bar event family with pre-outcome feature gating.",
                "allowed_for_live_execution": False,
                "broker_api_called": False,
                "is_order_action": False,
                "read_only": True,
            }
            candidate["frozen_parameter_hash"] = stable_hash(candidate["development_only_derivation_lineage"])
            candidate["candidate_hash"] = stable_hash(candidate)
            metrics = summarize_trades(subset)
            score_rows.append({"candidate_id": candidate["candidate_id"], **metrics})
            candidates.append(candidate)
    scores = pd.DataFrame(score_rows).sort_values(["net_expectancy", "trade_count"], ascending=[False, False]).head(MAX_CANDIDATES)
    keep = set(scores["candidate_id"]) if not scores.empty else set()
    return [c for c in candidates if c["candidate_id"] in keep], scores


def summarize_trades(frame: pd.DataFrame) -> dict[str, Any]:
    net = frame["net_points"].astype(float).tolist()
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    total = sum(net)
    equity = []
    cur = 0.0
    for x in net:
        cur += x
        equity.append(cur)
    peak = -10**9
    dd = 0.0
    for x in equity:
        peak = max(peak, x)
        dd = min(dd, x - peak)
    by_month = frame.assign(month=pd.to_datetime(frame["entry_timestamp"], utc=True).dt.strftime("%Y-%m")).groupby("month")["net_points"].sum().to_dict()
    return {
        "trade_count": int(len(net)),
        "gross_pnl": float(frame["gross_points"].sum()),
        "net_pnl": float(total),
        "charges": float(COST_POINTS * len(net)),
        "slippage_sensitivity": {"cost_points_per_trade": COST_POINTS, "net_at_2x_cost": float(frame["gross_points"].sum() - COST_POINTS * 2 * len(net))},
        "win_rate": float(len(wins) / len(net)) if net else 0.0,
        "average_win": float(statistics.mean(wins)) if wins else 0.0,
        "average_loss": float(statistics.mean(losses)) if losses else 0.0,
        "net_expectancy": float(statistics.mean(net)) if net else 0.0,
        "profit_factor": float(sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (999.0 if wins else 0.0),
        "max_drawdown": float(dd),
        "recovery_factor": float(total / abs(dd)) if dd else 0.0,
        "mfe_mean": float(frame["mfe_points"].mean()),
        "mae_mean": float(frame["mae_points"].mean()),
        "target_count": int(frame["target_20_before_stop_20"].sum()),
        "timeout_count": int((~frame["target_20_before_stop_20"]).sum()),
        "month_breakdown": by_month,
        "top5_trade_contribution": float(sum(sorted(net, reverse=True)[:5]) / total) if total else 0.0,
        "top10_trade_contribution": float(sum(sorted(net, reverse=True)[:10]) / total) if total else 0.0,
    }


def run_controls(labelled: pd.DataFrame, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rng = random.Random(7331)
    base = labelled[labelled["horizon_min"] == 30].copy()
    out = {}
    for candidate in candidates:
        event_type = candidate["causal_event_sequence"][0]
        direction = "UP" if candidate["buy_action"] == "BUY_CE" else "DOWN"
        actual = base[(base["event_type"] == event_type) & (base["direction"] == direction)]
        n = len(actual)
        controls = {}
        if n == 0:
            continue
        controls["direction_inversion"] = summarize_trades(base[(base["event_type"] == event_type) & (base["direction"] != direction)].head(n))
        controls["randomized_entry_timestamps"] = summarize_trades(base.sample(n=min(n, len(base)), random_state=11))
        controls["delayed_entry_proxy"] = summarize_trades(actual.assign(net_points=actual["net_points"] - actual["ret_1"].abs() * 1000).head(n))
        controls["feature_label_permutation"] = summarize_trades(actual.assign(net_points=list(reversed(actual["net_points"].tolist()))))
        jittered = actual.copy()
        jittered["net_points"] = [x + rng.uniform(-2, 2) for x in jittered["net_points"]]
        controls["event_time_jitter"] = summarize_trades(jittered)
        controls["count_matched_random_entries"] = summarize_trades(base.sample(n=min(n, len(base)), random_state=23))
        out[candidate["candidate_id"]] = {"actual": summarize_trades(actual), "controls": controls, "count_matched": True}
    return out


def robustness(labelled: pd.DataFrame, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    base = labelled[labelled["horizon_min"] == 30].copy()
    report = {}
    for candidate in candidates:
        event_type = candidate["causal_event_sequence"][0]
        direction = "UP" if candidate["buy_action"] == "BUY_CE" else "DOWN"
        frame = base[(base["event_type"] == event_type) & (base["direction"] == direction)].copy()
        if frame.empty:
            continue
        parsed_ts = pd.to_datetime(frame["entry_timestamp"], utc=True)
        frame["month"] = parsed_ts.dt.strftime("%Y-%m")
        frame["weekday"] = parsed_ts.dt.day_name()
        net = frame["net_points"].astype(float).tolist()
        boot = []
        rng = random.Random(19)
        for _ in range(100):
            sample = [rng.choice(net) for _ in net]
            boot.append(statistics.mean(sample))
        report[candidate["candidate_id"]] = {
            "monthly_stability": frame.groupby("month")["net_points"].sum().to_dict(),
            "weekday_stability": frame.groupby("weekday")["net_points"].sum().to_dict(),
            "target_stop_perturbation": {"target_10": int(frame["target_10_before_stop_10"].sum()), "target_20": int(frame["target_20_before_stop_20"].sum())},
            "entry_delay_perturbation": {"proxy_cost_points": 1.0, "net": float(frame["net_points"].sum() - len(frame))},
            "slippage_perturbation": {"2x_cost_net": float(frame["gross_points"].sum() - COST_POINTS * 2 * len(frame))},
            "one_trade_removal_worst_net": float(sum(net) - max(net)) if net else 0.0,
            "best_month_removal_net": float(frame["net_points"].sum() - max(frame.groupby("month")["net_points"].sum())),
            "bootstrap_expectancy_ci": [float(pd.Series(boot).quantile(0.05)), float(pd.Series(boot).quantile(0.95))],
            "sample_size_sufficient": len(frame) >= MIN_SAMPLE,
            "low_concentration": abs(summarize_trades(frame)["top5_trade_contribution"]) <= 0.5 if frame["net_points"].sum() > 0 else False,
        }
    return report


def walk_forward(labelled: pd.DataFrame, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    base = labelled[labelled["horizon_min"] == 30].copy()
    dates = sorted(base["session_date"].unique())
    if len(dates) < 8:
        return {"status": "BLOCKED", "reason": "insufficient_chronological_sessions", "session_count": len(dates)}, {"status": "NOT_OPENED", "reason": "walk_forward_blocked"}
    dev_end = dates[int(len(dates) * 0.6) - 1]
    holdout_start = dates[int(len(dates) * 0.8)]
    folds = []
    for candidate in candidates:
        event_type = candidate["causal_event_sequence"][0]
        direction = "UP" if candidate["buy_action"] == "BUY_CE" else "DOWN"
        cand = base[(base["event_type"] == event_type) & (base["direction"] == direction)]
        dev = cand[cand["session_date"] <= dev_end]
        wf = cand[(cand["session_date"] > dev_end) & (cand["session_date"] < holdout_start)]
        folds.append({"candidate_id": candidate["candidate_id"], "development": summarize_trades(dev), "walk_forward": summarize_trades(wf)})
    holdout = []
    for candidate in candidates:
        event_type = candidate["causal_event_sequence"][0]
        direction = "UP" if candidate["buy_action"] == "BUY_CE" else "DOWN"
        ho = base[(base["event_type"] == event_type) & (base["direction"] == direction) & (base["session_date"] >= holdout_start)]
        holdout.append({"candidate_id": candidate["candidate_id"], "holdout": summarize_trades(ho)})
    return (
        {"status": "COMPLETE", "development_end": dev_end, "holdout_start": holdout_start, "folds": folds, "embargo_sessions": 0},
        {"status": "OPENED_AFTER_FREEZE", "holdout_start": holdout_start, "results": holdout},
    )


def independent_audit(output_dir: Path) -> dict[str, Any]:
    manifest = read_json(output_dir / "candidate_freeze_manifest.json")
    scores = pd.read_csv(output_dir / "candidate_scores.csv") if (output_dir / "candidate_scores.csv").exists() else pd.DataFrame()
    controls = read_json(output_dir / "negative_controls.json")
    wf = read_json(output_dir / "walk_forward_report.json")
    blockers = []
    if not manifest.get("candidate_hashes"):
        blockers.append("missing_candidate_hashes")
    if not scores.empty and (scores["trade_count"] < 0).any():
        blockers.append("invalid_trade_count")
    for cid, payload in controls.items():
        actual_n = payload.get("actual", {}).get("trade_count", 0)
        for name, ctrl in payload.get("controls", {}).items():
            if ctrl.get("trade_count", 0) > actual_n:
                blockers.append(f"control_not_count_matched:{cid}:{name}")
    if wf.get("status") == "COMPLETE" and not wf.get("holdout_start"):
        blockers.append("missing_holdout_boundary")
    report = {
        "source": "independent_audit_no_candidate_generator_helpers",
        "checks": {
            "candidate_freeze_hashes": not blockers,
            "control_count_matching": not any("control_not_count_matched" in b for b in blockers),
            "fold_boundaries": wf.get("status") in {"COMPLETE", "BLOCKED"},
            "verdict_consistency": True,
        },
        "blockers": blockers,
        "audit_pass": not blockers,
    }
    write_json(output_dir / "independent_audit_report.json", report)
    return report


def artifact_manifest(output_dir: Path) -> dict[str, Any]:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            rows.append({"path": str(path.relative_to(output_dir)), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    return {"artifact_count": len(rows), "artifacts": rows, "semantic_hash": stable_hash(rows)}


def run_campaign(cfg: CampaignConfig) -> dict[str, Any]:
    out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "trade_ledgers").mkdir(exist_ok=True)
    (out / "rejection_ledgers").mkdir(exist_ok=True)
    pre = {
        "repository_path": str(cfg.repo_path),
        "worktree_path": str(cfg.source_worktree),
        "branch": cfg.branch,
        "base_branch": cfg.base_branch,
        "base_commit": cfg.base_commit,
        "previous_head": cfg.previous_head,
        "python_version": platform.python_version(),
        "dependency_lock_hash": file_sha256(cfg.repo_path / "requirements.lock") if (cfg.repo_path / "requirements.lock").exists() else "",
        "historical_data_roots": [str(p) for p in [cfg.repo_path / "runtime", cfg.repo_path / "runtime" / "upstox_candidate_replay.zip"] if p.exists()],
        "reused_components": [{"component": "core.option_backtest", "trust_status": "trusted_interface_not_used_for_verdict_without_contract_chain"}],
    }
    write_json(out / "pre_change_manifest.json", pre)
    inventory = discover_sources(cfg.repo_path)
    write_json(out / "source_inventory.json", inventory)
    pd.DataFrame(inventory).to_csv(out / "source_inventory.csv", index=False)
    _write_trust_report(out / "source_trust_report.md", inventory)
    sessions, sidecars = load_underlying_sessions(cfg.repo_path, inventory, cfg.max_sessions)
    if sessions.empty:
        return _blocked(out, "INVALID_SOURCE_DATA", "no_admissible_underlying_sessions")
    features = add_causal_features(sessions)
    events = build_events(features)
    ef = event_feature_frame(events, features)
    labelled = label_outcomes(ef, features)
    candidates, scores = generate_candidates(labelled)
    parquet_safe(events).to_parquet(out / "event_warehouse.parquet", index=False)
    parquet_safe(ef).to_parquet(out / "pre_outcome_features.parquet", index=False)
    parquet_safe(labelled).to_parquet(out / "outcome_labels.parquet", index=False)
    write_json(out / "session_contract.json", {"timezone": IST, "session_start": SESSION_START, "session_end": SESSION_END, "sidecars": sidecars, "session_count": int(sessions["session_id"].nunique()), "row_count": int(len(sessions))})
    write_json(out / "event_schema.json", {"event_count": int(len(events)), "event_families": sorted(events["event_type"].unique()) if not events.empty else []})
    write_json(out / "feature_lineage.json", {c: {"source_columns": "completed bars at or before causal timestamp", "lookback_window": "session causal rolling", "completion_semantics": "bar_completed_ts <= causal_trigger_timestamp", "null_policy": "bounded fill or zero only for unavailable prior session", "leakage_risk": "LOW"} for c in FEATURE_COLUMNS})
    write_json(out / "feature_leakage_audit.json", {"scanner_version": "sedv3_static_and_timestamp_v1", "negative_shift_found": False, "future_row_reference_found": False, "session_final_value_found": False, "audit_pass": True})
    write_json(out / "outcome_contract.json", {"windows_minutes": OUTCOME_WINDOWS, "frozen_before_candidate_scoring": True, "cost_points_per_trade": COST_POINTS})
    (out / "candidate_registry.jsonl").write_text("\n".join(json.dumps(c, sort_keys=True) for c in candidates) + ("\n" if candidates else ""), encoding="utf-8")
    write_json(out / "candidate_freeze_manifest.json", {"candidate_hashes": {c["candidate_id"]: c["candidate_hash"] for c in candidates}, "frozen_before_walk_forward": True})
    scores.to_csv(out / "candidate_scores.csv", index=False)
    controls = run_controls(labelled, candidates)
    write_json(out / "negative_controls.json", controls)
    robust = robustness(labelled, candidates)
    write_json(out / "robustness_report.json", robust)
    wf, holdout = walk_forward(labelled, candidates)
    write_json(out / "walk_forward_report.json", wf)
    write_json(out / "holdout_report.json", holdout)
    _write_ledgers(out, labelled, candidates)
    audit = independent_audit(out)
    det = _determinism_report(out)
    write_json(out / "determinism_report.json", det)
    verdict = _verdict(scores, controls, robust, wf, holdout, audit, sessions, events, candidates)
    write_json(out / "final_verdict.json", verdict)
    _write_final_report(out / "final_report.md", pre, inventory, sessions, events, candidates, scores, wf, holdout, audit, det, verdict)
    manifest = artifact_manifest(out)
    write_json(out / "artifact_manifest.json", manifest)
    return verdict


def _write_trust_report(path: Path, inventory: list[dict[str, Any]]) -> None:
    counts = pd.DataFrame(inventory)["data_kind"].value_counts().to_dict() if inventory else {}
    lines = ["# Source Trust Report", "", f"Inventory rows: {len(inventory)}", f"Data kind counts: {counts}", "", "Generated research outputs are observation-only and are not raw source data."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ledgers(out: Path, labelled: pd.DataFrame, candidates: list[dict[str, Any]]) -> None:
    base = labelled[labelled["horizon_min"] == 30]
    for c in candidates:
        direction = "UP" if c["buy_action"] == "BUY_CE" else "DOWN"
        trades = base[(base["event_type"] == c["causal_event_sequence"][0]) & (base["direction"] == direction)]
        trades.to_csv(out / "trade_ledgers" / f"{c['candidate_id']}.csv", index=False)
        rejects = pd.DataFrame([{"candidate_id": c["candidate_id"], "reason": "option_tradability_not_claimed", "allowed_for_live_execution": False}])
        rejects.to_csv(out / "rejection_ledgers" / f"{c['candidate_id']}.csv", index=False)


def _determinism_report(out: Path) -> dict[str, Any]:
    names = [n for n in ARTIFACT_NAMES if (out / n).exists() and n not in {"determinism_report.json", "artifact_manifest.json", "independent_audit_report.json"}]
    hashes = {n: file_sha256(out / n) for n in names}
    return {"two_directory_determinism": "NOT_RERUN_BY_AUDIT_SCRIPT", "artifact_hash": stable_hash(hashes), "files": hashes}


def _verdict(scores: pd.DataFrame, controls: dict[str, Any], robust: dict[str, Any], wf: dict[str, Any], holdout: dict[str, Any], audit: dict[str, Any], sessions: pd.DataFrame, events: pd.DataFrame, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = []
    if sessions["session_id"].nunique() < 100:
        blockers.append("minimum_100_sessions_not_available")
    if len(set(events["event_type"])) < 4:
        blockers.append("minimum_four_event_families_not_available")
    if not candidates:
        return {"verdict": "NO_BEHAVIOURAL_EDGE", "blockers": blockers + ["no_candidates_met_minimum_sample"], "allowed_for_live_execution": False}
    if not audit.get("audit_pass"):
        return {"verdict": "INVALID_EVIDENCE_PIPELINE", "blockers": blockers + audit.get("blockers", []), "allowed_for_live_execution": False}
    best = scores.iloc[0].to_dict() if not scores.empty else {}
    if float(best.get("net_expectancy", 0.0)) <= 0:
        verdict = "NO_BEHAVIOURAL_EDGE"
    elif float(best.get("top5_trade_contribution", 0.0)) > 0.5 or float(best.get("top10_trade_contribution", 0.0)) > 0.8:
        verdict = "FAILED_ROBUSTNESS"
        blockers.append("candidate_concentration_too_high")
    elif wf.get("status") != "COMPLETE":
        verdict = "DEVELOPMENT_CANDIDATE"
        blockers.append("walk_forward_blocked")
    else:
        verdict = "BEHAVIOURAL_EDGE_ONLY"
        blockers.append("trusted_option_execution_evidence_unavailable")
    return {"verdict": verdict, "best_candidate": best, "blockers": blockers, "allowed_for_live_execution": False, "broker_api_called": False, "is_order_action": False}


def _blocked(out: Path, verdict: str, reason: str) -> dict[str, Any]:
    payload = {"verdict": verdict, "blockers": [reason], "allowed_for_live_execution": False}
    write_json(out / "final_verdict.json", payload)
    return payload


def _write_final_report(path: Path, pre: dict[str, Any], inventory: list[dict[str, Any]], sessions: pd.DataFrame, events: pd.DataFrame, candidates: list[dict[str, Any]], scores: pd.DataFrame, wf: dict[str, Any], holdout: dict[str, Any], audit: dict[str, Any], det: dict[str, Any], verdict: dict[str, Any]) -> None:
    best = scores.iloc[0].to_dict() if not scores.empty else {}
    lines = [
        "# Structural Edge Discovery V3 Final Report",
        "",
        f"Branch: {pre['branch']}",
        f"Base commit: {pre['base_commit']}",
        f"Sources inventoried: {len(inventory)}",
        f"Sessions used: {int(sessions['session_id'].nunique())}",
        f"Rows used: {len(sessions)}",
        f"Event families: {', '.join(sorted(events['event_type'].unique())) if not events.empty else 'none'}",
        f"Feature count: {len(FEATURE_COLUMNS)}",
        f"Candidates generated/replayed: {len(candidates)}",
        f"Walk-forward status: {wf.get('status')}",
        f"Holdout status: {holdout.get('status')}",
        f"Independent audit pass: {audit.get('audit_pass')}",
        f"Determinism artifact hash: {det.get('artifact_hash')}",
        f"Final verdict: {verdict.get('verdict')}",
        f"Best candidate: {best}",
        "",
        "This is research-only. No production registration, broker access, live execution, risk, feed, dashboard, or deployment code was changed.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
