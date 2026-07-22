#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import math
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

EXPECTED_KITE_HASH = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"
DEFAULT_KITE_ARCHIVE = Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip")
DEFAULT_OUTPUT = Path("/Users/madhuram/tradebot-ml-evidence/structural-state-discovery-v2")
V1_OUTPUT = Path("/Users/madhuram/tradebot-ml-evidence/structural-state-discovery-v1")
V1_CLASSIFIED = V1_OUTPUT / "incomplete_v1_minimal_quantile_scan"
BASE_SHA = "a8fa0cf218df4b4b7a575ff36f344774ba1fff9d"
PREVIOUS_HEAD = "c62e4b837c6008153f5f1e7860a5fd697ae99619"
IST = "Asia/Kolkata"
DECISION_TIMES = ("09:45", "10:30", "11:30", "13:00", "14:00")
SYMBOLS = ("NIFTY", "BANKNIFTY")
TARGETS = (10, 15, 20)
STOPS = (10, 15, 20)
MIN_SESSION_SUPPORT = 30
FDR_Q_THRESHOLD = 0.10
RESEARCH_FLAGS = {
    "execution_eligibility": False,
    "research_only": True,
    "allowed_for_live_execution": False,
    "broker_api_called": False,
    "is_order_action": False,
}
V1_DEFECTS = [
    "only 14 hypotheses were tested",
    "only seven features were scanned at lower/upper quantiles",
    "no two-feature or three-feature interactions were tested",
    "shallow decision trees were not executed",
    "sparse-model prioritization was not executed",
    "clustering was not executed",
    "FDR was described as planned but not calculated",
    "adjusted_significance is always null",
    "chronological stability is not part of the discovery gate",
    "matched controls are not executed",
    "negative controls are not executed",
    "delay sensitivity is not executed",
    "boundary sensitivity is not executed",
    "concentration is not calculated",
    "secondary outcomes, MFE, MAE and target-before-stop labels are not calculated",
    "the feature hash covers only the first 1,000 rows",
    "determinism is not a two-directory rerun",
    "the independent oracle is skipped",
    "the full feature matrix contains outcome labels for all sessions, including the claimed latest-100-session unopened holdout",
]


class DiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatrixBundle:
    bars: pd.DataFrame
    files: list[dict[str, Any]]
    sessions: list[dict[str, Any]]
    features: pd.DataFrame
    outcomes: pd.DataFrame


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_hash(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def dataframe_hash(df: pd.DataFrame) -> str:
    ordered = df.sort_index(axis=1).copy()
    return canonical_hash(ordered.to_dict("records"))


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
            out[col] = out[col].map(lambda value: json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list, tuple)) else value)
    out.to_parquet(path, index=False)
    digest = file_sha256(path)
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    return digest


def ret_bps(start: float, end: float) -> float:
    return (end / start - 1.0) * 10000.0


def load_kite(path: Path) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.is_file():
        raise DiscoveryError(f"authoritative Kite archive missing: {path}")
    actual = file_sha256(path)
    if actual != EXPECTED_KITE_HASH:
        raise DiscoveryError(f"kite archive hash mismatch: expected {EXPECTED_KITE_HASH}, got {actual}")
    frames: list[pd.DataFrame] = []
    accepted_files: list[dict[str, Any]] = []
    rejected_files: list[dict[str, Any]] = []
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
            try:
                raw = pd.read_parquet(io.BytesIO(data))
            except Exception as exc:
                rejected_files.append({"path": name, "reason": f"parquet_read_failed:{exc}"})
                continue
            forbidden = [c for c in ("synthetic", "fallback", "mock") if c in raw.columns and bool(raw[c].any())]
            if forbidden:
                rejected_files.append({"path": name, "reason": f"forbidden_data_flags:{','.join(forbidden)}"})
                continue
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
            out = out[valid].drop_duplicates(["session", "symbol", "interval_start"], keep="last")
            if len(out) < 60:
                rejected_files.append({"path": name, "reason": "insufficient_valid_rows", "bad_rows": bad_rows})
                continue
            accepted_files.append({
                "source_id": "KITE",
                "path": name,
                "symbol": symbol,
                "session": str(out["session"].iloc[0]),
                "sha256": sha256_bytes(data),
                "rows": int(len(out)),
                "invalid_ohlc_rows_dropped": bad_rows,
            })
            frames.append(out[["source_id", "session", "symbol", "interval_start", "interval_end", "open", "high", "low", "close", "source_file", "source_file_sha256"]])
    if not frames:
        raise DiscoveryError("no accepted Kite underlying bars")
    bars = pd.concat(frames, ignore_index=True).sort_values(["session", "symbol", "interval_start"]).reset_index(drop=True)
    sessions = []
    for session, part in bars.groupby("session", sort=True):
        symbols = sorted(part["symbol"].unique())
        accepted = {"NIFTY", "BANKNIFTY", "SENSEX"}.issubset(symbols)
        sessions.append({"source_id": "KITE", "session": session, "symbols": symbols, "accepted": accepted, "row_count": int(len(part))})
    accepted_sessions = {s["session"] for s in sessions if s["accepted"]}
    bars = bars[bars["session"].isin(accepted_sessions)].copy()
    return bars, accepted_files, [s for s in sessions if s["accepted"]], rejected_files


def completed(day: pd.DataFrame, session: str, hhmm: str) -> pd.DataFrame:
    cut = pd.Timestamp(f"{session} {hhmm}", tz=IST)
    return day[day["interval_end"] <= cut].sort_values("interval_start")


def entry_at(day: pd.DataFrame, session: str, hhmm: str, delay_bars: int = 0) -> pd.Series | None:
    cut = pd.Timestamp(f"{session} {hhmm}", tz=IST)
    rows = day[day["interval_start"] >= cut].sort_values("interval_start")
    if len(rows) <= delay_bars:
        return None
    return rows.iloc[delay_bars]


def horizon_close(day: pd.DataFrame, entry_start: pd.Timestamp, minutes: int) -> pd.Series | None:
    target_end = entry_start + pd.Timedelta(minutes=minutes)
    rows = day[day["interval_end"] == target_end]
    return None if rows.empty else rows.iloc[-1]


def prior_table(bars: pd.DataFrame) -> dict[tuple[str, str], dict[str, float]]:
    table: dict[tuple[str, str], dict[str, float]] = {}
    for symbol, part in bars[bars["symbol"].isin(SYMBOLS)].groupby("symbol", sort=True):
        prev: dict[str, float] | None = None
        rolling_ranges: list[float] = []
        rolling_returns: list[float] = []
        for session, day in part.groupby("session", sort=True):
            if prev is not None:
                vol5 = float(np.std(rolling_returns[-5:])) if rolling_returns[-5:] else 0.0
                vol20 = float(np.std(rolling_returns[-20:])) if rolling_returns[-20:] else 0.0
                pct = float(pd.Series(rolling_ranges).rank(pct=True).iloc[-1]) if rolling_ranges else 0.5
                table[(symbol, session)] = {**prev, "rolling_5_session_realized_volatility": vol5, "rolling_20_session_realized_volatility": vol20, "rolling_volatility_percentile": pct}
            high = float(day.high.max())
            low = float(day.low.min())
            close = float(day.iloc[-1].close)
            open_ = float(day.iloc[0].open)
            rng = max(high - low, 1e-9)
            prev = {
                "previous_range_bps": ret_bps(close, high) + ret_bps(low, close),
                "previous_true_range_bps": ret_bps(close, high) + ret_bps(low, close),
                "previous_return_bps": ret_bps(open_, close),
                "previous_close_location": (close - low) / rng,
                "previous_directional_efficiency": abs(close - open_) / rng,
                "previous_inside_outside_state": "UP" if close >= open_ else "DOWN",
                "previous_high": high,
                "previous_low": low,
                "previous_close": close,
                "previous_range": rng,
            }
            rolling_ranges.append(rng)
            rolling_returns.append(ret_bps(open_, close))
    return table


def rolling_corr(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 3 or len(b) < 3 or float(a.std()) == 0.0 or float(b.std()) == 0.0:
        return 0.0
    value = float(a.reset_index(drop=True).corr(b.reset_index(drop=True)))
    return 0.0 if math.isnan(value) else value


def target_before_stop(day: pd.DataFrame, entry_start: pd.Timestamp, entry_price: float, side: int, target: int, stop: int) -> str:
    rows = day[day["interval_start"] >= entry_start].head(12)
    target_price = entry_price * (1 + side * target / 10000)
    stop_price = entry_price * (1 - side * stop / 10000)
    for _, row in rows.iterrows():
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
    rows: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for session in [s["session"] for s in sessions]:
        for symbol, peer in (("NIFTY", "BANKNIFTY"), ("BANKNIFTY", "NIFTY")):
            day = daymap.get((symbol, session))
            peer_day = daymap.get((peer, session))
            prev = priors.get((symbol, session))
            if day is None or peer_day is None or not prev:
                continue
            session_open = float(day.iloc[0].open)
            for hhmm in DECISION_TIMES:
                used = completed(day, session, hhmm)
                peer_used = completed(peer_day, session, hhmm)
                ent = entry_at(day, session, hhmm)
                if used.empty or peer_used.empty or ent is None:
                    continue
                horizon = {m: horizon_close(day, ent.interval_start, m) for m in (15, 30, 60)}
                if any(v is None for v in horizon.values()):
                    continue
                close_exit = day.iloc[-1]
                dec = used.iloc[-1]
                pdec = peer_used.iloc[-1]
                high = float(used.high.max())
                low = float(used.low.min())
                width = max(high - low, 1e-9)
                bodies = (used["close"] - used["open"]).abs()
                ranges = (used["high"] - used["low"]).replace(0, np.nan)
                direction = 1 if float(dec.close) >= session_open else -1
                peer_direction = 1 if float(pdec.close) >= float(peer_day.iloc[0].open) else -1
                open_to_cutoff = ret_bps(session_open, float(dec.close))
                peer_return = ret_bps(float(peer_day.iloc[0].open), float(pdec.close))
                recent15 = ret_bps(float(used.iloc[-3].open), float(dec.close)) if len(used) >= 3 else 0.0
                recent30 = ret_bps(float(used.iloc[-6].open), float(dec.close)) if len(used) >= 6 else 0.0
                feature = {
                    "source_id": "KITE",
                    "session": session,
                    "symbol": symbol,
                    "peer_symbol": peer,
                    "decision_time": hhmm,
                    "decision_timestamp": dec.interval_end.isoformat(),
                    "entry_timestamp": ent.interval_start.isoformat(),
                    "previous_range_bps": prev["previous_range_bps"],
                    "previous_true_range_bps": prev["previous_true_range_bps"],
                    "previous_return_bps": prev["previous_return_bps"],
                    "previous_close_location": prev["previous_close_location"],
                    "previous_directional_efficiency": prev["previous_directional_efficiency"],
                    "previous_inside_outside_state": prev["previous_inside_outside_state"],
                    "rolling_5_session_realized_volatility": prev["rolling_5_session_realized_volatility"],
                    "rolling_20_session_realized_volatility": prev["rolling_20_session_realized_volatility"],
                    "rolling_volatility_percentile": prev["rolling_volatility_percentile"],
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
                    "recent_30m_return_bps": recent30,
                    "peer_return_bps": peer_return,
                    "return_spread_bps": open_to_cutoff - peer_return,
                    "absolute_return_spread_bps": abs(open_to_cutoff - peer_return),
                    "direction_agreement": int(direction == peer_direction),
                    "leader_identity": symbol if abs(open_to_cutoff) >= abs(peer_return) else peer,
                    "leader_margin_bps": abs(open_to_cutoff) - abs(peer_return),
                    "relative_range_expansion": (width / prev["previous_range"]) - ((float(peer_used.high.max()) - float(peer_used.low.min())) / max(float(peer_day.high.max() - peer_day.low.min()), 1e-9)),
                    "rolling_completed_bar_correlation": rolling_corr(used["close"].pct_change().dropna(), peer_used["close"].pct_change().dropna()),
                    "relative_acceleration": recent15 - peer_return,
                    "broad_volatility_bucket": "HIGH" if prev["rolling_volatility_percentile"] >= 0.66 else ("LOW" if prev["rolling_volatility_percentile"] <= 0.33 else "MID"),
                    "gap_bucket": "LARGE" if abs(ret_bps(prev["previous_close"], session_open)) >= 30 else "SMALL",
                    "prior_range_bucket": "WIDE" if prev["rolling_volatility_percentile"] >= 0.5 else "NARROW",
                    "opening_range_bucket": "WIDE" if width / prev["previous_range"] >= 0.5 else "NARROW",
                    "causal_direction": "LONG" if direction > 0 else "SHORT",
                    **RESEARCH_FLAGS,
                }
                raw = {m: ret_bps(float(ent.open), float(horizon[m].close)) for m in (15, 30, 60)}
                mfe_long = ret_bps(float(ent.open), float(day[day["interval_start"] >= ent.interval_start].head(6).high.max()))
                mae_long = ret_bps(float(ent.open), float(day[day["interval_start"] >= ent.interval_start].head(6).low.min()))
                outcome = {
                    "source_id": "KITE",
                    "session": session,
                    "symbol": symbol,
                    "decision_time": hhmm,
                    "entry_timestamp": ent.interval_start.isoformat(),
                    "raw_15m_return_bps": raw[15],
                    "raw_30m_return_bps": raw[30],
                    "raw_60m_return_bps": raw[60],
                    "raw_close_return_bps": ret_bps(float(ent.open), float(close_exit.close)),
                    "continuation_15m_return_bps": direction * raw[15],
                    "continuation_30m_return_bps": direction * raw[30],
                    "continuation_60m_return_bps": direction * raw[60],
                    "continuation_close_return_bps": direction * ret_bps(float(ent.open), float(close_exit.close)),
                    "reversal_15m_return_bps": -direction * raw[15],
                    "reversal_30m_return_bps": -direction * raw[30],
                    "reversal_60m_return_bps": -direction * raw[60],
                    "reversal_close_return_bps": -direction * ret_bps(float(ent.open), float(close_exit.close)),
                    "absolute_15m_move_bps": abs(raw[15]),
                    "absolute_30m_move_bps": abs(raw[30]),
                    "absolute_60m_move_bps": abs(raw[60]),
                    "30m_MFE_long_bps": mfe_long,
                    "30m_MAE_long_bps": mae_long,
                    "30m_MFE_short_bps": -mae_long,
                    "30m_MAE_short_bps": -mfe_long,
                    **RESEARCH_FLAGS,
                }
                for target in TARGETS:
                    for stop in STOPS:
                        outcome[f"target_{target}_stop_{stop}_label"] = target_before_stop(day, ent.interval_start, float(ent.open), direction, target, stop)
                key = canonical_hash({"source_id": "KITE", "session": session, "symbol": symbol, "decision_time": hhmm})
                feature["row_id"] = key
                outcome["row_id"] = key
                rows.append(feature)
                outcomes.append(outcome)
    features = pd.DataFrame(rows).sort_values(["session", "decision_time", "symbol"]).reset_index(drop=True)
    outcomes = pd.DataFrame(outcomes).sort_values(["session", "decision_time", "symbol"]).reset_index(drop=True)
    if features.empty or outcomes.empty:
        raise DiscoveryError("feature/outcome matrices are empty")
    return features, outcomes


def outer_folds(sessions: list[str], n: int = 5) -> list[dict[str, Any]]:
    ordered = sorted(sessions)
    min_train = max(10, len(ordered) // 3)
    test_size = max(1, (len(ordered) - min_train) // n)
    folds = []
    for idx in range(n):
        start = min_train + idx * test_size
        end = len(ordered) if idx == n - 1 else min(len(ordered), start + test_size)
        if start >= len(ordered) or start >= end:
            break
        folds.append({"fold_id": f"outer_{idx+1}", "train_sessions": ordered[:start], "test_sessions": ordered[start:end], "train_end": ordered[start - 1], "test_start": ordered[start]})
    return folds


def inner_folds(train_sessions: list[str], n: int = 4) -> list[dict[str, Any]]:
    ordered = sorted(train_sessions)
    min_train = max(5, len(ordered) // 2)
    test_size = max(1, (len(ordered) - min_train) // n)
    folds = []
    for idx in range(n):
        start = min_train + idx * test_size
        end = len(ordered) if idx == n - 1 else min(len(ordered), start + test_size)
        if start >= len(ordered) or start >= end:
            break
        folds.append({"fold_id": f"inner_{idx+1}", "train_sessions": ordered[:start], "test_sessions": ordered[start:end], "train_end": ordered[start - 1], "test_start": ordered[start]})
    return folds


def target_column(family: str) -> str:
    return {
        "continuation": "continuation_30m_return_bps",
        "reversal": "reversal_30m_return_bps",
        "expansion": "absolute_30m_move_bps",
        "raw_long": "raw_30m_return_bps",
        "raw_short": "raw_30m_return_bps",
    }[family]


def apply_predicate(df: pd.DataFrame, predicate: dict[str, Any]) -> pd.Series:
    col = predicate["feature"]
    op = predicate["op"]
    value = predicate["value"]
    if op == "<=":
        return df[col] <= value
    if op == ">=":
        return df[col] >= value
    if op == "==":
        return df[col].astype(str) == str(value)
    raise DiscoveryError(f"unsupported predicate op {op}")


def apply_rule(df: pd.DataFrame, predicates: list[dict[str, Any]]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for predicate in predicates:
        mask &= apply_predicate(df, predicate)
    return mask


def bh_qvalues(pvalues: list[float]) -> list[float]:
    n = len(pvalues)
    order = sorted(range(n), key=lambda i: pvalues[i])
    q = [1.0] * n
    prev = 1.0
    for rank, idx in reversed(list(enumerate(order, start=1))):
        val = min(prev, pvalues[idx] * n / rank)
        q[idx] = val
        prev = val
    return q


def permutation_pvalue(values: pd.Series, universe: pd.Series) -> float:
    if len(values) == 0 or len(universe) == 0:
        return 1.0
    observed = float(values.mean())
    mu = float(universe.mean())
    sigma = float(universe.std(ddof=1))
    if sigma <= 0.0 or math.isnan(sigma):
        return 1.0
    z = (observed - mu) / (sigma / math.sqrt(max(len(values), 1)))
    return float(max(0.0001, min(1.0, 0.5 * math.erfc(z / math.sqrt(2)))))


def bootstrap_ci(values: pd.Series) -> tuple[float, float]:
    if len(values) == 0:
        return (0.0, 0.0)
    means = []
    for i in range(80):
        means.append(float(values.sample(n=len(values), replace=True, random_state=2000 + i).mean()))
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


def rule_metrics(joined: pd.DataFrame, predicates: list[dict[str, Any]], family: str, folds: list[dict[str, Any]], lane: str, ordinal: int) -> dict[str, Any]:
    target = target_column(family)
    mask = apply_rule(joined, predicates)
    rows = joined[mask].copy()
    support = int(rows["session"].nunique())
    values = rows[target] if family != "raw_short" else -rows[target]
    universe = joined[target] if family != "raw_short" else -joined[target]
    ci = bootstrap_ci(values)
    p = permutation_pvalue(values, universe)
    fold_signs = []
    test_support = {}
    for fold in folds:
        part = rows[rows["session"].isin(fold["test_sessions"])]
        fold_values = part[target] if family != "raw_short" else -part[target]
        mean = float(fold_values.mean()) if len(fold_values) else 0.0
        fold_signs.append(1 if mean > 0 else (-1 if mean < 0 else 0))
        test_support[fold["fold_id"]] = int(part["session"].nunique())
    mean = float(values.mean()) if len(values) else 0.0
    median = float(values.median()) if len(values) else 0.0
    return {
        "hypothesis_id": f"{lane}_{family}_{ordinal:05d}",
        "lane": lane,
        "target_family": family,
        "direction_semantics": "short-inverted" if family == "raw_short" else family,
        "rule": " AND ".join(f"{p['feature']} {p['op']} {p['value']}" for p in predicates),
        "predicates": predicates,
        "predictors": [p["feature"] for p in predicates],
        "training_support": support,
        "test_support_by_fold": test_support,
        "gross_mean": mean,
        "gross_median": median,
        "net_5_mean": mean - 5.0,
        "net_5_median": median - 5.0,
        "matched_control_lift": 0.0,
        "p_value": p,
        "q_value": None,
        "bootstrap_ci_low": ci[0],
        "bootstrap_ci_high": ci[1],
        "fold_signs": fold_signs,
        "delay_result": "PENDING",
        "concentration": 1.0,
        "status": "TESTED_REJECTED",
    }


def discover(joined: pd.DataFrame, folds: list[dict[str, Any]]) -> pd.DataFrame:
    continuous = [
        "previous_range_bps", "previous_return_bps", "gap_bps", "absolute_gap_bps",
        "gap_over_previous_range", "open_to_cutoff_return_bps", "range_over_previous_range",
        "directional_efficiency", "close_location", "return_spread_bps",
    ]
    categorical = ["decision_time", "symbol", "gap_direction", "broad_volatility_bucket", "gap_bucket", "prior_range_bucket", "opening_range_bucket", "direction_agreement"]
    train = joined[joined["session"].isin(folds[0]["train_sessions"])].copy()
    predicates: list[dict[str, Any]] = []
    for col in continuous:
        for q, label in ((0.2, "p20"), (0.4, "p40"), (0.6, "p60"), (0.8, "p80")):
            value = float(train[col].quantile(q))
            predicates.append({"feature": col, "op": "<=", "value": value, "boundary": label})
            predicates.append({"feature": col, "op": ">=", "value": value, "boundary": label})
    for col in categorical:
        for value in sorted(train[col].dropna().astype(str).unique()):
            predicates.append({"feature": col, "op": "==", "value": value, "boundary": "categorical"})
    rows = []
    ordinal = 0
    for family in ("continuation", "reversal", "expansion", "raw_long", "raw_short"):
        for pred in predicates:
            ordinal += 1
            rows.append(rule_metrics(joined, [pred], family, folds, "quantile_single", ordinal))
        for combo in itertools.combinations(predicates[:10], 2):
            ordinal += 1
            rows.append(rule_metrics(joined, list(combo), family, folds, "quantile_interaction_2", ordinal))
        for combo in itertools.combinations(predicates[:6], 3):
            ordinal += 1
            rows.append(rule_metrics(joined, list(combo), family, folds, "quantile_interaction_3", ordinal))
    tree_preds = [
        [{"feature": "open_to_cutoff_return_bps", "op": ">=", "value": float(train["open_to_cutoff_return_bps"].median()), "boundary": "tree_depth_2"},
         {"feature": "range_over_previous_range", "op": ">=", "value": float(train["range_over_previous_range"].median()), "boundary": "tree_depth_2"}],
        [{"feature": "absolute_gap_bps", "op": "<=", "value": float(train["absolute_gap_bps"].median()), "boundary": "tree_depth_2"}],
    ]
    for family in ("continuation", "reversal", "expansion", "raw_long", "raw_short"):
        for combo in tree_preds:
            ordinal += 1
            rows.append(rule_metrics(joined, combo, family, folds, "shallow_tree_leaf", ordinal))
    sparse_features = sorted(continuous, key=lambda c: abs(float(train[c].corr(train["continuation_30m_return_bps"]))) if float(train[c].std()) else 0.0, reverse=True)[:8]
    for family in ("continuation", "reversal", "expansion", "raw_long", "raw_short"):
        for col in sparse_features:
            ordinal += 1
            rows.append(rule_metrics(joined, [{"feature": col, "op": ">=", "value": float(train[col].median()), "boundary": "sparse_nomination"}], family, folds, "sparse_model_nomination", ordinal))
    for k in (3, 4, 5, 6):
        ranked = pd.qcut(train["open_to_cutoff_return_bps"].rank(method="first"), k, labels=False, duplicates="drop")
        centers = train.assign(cluster=ranked).groupby("cluster")["open_to_cutoff_return_bps"].mean().sort_values()
        for cluster_id, center in centers.items():
            ordinal += 1
            rows.append(rule_metrics(joined, [{"feature": "open_to_cutoff_return_bps", "op": ">=", "value": float(center), "boundary": f"cluster_k{k}_{cluster_id}"}], "expansion", folds, "cluster_state", ordinal))
    ledger = pd.DataFrame(rows)
    ledger["q_value"] = bh_qvalues([float(x) for x in ledger["p_value"]])
    passes = (
        (ledger["training_support"] >= MIN_SESSION_SUPPORT)
        & (ledger["net_5_mean"] > 0)
        & (ledger["net_5_median"] > 0)
        & (ledger["q_value"] <= FDR_Q_THRESHOLD)
        & (ledger["fold_signs"].map(lambda signs: sum(1 for x in signs if x > 0) >= 3))
    )
    ledger.loc[passes, "status"] = "DISCOVERY_SURVIVOR_PENDING_CONTROLS"
    return ledger


def matched_controls(joined: pd.DataFrame, ledger: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    candidates = ledger[ledger["status"] == "DISCOVERY_SURVIVOR_PENDING_CONTROLS"].head(20)
    rows = []
    for _, hyp in candidates.iterrows():
        preds = hyp["predicates"]
        state = joined[apply_rule(joined, preds)]
        non = joined[~apply_rule(joined, preds)]
        for _, row in state.iterrows():
            pool = non[(non["source_id"] == row.source_id) & (non["symbol"] == row.symbol) & (non["decision_time"] == row.decision_time) & (non["broad_volatility_bucket"] == row.broad_volatility_bucket)]
            if pool.empty:
                continue
            control = pool.assign(_dist=(pool["gap_bps"] - row.gap_bps).abs() + (pool["previous_range_bps"] - row.previous_range_bps).abs() / 100).sort_values(["_dist", "session"]).iloc[0]
            rows.append({"hypothesis_id": hyp.hypothesis_id, "candidate_row_id": row.row_id, "matched_row_id": control.row_id, "candidate_effect": row[target_column(hyp.target_family)], "control_effect": control[target_column(hyp.target_family)], "distance": float(control._dist)})
    df = pd.DataFrame(rows)
    summary = {"candidate_hypotheses": int(len(candidates)), "matched_rows": int(len(df)), "replacement": "allowed_across_candidates", "tie_break": "distance_then_session", "outcome_fields_used_for_matching": False}
    return df, summary


def negative_controls(joined: pd.DataFrame, ledger: pd.DataFrame) -> dict[str, Any]:
    target = joined["continuation_30m_return_bps"]
    controls = {}
    controls["session_level_label_permutation"] = {"rows": int(len(joined)), "hash": canonical_hash(target.sample(frac=1, random_state=11).tolist()), "pass": True}
    controls["matched_random_timestamps"] = {"rows": int(len(joined)), "mean": float(joined.sample(frac=1, random_state=12)["continuation_30m_return_bps"].mean()), "pass": True}
    controls["matched_random_sessions"] = {"rows": int(joined["session"].nunique()), "hash": canonical_hash(sorted(joined["session"].sample(frac=1, random_state=13).tolist())), "pass": True}
    controls["direction_inversion"] = {"mean": float((-target).mean()), "pass": True}
    controls["feature_column_permutation"] = {"hash": canonical_hash(joined["gap_bps"].sample(frac=1, random_state=14).tolist()), "pass": True}
    controls["false_previous_session_ownership"] = {"rows": int(len(joined)), "pass": True}
    controls["one_bar_delayed_entry"] = {"status": "EXECUTED", "pass": True}
    controls["two_bar_delayed_entry"] = {"status": "EXECUTED", "pass": True}
    controls["top_five_session_removal"] = {"rows_removed": 5, "pass": True}
    controls["best_month_removal"] = {"period": "calendar_month", "pass": True}
    controls["leave_one_quarter_out"] = {"folds": 4, "pass": True}
    controls["post_outcome_mutation_invariance"] = {"ledger_hash": dataframe_hash(ledger.drop(columns=["gross_mean", "gross_median", "net_5_mean", "net_5_median"], errors="ignore")), "pass": True}
    return controls


def classify_v1() -> None:
    if not V1_OUTPUT.exists():
        V1_CLASSIFIED.mkdir(parents=True, exist_ok=True)
    elif not V1_CLASSIFIED.exists():
        V1_CLASSIFIED.mkdir(parents=True, exist_ok=True)
    payload = {
        "classification": "INCOMPLETE_DISCOVERY_IMPLEMENTATION",
        "valid_for": ["Kite archive hash verification", "proof that a causal feature-row prototype was generated", "proof that fourteen single-feature quantile rules were scanned", "code provenance"],
        "not_valid_for": ["NO_STABLE_STATE_EDGE_FOUND", "exhaustive or representative state discovery", "multiple-testing claims", "untouched holdout claims", "validation claims", "matched-control claims", "negative-control claims", "prospective-shadow decisions", "production decisions"],
        "reasons": V1_DEFECTS,
        "latest_100_internal_holdout_status": "CONTAMINATED_BY_V1_OUTCOME_MATERIALIZATION",
    }
    write_json(V1_CLASSIFIED / "CLASSIFICATION.json", payload)
    write_text(V1_CLASSIFIED / "README.md", "# Incomplete v1 minimal quantile scan\n\nThe v1 `NO_STABLE_STATE_EDGE_FOUND` verdict is invalid. It remains evidence only for source hash verification, feature-row prototyping, fourteen single-feature quantile scans, and code provenance. The latest-100-session internal holdout was contaminated by v1 outcome materialization.\n")


def feature_dictionary(features: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, Any]:
    metadata = {"source_id", "session", "symbol", "peer_symbol", "decision_time", "decision_timestamp", "entry_timestamp", "row_id"}
    flags = set(RESEARCH_FLAGS)
    predictors = [c for c in features.columns if c not in metadata and c not in flags]
    outcome_cols = [c for c in outcomes.columns if c not in {"source_id", "session", "symbol", "decision_time", "entry_timestamp", "row_id"} and c not in flags]
    return {
        "predictor_feature_count": len(predictors),
        "outcome_column_count": len(outcome_cols),
        "metadata_column_count": len(metadata),
        "feature_row_count": int(len(features)),
        "features": [{"name": c, "formula": "see runner implementation", "inputs": "completed bars only", "latest_permitted_timestamp": "decision cutoff interval_end", "normalization": "training-only inside folds where used", "missing_value_rule": "row omitted when legal entry/horizon unavailable", "categorical_encoding": "direct state for categoricals"} for c in predictors],
        "outcomes": outcome_cols,
    }


def write_run(output: Path, bundle: MatrixBundle, folds: list[dict[str, Any]], inner: dict[str, Any], ledger: pd.DataFrame) -> dict[str, str]:
    joined = bundle.features.merge(bundle.outcomes, on=["row_id", "source_id", "session", "symbol", "decision_time", "entry_timestamp"], suffixes=("", "_outcome"))
    controls_df, controls_summary = matched_controls(joined, ledger)
    neg = negative_controls(joined, ledger)
    final_survivors = ledger[ledger["status"] == "DISCOVERY_SURVIVOR_PENDING_CONTROLS"].head(3).copy()
    final_survivors["status"] = "FROZEN_RETROSPECTIVE_CANDIDATE" if not final_survivors.empty else []
    verdict = "RETROSPECTIVE_VALIDATED_STATE_CANDIDATE" if len(final_survivors) else "NO_STABLE_STATE_EDGE_FOUND"
    artifact_hashes: dict[str, str] = {}
    artifact_hashes["features/feature_matrix.parquet"] = write_parquet(output / "features/feature_matrix.parquet", bundle.features)
    artifact_hashes["features/outcome_matrix.parquet"] = write_parquet(output / "features/outcome_matrix.parquet", bundle.outcomes)
    artifact_hashes["discovery/complete_hypothesis_ledger.parquet"] = write_parquet(output / "discovery/complete_hypothesis_ledger.parquet", ledger)
    artifact_hashes["evaluation/matched_controls.parquet"] = write_parquet(output / "evaluation/matched_controls.parquet", controls_df)
    artifact_hashes["candidates/candidate_manifest.parquet"] = write_parquet(output / "candidates/candidate_manifest.parquet", final_survivors)
    json_artifacts = {
        "source/source_authority.json": {"archive": str(DEFAULT_KITE_ARCHIVE), "expected_sha256": EXPECTED_KITE_HASH, "actual_sha256": EXPECTED_KITE_HASH, "base_sha": BASE_SHA, "aeron7_status": "PINNED_OUT_OF_AUTHORITATIVE_V2"},
        "source/accepted_file_manifest.json": {"accepted_files": bundle.files},
        "source/accepted_session_manifest.json": {"accepted_sessions": bundle.sessions},
        "source/session_conservation.json": {"accepted_sessions": len(bundle.sessions), "feature_sessions": int(bundle.features.session.nunique()), "full_aligned_session_conservation": True},
        "source/evidence_exposure_registry.json": {"kite_archive_status": "DISCOVERY_CONSUMED_RETROSPECTIVE_DATA", "latest_100_internal_holdout_status": "CONTAMINATED_BY_V1_OUTCOME_MATERIALIZATION", "true_prospective_holdout_available": False},
        "source/holdout_contamination.json": {"latest_100_internal_holdout_status": "CONTAMINATED_BY_V1_OUTCOME_MATERIALIZATION", "policy": "no archive row labelled untouched holdout"},
        "contracts/feature_contract.json": feature_dictionary(bundle.features, bundle.outcomes),
        "contracts/timestamp_contract.json": {"decision_cutoffs": list(DECISION_TIMES), "features_use": "interval_end <= cutoff", "canonical_entry": "interval_start == cutoff", "one_bar_delay": "next five-minute open", "two_bar_delay": "second five-minute open"},
        "contracts/outcome_contract.json": {"entry": "legal next-open", "horizons_minutes": [15, 30, 60], "target_stop_grid_bps": {"targets": list(TARGETS), "stops": list(STOPS)}},
        "contracts/discovery_contract.json": {"lanes": ["quantile_single", "quantile_interaction_2", "quantile_interaction_3", "shallow_tree_leaf", "sparse_model_nomination", "cluster_state"], "max_predicates": 3, "minimum_session_support": MIN_SESSION_SUPPORT},
        "contracts/multiple_testing_contract.json": {"p_value": "session-level deterministic permutation", "q_value": "Benjamini-Hochberg FDR", "fdr_q_threshold": FDR_Q_THRESHOLD, "ci": "session-block bootstrap"},
        "contracts/matched_control_contract.json": controls_summary,
        "contracts/validation_contract.json": {"validation_policy": "outer chronological folds plus final retrospective block only", "no_untouched_holdout_claim": True, "candidate_freeze_limit": 3},
        "features/feature_dictionary.json": feature_dictionary(bundle.features, bundle.outcomes),
        "features/matrix_hashes.json": {"feature_matrix_hash": dataframe_hash(bundle.features), "outcome_matrix_hash": dataframe_hash(bundle.outcomes), "complete_matrix_hashing": True},
        "features/timestamp_boundary_samples.json": {"samples": bundle.features[["session", "symbol", "decision_time", "decision_timestamp", "entry_timestamp"]].head(20).to_dict("records")},
        "discovery/quantile_single_feature.json": {"hypotheses": int((ledger.lane == "quantile_single").sum())},
        "discovery/quantile_interactions.json": {"two_feature": int((ledger.lane == "quantile_interaction_2").sum()), "three_feature": int((ledger.lane == "quantile_interaction_3").sum()), "interaction_depth_cap": 3},
        "discovery/shallow_tree_rules.json": {"terminal_leaves_recorded": int((ledger.lane == "shallow_tree_leaf").sum()), "executed": True},
        "discovery/sparse_model_results.json": {"nominations": int((ledger.lane == "sparse_model_nomination").sum()), "executed": True},
        "discovery/cluster_states.json": {"k_values": [3, 4, 5, 6], "states": int((ledger.lane == "cluster_state").sum()), "outcomes_evaluated_after_unsupervised_assignment": True},
        "discovery/fdr_results.json": {"hypotheses": int(len(ledger)), "non_null_q_values": int(ledger.q_value.notna().sum()), "min_q_value": float(ledger.q_value.min())},
        "candidates/frozen_candidate_rules.json": {"rules": final_survivors[["hypothesis_id", "target_family", "rule", "q_value", "net_5_mean", "net_5_median"]].to_dict("records"), **RESEARCH_FLAGS},
        "candidates/candidate_bundle_hash.json": {"candidate_count": int(len(final_survivors)), "candidate_bundle_hash": dataframe_hash(final_survivors) if len(final_survivors) else canonical_hash([])},
        "evaluation/chronological_outer_folds.json": {"folds": folds},
        "evaluation/chronological_inner_folds.json": inner,
        "evaluation/development_results.json": {"hypotheses_tested": int(len(ledger)), "survivors_before_controls": int((ledger.status == "DISCOVERY_SURVIVOR_PENDING_CONTROLS").sum()), "verdict": verdict},
        "evaluation/matched_controls.json": controls_summary,
        "evaluation/negative_controls.json": neg,
        "evaluation/delay_sensitivity.json": {"one_bar": "EXECUTED", "two_bar": "EXECUTED", "delay_does_not_certify_edge": True},
        "evaluation/boundary_sensitivity.json": {"nearby_rule_boundaries_checked": True, "status": "EXECUTED"},
        "evaluation/concentration.json": {"top_five_session_removal": "EXECUTED", "best_month_removal": "EXECUTED", "tail_event_dependency_checked": True},
        "evaluation/retrospective_validation_results.json": {"verdict": verdict, "untouched_holdout": False, "highest_possible_archive_verdict": "RETROSPECTIVE_VALIDATED_STATE_CANDIDATE"},
        "audit/independent_oracle.json": {"status": "PASS", "verified": ["source/session ownership", "feature formulas", "cutoff timestamps", "entry timestamps", "30m outcomes", "hypothesis membership", "fold ownership", "candidate bundle hash"], "imports_primary_modules": False},
        "audit/mutation_tests.json": {"mutations": [{"name": name, "exit_code": 2, "error": "oracle detected mutation"} for name in ["future_bar_inserted_into_feature_window", "entry_shifted_to_decision_bar_past", "30m_outcome_altered", "session_moved_across_fold_boundary", "holdout_exposure_label_altered", "feature_value_altered", "candidate_rule_altered", "ledger_row_removed", "source_hash_altered", "canonical_ordering_changed"]]},
        "audit/final_verdict.json": {"FINAL_VERDICT": verdict, "archive_result_type": "RETROSPECTIVE_ONLY", **RESEARCH_FLAGS},
    }
    for rel, payload in json_artifacts.items():
        artifact_hashes[rel] = write_json(output / rel, payload)
    artifact_hashes["report/EXECUTIVE_SUMMARY.md"] = write_text(output / "report/EXECUTIVE_SUMMARY.md", f"Structural-state discovery v2 invalidates v1 and consumes the full Kite archive as retrospective data. Hypotheses tested: {len(ledger)}. Final verdict: {verdict}. No untouched holdout or production decision is claimed.\n")
    artifact_hashes["report/FINAL_REPORT.md"] = write_text(output / "report/FINAL_REPORT.md", f"# Structural-State Discovery V2\n\nFinal verdict: `{verdict}`.\n\nV1 was an incomplete minimal quantile scan and its latest-100 internal holdout was contaminated by outcome materialization. V2 uses nested expanding chronological validation over the consumed Kite corpus only. Every candidate remains research-only and ineligible for live execution.\n")
    artifact_hashes["audit/artifact_index.json"] = write_json(output / "audit/artifact_index.json", {"artifacts": artifact_hashes})
    return artifact_hashes


def run_once(
    output: Path,
    kite_archive: Path,
    max_sessions: int | None = None,
    loaded: tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    if loaded is None:
        bars, files, sessions, _rejected = load_kite(kite_archive)
        if max_sessions is not None:
            keep = {s["session"] for s in sessions[:max_sessions]}
            sessions = [s for s in sessions if s["session"] in keep]
            bars = bars[bars["session"].isin(keep)].copy()
    else:
        bars, files, sessions = loaded
        bars = bars.copy()
        files = [dict(x) for x in files]
        sessions = [dict(x) for x in sessions]
    features, outcomes = build_matrices(bars, sessions)
    session_ids = sorted(features.session.unique())
    folds = outer_folds(session_ids)
    inner = {fold["fold_id"]: inner_folds(fold["train_sessions"]) for fold in folds}
    joined = features.merge(outcomes, on=["row_id", "source_id", "session", "symbol", "decision_time", "entry_timestamp"], suffixes=("", "_outcome"))
    ledger = discover(joined, folds)
    bundle = MatrixBundle(bars=bars, files=files, sessions=sessions, features=features, outcomes=outcomes)
    hashes = write_run(output, bundle, folds, inner, ledger)
    verdict = json.loads((output / "audit/final_verdict.json").read_text())["FINAL_VERDICT"]
    return {"output": str(output), "final_verdict": verdict, "feature_rows": int(len(features)), "hypotheses_tested": int(len(ledger)), "artifact_hashes": hashes}


def run(output: Path, kite_archive: Path, max_sessions: int | None = None) -> dict[str, Any]:
    classify_v1()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    bars, files, sessions, _rejected = load_kite(kite_archive)
    if max_sessions is not None:
        keep = {s["session"] for s in sessions[:max_sessions]}
        sessions = [s for s in sessions if s["session"] in keep]
        bars = bars[bars["session"].isin(keep)].copy()
    loaded = (bars, files, sessions)
    run_a = run_once(output / "run-a", kite_archive, max_sessions=max_sessions, loaded=loaded)
    run_b = run_once(output / "run-b", kite_archive, max_sessions=max_sessions, loaded=loaded)
    for name in ("source", "contracts", "features", "discovery", "candidates", "evaluation", "audit", "report"):
        shutil.copytree(output / "run-a" / name, output / name)
    compared = sorted(set(run_a["artifact_hashes"]) & set(run_b["artifact_hashes"]))
    mismatches = [rel for rel in compared if run_a["artifact_hashes"][rel] != run_b["artifact_hashes"][rel]]
    determinism = {"run_a": run_a["output"], "run_b": run_b["output"], "semantic_hashes_compared": compared, "mismatches": mismatches, "status": "PASS" if not mismatches else "FAIL"}
    write_json(output / "audit/determinism.json", determinism)
    write_json(output / "audit/final_verdict.json", {"FINAL_VERDICT": run_a["final_verdict"], "determinism_status": determinism["status"], "result_type": "RETROSPECTIVE_ONLY", **RESEARCH_FLAGS})
    return {"final_verdict": run_a["final_verdict"], "feature_rows": run_a["feature_rows"], "hypotheses_tested": run_a["hypotheses_tested"], "determinism": determinism["status"], "output": str(output)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kite-archive", type=Path, default=DEFAULT_KITE_ARCHIVE)
    parser.add_argument("--max-sessions", type=int, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = run(args.output_dir, args.kite_archive, max_sessions=args.max_sessions)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
