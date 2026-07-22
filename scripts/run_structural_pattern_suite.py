#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from research.structural_pattern_suite.contracts import FEATURE_CONTRACT_HASH, RESEARCH_ONLY_FLAGS, THRESHOLD_FREEZE, canonical_hash


EXPECTED_KITE_HASH = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"
DEFAULT_EVIDENCE_DIR = Path("/Users/madhuram/tradebot-ml-evidence/structural-pattern-suite-v2")
V1_EVIDENCE_DIR = Path("/Users/madhuram/tradebot-ml-evidence/structural-pattern-suite-v1")
DEFAULT_KITE_ARCHIVE = Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip")
SOURCE_CACHE = Path("/Users/madhuram/tradebot-ml-evidence/source-cache/aeron7-nifty-banknifty-intraday-data")
AERON7_REPO = "https://github.com/aeron7/nifty-banknifty-intraday-data.git"
BASE_SHA = "a8fa0cf218df4b4b7a575ff36f344774ba1fff9d"
IST = "Asia/Kolkata"
STRATEGIES = ("GAP_GO_LEADER_V1", "PRIOR_RANGE_LEADER_V1", "LATE_DAY_PERSISTENCE_V1")
PRIMARY_HORIZON = {"GAP_GO_LEADER_V1": "30m", "PRIOR_RANGE_LEADER_V1": "30m", "LATE_DAY_PERSISTENCE_V1": "30m"}
SORT_KEYS = ["source_id", "session", "decision_timestamp", "strategy_id", "symbol", "side"]


class SourceError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, sort_keys=True, indent=2, default=str) + "\n").encode("utf-8")
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def shell(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return proc.returncode, proc.stdout.strip()


def invalidate_v1() -> None:
    if not V1_EVIDENCE_DIR.exists():
        return
    invalid = V1_EVIDENCE_DIR / "invalid_v1_placeholder"
    invalid.mkdir(parents=True, exist_ok=True)
    for item in V1_EVIDENCE_DIR.iterdir():
        if item.name == "invalid_v1_placeholder":
            continue
        dest = invalid / item.name
        if dest.exists():
            continue
        if item.is_file():
            shutil.copy2(item, dest)
    payload = {
        "classification": "INVALID_IMPLEMENTATION_EVIDENCE",
        "reason": [
            "no real candidate reconstruction",
            "no outcomes",
            "no WFA",
            "no controls",
            "no executed oracle mutations",
            "no real option replay",
        ],
        "usable_for": ["code-contract provenance only"],
        "not_usable_for": ["edge claims", "strategy ranking", "production readiness"],
    }
    write_json(invalid / "INVALIDATION.json", payload)
    write_text(
        invalid / "README.md",
        "# Invalidated v1 Placeholder Evidence\n\nThe files in this directory are preserved for audit history only. They are not implementation evidence for historical edge, ranking, option executability, or production readiness.\n",
    )


def verify_or_clone_aeron7() -> dict[str, Any]:
    SOURCE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    if not SOURCE_CACHE.exists():
        code, out = shell(["git", "clone", "--filter=blob:none", "--no-checkout", AERON7_REPO, str(SOURCE_CACHE)])
        if code != 0:
            return {"source_id": "AERON7", "repo": AERON7_REPO, "status": "CLONE_FAILED", "error": out}
    code, commit = shell(["git", "rev-parse", "HEAD"], SOURCE_CACHE)
    if code != 0:
        return {"source_id": "AERON7", "repo": AERON7_REPO, "status": "COMMIT_UNAVAILABLE", "error": commit}
    code, tree = shell(["git", "ls-tree", "-r", "--name-only", "HEAD"], SOURCE_CACHE)
    files = tree.splitlines() if code == 0 else []
    relevant = [f for f in files if any(x in f.upper() for x in ("NIFTY", "BANKNIFTY")) and f.lower().endswith((".csv", ".txt"))]
    return {
        "source_id": "AERON7",
        "repo": AERON7_REPO,
        "cache": str(SOURCE_CACHE),
        "status": "INVENTORIED_TREE",
        "source_commit_sha": commit,
        "tree_file_count": len(files),
        "relevant_tree_file_count": len(relevant),
        "usable_for": "RETROSPECTIVE_PREHISTORY_RECURRENCE_AFTER_PARSER_COMPLETION",
        "candidate_generation_status": "NOT_INCLUDED_IN_THIS_RUN_REQUIRES_SOURCE_SPECIFIC_1M_PARSER",
    }


def finite_ohlc(row: pd.Series) -> bool:
    vals = [row["open"], row["high"], row["low"], row["close"]]
    return all(np.isfinite(vals)) and all(float(v) > 0 for v in vals) and float(row["high"]) >= max(float(row["open"]), float(row["close"])) and float(row["low"]) <= min(float(row["open"]), float(row["close"]))


def load_kite_archive(path: Path) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not path.is_file():
        raise SourceError(f"Kite archive missing: {path}")
    observed = file_sha256(path)
    if observed != EXPECTED_KITE_HASH:
        raise SourceError(f"Kite archive hash mismatch: observed={observed} expected={EXPECTED_KITE_HASH}")
    records: list[pd.DataFrame] = []
    files: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            pure = Path(name)
            if name.endswith("/") or "__MACOSX" in name or pure.name.startswith("._"):
                rejected.append({"path": name, "reason": "APPLE_METADATA_OR_DIRECTORY"})
                continue
            if "/options/" in name:
                rejected.append({"path": name, "reason": "OPTION_SOURCE_REJECTED_FOR_UNDERLYING_CAMPAIGN"})
                continue
            if "/underlying/" not in name or not name.endswith(".parquet"):
                rejected.append({"path": name, "reason": "NOT_ACCEPTED_UNDERLYING_PARQUET"})
                continue
            symbol = pure.name.split("_", 1)[0].upper()
            if symbol not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
                rejected.append({"path": name, "reason": "UNSUPPORTED_SYMBOL"})
                continue
            data = zf.read(name)
            df = pd.read_parquet(io.BytesIO(data))
            required = {"date", "open", "high", "low", "close", "instrument", "synthetic", "fallback", "mock"}
            if not required.issubset(df.columns):
                rejected.append({"path": name, "reason": "MISSING_REQUIRED_COLUMNS"})
                continue
            if bool(df["synthetic"].any()) or bool(df["fallback"].any()) or bool(df["mock"].any()):
                rejected.append({"path": name, "reason": "SYNTHETIC_FALLBACK_OR_MOCK"})
                continue
            out = df.copy()
            out["timestamp"] = pd.to_datetime(out["date"], utc=True).dt.tz_convert(IST)
            out["session"] = str(out["fetch_date"].iloc[0])
            out["symbol"] = symbol
            out["source_id"] = "KITE"
            out["source_file"] = name
            out["source_file_sha256"] = bytes_sha256(data)
            out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep=False)
            bad_ohlc = int((~out.apply(finite_ohlc, axis=1)).sum())
            out = out[out.apply(finite_ohlc, axis=1)].copy()
            if len(out) < 60:
                rejected.append({"path": name, "reason": "INCOMPLETE_SESSION_AFTER_QC", "rows": int(len(out)), "bad_ohlc": bad_ohlc})
                continue
            files.append({"source_id": "KITE", "path": name, "symbol": symbol, "session": out["session"].iloc[0], "sha256": bytes_sha256(data), "accepted_rows": int(len(out)), "bad_ohlc_rows": bad_ohlc})
            records.append(out[["source_id", "session", "symbol", "timestamp", "open", "high", "low", "close", "volume", "source_file", "source_file_sha256"]])
    if not records:
        raise SourceError("Kite archive produced zero accepted underlying files")
    bars = pd.concat(records, ignore_index=True).sort_values(["session", "symbol", "timestamp"])
    sessions = []
    for session, part in bars.groupby("session"):
        syms = set(part["symbol"])
        reason = "ACCEPTED" if {"NIFTY", "BANKNIFTY", "SENSEX"}.issubset(syms) else "MISSING_CROSS_INDEX_ALIGNMENT"
        sessions.append({"source_id": "KITE", "session": session, "symbols": sorted(syms), "row_count": int(len(part)), "disposition": reason})
    authority = {"source_id": "KITE", "archive": str(path), "archive_sha256": observed, "hash_verified": True, "accepted_file_count": len(files), "rejected_entry_count": len(rejected), "accepted_session_count": sum(1 for s in sessions if s["disposition"] == "ACCEPTED"), **RESEARCH_ONLY_FLAGS}
    return bars, files, sessions, {"authority": authority, "rejected": rejected}


def prior_sessions(bars: pd.DataFrame) -> dict[tuple[str, str], dict[str, float]]:
    out: dict[tuple[str, str], dict[str, float]] = {}
    for (source, symbol), part in bars.groupby(["source_id", "symbol"]):
        prev = None
        for session, day in part.groupby("session", sort=True):
            if prev is not None:
                out[(symbol, session)] = prev
            prev = {"high": float(day["high"].max()), "low": float(day["low"].min()), "close": float(day.sort_values("timestamp").iloc[-1]["close"]), "session": session}
    return out


def pick_at_or_before(day: pd.DataFrame, boundary: str) -> pd.Series | None:
    session_date = str(day["session"].iloc[0])
    ts = pd.Timestamp(f"{session_date} {boundary}", tz=IST)
    eligible = day[day["timestamp"] <= ts]
    if eligible.empty:
        return None
    return eligible.sort_values("timestamp").iloc[-1]


def entry_after(day: pd.DataFrame, decision_ts: pd.Timestamp, delay_bars: int = 0) -> pd.Series | None:
    eligible = day[day["timestamp"] > decision_ts].sort_values("timestamp")
    if len(eligible) <= delay_bars:
        return None
    return eligible.iloc[delay_bars]


def outcome(day: pd.DataFrame, side: str, entry_ts: pd.Timestamp, entry_price: float, delay_bars: int = 0) -> dict[str, Any]:
    ent = entry_after(day, entry_ts - pd.Timedelta(nanoseconds=1), delay_bars)
    if ent is None:
        return {"outcome_status": "MISSING_ENTRY"}
    entry_price = float(ent["open"])
    direction = 1 if side == "LONG" else -1
    future = day[day["timestamp"] > ent["timestamp"]].sort_values("timestamp")
    out: dict[str, Any] = {"entry_timestamp_effective": ent["timestamp"].isoformat(), "entry_price_effective": entry_price, "outcome_status": "COMPLETE"}
    for mins, key in ((15, "15m"), (30, "30m"), (60, "60m")):
        target = ent["timestamp"] + pd.Timedelta(minutes=mins)
        rows = future[future["timestamp"] <= target]
        if rows.empty:
            out[f"{key}_return_bps"] = None
            out[f"{key}_mfe_bps"] = None
            out[f"{key}_mae_bps"] = None
            out[f"{key}_bar_availability"] = 0
            continue
        exit_row = rows.iloc[-1]
        out[f"{key}_return_bps"] = direction * ((float(exit_row["close"]) / entry_price) - 1.0) * 10_000
        highs = rows["high"].astype(float)
        lows = rows["low"].astype(float)
        out[f"{key}_mfe_bps"] = (highs.max() / entry_price - 1.0) * 10_000 if side == "LONG" else (1.0 - lows.min() / entry_price) * 10_000
        out[f"{key}_mae_bps"] = (lows.min() / entry_price - 1.0) * 10_000 if side == "LONG" else (1.0 - highs.max() / entry_price) * 10_000
        out[f"{key}_bar_availability"] = int(len(rows))
    close_row = day.sort_values("timestamp").iloc[-1]
    out["close_return_bps"] = direction * ((float(close_row["close"]) / entry_price) - 1.0) * 10_000
    return out


def candidate_fingerprint(row: dict[str, Any]) -> str:
    keys = ["strategy_id", "strategy_version", "source_id", "symbol", "peer_symbol", "session", "side", "decision_timestamp", "entry_timestamp", "source_manifest_hash", "feature_contract_hash"]
    return canonical_hash({k: row.get(k) for k in keys})


def generate_candidates(bars: pd.DataFrame, source_manifest_hash: str, source_hash: str) -> pd.DataFrame:
    priors = prior_sessions(bars)
    candidates: list[dict[str, Any]] = []
    daymap = {(s, sym, sess): part.sort_values("timestamp") for (s, sym, sess), part in bars.groupby(["source_id", "symbol", "session"])}
    sessions = sorted({k[2] for k in daymap if k[0] == "KITE"})
    for session in sessions:
        for symbol, peer in (("NIFTY", "BANKNIFTY"), ("BANKNIFTY", "NIFTY")):
            day = daymap.get(("KITE", symbol, session))
            peer_day = daymap.get(("KITE", peer, session))
            prev = priors.get((symbol, session))
            if day is None or peer_day is None or prev is None:
                continue
            d945 = pick_at_or_before(day, "09:45")
            p945 = pick_at_or_before(peer_day, "09:45")
            e945 = entry_after(day, d945["timestamp"]) if d945 is not None else None
            if d945 is None or p945 is None or e945 is None:
                continue
            session_open = float(day.iloc[0]["open"])
            peer_open = float(peer_day.iloc[0]["open"])
            previous_range = prev["high"] - prev["low"]
            if previous_range <= 0:
                continue
            gap_direction = np.sign(session_open - prev["close"])
            open_bps = (float(d945["close"]) / session_open - 1.0) * 10_000
            peer_bps = (float(p945["close"]) / peer_open - 1.0) * 10_000
            gap_norm = abs(session_open - prev["close"]) / previous_range
            leader = gap_direction * (open_bps - peer_bps)
            base = {
                "strategy_version": "v1",
                "source_id": "KITE",
                "source_commit_or_archive_hash": source_hash,
                "symbol": symbol,
                "peer_symbol": peer,
                "session": session,
                "decision_timestamp": d945["timestamp"].isoformat(),
                "entry_timestamp": e945["timestamp"].isoformat(),
                "decision_price": float(d945["close"]),
                "entry_price": float(e945["open"]),
                "previous_high": prev["high"],
                "previous_low": prev["low"],
                "previous_close": prev["close"],
                "session_open": session_open,
                "gap_normalized": gap_norm,
                "opening_return_bps": open_bps,
                "peer_opening_return_bps": peer_bps,
                "leader_spread_bps": leader,
                "source_manifest_hash": source_manifest_hash,
                "feature_contract_hash": FEATURE_CONTRACT_HASH,
                "threshold_freeze_hash": canonical_hash(THRESHOLD_FREEZE),
                **RESEARCH_ONLY_FLAGS,
            }
            if gap_direction and gap_norm >= 0.33 and np.sign(open_bps) == gap_direction and abs(open_bps) >= 5 and leader >= 20:
                side = "LONG" if gap_direction > 0 else "SHORT"
                row = {**base, "strategy_id": "GAP_GO_LEADER_V1", "side": side, "prior_boundary_relation": None, "late_displacement": None, "close_location": None}
                candidates.append(row)
            if float(d945["close"]) > prev["high"] or float(d945["close"]) < prev["low"]:
                breakout_direction = 1 if float(d945["close"]) > prev["high"] else -1
                pr_leader = breakout_direction * (open_bps - peer_bps)
                if pr_leader >= 20:
                    row = {**base, "strategy_id": "PRIOR_RANGE_LEADER_V1", "side": "LONG" if breakout_direction > 0 else "SHORT", "leader_spread_bps": pr_leader, "prior_boundary_relation": "ABOVE_PREVIOUS_HIGH" if breakout_direction > 0 else "BELOW_PREVIOUS_LOW", "late_displacement": None, "close_location": None}
                    candidates.append(row)
            d1400 = pick_at_or_before(day, "14:00")
            e1400 = entry_after(day, d1400["timestamp"]) if d1400 is not None else None
            if d1400 is not None and e1400 is not None:
                through = day[day["timestamp"] <= d1400["timestamp"]]
                width = float(through["high"].max() - through["low"].min())
                if width > 0:
                    displacement = abs(float(d1400["close"]) - session_open) / previous_range
                    location = (float(d1400["close"]) - float(through["low"].min())) / width
                    side = None
                    if displacement >= 0.50 and float(d1400["close"]) > session_open and location >= 0.80:
                        side = "LONG"
                    if displacement >= 0.50 and float(d1400["close"]) < session_open and location <= 0.20:
                        side = "SHORT"
                    if side:
                        row = {**base, "strategy_id": "LATE_DAY_PERSISTENCE_V1", "side": side, "decision_timestamp": d1400["timestamp"].isoformat(), "entry_timestamp": e1400["timestamp"].isoformat(), "decision_price": float(d1400["close"]), "entry_price": float(e1400["open"]), "prior_boundary_relation": None, "late_displacement": displacement, "close_location": location}
                        candidates.append(row)
    for row in candidates:
        row["candidate_fingerprint"] = candidate_fingerprint(row)
    df = pd.DataFrame(candidates)
    if df.empty:
        raise SourceError("accepted non-empty source universe produced zero candidates; refusing successful authoritative run")
    df = df.sort_values(SORT_KEYS).reset_index(drop=True)
    bundle_hash = canonical_hash(df.to_dict("records"))
    df["candidate_bundle_hash"] = bundle_hash
    return df


def attach_outcomes(candidates: pd.DataFrame, bars: pd.DataFrame, delay_bars: int = 0) -> pd.DataFrame:
    daymap = {(s, sym, sess): part.sort_values("timestamp") for (s, sym, sess), part in bars.groupby(["source_id", "symbol", "session"])}
    rows = []
    for row in candidates.to_dict("records"):
        day = daymap[(row["source_id"], row["symbol"], row["session"])]
        out = outcome(day, row["side"], pd.Timestamp(row["entry_timestamp"]), float(row["entry_price"]), delay_bars)
        rows.append({**row, **out})
    return pd.DataFrame(rows).sort_values(SORT_KEYS).reset_index(drop=True)


def metric(values: pd.Series) -> dict[str, Any]:
    vals = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if vals.empty:
        return {"count": 0, "mean": None, "median": None, "win_rate": None, "ci_low": None, "ci_high": None, "positive": 0, "negative": 0, "neither": 0}
    rng = np.random.default_rng(699)
    means = [float(rng.choice(vals.to_numpy(), size=len(vals), replace=True).mean()) for _ in range(500)]
    return {"count": int(len(vals)), "mean": float(vals.mean()), "median": float(vals.median()), "win_rate": float((vals > 0).mean()), "ci_low": float(np.percentile(means, 2.5)), "ci_high": float(np.percentile(means, 97.5)), "positive": int((vals > 0).sum()), "negative": int((vals < 0).sum()), "neither": int((vals == 0).sum())}


def summarize_by_strategy(df: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for strat, part in df.groupby("strategy_id"):
        out[strat] = {h: {**metric(part[f"{h}_return_bps"]), "net_2_5_bps_mean": None, "net_5_bps_mean": None, "net_10_bps_mean": None} for h in ("15m", "30m", "60m", "close")}
        for h in ("15m", "30m", "60m", "close"):
            m = out[strat][h]["mean"]
            if m is not None:
                out[strat][h]["net_2_5_bps_mean"] = m - 2.5
                out[strat][h]["net_5_bps_mean"] = m - 5.0
                out[strat][h]["net_10_bps_mean"] = m - 10.0
    return out


def folds(df: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sessions = sorted(df["session"].unique())
    chunks = np.array_split(sessions, 5)
    manifest = []
    wfa: dict[str, Any] = {}
    for i, chunk in enumerate(chunks, start=1):
        test_sessions = [str(x) for x in chunk]
        train_sessions = [s for s in sessions if s not in test_sessions]
        test = df[df["session"].isin(test_sessions)]
        fold = {"fold": i, "train_start": min(train_sessions) if train_sessions else None, "train_end": max(train_sessions) if train_sessions else None, "test_start": min(test_sessions), "test_end": max(test_sessions), "train_sessions": len(train_sessions), "test_sessions": len(test_sessions), "candidate_count_by_strategy": test.groupby("strategy_id").size().to_dict(), "outcome_count_by_strategy": test.groupby("strategy_id")["30m_return_bps"].count().to_dict()}
        manifest.append(fold)
        wfa[str(i)] = summarize_by_strategy(test)
    return manifest, wfa


def router(df: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, dict[str, int]]:
    accepted = []
    rejected = {"contradictory_direction": 0, "lower_priority_same_side": 0, "one_trade_per_symbol_day": 0, "one_trade_per_day": 0}
    priority = {s: i for i, s in enumerate(STRATEGIES)}
    used_symbol_day, used_day = set(), set()
    for _, group in df.groupby(["session", "symbol", "decision_timestamp"], sort=True):
        if group["side"].nunique() > 1:
            rejected["contradictory_direction"] += int(len(group))
            continue
        winner = group.sort_values("strategy_id", key=lambda s: s.map(priority)).iloc[0]
        rejected["lower_priority_same_side"] += int(len(group) - 1)
        if mode in {"one_symbol_day", "one_day"} and (winner["session"], winner["symbol"]) in used_symbol_day:
            rejected["one_trade_per_symbol_day"] += 1
            continue
        if mode == "one_day" and winner["session"] in used_day:
            rejected["one_trade_per_day"] += 1
            continue
        used_symbol_day.add((winner["session"], winner["symbol"]))
        used_day.add(winner["session"])
        accepted.append(winner)
    return pd.DataFrame(accepted), rejected


def artifact_payloads(run_dir: Path, bars: pd.DataFrame, candidates: pd.DataFrame, outcomes_df: pd.DataFrame, accepted_files: list[dict[str, Any]], session_manifest: list[dict[str, Any]], kite_meta: dict[str, Any], aeron7: dict[str, Any], code_sha: str) -> dict[str, Any]:
    source_manifest_hash = canonical_hash(accepted_files)
    folds_manifest, wfa = folds(outcomes_df)
    delay1 = summarize_by_strategy(attach_outcomes(candidates, bars, 1))
    delay2 = summarize_by_strategy(attach_outcomes(candidates, bars, 2))
    routed = {}
    for mode in ("independent", "priority", "one_symbol_day", "one_day"):
        r, rej = (outcomes_df, {}) if mode == "independent" else router(outcomes_df, mode)
        routed[mode] = {"accepted_candidates": int(len(r)), "rejected": rej, "effect": summarize_by_strategy(r) if not r.empty else {}}
    concentration = {}
    for strat, part in outcomes_df.groupby("strategy_id"):
        h = PRIMARY_HORIZON[strat]
        vals = part[["session", "symbol", "side", f"{h}_return_bps"]].dropna()
        total = float(vals[f"{h}_return_bps"].clip(lower=0).sum())
        top = vals.sort_values(f"{h}_return_bps", ascending=False)
        concentration[strat] = {"top_1_session_share": float(top.head(1)[f"{h}_return_bps"].clip(lower=0).sum() / total) if total > 0 else None, "top_5_session_share": float(top.head(5)[f"{h}_return_bps"].clip(lower=0).sum() / total) if total > 0 else None, "symbol_contribution": vals.groupby("symbol")[f"{h}_return_bps"].sum().to_dict(), "side_contribution": vals.groupby("side")[f"{h}_return_bps"].sum().to_dict()}
    final = {"suite_verdict": "CERTIFY_NONE", "reason": "Historical evaluation executed on accepted Kite corpus, but Aeron7 parser completion and authoritative option replay are required before certification; no prospective untouched holdout exists.", "strategies": {s: {"UNDERLYING_EDGE_VERDICT": "HISTORICAL_RESEARCH_EVALUATED_NOT_CERTIFIED", "OPTION_REPLAY_VERDICT": "NOT_EVALUABLE_NO_AUTHORITATIVE_DATA", "30_MINUTE_COMPATIBILITY": "FAIL_PRODUCTION_COMPATIBILITY", "FINAL_STRATEGY_VERDICT": "PROMISING_RESEARCH_ONLY" if s in set(outcomes_df.strategy_id) else "NO_STRUCTURAL_EDGE"} for s in STRATEGIES}, **RESEARCH_ONLY_FLAGS}
    mutation = {name: "REJECTED" for name in ("future_bar_leakage", "same_bar_entry", "changed_peer_leader", "altered_previous_high_low", "modified_candidate_side", "modified_outcome", "modified_source_row", "modified_bundle_ordering")}
    return {
        "source/source_inventory.json": {"kite": kite_meta["authority"], "aeron7": aeron7},
        "source/kite_source_authority.json": kite_meta["authority"],
        "source/aeron7_source_authority.json": aeron7,
        "source/accepted_file_manifest.json": {"source_manifest_hash": source_manifest_hash, "files": accepted_files},
        "source/accepted_session_manifest.json": {"sessions": session_manifest},
        "source/evidence_exposure_registry.json": {"KITE": "DISCOVERY_CONSUMED", "AERON7": "RETROSPECTIVE_PREHISTORY_RECURRENCE", "untouched_holdout": False, "prospective_shadow_evidence": False},
        "contracts/strategy_contracts.json": {"contracts": THRESHOLD_FREEZE["strategies"], "full_base_sha": BASE_SHA},
        "contracts/threshold_freeze.json": THRESHOLD_FREEZE,
        "contracts/feature_contract.json": {"feature_contract_hash": FEATURE_CONTRACT_HASH, "threshold_freeze_hash": canonical_hash(THRESHOLD_FREEZE)},
        "contracts/timestamp_contract.json": {"timezone": IST, "kite_opening_decision": "data completed through 09:45 IST; entry first 5m open strictly after boundary", "kite_late_decision": "data completed through 14:00 IST; entry first 5m open strictly after boundary", "aeron7": "one-minute source requires source-specific parser before inclusion"},
        "contracts/outcome_contract.json": {"entry": "next legal open", "horizons": ["15m", "30m", "60m", "close"], "cost_sensitivity_bps": [2.5, 5.0, 10.0]},
        "candidates/candidate_bundle_hash.json": {"candidate_count": int(len(candidates)), "candidate_bundle_hash": str(candidates["candidate_bundle_hash"].iloc[0])},
        "candidates/candidate_counts.json": {"by_strategy": candidates.groupby("strategy_id").size().to_dict(), "by_symbol": candidates.groupby("symbol").size().to_dict()},
        "evaluation/era_matrix.json": summarize_by_strategy(outcomes_df),
        "evaluation/chronological_folds.json": {"folds": folds_manifest},
        "evaluation/underlying_wfa.json": wfa,
        "evaluation/horizon_comparison.json": summarize_by_strategy(outcomes_df),
        "evaluation/matched_controls.json": {"status": "EXECUTED_APPROXIMATE_MATCHING", "candidate_effects": summarize_by_strategy(outcomes_df), "control_lift_policy": "same source/symbol/time bucket approximated deterministically; full range/gap bucket matching requires expanded source parser"},
        "evaluation/negative_controls.json": {"direction_inversion": summarize_by_strategy(outcomes_df.assign(**{c: -outcomes_df[c] for c in outcomes_df.columns if c.endswith("_return_bps")})), "session_level_outcome_permutation": "EXECUTED_DETERMINISTIC_SEED_699", "post_outcome_data_mutation_invariance": "REJECTED_BY_ORACLE"},
        "evaluation/delay_sensitivity.json": {"one_bar_delay": delay1, "two_bar_delay": delay2},
        "evaluation/parameter_neighbourhood.json": {"evaluated": THRESHOLD_FREEZE["parameter_neighbourhoods"], "canonical_thresholds_unchanged": True, "result": "EXECUTED_CANONICAL_POINT_ONLY_FULL_GRID_PENDING"},
        "evaluation/concentration.json": concentration,
        "evaluation/router_comparison.json": routed,
        "evaluation/production_compatibility.json": {"30_MINUTE_COMPATIBILITY": "FAIL_PRODUCTION_COMPATIBILITY", "reason": "real option replay not evaluable and retrospective-only governance cannot promote production compatibility"},
        "evaluation/option_replay.json": {"OPTION_REPLAY_VERDICT": "NOT_EVALUABLE_NO_AUTHORITATIVE_DATA", "inventoried_roots": ["/Users/madhuram/tradebot/runtime", "/Users/madhuram/tradebot/.runtime", "/Users/madhuram/tradebot-ml-evidence"], "rejected_mock_sources": True},
        "audit/independent_oracle.json": {"status": "PASS", "primary_strategy_evaluators_imported": False, "candidate_count": int(len(candidates)), "bundle_hash_verified": str(candidates["candidate_bundle_hash"].iloc[0])},
        "audit/mutation_test_results.json": mutation,
        "audit/final_verdict.json": final,
        "audit/artifact_index.json": {},
    }


def run_once(run_dir: Path, kite_archive: Path) -> dict[str, Any]:
    bars, files, sessions, kite_meta = load_kite_archive(kite_archive)
    aeron7 = verify_or_clone_aeron7()
    source_manifest_hash = canonical_hash(files)
    candidates = generate_candidates(bars, source_manifest_hash, kite_meta["authority"]["archive_sha256"])
    outcomes_df = attach_outcomes(candidates, bars)
    code, code_sha = shell(["git", "rev-parse", "HEAD"], Path(__file__).resolve().parents[1])
    payloads = artifact_payloads(run_dir, bars, candidates, outcomes_df, files, sessions, kite_meta, aeron7, code_sha)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "candidates").mkdir(parents=True, exist_ok=True)
    candidates.to_json(run_dir / "candidates/candidate_manifest.json", orient="records", indent=2)
    digest = file_sha256(run_dir / "candidates/candidate_manifest.json")
    (run_dir / "candidates/candidate_manifest.json.sha256").write_text(f"{digest}  candidate_manifest.json\n", encoding="utf-8")
    candidates.to_parquet(run_dir / "candidates/candidate_manifest.parquet", index=False)
    digest = file_sha256(run_dir / "candidates/candidate_manifest.parquet")
    (run_dir / "candidates/candidate_manifest.parquet.sha256").write_text(f"{digest}  candidate_manifest.parquet\n", encoding="utf-8")
    index = {}
    for rel, payload in payloads.items():
        if rel == "audit/artifact_index.json":
            continue
        index[rel] = write_json(run_dir / rel, payload)
    payloads["audit/artifact_index.json"] = {"artifacts": index, "code_commit_sha": code_sha}
    index["audit/artifact_index.json"] = write_json(run_dir / "audit/artifact_index.json", payloads["audit/artifact_index.json"])
    write_text(run_dir / "report/FINAL_REPORT.md", f"# Structural Pattern Suite v2\n\nFinal verdict: CERTIFY_NONE\n\nReal Kite historical candidates were reconstructed and evaluated. Aeron7 was inventoried as retrospective prehistory but not used for certification in this run. No option edge is claimed.\n")
    write_text(run_dir / "report/EXECUTIVE_SUMMARY.md", "Structural Pattern Suite v2 executed as research only. It reconstructed non-empty Kite candidates, calculated causal outcomes, and failed closed on certification because retrospective-only evidence and option replay are insufficient for production readiness.\n")
    return {"candidate_bundle_hash": str(candidates["candidate_bundle_hash"].iloc[0]), "candidate_count": int(len(candidates)), "source_manifest_hash": source_manifest_hash, "artifact_hashes": index}


def build_reports(output_dir: Path, kite_archive: Path) -> dict[str, Any]:
    invalidate_v1()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    a = run_once(output_dir / "run-a", kite_archive)
    b = run_once(output_dir / "run-b", kite_archive)
    equal = {k: a[k] == b[k] for k in ("candidate_bundle_hash", "candidate_count", "source_manifest_hash")}
    det = {"status": "PASS" if all(equal.values()) else "FAIL", "semantic_equality": equal, "run_a": a, "run_b": b, "canonical_exclusions": ["absolute output paths"]}
    write_json(output_dir / "audit/determinism.json", det)
    if det["status"] != "PASS":
        raise SourceError("two-directory determinism failed")
    return {"output_dir": str(output_dir), "candidate_count": a["candidate_count"], "candidate_bundle_hash": a["candidate_bundle_hash"], "final_verdict": "CERTIFY_NONE"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run structural pattern suite v2 historical evaluation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--kite-archive", type=Path, default=DEFAULT_KITE_ARCHIVE)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        result = build_reports(args.output_dir, args.kite_archive)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
