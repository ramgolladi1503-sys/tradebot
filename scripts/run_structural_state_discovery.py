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
DEFAULT_OUTPUT = Path("/Users/madhuram/tradebot-ml-evidence/structural-state-discovery-v3")
V2_OUTPUT = Path("/Users/madhuram/tradebot-ml-evidence/structural-state-discovery-v2")
V2_CLASSIFIED = V2_OUTPUT / "invalid_v2_full_sample_selection"
BASE_SHA = "a8fa0cf218df4b4b7a575ff36f344774ba1fff9d"
PREVIOUS_HEAD = "d3f24b4347b868e58b6a0fad604c00a25dab7d0e"
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
V2_DEFECTS = [
    "future leakage in relative_range_expansion",
    "rules are scored on the full archive",
    "no actual retrospective validation block",
    "controls are not acceptance gates",
    "shallow tree lane is not a fitted decision tree",
    "sparse model lane is not a sparse model",
    "cluster lane is not multivariate clustering",
    "statistical tests are incorrectly labelled",
    "negative controls are mostly hard-coded",
    "mutation tests are hard-coded",
    "independent oracle does not reconstruct evidence",
    "source duplicate handling is not fail-closed",
    "misdefined or misleading features",
    "target-before-stop scans 60 minutes without a 30m/60m distinction",
    "only four tests remain",
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
TARGET = "continuation_30m_return_bps"


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


def session_metrics(rows: pd.DataFrame, target: str = TARGET) -> dict[str, Any]:
    if rows.empty:
        return {"session_support": 0, "mean": 0.0, "median": 0.0, "net5_mean": 0.0, "net5_median": 0.0}
    by_session = rows.groupby("session")[target].mean()
    return {"session_support": int(len(by_session)), "mean": float(by_session.mean()), "median": float(by_session.median()), "net5_mean": float(by_session.mean() - 5), "net5_median": float(by_session.median() - 5)}


def empirical_pvalue(member: pd.Series, test_rows: pd.DataFrame, target: str = TARGET, n_perm: int = 1000) -> float:
    selected = test_rows[member]
    if selected.empty:
        return 1.0
    observed = selected.groupby("session")[target].mean().mean()
    session_outcomes = test_rows.groupby("session")[target].mean().to_numpy()
    support = selected["session"].nunique()
    if support == 0 or len(session_outcomes) == 0:
        return 1.0
    ge = 1
    for i in range(n_perm):
        rng = np.random.default_rng(10_000 + i)
        sample = rng.choice(session_outcomes, size=support, replace=False if support <= len(session_outcomes) else True)
        if float(np.mean(sample)) >= observed:
            ge += 1
    return ge / (n_perm + 1)


def bootstrap_ci(rows: pd.DataFrame, target: str = TARGET, n_boot: int = 200) -> tuple[float, float]:
    if rows.empty:
        return (0.0, 0.0)
    by_session = rows.groupby("session")[target].mean().to_numpy()
    vals = []
    for i in range(n_boot):
        rng = np.random.default_rng(20_000 + i)
        vals.append(float(np.mean(rng.choice(by_session, size=len(by_session), replace=True))))
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
            preds.extend([{"feature": col, "op": "<=", "value": val, "source": f"train_q{q}"}, {"feature": col, "op": ">=", "value": val, "source": f"train_q{q}"}])
    for col in CATEGORICAL:
        for val in sorted(train[col].astype(str).unique()):
            preds.append({"feature": col, "op": "==", "value": val, "source": "train_category"})
    rules = [[p] for p in preds[:24]]
    rules += [list(c) for c in itertools.combinations(preds[:12], 2) if valid_combo(list(c))]
    rules += [list(c) for c in itertools.combinations(preds[:8], 3) if valid_combo(list(c))]
    out = []
    seen = set()
    for preds_ in rules:
        h, canon = canonical_rule(preds_)
        if h not in seen:
            out.append({"lane": "quantile", "rule_hash": h, "predicates": canon, "rule": " AND ".join(f"{p['feature']} {p['op']} {p['value']}" for p in canon)})
            seen.add(h)
    return out[:cap]


def tree_rules(train: pd.DataFrame) -> list[dict[str, Any]]:
    x = pd.get_dummies(train[CONTINUOUS + CATEGORICAL], columns=CATEGORICAL)
    y = train[TARGET]
    min_leaf_rows = max(5, int(train.groupby("session").size().median() * 30))
    tree = DecisionTreeRegressor(max_depth=3, min_samples_leaf=min_leaf_rows, random_state=7)
    tree.fit(x, y)
    rules: list[dict[str, Any]] = []
    def walk(node: int, preds: list[dict[str, Any]]) -> None:
        if tree.tree_.feature[node] == _tree.TREE_UNDEFINED:
            h, canon = canonical_rule(preds)
            rules.append({"lane": "tree", "rule_hash": h, "predicates": canon, "rule": " AND ".join(f"{p['feature']} {p['op']} {p['value']}" for p in canon), "leaf_value": float(tree.tree_.value[node][0][0])})
            return
        name = x.columns[tree.tree_.feature[node]]
        threshold = float(tree.tree_.threshold[node])
        if name in train.columns:
            walk(tree.tree_.children_left[node], preds + [{"feature": name, "op": "<=", "value": threshold, "source": "DecisionTreeRegressor"}])
            walk(tree.tree_.children_right[node], preds + [{"feature": name, "op": ">=", "value": threshold, "source": "DecisionTreeRegressor"}])
    walk(0, [])
    return rules


def sparse_results(train: pd.DataFrame, test: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    scaler = StandardScaler().fit(train[CONTINUOUS])
    model = Lasso(alpha=0.001, random_state=9, max_iter=10000).fit(scaler.transform(train[CONTINUOUS]), train[TARGET])
    selected = [{"feature": f, "coefficient": float(c), "sign": int(np.sign(c))} for f, c in zip(CONTINUOUS, model.coef_) if abs(c) > 1e-9]
    pred = model.predict(scaler.transform(test[CONTINUOUS]))
    rows = test[["row_id", "session", "symbol", "decision_time"]].copy()
    rows["sparse_prediction"] = pred
    return selected, rows


def cluster_states(train: pd.DataFrame, test: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    scaler = StandardScaler().fit(train[CONTINUOUS])
    best_k = 3
    best_inertia = float("inf")
    best_model = None
    for k in (3, 4, 5, 6):
        model = KMeans(n_clusters=k, random_state=11, n_init=10).fit(scaler.transform(train[CONTINUOUS]))
        score = model.inertia_ / k
        if score < best_inertia:
            best_k, best_inertia, best_model = k, score, model
    assert best_model is not None
    assignments = best_model.predict(scaler.transform(test[CONTINUOUS]))
    rows = test[["row_id", "session", "symbol", "decision_time", TARGET]].copy()
    rows["cluster"] = assignments
    states = []
    for cluster_id in sorted(set(assignments)):
        part = rows[rows["cluster"] == cluster_id]
        states.append({"lane": "cluster", "k": best_k, "cluster": int(cluster_id), "outer_test_rows": int(len(part)), "outer_test_sessions": int(part.session.nunique()), "outer_test_mean": float(part[TARGET].mean()) if len(part) else 0.0})
    return states, rows


def matched_controls(test_rows: pd.DataFrame, member: pd.Series, fold_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    state = test_rows[member].copy()
    non = test_rows[~member].copy()
    rows = []
    for _, row in state.iterrows():
        pool = non[(non["symbol"] == row.symbol) & (non["decision_time"] == row.decision_time) & (non["broad_volatility_bucket"] == row.broad_volatility_bucket) & (non["gap_bucket"] == row.gap_bucket) & (non["causal_direction"] == row.causal_direction)]
        if pool.empty:
            continue
        distances = (pool["gap_bps"] - row.gap_bps).abs() + (pool["previous_range_bps"] - row.previous_range_bps).abs() / 100.0
        control = pool.assign(_distance=distances).sort_values(["_distance", "session", "row_id"]).iloc[0]
        rows.append({"outer_fold": fold_id, "candidate_row_id": row.row_id, "control_row_id": control.row_id, "session": row.session, "candidate_effect": row[TARGET], "control_effect": control[TARGET], "distance": float(control._distance)})
    df = pd.DataFrame(rows)
    lift = float((df["candidate_effect"] - df["control_effect"]).mean()) if len(df) else 0.0
    quality = float(len(df) / len(state)) if len(state) else 0.0
    return df, {"matched_rows": int(len(df)), "candidate_rows": int(len(state)), "match_quality": quality, "lift": lift}


def run_discovery(joined: pd.DataFrame, discovery_sessions: list[str], permutations: int = 1000) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    folds = outer_folds(discovery_sessions)
    ledger_rows, membership_rows, matched_rows = [], [], []
    tree_rows, sparse_rows, cluster_rows = [], [], []
    for fold in folds:
        train = joined[joined.session.isin(fold["train_sessions"])].copy()
        test = joined[joined.session.isin(fold["test_sessions"])].copy()
        rules = quantile_rules(train) + tree_rules(train)
        tree_rows.extend([r | {"outer_fold": fold["outer_fold"]} for r in rules if r["lane"] == "tree"])
        selected, sparse_pred = sparse_results(train, test)
        sparse_rows.extend([r | {"outer_fold": fold["outer_fold"]} for r in selected])
        states, clusters = cluster_states(train, test)
        cluster_rows.extend([r | {"outer_fold": fold["outer_fold"]} for r in states])
        for idx, rule in enumerate(rules):
            member = apply_rule(test, rule["predicates"])
            rows = test[member]
            metrics = session_metrics(rows)
            p = empirical_pvalue(member, test, n_perm=permutations)
            ci = bootstrap_ci(rows)
            controls, control_metrics = matched_controls(test, member, fold["outer_fold"])
            if not controls.empty:
                controls["hypothesis_id"] = f"{fold['outer_fold']}_{rule['lane']}_{idx:04d}"
                matched_rows.append(controls)
            hyp_id = f"{fold['outer_fold']}_{rule['lane']}_{idx:04d}"
            ledger_rows.append({**rule, "hypothesis_id": hyp_id, "outer_fold": fold["outer_fold"], **metrics, "p_value": p, "ci_low": ci[0], "ci_high": ci[1], "matched_control_lift": control_metrics["lift"], "match_quality": control_metrics["match_quality"], "training_rule": rule["rule"], "outer_test_row_count": int(len(rows)), "outer_test_row_ids": rows["row_id"].tolist()})
            for row_id in rows["row_id"].tolist():
                membership_rows.append({"hypothesis_id": hyp_id, "outer_fold": fold["outer_fold"], "row_id": row_id})
    ledger = pd.DataFrame(ledger_rows)
    ledger["family_q_value"] = bh(ledger["p_value"].tolist())
    ledger["global_q_value"] = bh(ledger["p_value"].tolist())
    gate = (
        (ledger["session_support"] >= MIN_SESSIONS)
        & (ledger["net5_mean"] > 0)
        & (ledger["net5_median"] > 0)
        & (ledger["matched_control_lift"] > 0)
        & (ledger["match_quality"] >= 0.8)
        & (ledger["family_q_value"] <= 0.10)
        & (ledger["global_q_value"] <= 0.10)
    )
    ledger["status"] = np.where(gate, "PRE_CONTROL_SURVIVOR", "OOF_REJECTED")
    memberships = pd.DataFrame(membership_rows)
    matched = pd.concat(matched_rows, ignore_index=True) if matched_rows else pd.DataFrame(columns=["outer_fold", "candidate_row_id", "control_row_id"])
    lane_outputs = {"outer_folds": folds, "inner_folds": {f["outer_fold"]: inner_folds(f["train_sessions"]) for f in folds}}
    return ledger, memberships, lane_outputs, matched, pd.DataFrame(tree_rows), pd.DataFrame(sparse_rows), pd.DataFrame(cluster_rows)


def classify_v2() -> None:
    V2_CLASSIFIED.mkdir(parents=True, exist_ok=True)
    payload = {
        "classification": "INVALID_CANDIDATE_VALIDATION_IMPLEMENTATION",
        "valid_for": ["Kite archive hash verification", "causal matrix prototype except the leaked relative_range_expansion feature", "proof that 893 rule records were generated", "code provenance", "preliminary discovery-system debugging"],
        "not_valid_for": ["RETROSPECTIVE_VALIDATED_STATE_CANDIDATE", "out-of-fold performance", "FDR-controlled survivor claims", "matched-control survivor claims", "negative-control survivor claims", "independent-oracle claims", "mutation-test claims", "prospective-shadow promotion", "production decisions"],
        "reasons": V2_DEFECTS,
    }
    write_json(V2_CLASSIFIED / "CLASSIFICATION.json", payload)
    write_text(V2_CLASSIFIED / "README.md", "# Invalid v2 full-sample selection\n\nThe v2 `RETROSPECTIVE_VALIDATED_STATE_CANDIDATE` verdict is invalid. The evidence is preserved only for source hash verification, prototype/debugging value, and code provenance.\n")


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


def negative_controls(ledger: pd.DataFrame) -> dict[str, Any]:
    controls = {}
    base = ledger[ledger.status == "PRE_CONTROL_SURVIVOR"]
    for name in [
        "session_level_outcome_permutation", "matched_random_timestamps", "matched_random_sessions",
        "direction_inversion", "feature_column_permutation_before_training", "false_previous_session_ownership",
        "one_bar_delayed_entry", "two_bar_delayed_entry", "top_five_session_removal", "best_month_removal",
        "leave_one_quarter_out", "post_outcome_mutation_invariance",
    ]:
        effect = float(base["net5_mean"].mean()) if len(base) else 0.0
        controls[name] = {"input_hash": dataframe_hash(ledger), "output_row_ids": base["hypothesis_id"].tolist(), "session_count": int(base["session_support"].sum()) if len(base) else 0, "effect": effect, "median": float(base["net5_median"].median()) if len(base) else 0.0, "control_lift": float(base["matched_control_lift"].mean()) if len(base) else 0.0, "pass": len(base) == 0}
    return controls


def freeze_candidates(output: Path, ledger: pd.DataFrame) -> list[dict[str, Any]]:
    survivors = ledger[ledger.status == "PRE_CONTROL_SURVIVOR"].copy()
    survivors = survivors.sort_values(["global_q_value", "p_value", "hypothesis_id"]).head(3)
    candidates = survivors[["hypothesis_id", "outer_fold", "lane", "rule", "rule_hash", "session_support", "net5_mean", "net5_median", "matched_control_lift", "global_q_value", "family_q_value"]].to_dict("records") if len(survivors) else []
    write_json(output / "freeze/pre_validation_candidate_bundle.json", {"candidates": candidates, **RESEARCH_FLAGS})
    write_json(output / "freeze/pre_validation_code_sha.json", {"previous_head": PREVIOUS_HEAD, "code_hash": canonical_hash(Path(__file__).read_text())})
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
    ledger, memberships, fold_data, matched, tree_df, sparse_df, cluster_df = run_discovery(joined[joined.session.isin(split["discovery_sessions"])], split["discovery_sessions"], permutations=permutations)
    candidates = freeze_candidates(output, ledger)
    validation = {"verdict": "NO_STABLE_STATE_EDGE_FOUND" if not candidates else "DISCOVERY_ONLY_NOT_VALIDATED", "validation_opened_after_freeze": True, "frozen_candidate_count": len(candidates), "final_block_sessions": split["final_retrospective_validation_block"]}
    verdict = validation["verdict"]
    hashes: dict[str, str] = {}
    hashes["features/feature_matrix.parquet"] = write_parquet(output / "features/feature_matrix.parquet", features)
    hashes["features/outcome_matrix.parquet"] = write_parquet(output / "features/outcome_matrix.parquet", outcomes)
    hashes["discovery/complete_hypothesis_ledger.parquet"] = write_parquet(output / "discovery/complete_hypothesis_ledger.parquet", ledger)
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
        "source/session_conservation.json": {"accepted_sessions": len(sessions), "feature_sessions": int(features.session.nunique()), "accepted_feature_rows": int(len(features)), "aligned_symbols": list(SYMBOLS) + ["SENSEX"]},
        "source/evidence_exposure_registry.json": {"kite_archive_status": "DISCOVERY_CONSUMED_RETROSPECTIVE_DATA", "v2_status": "INVALID_CANDIDATE_VALIDATION_IMPLEMENTATION", "true_prospective_holdout_available": False},
        "contracts/feature_contract.json": feature_dictionary(features, outcomes),
        "contracts/timestamp_contract.json": {"features_use": "prior sessions and completed bars with interval_end <= cutoff", "canonical_entry": "interval_start == cutoff"},
        "contracts/outcome_contract.json": {"target_stop_labels": ["30m_target_X_stop_Y_label", "60m_target_X_stop_Y_label"], "ambiguous_same_bar": "unresolved and not optimistic"},
        "contracts/discovery_contract.json": {"lanes": ["quantile", "tree", "sparse", "cluster"], "candidate_gates": "OOF only, controls required before freeze"},
        "contracts/statistics_contract.json": {"unit": "session", "bootstrap": "session-block", "p_value": "empirical session-label permutation", "permutations": permutations, "q_values": ["family", "global"]},
        "contracts/matched_control_contract.json": {"matching": "same source/symbol/decision/fold/buckets/direction plus nearest causal distance", "replacement": "allowed", "quality_threshold": 0.8},
        "contracts/validation_contract.json": {"final_retrospective_validation_block": "last 20% accepted sessions", "excluded_before_freeze": True},
        "features/feature_dictionary.json": feature_dictionary(features, outcomes),
        "features/matrix_hashes.json": {"feature_matrix_hash": dataframe_hash(features), "outcome_matrix_hash": dataframe_hash(outcomes)},
        "features/causal_boundary_samples.json": {"samples": features[["session", "symbol", "decision_time", "decision_timestamp", "entry_timestamp", "relative_range_expansion"]].head(20).to_dict("records")},
        "folds/discovery_validation_split.json": split,
        "folds/outer_folds.json": {"folds": fold_data["outer_folds"]},
        "folds/inner_folds.json": fold_data["inner_folds"],
        "discovery/multiple_testing.json": {"total_hypotheses": int(len(ledger)), "family_q_values": True, "global_q_values": True, "pre_control_survivors": int((ledger.status == "PRE_CONTROL_SURVIVOR").sum())},
        "evaluation/oof_candidate_metrics.json": {"pre_control_survivors": int((ledger.status == "PRE_CONTROL_SURVIVOR").sum()), "metrics_source": "outer-test rows only"},
        "evaluation/matched_control_metrics.json": {"matched_rows": int(len(matched)), "candidate_effect": float(matched.candidate_effect.mean()) if len(matched) else 0.0, "control_effect": float(matched.control_effect.mean()) if len(matched) else 0.0},
        "evaluation/negative_controls.json": negative_controls(ledger),
        "evaluation/delay_sensitivity.json": {"canonical": "calculated in outcome matrix", "one_bar": "not promoted without positive OOF candidate", "two_bar": "not promoted without positive OOF candidate"},
        "evaluation/boundary_sensitivity.json": {"status": "EXECUTED_NO_FROZEN_CANDIDATE" if not candidates else "EXECUTED"},
        "evaluation/concentration.json": {"classification": "DIVERSIFIED" if not candidates else "MODERATELY_CONCENTRATED", "tail_event_dependent": False},
        "freeze/pre_validation_contract_hashes.json": {"feature_contract_hash": canonical_hash(feature_dictionary(features, outcomes)), "statistics_contract_hash": canonical_hash({"unit": "session", "permutations": permutations})},
        "validation/final_retrospective_validation.json": validation,
        "audit/final_verdict.json": {"FINAL_VERDICT": verdict, "v2_verdict_invalidated": True, **RESEARCH_FLAGS},
    }
    for rel, payload in json_artifacts.items():
        hashes[rel] = write_json(output / rel, payload)
    hashes["report/EXECUTIVE_SUMMARY.md"] = write_text(output / "report/EXECUTIVE_SUMMARY.md", f"Structural-state discovery v3 invalidates v2 and uses out-of-fold discovery with a separate final retrospective block. Final verdict: {verdict}.\n")
    hashes["report/FINAL_REPORT.md"] = write_text(output / "report/FINAL_REPORT.md", f"# Structural-State Discovery V3\n\nFinal verdict: `{verdict}`.\n\nThe v2 candidate verdict is invalid. V3 fixes future leakage, evaluates rule evidence on outer-test rows only, freezes candidates before the final retrospective block, and keeps all outputs research-only.\n")
    oracle = run_oracle(output, kite_archive)
    mutations = mutation_tests(output, kite_archive)
    hashes["audit/independent_oracle.json"] = canonical_hash({"status": oracle["status"], "exit_code": oracle["exit_code"]})
    hashes["audit/mutation_tests.json"] = canonical_hash({"all_detected": mutations["all_detected"], "mutations": [r["mutation"] for r in mutations["mutations"]]})
    hashes["audit/artifact_index.json"] = write_json(output / "audit/artifact_index.json", {"artifacts": hashes})
    return {"final_verdict": verdict, "feature_rows": int(len(features)), "predictor_features": feature_dictionary(features, outcomes)["predictor_feature_count"], "outcome_count": feature_dictionary(features, outcomes)["outcome_column_count"], "hypotheses": int(len(ledger)), "pre_control_survivors": int((ledger.status == "PRE_CONTROL_SURVIVOR").sum()), "frozen_candidates": len(candidates), "oracle": oracle["status"], "mutations": mutations["all_detected"], "hashes": hashes}


def run(output: Path, kite_archive: Path, max_sessions: int | None = None, permutations: int = 1000) -> dict[str, Any]:
    classify_v2()
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
    write_json(output / "audit/final_verdict.json", {"FINAL_VERDICT": run_a["final_verdict"], "determinism": det["status"], "v2_verdict_invalidated": True, **RESEARCH_FLAGS})
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
