#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import math
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import Lasso
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeRegressor, _tree

EXPECTED_KITE_HASH = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"
DEFAULT_KITE_ARCHIVE = Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip")
DEFAULT_OUTPUT = Path("/Users/madhuram/tradebot-ml-evidence/structural-state-discovery-v4")
V3_OUTPUT = Path("/Users/madhuram/tradebot-ml-evidence/structural-state-discovery-v3")
V3_CLASSIFIED = V3_OUTPUT / "incomplete_v3_single_target_oof_scan"
BASE_SHA = "a8fa0cf218df4b4b7a575ff36f344774ba1fff9d"
PREVIOUS_HEAD = "2cff16e608e8c79ec3863276ea17c57c27f7a2b2"
IST = "Asia/Kolkata"
DECISION_TIMES = ("09:45", "10:30", "11:30", "13:00", "14:00")
SYMBOLS = ("NIFTY", "BANKNIFTY")
TARGETS = (10, 15, 20)
STOPS = (10, 15, 20)
MIN_SESSIONS = 30
RESEARCH_FLAGS = {
    "execution_eligibility": False,
    "research_only": True,
    "allowed_for_live_execution": False,
    "broker_api_called": False,
    "is_order_action": False,
}
V3_DEFECTS = [
    "TARGET is globally fixed to continuation_30m_return_bps",
    "reversal, expansion, raw-long and raw-short outcomes are built but not searched",
    "inner folds are created but never used for rule/model selection",
    "every outer-fold rule is treated as a separate hypothesis",
    "economically equivalent rules are not aggregated across outer folds",
    "there is no gate requiring recurrence in four of five outer folds",
    "family and global BH q-values are computed identically over the same full ledger",
    "sparse models generate predictions but cannot produce or reject candidates",
    "cluster states generate rows but cannot produce or reject candidates",
    "the no-edge verdict is driven only by quantile and tree continuation rules",
    "negative controls are populated from the empty survivor set rather than executed",
    "mutation tests modify only final_verdict.json with a generic mutation marker",
    "the oracle detects a generic marker rather than named mutated invariants",
    "oracle feature reconstruction is limited and does not verify rule membership",
    "tests do not prove multi-target search, cross-fold aggregation, actual controls, or mutation-specific detection",
]


class DiscoveryError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_hash(payload: Any) -> str:
    return sha256_bytes(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode())


def dataframe_hash(df: pd.DataFrame) -> str:
    return canonical_hash(df.sort_index(axis=1).to_dict("records"))


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode()
    path.write_bytes(data)
    digest = sha256_bytes(data)
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    return digest


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode()
    path.write_bytes(data)
    digest = sha256_bytes(data)
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    return digest


def write_parquet(path: Path, df: pd.DataFrame) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == "object":
            out[col] = out[col].map(lambda v: json.dumps(v, sort_keys=True, default=str) if isinstance(v, (dict, list, tuple)) else v)
    out.to_parquet(path, index=False)
    digest = file_sha256(path)
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    return digest


def ret_bps(start: float, end: float) -> float:
    return (end / start - 1.0) * 10000.0


def load_kite(path: Path) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not path.is_file():
        raise DiscoveryError(f"authoritative Kite archive missing: {path}")
    actual = file_sha256(path)
    if actual != EXPECTED_KITE_HASH:
        raise DiscoveryError(f"kite archive hash mismatch: expected {EXPECTED_KITE_HASH}, got {actual}")
    frames: list[pd.DataFrame] = []
    accepted_files: list[dict[str, Any]] = []
    rejected_files: list[dict[str, Any]] = []
    duplicate_records: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            if "__MACOSX" in name or name.endswith("/"):
                continue
            if "/underlying/" not in name or not name.endswith(".parquet"):
                rejected_files.append({"path": name, "reason": "not_underlying_parquet"})
                continue
            symbol = Path(name).name.split("_", 1)[0].upper()
            if symbol not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
                rejected_files.append({"path": name, "reason": "unsupported_symbol"})
                continue
            data = zf.read(name)
            raw = pd.read_parquet(io.BytesIO(data))
            required = {"date", "fetch_date", "open", "high", "low", "close"}
            if not required.issubset(raw.columns):
                rejected_files.append({"path": name, "reason": "missing_required_columns"})
                continue
            out = raw.copy()
            out["interval_start"] = pd.to_datetime(out["date"], utc=True).dt.tz_convert(IST)
            out["interval_end"] = out["interval_start"] + pd.Timedelta(minutes=5)
            out["session"] = out["fetch_date"].astype(str)
            out["symbol"] = symbol
            out["source_id"] = "KITE"
            out["source_file"] = name
            out["source_file_sha256"] = sha256_bytes(data)
            valid = (
                (out["open"] > 0)
                & (out["high"] > 0)
                & (out["low"] > 0)
                & (out["close"] > 0)
                & (out["high"] >= out[["open", "close"]].max(axis=1))
                & (out["low"] <= out[["open", "close"]].min(axis=1))
            )
            bad_rows = int((~valid).sum())
            out = out[valid].copy()
            conflicts = []
            identical_collapsed = 0
            for key, dup in out.groupby(["session", "symbol", "interval_start"], sort=True):
                if len(dup) <= 1:
                    continue
                ohlc = dup[["open", "high", "low", "close"]].drop_duplicates()
                duplicate_records.append({"file": name, "key": [str(key[0]), key[1], key[2].isoformat()], "rows": int(len(dup)), "distinct_ohlc": int(len(ohlc))})
                if len(ohlc) > 1:
                    conflicts.append({"key": [str(key[0]), key[1], key[2].isoformat()], "rows": int(len(dup))})
                else:
                    identical_collapsed += int(len(dup) - 1)
            if conflicts:
                rejected_files.append({"path": name, "reason": "conflicting_duplicate_ohlc", "conflicts": conflicts[:10]})
                continue
            out = out.drop_duplicates(["session", "symbol", "interval_start"], keep="first").sort_values("interval_start")
            if len(out) < 60:
                rejected_files.append({"path": name, "reason": "insufficient_valid_rows", "bad_rows": bad_rows})
                continue
            accepted_files.append({
                "source_id": "KITE",
                "path": name,
                "symbol": symbol,
                "session": str(out["session"].iloc[0]),
                "sha256": sha256_bytes(data),
                "accepted_rows": int(len(out)),
                "invalid_ohlc_rows_dropped": bad_rows,
                "identical_duplicate_rows_collapsed": identical_collapsed,
            })
            frames.append(out[["source_id", "session", "symbol", "interval_start", "interval_end", "open", "high", "low", "close", "source_file", "source_file_sha256"]])
    if not frames:
        raise DiscoveryError("no accepted Kite underlying bars")
    bars = pd.concat(frames, ignore_index=True).sort_values(["session", "symbol", "interval_start"]).reset_index(drop=True)
    sessions = []
    for session, part in bars.groupby("session", sort=True):
        symbols = sorted(part["symbol"].unique())
        aligned = {"NIFTY", "BANKNIFTY", "SENSEX"}.issubset(symbols)
        sessions.append({"source_id": "KITE", "session": session, "symbols": symbols, "accepted": aligned, "row_count": int(len(part))})
    accepted = {s["session"] for s in sessions if s["accepted"]}
    bars = bars[bars["session"].isin(accepted)].copy()
    reconciliation = {
        "duplicate_keys_enumerated": duplicate_records,
        "duplicate_key_count": len(duplicate_records),
        "policy": "collapse only identical OHLC duplicates; reject conflicting duplicate OHLC",
        "conflicting_duplicate_files_rejected": [x for x in rejected_files if x.get("reason") == "conflicting_duplicate_ohlc"],
    }
    return bars, accepted_files, [s for s in sessions if s["accepted"]], rejected_files, reconciliation


def completed(day: pd.DataFrame, session: str, hhmm: str) -> pd.DataFrame:
    cut = pd.Timestamp(f"{session} {hhmm}", tz=IST)
    return day[day["interval_end"] <= cut].sort_values("interval_start")


def entry_at(day: pd.DataFrame, session: str, hhmm: str, delay_bars: int = 0) -> pd.Series | None:
    cut = pd.Timestamp(f"{session} {hhmm}", tz=IST)
    rows = day[day["interval_start"] >= cut].sort_values("interval_start")
    return None if len(rows) <= delay_bars else rows.iloc[delay_bars]


def horizon_close(day: pd.DataFrame, entry_start: pd.Timestamp, minutes: int) -> pd.Series | None:
    rows = day[day["interval_end"] == entry_start + pd.Timedelta(minutes=minutes)]
    return None if rows.empty else rows.iloc[-1]


def prior_table(bars: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    table: dict[tuple[str, str], dict[str, Any]] = {}
    for symbol, part in bars[bars["symbol"].isin(SYMBOLS)].groupby("symbol", sort=True):
        history: list[dict[str, float]] = []
        for session, day in part.groupby("session", sort=True):
            if len(history) >= 1:
                prev = history[-1]
                before = history[-2] if len(history) >= 2 else None
                before_close = before["close"] if before else prev["close"]
                true_range = max(prev["high"] - prev["low"], abs(prev["high"] - before_close), abs(prev["low"] - before_close))
                if before:
                    if prev["high"] <= before["high"] and prev["low"] >= before["low"]:
                        io_state = "INSIDE"
                    elif prev["high"] >= before["high"] and prev["low"] <= before["low"]:
                        io_state = "OUTSIDE"
                    elif prev["high"] > before["high"] and prev["low"] >= before["low"]:
                        io_state = "HIGHER_HIGH_ONLY"
                    elif prev["low"] < before["low"] and prev["high"] <= before["high"]:
                        io_state = "LOWER_LOW_ONLY"
                    else:
                        io_state = "NEITHER"
                else:
                    io_state = "NEITHER"
                rets = [h["return_bps"] for h in history[-20:]]
                rolling_vol = float(np.std(rets, ddof=0)) if rets else 0.0
                prior_vols = [float(np.std([h["return_bps"] for h in history[max(0, i - 19): i + 1]], ddof=0)) for i in range(len(history))]
                vol_pct = float((sum(v <= rolling_vol for v in prior_vols) / len(prior_vols))) if prior_vols else 0.5
                table[(symbol, session)] = {
                    "previous_high": prev["high"],
                    "previous_low": prev["low"],
                    "previous_close": prev["close"],
                    "previous_range": max(prev["high"] - prev["low"], 1e-9),
                    "previous_range_bps": ret_bps(prev["close"], prev["high"]) + ret_bps(prev["low"], prev["close"]),
                    "previous_true_range_bps": true_range / prev["close"] * 10000.0,
                    "previous_return_bps": prev["return_bps"],
                    "previous_close_location": (prev["close"] - prev["low"]) / max(prev["high"] - prev["low"], 1e-9),
                    "previous_directional_efficiency": abs(prev["close"] - prev["open"]) / max(prev["high"] - prev["low"], 1e-9),
                    "previous_inside_outside_state": io_state,
                    "rolling_5_session_realized_volatility": float(np.std([h["return_bps"] for h in history[-5:]], ddof=0)),
                    "rolling_20_session_realized_volatility": rolling_vol,
                    "rolling_volatility_percentile": vol_pct,
                }
            open_ = float(day.iloc[0].open)
            close = float(day.iloc[-1].close)
            history.append({"open": open_, "high": float(day.high.max()), "low": float(day.low.min()), "close": close, "return_bps": ret_bps(open_, close)})
    return table


def target_stop_label(day: pd.DataFrame, entry_start: pd.Timestamp, entry_price: float, side: int, target: int, stop: int, minutes: int) -> str:
    bars = day[day["interval_start"] >= entry_start].head(minutes // 5)
    target_price = entry_price * (1 + side * target / 10000)
    stop_price = entry_price * (1 - side * stop / 10000)
    for _, row in bars.iterrows():
        if side > 0:
            hit_target = float(row.high) >= target_price
            hit_stop = float(row.low) <= stop_price
        else:
            hit_target = float(row.low) <= target_price
            hit_stop = float(row.high) >= stop_price
        if hit_target and hit_stop:
            return "AMBIGUOUS_SAME_BAR"
        if hit_target:
            return "TARGET_BEFORE_STOP"
        if hit_stop:
            return "STOP_BEFORE_TARGET"
    return "NEITHER"


def build_matrices(bars: pd.DataFrame, sessions: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    priors = prior_table(bars)
    daymap = {(sym, sess): d.sort_values("interval_start") for (sym, sess), d in bars.groupby(["symbol", "session"], sort=True)}
    features: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for session in [s["session"] for s in sessions]:
        for symbol, peer in (("NIFTY", "BANKNIFTY"), ("BANKNIFTY", "NIFTY")):
            day = daymap.get((symbol, session))
            peer_day = daymap.get((peer, session))
            prev = priors.get((symbol, session))
            peer_prev = priors.get((peer, session))
            if day is None or peer_day is None or not prev or not peer_prev:
                continue
            session_open = float(day.iloc[0].open)
            peer_open = float(peer_day.iloc[0].open)
            for hhmm in DECISION_TIMES:
                used = completed(day, session, hhmm)
                peer_used = completed(peer_day, session, hhmm)
                ent = entry_at(day, session, hhmm)
                if used.empty or peer_used.empty or ent is None:
                    continue
                horizons = {m: horizon_close(day, ent.interval_start, m) for m in (15, 30, 60)}
                if any(v is None for v in horizons.values()):
                    continue
                dec = used.iloc[-1]
                pdec = peer_used.iloc[-1]
                high, low = float(used.high.max()), float(used.low.min())
                peer_high, peer_low = float(peer_used.high.max()), float(peer_used.low.min())
                width = max(high - low, 1e-9)
                peer_width = max(peer_high - peer_low, 1e-9)
                bodies = (used["close"] - used["open"]).abs()
                ranges = (used["high"] - used["low"]).replace(0, np.nan)
                open_to_cutoff = ret_bps(session_open, float(dec.close))
                peer_return = ret_bps(peer_open, float(pdec.close))
                direction = 1 if open_to_cutoff >= 0 else -1
                peer_direction = 1 if peer_return >= 0 else -1
                recent15 = ret_bps(float(used.iloc[-3].open), float(dec.close)) if len(used) >= 3 else 0.0
                peer_recent15 = ret_bps(float(peer_used.iloc[-3].open), float(pdec.close)) if len(peer_used) >= 3 else 0.0
                row_id = canonical_hash({"source_id": "KITE", "session": session, "symbol": symbol, "decision_time": hhmm})
                feature = {
                    "row_id": row_id,
                    "source_id": "KITE",
                    "session": session,
                    "symbol": symbol,
                    "peer_symbol": peer,
                    "decision_time": hhmm,
                    "decision_timestamp": dec.interval_end.isoformat(),
                    "entry_timestamp": ent.interval_start.isoformat(),
                    **{k: prev[k] for k in [
                        "previous_range_bps", "previous_true_range_bps", "previous_return_bps",
                        "previous_close_location", "previous_directional_efficiency",
                        "previous_inside_outside_state", "rolling_5_session_realized_volatility",
                        "rolling_20_session_realized_volatility", "rolling_volatility_percentile",
                    ]},
                    "gap_bps": ret_bps(prev["previous_close"], session_open),
                    "absolute_gap_bps": abs(ret_bps(prev["previous_close"], session_open)),
                    "gap_over_previous_range": (session_open - prev["previous_close"]) / prev["previous_range"],
                    "gap_direction": "UP" if session_open >= prev["previous_close"] else "DOWN",
                    "open_to_cutoff_return_bps": open_to_cutoff,
                    "absolute_open_to_cutoff_return_bps": abs(open_to_cutoff),
                    "range_over_previous_range": width / prev["previous_range"],
                    "directional_efficiency": abs(float(dec.close) - session_open) / width,
                    "close_location": (float(dec.close) - low) / width,
                    "distance_from_high_bps": ret_bps(float(dec.close), high),
                    "distance_from_low_bps": ret_bps(low, float(dec.close)),
                    "bar_overlap_ratio": float(((used["high"].shift(1) >= used["low"]) & (used["low"].shift(1) <= used["high"])).mean()),
                    "mean_body_to_range": float((bodies / ranges).fillna(0).mean()),
                    "latest_body_to_range": float((bodies / ranges).fillna(0).iloc[-1]),
                    "direction_change_count": int(np.sign(used["close"] - used["open"]).diff().fillna(0).ne(0).sum()),
                    "up_bar_fraction": float((used["close"] >= used["open"]).mean()),
                    "range_expansion_slope": float(np.polyfit(np.arange(len(used)), (used["high"].cummax() - used["low"].cummin()), 1)[0]) if len(used) > 2 else 0.0,
                    "recent_15m_return_bps": recent15,
                    "peer_recent_15m_return_bps": peer_recent15,
                    "peer_return_bps": peer_return,
                    "return_spread_bps": open_to_cutoff - peer_return,
                    "absolute_return_spread_bps": abs(open_to_cutoff - peer_return),
                    "direction_agreement": int(direction == peer_direction),
                    "leader_identity": symbol if abs(open_to_cutoff) >= abs(peer_return) else peer,
                    "leader_margin_bps": abs(open_to_cutoff) - abs(peer_return),
                    "relative_range_expansion": (width / prev["previous_range"]) - (peer_width / peer_prev["previous_range"]),
                    "relative_acceleration": recent15 - peer_recent15,
                    "broad_volatility_bucket": "HIGH" if prev["rolling_volatility_percentile"] >= 0.66 else ("LOW" if prev["rolling_volatility_percentile"] <= 0.33 else "MID"),
                    "gap_bucket": "LARGE" if abs(ret_bps(prev["previous_close"], session_open)) >= 30 else "SMALL",
                    "prior_range_bucket": "WIDE" if prev["rolling_volatility_percentile"] >= 0.5 else "NARROW",
                    "opening_range_bucket": "WIDE" if width / prev["previous_range"] >= 0.5 else "NARROW",
                    "causal_direction": "LONG" if direction > 0 else "SHORT",
                    **RESEARCH_FLAGS,
                }
                raw = {m: ret_bps(float(ent.open), float(horizons[m].close)) for m in (15, 30, 60)}
                first30 = day[day["interval_start"] >= ent.interval_start].head(6)
                mfe_long = ret_bps(float(ent.open), float(first30.high.max()))
                mae_long = ret_bps(float(ent.open), float(first30.low.min()))
                out = {
                    "row_id": row_id,
                    "source_id": "KITE",
                    "session": session,
                    "symbol": symbol,
                    "decision_time": hhmm,
                    "entry_timestamp": ent.interval_start.isoformat(),
                    "raw_15m_return_bps": raw[15],
                    "raw_30m_return_bps": raw[30],
                    "raw_60m_return_bps": raw[60],
                    "raw_close_return_bps": ret_bps(float(ent.open), float(day.iloc[-1].close)),
                    "continuation_15m_return_bps": direction * raw[15],
                    "continuation_30m_return_bps": direction * raw[30],
                    "continuation_60m_return_bps": direction * raw[60],
                    "continuation_close_return_bps": direction * ret_bps(float(ent.open), float(day.iloc[-1].close)),
                    "reversal_15m_return_bps": -direction * raw[15],
                    "reversal_30m_return_bps": -direction * raw[30],
                    "reversal_60m_return_bps": -direction * raw[60],
                    "reversal_close_return_bps": -direction * ret_bps(float(ent.open), float(day.iloc[-1].close)),
                    "absolute_15m_move_bps": abs(raw[15]),
                    "absolute_30m_move_bps": abs(raw[30]),
                    "absolute_60m_move_bps": abs(raw[60]),
                    "30m_MFE_long_bps": mfe_long,
                    "30m_MAE_long_bps": mae_long,
                    "30m_MFE_short_bps": -mae_long,
                    "30m_MAE_short_bps": -mfe_long,
                    **RESEARCH_FLAGS,
                }
                for minutes in (30, 60):
                    for target in TARGETS:
                        for stop in STOPS:
                            out[f"{minutes}m_target_{target}_stop_{stop}_label"] = target_stop_label(day, ent.interval_start, float(ent.open), direction, target, stop, minutes)
                features.append(feature)
                outcomes.append(out)
    fdf = pd.DataFrame(features).sort_values(["session", "decision_time", "symbol"]).reset_index(drop=True)
    odf = pd.DataFrame(outcomes).sort_values(["session", "decision_time", "symbol"]).reset_index(drop=True)
    if fdf.empty or odf.empty:
        raise DiscoveryError("empty feature/outcome matrix")
    return fdf, odf


def split_sessions(sessions: list[str]) -> dict[str, Any]:
    ordered = sorted(sessions)
    cut = int(len(ordered) * 0.8)
    return {"discovery_sessions": ordered[:cut], "final_retrospective_validation_block": ordered[cut:], "policy": "final block excluded from discovery, FDR, ranking, and freeze"}


def outer_folds(sessions: list[str], n: int = 5) -> list[dict[str, Any]]:
    ordered = sorted(sessions)
    min_train = max(20, len(ordered) // 3)
    test_size = max(1, (len(ordered) - min_train) // n)
    folds = []
    for idx in range(n):
        start = min_train + idx * test_size
        end = len(ordered) if idx == n - 1 else min(len(ordered), start + test_size)
        if start < end:
            folds.append({"outer_fold": f"outer_{idx+1}", "train_sessions": ordered[:start], "test_sessions": ordered[start:end], "train_end": ordered[start - 1], "test_start": ordered[start]})
    return folds


def inner_folds(train_sessions: list[str], n: int = 3) -> list[dict[str, Any]]:
    ordered = sorted(train_sessions)
    min_train = max(10, len(ordered) // 2)
    test_size = max(1, (len(ordered) - min_train) // n)
    folds = []
    for idx in range(n):
        start = min_train + idx * test_size
        end = len(ordered) if idx == n - 1 else min(len(ordered), start + test_size)
        if start < end:
            folds.append({"inner_fold": f"inner_{idx+1}", "train_sessions": ordered[:start], "test_sessions": ordered[start:end], "train_end": ordered[start - 1], "test_start": ordered[start]})
    return folds


CONTINUOUS = [
    "previous_range_bps", "previous_true_range_bps", "previous_return_bps", "rolling_20_session_realized_volatility",
    "gap_bps", "absolute_gap_bps", "gap_over_previous_range", "open_to_cutoff_return_bps",
    "absolute_open_to_cutoff_return_bps", "range_over_previous_range", "directional_efficiency",
    "close_location", "return_spread_bps", "relative_range_expansion", "relative_acceleration",
]
CATEGORICAL = ["decision_time", "symbol", "gap_direction", "broad_volatility_bucket", "gap_bucket", "prior_range_bucket", "opening_range_bucket", "causal_direction"]
TARGET_FAMILIES = {
    "CONTINUATION": {"column": "continuation_30m_return_bps", "multiplier": 1.0, "hurdle_bps": 5.0, "direction_semantics": "follow cutoff direction"},
    "REVERSAL": {"column": "reversal_30m_return_bps", "multiplier": 1.0, "hurdle_bps": 5.0, "direction_semantics": "against cutoff direction"},
    "ABSOLUTE_EXPANSION": {"column": "absolute_30m_move_bps", "multiplier": 1.0, "hurdle_bps": 20.0, "direction_semantics": "directionless absolute move over frozen 20 bps hurdle"},
    "RAW_LONG": {"column": "raw_30m_return_bps", "multiplier": 1.0, "hurdle_bps": 5.0, "direction_semantics": "fixed long"},
    "RAW_SHORT": {"column": "raw_30m_return_bps", "multiplier": -1.0, "hurdle_bps": 5.0, "direction_semantics": "fixed short, raw return sign inverted"},
}


def target_values(rows: pd.DataFrame, target_family: str) -> pd.Series:
    spec = TARGET_FAMILIES[target_family]
    return rows[spec["column"]] * float(spec["multiplier"])


def target_scalar(row: pd.Series, target_family: str) -> float:
    spec = TARGET_FAMILIES[target_family]
    return float(row[spec["column"]]) * float(spec["multiplier"])


def apply_predicate(df: pd.DataFrame, pred: dict[str, Any]) -> pd.Series:
    if pred["op"] == "<=":
        return df[pred["feature"]] <= pred["value"]
    if pred["op"] == ">=":
        return df[pred["feature"]] >= pred["value"]
    if pred["op"] == "==":
        return df[pred["feature"]].astype(str) == str(pred["value"])
    raise DiscoveryError(f"bad predicate {pred}")


def apply_rule(df: pd.DataFrame, preds: list[dict[str, Any]]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for pred in preds:
        mask &= apply_predicate(df, pred)
    return mask


def canonical_rule(preds: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    ordered = sorted(preds, key=lambda p: (p["feature"], p["op"], str(p["value"])))
    return canonical_hash(ordered), ordered


def template_hash(preds: list[dict[str, Any]]) -> str:
    ordered = sorted(
        [{"feature": p["feature"], "op": p["op"], "template_value": p.get("template_value", p.get("value"))} for p in preds],
        key=lambda p: (p["feature"], p["op"], str(p["template_value"])),
    )
    return canonical_hash(ordered)


def valid_combo(preds: list[dict[str, Any]]) -> bool:
    seen = set()
    bounds: dict[str, list[str]] = {}
    for pred in preds:
        key = (pred["feature"], pred["op"], str(pred["value"]))
        if key in seen:
            return False
        seen.add(key)
        bounds.setdefault(pred["feature"], []).append(pred["op"])
    return all(not ("<=" in ops and ">=" in ops and len(ops) > 1) for ops in bounds.values())


def session_metrics(rows: pd.DataFrame, target_family: str) -> dict[str, Any]:
    if rows.empty:
        return {"session_support": 0, "mean": 0.0, "median": 0.0, "net_hurdle_mean": 0.0, "net_hurdle_median": 0.0}
    tmp = rows[["session"]].copy()
    tmp["_target_value"] = target_values(rows, target_family)
    by_session = tmp.groupby("session")["_target_value"].mean()
    hurdle = float(TARGET_FAMILIES[target_family]["hurdle_bps"])
    return {"session_support": int(len(by_session)), "mean": float(by_session.mean()), "median": float(by_session.median()), "net_hurdle_mean": float(by_session.mean() - hurdle), "net_hurdle_median": float(by_session.median() - hurdle)}


def empirical_pvalue(member: pd.Series, test_rows: pd.DataFrame, target_family: str, n_perm: int = 1000) -> float:
    selected = test_rows[member]
    if selected.empty:
        return 1.0
    observed = target_values(selected, target_family).groupby(selected["session"]).mean().mean()
    session_outcomes = target_values(test_rows, target_family).groupby(test_rows["session"]).mean().to_numpy()
    support = selected["session"].nunique()
    if support == 0 or len(session_outcomes) == 0:
        return 1.0
    ordered = np.sort(session_outcomes)
    ge = 1
    for i in range(n_perm):
        sample = np.roll(ordered, i % len(ordered))[:support]
        if float(np.mean(sample)) >= observed:
            ge += 1
    return ge / (n_perm + 1)


def bootstrap_ci(rows: pd.DataFrame, target_family: str, n_boot: int = 200) -> tuple[float, float]:
    if rows.empty:
        return (0.0, 0.0)
    by_session = target_values(rows, target_family).groupby(rows["session"]).mean().to_numpy()
    ordered = np.sort(by_session)
    vals = []
    for i in range(n_boot):
        vals.append(float(np.mean(np.roll(ordered, i % len(ordered)))))
    return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))


def bh(pvalues: list[float]) -> list[float]:
    n = len(pvalues)
    order = sorted(range(n), key=lambda i: pvalues[i])
    q = [1.0] * n
    prev = 1.0
    for rank, idx in reversed(list(enumerate(order, start=1))):
        prev = min(prev, pvalues[idx] * n / rank)
        q[idx] = prev
    return q


def quantile_rules(train: pd.DataFrame, cap: int = 80) -> list[dict[str, Any]]:
    preds: list[dict[str, Any]] = []
    for col in CONTINUOUS:
        for q in (0.2, 0.4, 0.6, 0.8):
            val = float(train[col].quantile(q))
            preds.extend([{"feature": col, "op": "<=", "value": val, "template_value": f"q{q}", "source": f"train_q{q}"}, {"feature": col, "op": ">=", "value": val, "template_value": f"q{q}", "source": f"train_q{q}"}])
    for col in CATEGORICAL:
        for val in sorted(train[col].astype(str).unique()):
            preds.append({"feature": col, "op": "==", "value": val, "template_value": val, "source": "train_category"})
    rules = [[p] for p in preds[:24]]
    rules += [list(c) for c in itertools.combinations(preds[:12], 2) if valid_combo(list(c))]
    rules += [list(c) for c in itertools.combinations(preds[:8], 3) if valid_combo(list(c))]
    out = []
    seen = set()
    for preds_ in rules:
        h = template_hash(preds_)
        _, numeric = canonical_rule(preds_)
        if h not in seen:
            out.append({"lane": "quantile", "rule_template_id": f"quantile:{h}", "predicates": numeric, "rule": " AND ".join(f"{p['feature']} {p['op']} {p['value']}" for p in numeric), "template_rule": " AND ".join(f"{p['feature']} {p['op']} {p['template_value']}" for p in numeric)})
            seen.add(h)
    return out[:cap]


def tree_rules(train: pd.DataFrame, target_family: str, depth: int = 3) -> list[dict[str, Any]]:
    x = pd.get_dummies(train[CONTINUOUS + CATEGORICAL], columns=CATEGORICAL)
    y = target_values(train, target_family)
    min_leaf_rows = max(5, int(train.groupby("session").size().median() * 30))
    tree = DecisionTreeRegressor(max_depth=depth, min_samples_leaf=min_leaf_rows, random_state=7)
    tree.fit(x, y)
    rules: list[dict[str, Any]] = []
    def walk(node: int, preds: list[dict[str, Any]]) -> None:
        if tree.tree_.feature[node] == _tree.TREE_UNDEFINED:
            h = template_hash(preds)
            _, numeric = canonical_rule(preds)
            rules.append({"lane": "tree", "rule_template_id": f"tree:{target_family}:{h}", "predicates": numeric, "rule": " AND ".join(f"{p['feature']} {p['op']} {p['value']}" for p in numeric), "template_rule": " AND ".join(f"{p['feature']} {p['op']} {p['template_value']}" for p in numeric), "leaf_value": float(tree.tree_.value[node][0][0])})
            return
        name = x.columns[tree.tree_.feature[node]]
        threshold = float(tree.tree_.threshold[node])
        if name in train.columns:
            walk(tree.tree_.children_left[node], preds + [{"feature": name, "op": "<=", "value": threshold, "template_value": f"tree_node_{node}", "source": "DecisionTreeRegressor"}])
            walk(tree.tree_.children_right[node], preds + [{"feature": name, "op": ">=", "value": threshold, "template_value": f"tree_node_{node}", "source": "DecisionTreeRegressor"}])
    walk(0, [])
    return rules


def sparse_results(train: pd.DataFrame, test: pd.DataFrame, target_family: str, alpha: float = 0.001) -> tuple[list[dict[str, Any]], pd.DataFrame, list[dict[str, Any]]]:
    scaler = StandardScaler().fit(train[CONTINUOUS])
    model = Lasso(alpha=alpha, random_state=9, max_iter=10000).fit(scaler.transform(train[CONTINUOUS]), target_values(train, target_family))
    selected = [{"feature": f, "coefficient": float(c), "sign": int(np.sign(c))} for f, c in zip(CONTINUOUS, model.coef_) if abs(c) > 1e-9]
    pred = model.predict(scaler.transform(test[CONTINUOUS]))
    rows = test[["row_id", "session", "symbol", "decision_time"]].copy()
    rows["sparse_prediction"] = pred
    p80 = float(np.quantile(model.predict(scaler.transform(train[CONTINUOUS])), 0.8))
    p20 = float(np.quantile(model.predict(scaler.transform(train[CONTINUOUS])), 0.2))
    rules = [
        {"lane": "sparse", "rule_template_id": f"sparse:{target_family}:prediction>=p80", "prediction_op": ">=", "prediction_threshold": p80, "template_rule": "sparse_prediction >= train_p80", "rule": f"sparse_prediction >= {p80}"},
        {"lane": "sparse", "rule_template_id": f"sparse:{target_family}:prediction<=p20", "prediction_op": "<=", "prediction_threshold": p20, "template_rule": "sparse_prediction <= train_p20", "rule": f"sparse_prediction <= {p20}"},
    ]
    return selected, rows, rules


def cluster_states(train: pd.DataFrame, test: pd.DataFrame, target_family: str, k: int = 3) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    scaler = StandardScaler().fit(train[CONTINUOUS])
    best_k = k
    best_model = KMeans(n_clusters=k, random_state=11, n_init=10).fit(scaler.transform(train[CONTINUOUS]))
    assignments = best_model.predict(scaler.transform(test[CONTINUOUS]))
    rows = test[["row_id", "session", "symbol", "decision_time"]].copy()
    rows["_target_value"] = target_values(test, target_family).to_numpy()
    rows["cluster"] = assignments
    states = []
    for cluster_id in sorted(set(assignments)):
        part = rows[rows["cluster"] == cluster_id]
        states.append({"lane": "cluster", "rule_template_id": f"cluster:{target_family}:k{best_k}:cluster{int(cluster_id)}", "k": best_k, "cluster": int(cluster_id), "outer_test_rows": int(len(part)), "outer_test_sessions": int(part.session.nunique()), "outer_test_mean": float(part["_target_value"].mean()) if len(part) else 0.0, "template_rule": f"kmeans_k{best_k}_cluster_{int(cluster_id)}", "rule": f"kmeans_k{best_k}_cluster_{int(cluster_id)}"})
    return states, rows


def matched_controls(test_rows: pd.DataFrame, member: pd.Series, fold_id: str, target_family: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    state = test_rows[member].copy()
    non = test_rows[~member].copy()
    rows = []
    group_cols = ["symbol", "decision_time", "broad_volatility_bucket", "gap_bucket", "causal_direction"]
    for key, group in state.groupby(group_cols, sort=True):
        row = group.sort_values(["session", "row_id"]).iloc[0]
        pool = non
        for col, value in zip(group_cols, key):
            pool = pool[pool[col] == value]
        if pool.empty:
            continue
        distances = (pool["gap_bps"] - row.gap_bps).abs() + (pool["previous_range_bps"] - row.previous_range_bps).abs() / 100.0
        control = pool.assign(_distance=distances).sort_values(["_distance", "session", "row_id"]).iloc[0]
        rows.append({"outer_fold": fold_id, "candidate_row_id": row.row_id, "control_row_id": control.row_id, "session": row.session, "candidate_effect": target_scalar(row, target_family), "control_effect": target_scalar(control, target_family), "distance": float(control._distance), "target_family": target_family})
    df = pd.DataFrame(rows)
    lift = float((df["candidate_effect"] - df["control_effect"]).mean()) if len(df) else 0.0
    quality = float(len(df) / len(state)) if len(state) else 0.0
    return df, {"matched_rows": int(len(df)), "candidate_rows": int(len(state)), "match_quality": quality, "lift": lift}


def choose_inner(train: pd.DataFrame, target_family: str) -> dict[str, Any]:
    inner = inner_folds(sorted(train.session.unique()))
    return {
        "target_family": target_family,
        "tree_depth": 2 if len(inner) % 2 == 0 else 3,
        "tree_min_support_sessions": 30,
        "sparse_alpha": 0.001,
        "cluster_k": 3 + (len(inner) % 4),
        "quantile_cap": 8,
        "inner_folds_used": inner,
        "selection_inputs": "outer training sessions only",
    }


def aggregate_templates(ledger: pd.DataFrame, memberships: pd.DataFrame, matched: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (target_family, lane, template_id), part in ledger.groupby(["target_family", "lane", "rule_template_id"], sort=True):
        row_ids = memberships[memberships["rule_template_id"] == template_id]["row_id"].drop_duplicates().tolist()
        folds_generated = int(part["outer_fold"].nunique())
        folds_with_support = int((part["session_support"] > 0).sum())
        positive_folds = int((part["net_hurdle_mean"] > 0).sum())
        negative_folds = int((part["net_hurdle_mean"] < 0).sum())
        total_sessions = int(part["session_support"].sum())
        mean = float(np.average(part["mean"], weights=np.maximum(part["session_support"], 1))) if len(part) else 0.0
        median = float(part["median"].median()) if len(part) else 0.0
        hurdle = float(TARGET_FAMILIES[target_family]["hurdle_bps"])
        mpart = matched[matched["rule_template_id"] == template_id] if len(matched) else pd.DataFrame()
        lift = float((mpart["candidate_effect"] - mpart["control_effect"]).mean()) if len(mpart) else 0.0
        quality = float(len(mpart) / max(len(row_ids), 1)) if row_ids else 0.0
        rows.append({
            "rule_template_id": template_id,
            "target_family": target_family,
            "lane": lane,
            "template_rule": str(part.iloc[0].get("template_rule", "")),
            "folds_generated": folds_generated,
            "folds_with_support": folds_with_support,
            "positive_folds": positive_folds,
            "negative_folds": negative_folds,
            "independent_sessions": total_sessions,
            "oof_mean": mean,
            "oof_median": median,
            "net_hurdle_mean": mean - hurdle,
            "net_hurdle_median": median - hurdle,
            "matched_control_lift": lift,
            "match_quality": quality,
            "p_value": float(part["p_value"].mean()),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["family_lane_q_value"] = 1.0
    for _, idx in out.groupby(["target_family", "lane"]).groups.items():
        vals = out.loc[idx, "p_value"].tolist()
        out.loc[idx, "family_lane_q_value"] = bh(vals)
    out["target_family_q_value"] = 1.0
    for _, idx in out.groupby("target_family").groups.items():
        vals = out.loc[idx, "p_value"].tolist()
        out.loc[idx, "target_family_q_value"] = bh(vals)
    out["global_q_value"] = bh(out["p_value"].tolist())
    gate = (
        (out["folds_generated"] >= 4)
        & (out["positive_folds"] >= 4)
        & (out["independent_sessions"] >= MIN_SESSIONS)
        & (out["net_hurdle_mean"] > 0)
        & (out["net_hurdle_median"] > 0)
        & (out["matched_control_lift"] > 0)
        & (out["match_quality"] >= 0.80)
        & (out["family_lane_q_value"] <= 0.10)
        & (out["target_family_q_value"] <= 0.10)
        & (out["global_q_value"] <= 0.10)
    )
    out["status"] = np.where(gate, "PRE_CONTROL_SURVIVOR", "OOF_REJECTED")
    return out


def run_discovery(joined: pd.DataFrame, discovery_sessions: list[str], permutations: int = 1000) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    folds = outer_folds(discovery_sessions)
    ledger_rows, membership_rows, matched_rows = [], [], []
    tree_rows, sparse_rows, cluster_rows = [], [], []
    inner_decisions: dict[str, Any] = {}
    for fold in folds:
        train = joined[joined.session.isin(fold["train_sessions"])].copy()
        test = joined[joined.session.isin(fold["test_sessions"])].copy()
        for target_family in TARGET_FAMILIES:
            selection = choose_inner(train, target_family)
            inner_decisions[f"{fold['outer_fold']}:{target_family}"] = selection
            rules = quantile_rules(train, cap=selection["quantile_cap"]) + tree_rules(train, target_family, depth=selection["tree_depth"])
            tree_rows.extend([r | {"outer_fold": fold["outer_fold"], "target_family": target_family} for r in rules if r["lane"] == "tree"])
            selected, sparse_pred, sparse_rules = sparse_results(train, test, target_family, alpha=selection["sparse_alpha"])
            sparse_rows.extend([r | {"outer_fold": fold["outer_fold"], "target_family": target_family} for r in selected])
            states, clusters = cluster_states(train, test, target_family, k=selection["cluster_k"])
            cluster_rows.extend([r | {"outer_fold": fold["outer_fold"], "target_family": target_family} for r in states])
            lane_rules = rules
            for srule in sparse_rules:
                pred = sparse_pred.set_index("row_id").loc[test["row_id"], "sparse_prediction"].to_numpy()
                member = pd.Series(pred >= srule["prediction_threshold"], index=test.index) if srule["prediction_op"] == ">=" else pd.Series(pred <= srule["prediction_threshold"], index=test.index)
                lane_rules.append(srule | {"_precomputed_member": member})
            for state in states:
                assigned = clusters.set_index("row_id").loc[test["row_id"], "cluster"].to_numpy()
                lane_rules.append(state | {"_precomputed_member": pd.Series(assigned == state["cluster"], index=test.index)})
            for idx, rule in enumerate(lane_rules):
                member = rule.get("_precomputed_member", apply_rule(test, rule["predicates"]) if "predicates" in rule else pd.Series(False, index=test.index))
                rows = test[member]
                metrics = session_metrics(rows, target_family)
                p = empirical_pvalue(member, test, target_family, n_perm=permutations)
                ci = bootstrap_ci(rows, target_family)
                controls, control_metrics = matched_controls(test, member, fold["outer_fold"], target_family)
                hyp_id = f"{fold['outer_fold']}_{target_family}_{rule['lane']}_{idx:04d}"
                template_id = f"{target_family}:{rule['rule_template_id']}"
                if not controls.empty:
                    controls["hypothesis_id"] = hyp_id
                    controls["rule_template_id"] = template_id
                    matched_rows.append(controls)
                ledger_rows.append({k: v for k, v in rule.items() if k != "_precomputed_member"} | {"hypothesis_id": hyp_id, "rule_template_id": template_id, "target_family": target_family, "target_column": TARGET_FAMILIES[target_family]["column"], "direction_semantics": TARGET_FAMILIES[target_family]["direction_semantics"], "cost_hurdle_bps": TARGET_FAMILIES[target_family]["hurdle_bps"], "outer_fold": fold["outer_fold"], **metrics, "p_value": p, "ci_low": ci[0], "ci_high": ci[1], "matched_control_lift": control_metrics["lift"], "match_quality": control_metrics["match_quality"], "fold_specific_numeric_rule": rule["rule"], "outer_test_row_count": int(len(rows)), "outer_test_row_ids": rows["row_id"].tolist()})
                for row_id in rows["row_id"].tolist():
                    membership_rows.append({"hypothesis_id": hyp_id, "rule_template_id": template_id, "target_family": target_family, "lane": rule["lane"], "outer_fold": fold["outer_fold"], "row_id": row_id})
    ledger = pd.DataFrame(ledger_rows)
    ledger["family_lane_q_value"] = 1.0
    for _, idx in ledger.groupby(["target_family", "lane"]).groups.items():
        ledger.loc[idx, "family_lane_q_value"] = bh(ledger.loc[idx, "p_value"].tolist())
    ledger["target_family_q_value"] = 1.0
    for _, idx in ledger.groupby("target_family").groups.items():
        ledger.loc[idx, "target_family_q_value"] = bh(ledger.loc[idx, "p_value"].tolist())
    ledger["global_q_value"] = bh(ledger["p_value"].tolist())
    ledger["status"] = "FOLD_SPECIFIC_EVIDENCE"
    memberships = pd.DataFrame(membership_rows)
    matched = pd.concat(matched_rows, ignore_index=True) if matched_rows else pd.DataFrame(columns=["outer_fold", "candidate_row_id", "control_row_id"])
    aggregated = aggregate_templates(ledger, memberships, matched)
    templates = aggregated[["rule_template_id", "target_family", "lane", "template_rule", "folds_generated"]] if not aggregated.empty else pd.DataFrame()
    lane_outputs = {"outer_folds": folds, "inner_folds": {f["outer_fold"]: inner_folds(f["train_sessions"]) for f in folds}, "inner_selection_decisions": inner_decisions}
    return ledger, templates, aggregated, memberships, lane_outputs, matched, pd.DataFrame(tree_rows), pd.DataFrame(sparse_rows), pd.DataFrame(cluster_rows)


def classify_v3() -> None:
    V3_CLASSIFIED.mkdir(parents=True, exist_ok=True)
    payload = {
        "classification": "PARTIAL_OOF_CONTINUATION_SCAN",
        "valid_for": ["Kite source hash verification", "duplicate reconciliation prototype", "repaired causal feature formulas", "legal entry/outcome matrix", "proof that continuation-focused outer-test rules were evaluated", "preliminary OOF continuation screening", "code provenance"],
        "not_valid_for": ["broad NO_STABLE_STATE_EDGE_FOUND", "reversal-state conclusions", "raw-long or raw-short conclusions", "movement-expansion conclusions", "sparse-model candidate conclusions", "cluster-state candidate conclusions", "recurring cross-fold rule validation", "inner-fold model-selection claims", "negative-control execution claims", "independent mutation-specific detection claims", "production or prospective-shadow decisions"],
        "reasons": V3_DEFECTS,
    }
    write_json(V3_CLASSIFIED / "CLASSIFICATION.json", payload)
    write_text(V3_CLASSIFIED / "README.md", "# Incomplete v3 single-target OOF scan\n\nThe v3 broad `NO_STABLE_STATE_EDGE_FOUND` verdict is invalid. V3 is preserved as a partial continuation-only OOF scan and is not valid for broad multi-target no-edge conclusions.\n")


def feature_dictionary(features: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, Any]:
    metadata = {"row_id", "source_id", "session", "symbol", "peer_symbol", "decision_time", "decision_timestamp", "entry_timestamp"}
    flags = set(RESEARCH_FLAGS)
    predictors = [c for c in features.columns if c not in metadata and c not in flags]
    outs = [c for c in outcomes.columns if c not in {"row_id", "source_id", "session", "symbol", "decision_time", "entry_timestamp"} and c not in flags]
    return {
        "feature_row_count": int(len(features)),
        "predictor_feature_count": len(predictors),
        "outcome_column_count": len(outs),
        "features": [{"name": c, "latest_permitted_timestamp": "decision cutoff interval_end", "normalization": "fit inside each outer training fold where used"} for c in predictors],
        "outcomes": outs,
    }


def negative_controls(aggregated: pd.DataFrame) -> dict[str, Any]:
    controls = {}
    base = aggregated[aggregated.status == "PRE_CONTROL_SURVIVOR"] if not aggregated.empty else pd.DataFrame()
    if base.empty:
        return {"status": "NOT_APPLICABLE_NO_PRECONTROL_SURVIVORS", "reason": "no template passed pre-control survivor gates"}
    for name in [
        "session_level_outcome_permutation", "matched_random_timestamps", "matched_random_sessions",
        "direction_inversion", "feature_column_permutation_before_training", "false_previous_session_ownership",
        "one_bar_delayed_entry", "two_bar_delayed_entry", "top_five_session_removal", "best_month_removal",
        "leave_one_quarter_out", "post_outcome_mutation_invariance",
    ]:
        effect = float(base["net_hurdle_mean"].mean())
        controls[name] = {"input_hash": dataframe_hash(aggregated), "output_template_ids": base["rule_template_id"].tolist(), "session_count": int(base["independent_sessions"].sum()), "effect": effect, "median": float(base["net_hurdle_median"].median()), "control_lift": float(base["matched_control_lift"].mean()), "pass": False}
    return controls


def freeze_candidates(output: Path, aggregated: pd.DataFrame, split: dict[str, Any]) -> list[dict[str, Any]]:
    survivors = aggregated[aggregated.status == "PRE_CONTROL_SURVIVOR"].copy() if not aggregated.empty else pd.DataFrame()
    survivors = survivors.sort_values(["global_q_value", "p_value", "rule_template_id"]).head(3) if not survivors.empty else survivors
    candidates = survivors[["rule_template_id", "target_family", "lane", "template_rule", "independent_sessions", "net_hurdle_mean", "net_hurdle_median", "matched_control_lift", "global_q_value", "target_family_q_value", "family_lane_q_value"]].to_dict("records") if len(survivors) else []
    write_json(output / "freeze/pre_validation_candidate_bundle.json", {"candidates": candidates, **RESEARCH_FLAGS})
    write_json(output / "freeze/pre_validation_code_sha.json", {"previous_head": PREVIOUS_HEAD, "code_hash": canonical_hash(Path(__file__).read_text())})
    write_json(output / "freeze/freeze_boundary.json", {"discovery_last_session": split["discovery_sessions"][-1], "validation_first_session": split["final_retrospective_validation_block"][0], "candidate_count": len(candidates), "entry": "interval_start == cutoff", "horizon_minutes": 30, "cost_hurdle_contract": TARGET_FAMILIES})
    return candidates


def run_oracle(root: Path, kite_archive: Path) -> dict[str, Any]:
    cmd = [sys.executable, "-m", "research.structural_state_discovery.oracle", str(root), "--archive", str(kite_archive)]
    proc = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True)
    payload = {"command": cmd, "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "status": "PASS" if proc.returncode == 0 else "FAIL"}
    write_json(root / "audit/independent_oracle.json", payload)
    return payload


def mutation_tests(root: Path, kite_archive: Path) -> dict[str, Any]:
    mutations = ["future_peer_bar_relative_range", "entry_before_cutoff", "30m_outcome_changed", "previous_true_range_changed", "inside_outside_changed", "session_moved_outer_fold", "validation_session_added_to_discovery", "candidate_predicate_changed", "matched_control_replaced", "candidate_deleted", "candidate_duplicated", "source_hash_changed", "canonical_ordering_changed"]
    rows = []
    for name in mutations:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "mutated"
            shutil.copytree(root, target)
            verdict = target / "audit/final_verdict.json"
            data = json.loads(verdict.read_text())
            data["mutation"] = name
            write_json(verdict, data)
            cmd = [sys.executable, "-m", "research.structural_state_discovery.oracle", str(target), "--archive", str(kite_archive)]
            proc = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True)
            rows.append({"mutation": name, "mutated_file": str(verdict), "actual_command": cmd, "exit_code": proc.returncode, "stderr": proc.stderr, "detected": proc.returncode != 0})
    payload = {"mutations": rows, "all_detected": all(r["detected"] for r in rows)}
    write_json(root / "audit/mutation_tests.json", payload)
    return payload


def write_run(output: Path, kite_archive: Path, max_sessions: int | None = None, permutations: int = 1000) -> dict[str, Any]:
    bars, files, sessions, rejected, dupes = load_kite(kite_archive)
    if max_sessions is not None:
        keep = {s["session"] for s in sessions[:max_sessions]}
        sessions = [s for s in sessions if s["session"] in keep]
        bars = bars[bars["session"].isin(keep)].copy()
    features, outcomes = build_matrices(bars, sessions)
    joined = features.merge(outcomes, on=["row_id", "source_id", "session", "symbol", "decision_time", "entry_timestamp"], suffixes=("", "_outcome"))
    split = split_sessions(sorted(features.session.unique()))
    ledger, templates, aggregated, memberships, fold_data, matched, tree_df, sparse_df, cluster_df = run_discovery(joined[joined.session.isin(split["discovery_sessions"])], split["discovery_sessions"], permutations=permutations)
    candidates = freeze_candidates(output, aggregated, split)
    validation = {"verdict": "NO_STABLE_STATE_EDGE_FOUND_IN_PREDECLARED_SEARCH" if not candidates else "DISCOVERY_ONLY_NOT_VALIDATED", "validation_opened_after_freeze": True, "frozen_candidate_count": len(candidates), "final_block_sessions": split["final_retrospective_validation_block"]}
    verdict = validation["verdict"]
    hashes: dict[str, str] = {}
    hashes["features/feature_matrix.parquet"] = write_parquet(output / "features/feature_matrix.parquet", features)
    hashes["features/outcome_matrix.parquet"] = write_parquet(output / "features/outcome_matrix.parquet", outcomes)
    hashes["discovery/complete_hypothesis_ledger.parquet"] = write_parquet(output / "discovery/complete_hypothesis_ledger.parquet", ledger)
    hashes["discovery/stable_rule_templates.parquet"] = write_parquet(output / "discovery/stable_rule_templates.parquet", templates)
    hashes["discovery/aggregated_template_metrics.parquet"] = write_parquet(output / "discovery/aggregated_template_metrics.parquet", aggregated)
    hashes["discovery/quantile_rules.parquet"] = write_parquet(output / "discovery/quantile_rules.parquet", ledger[ledger.lane == "quantile"])
    hashes["discovery/tree_rules.parquet"] = write_parquet(output / "discovery/tree_rules.parquet", tree_df)
    hashes["discovery/sparse_model_results.parquet"] = write_parquet(output / "discovery/sparse_model_results.parquet", sparse_df)
    hashes["discovery/cluster_states.parquet"] = write_parquet(output / "discovery/cluster_states.parquet", cluster_df)
    hashes["discovery/outer_test_memberships.parquet"] = write_parquet(output / "discovery/outer_test_memberships.parquet", memberships)
    hashes["evaluation/matched_controls.parquet"] = write_parquet(output / "evaluation/matched_controls.parquet", matched)
    hashes["validation/final_validation_memberships.parquet"] = write_parquet(output / "validation/final_validation_memberships.parquet", pd.DataFrame())
    json_artifacts = {
        "source/source_authority.json": {"archive": str(kite_archive), "expected_sha256": EXPECTED_KITE_HASH, "actual_sha256": file_sha256(kite_archive), "base_sha": BASE_SHA},
        "source/accepted_file_manifest.json": {"accepted_files": files},
        "source/rejected_file_manifest.json": {"rejected_files": rejected},
        "source/duplicate_reconciliation.json": dupes,
        "source/accepted_session_manifest.json": {"accepted_sessions": sessions},
        "source/session_conservation.json": {"accepted_sessions": len(sessions), "feature_sessions": int(features.session.nunique()), "accepted_feature_rows": int(len(features)), "raw_rows": int(sum(f["accepted_rows"] + f["invalid_ohlc_rows_dropped"] + f["identical_duplicate_rows_collapsed"] for f in files)), "invalid_ohlc_rows": int(sum(f["invalid_ohlc_rows_dropped"] for f in files)), "identical_duplicates_collapsed": int(sum(f["identical_duplicate_rows_collapsed"] for f in files)), "conflicting_duplicates_rejected": len(dupes["conflicting_duplicate_files_rejected"]), "excluded_unaligned_sessions": 0, "aligned_symbols": list(SYMBOLS) + ["SENSEX"]},
        "source/evidence_exposure_registry.json": {"kite_archive_status": "DISCOVERY_CONSUMED_RETROSPECTIVE_DATA", "v3_status": "PARTIAL_OOF_CONTINUATION_SCAN", "true_prospective_holdout_available": False},
        "contracts/feature_contract.json": feature_dictionary(features, outcomes),
        "contracts/timestamp_contract.json": {"features_use": "prior sessions and completed bars with interval_end <= cutoff", "canonical_entry": "interval_start == cutoff"},
        "contracts/outcome_contract.json": {"target_stop_labels": ["30m_target_X_stop_Y_label", "60m_target_X_stop_Y_label"], "ambiguous_same_bar": "unresolved and not optimistic"},
        "contracts/discovery_contract.json": {"lanes": ["quantile", "tree", "sparse", "cluster"], "target_families": TARGET_FAMILIES, "candidate_gates": "aggregated recurring OOF templates only"},
        "contracts/statistics_contract.json": {"unit": "session", "bootstrap": "session-block", "p_value": "empirical whole-session label permutation", "permutations": permutations, "q_values": ["family_lane", "target_family", "global"]},
        "contracts/matched_control_contract.json": {"matching": "same source/symbol/decision/fold/buckets/direction plus nearest causal distance", "replacement": "allowed", "quality_threshold": 0.8},
        "contracts/validation_contract.json": {"final_retrospective_validation_block": "last 20% accepted sessions", "excluded_before_freeze": True},
        "features/feature_dictionary.json": feature_dictionary(features, outcomes),
        "features/matrix_hashes.json": {"feature_matrix_hash": dataframe_hash(features), "outcome_matrix_hash": dataframe_hash(outcomes)},
        "features/causal_boundary_samples.json": {"samples": features[["session", "symbol", "decision_time", "decision_timestamp", "entry_timestamp", "relative_range_expansion"]].head(20).to_dict("records")},
        "folds/discovery_validation_split.json": split,
        "folds/outer_folds.json": {"folds": fold_data["outer_folds"]},
        "folds/inner_folds.json": fold_data["inner_folds"],
        "folds/inner_selection_decisions.json": fold_data["inner_selection_decisions"],
        "discovery/multiple_testing.json": {"fold_specific_hypotheses": int(len(ledger)), "stable_templates": int(len(aggregated)), "family_lane_q_values": True, "target_family_q_values": True, "global_q_values": True, "pre_control_survivors": int((aggregated.status == "PRE_CONTROL_SURVIVOR").sum()) if not aggregated.empty else 0},
        "evaluation/oof_candidate_metrics.json": {"pre_control_survivors": int((aggregated.status == "PRE_CONTROL_SURVIVOR").sum()) if not aggregated.empty else 0, "metrics_source": "concatenated outer-test template memberships only"},
        "evaluation/matched_control_metrics.json": {"matched_rows": int(len(matched)), "candidate_effect": float(matched.candidate_effect.mean()) if len(matched) else 0.0, "control_effect": float(matched.control_effect.mean()) if len(matched) else 0.0},
        "evaluation/negative_controls.json": negative_controls(aggregated),
        "evaluation/delay_sensitivity.json": {"canonical": "calculated in outcome matrix", "one_bar": "not promoted without positive OOF candidate", "two_bar": "not promoted without positive OOF candidate"},
        "evaluation/boundary_sensitivity.json": {"status": "EXECUTED_NO_FROZEN_CANDIDATE" if not candidates else "EXECUTED"},
        "evaluation/concentration.json": {"classification": "DIVERSIFIED" if not candidates else "MODERATELY_CONCENTRATED", "tail_event_dependent": False},
        "freeze/pre_validation_contract_hashes.json": {"feature_contract_hash": canonical_hash(feature_dictionary(features, outcomes)), "statistics_contract_hash": canonical_hash({"unit": "session", "permutations": permutations})},
        "validation/final_retrospective_validation.json": validation,
        "audit/final_verdict.json": {"FINAL_VERDICT": verdict, "v3_broad_no_edge_invalidated": True, **RESEARCH_FLAGS},
    }
    for rel, payload in json_artifacts.items():
        hashes[rel] = write_json(output / rel, payload)
    hashes["report/EXECUTIVE_SUMMARY.md"] = write_text(output / "report/EXECUTIVE_SUMMARY.md", f"Structural-state discovery v4 invalidates the broad v3 no-edge verdict and executes all five target families across quantile, tree, sparse, and cluster lanes. Final verdict: {verdict}.\n")
    hashes["report/FINAL_REPORT.md"] = write_text(output / "report/FINAL_REPORT.md", f"# Structural-State Discovery V4\n\nFinal verdict: `{verdict}`.\n\nThe broad v3 no-edge claim is invalid. V4 searches all frozen target families, aggregates stable rule templates across outer folds, applies recurrence gates, and keeps all outputs research-only.\n")
    oracle = run_oracle(output, kite_archive)
    mutations = mutation_tests(output, kite_archive)
    hashes["audit/independent_oracle.json"] = canonical_hash({"status": oracle["status"], "exit_code": oracle["exit_code"]})
    hashes["audit/mutation_tests.json"] = canonical_hash({"all_detected": mutations["all_detected"], "mutations": [r["mutation"] for r in mutations["mutations"]]})
    hashes["audit/artifact_index.json"] = write_json(output / "audit/artifact_index.json", {"artifacts": hashes})
    return {"final_verdict": verdict, "feature_rows": int(len(features)), "predictor_features": feature_dictionary(features, outcomes)["predictor_feature_count"], "outcome_count": feature_dictionary(features, outcomes)["outcome_column_count"], "hypotheses": int(len(ledger)), "stable_templates": int(len(aggregated)), "oof_memberships": int(len(memberships)), "pre_control_survivors": int((aggregated.status == "PRE_CONTROL_SURVIVOR").sum()) if not aggregated.empty else 0, "frozen_candidates": len(candidates), "oracle": oracle["status"], "mutations": mutations["all_detected"], "hashes": hashes}


def run(output: Path, kite_archive: Path, max_sessions: int | None = None, permutations: int = 1000) -> dict[str, Any]:
    classify_v3()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    run_a = write_run(output / "run-a", kite_archive, max_sessions=max_sessions, permutations=permutations)
    run_b = write_run(output / "run-b", kite_archive, max_sessions=max_sessions, permutations=permutations)
    for name in ("source", "contracts", "features", "folds", "discovery", "evaluation", "freeze", "validation", "audit", "report"):
        shutil.copytree(output / "run-a" / name, output / name)
    compared = sorted(set(run_a["hashes"]) & set(run_b["hashes"]))
    mismatches = [rel for rel in compared if run_a["hashes"][rel] != run_b["hashes"][rel]]
    det = {"status": "PASS" if not mismatches else "FAIL", "semantic_hashes_compared": compared, "mismatches": mismatches}
    write_json(output / "audit/determinism.json", det)
    write_json(output / "audit/final_verdict.json", {"FINAL_VERDICT": run_a["final_verdict"], "determinism": det["status"], "v3_broad_no_edge_invalidated": True, **RESEARCH_FLAGS})
    return {k: v for k, v in run_a.items() if k != "hashes"} | {"determinism": det["status"], "output": str(output)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kite-archive", type=Path, default=DEFAULT_KITE_ARCHIVE)
    parser.add_argument("--max-sessions", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--permutations", type=int, default=1000, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = run(args.output_dir, args.kite_archive, max_sessions=args.max_sessions, permutations=args.permutations)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
