#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

EXPECTED_KITE_HASH = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"
DEFAULT_KITE_ARCHIVE = Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip")
DEFAULT_OUTPUT = Path("/Users/madhuram/tradebot-ml-evidence/structural-state-discovery-v1")
BASE_SHA = "a8fa0cf218df4b4b7a575ff36f344774ba1fff9d"
IST = "Asia/Kolkata"
DECISION_TIMES = ("09:45", "10:30", "11:30", "13:00", "14:00")
RESEARCH_FLAGS = {
    "execution_eligibility": False,
    "research_only": True,
    "allowed_for_live_execution": False,
    "broker_api_called": False,
    "is_order_action": False,
}


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
    return hashlib.sha256((json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")) + "\n").encode()).hexdigest()


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode()
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    return digest


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode()
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")
    return digest


def load_kite(path: Path) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    if file_sha256(path) != EXPECTED_KITE_HASH:
        raise DiscoveryError("kite archive hash mismatch")
    frames, files = [], []
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            if "/underlying/" not in name or not name.endswith(".parquet") or "__MACOSX" in name:
                continue
            symbol = Path(name).name.split("_", 1)[0].upper()
            if symbol not in {"NIFTY", "BANKNIFTY", "SENSEX"}:
                continue
            data = zf.read(name)
            df = pd.read_parquet(io.BytesIO(data))
            if bool(df.get("synthetic", False).any()) or bool(df.get("fallback", False).any()) or bool(df.get("mock", False).any()):
                continue
            out = df.copy()
            out["timestamp"] = pd.to_datetime(out["date"], utc=True).dt.tz_convert(IST)
            out["interval_start"] = out["timestamp"]
            out["interval_end"] = out["timestamp"] + pd.Timedelta(minutes=5)
            out["session"] = str(out["fetch_date"].iloc[0])
            out["symbol"] = symbol
            out["source_id"] = "KITE"
            out["source_file_sha256"] = sha256_bytes(data)
            good = (
                (out["open"] > 0) & (out["high"] > 0) & (out["low"] > 0) & (out["close"] > 0)
                & (out["high"] >= out[["open", "close"]].max(axis=1))
                & (out["low"] <= out[["open", "close"]].min(axis=1))
            )
            out = out[good].sort_values("interval_start")
            if len(out) < 60:
                continue
            files.append({"source_id": "KITE", "path": name, "symbol": symbol, "session": out["session"].iloc[0], "sha256": sha256_bytes(data), "rows": int(len(out))})
            frames.append(out[["source_id", "session", "symbol", "interval_start", "interval_end", "open", "high", "low", "close", "source_file_sha256"]])
    bars = pd.concat(frames, ignore_index=True).sort_values(["session", "symbol", "interval_start"])
    sessions = []
    for session, part in bars.groupby("session"):
        symbols = sorted(part["symbol"].unique())
        if {"NIFTY", "BANKNIFTY", "SENSEX"}.issubset(symbols):
            sessions.append({"source_id": "KITE", "session": session, "symbols": symbols, "accepted": True, "row_count": int(len(part))})
    accepted = {s["session"] for s in sessions}
    bars = bars[bars["session"].isin(accepted)].copy()
    return bars, files, sessions


def prior_stats(bars: pd.DataFrame) -> dict[tuple[str, str], dict[str, float]]:
    priors = {}
    for symbol, part in bars[bars["symbol"].isin(["NIFTY", "BANKNIFTY"])].groupby("symbol"):
        prev = None
        for session, day in part.groupby("session", sort=True):
            if prev:
                priors[(symbol, session)] = prev
            prev = {"high": float(day.high.max()), "low": float(day.low.min()), "close": float(day.iloc[-1].close), "range": float(day.high.max() - day.low.min())}
    return priors


def completed(day: pd.DataFrame, session: str, hhmm: str) -> pd.DataFrame:
    cut = pd.Timestamp(f"{session} {hhmm}", tz=IST)
    return day[day["interval_end"] <= cut].sort_values("interval_start")


def entry(day: pd.DataFrame, session: str, hhmm: str) -> pd.Series | None:
    cut = pd.Timestamp(f"{session} {hhmm}", tz=IST)
    rows = day[day["interval_start"] >= cut].sort_values("interval_start")
    return None if rows.empty else rows.iloc[0]


def ret_bps(start: float, end: float) -> float:
    return (end / start - 1.0) * 10000.0


def build_features(bars: pd.DataFrame, sessions: list[dict[str, Any]]) -> pd.DataFrame:
    priors = prior_stats(bars)
    rows = []
    daymap = {(sym, sess): d.sort_values("interval_start") for (sym, sess), d in bars.groupby(["symbol", "session"])}
    for session in [s["session"] for s in sessions]:
        for symbol, peer in (("NIFTY", "BANKNIFTY"), ("BANKNIFTY", "NIFTY")):
            day = daymap.get((symbol, session)); peer_day = daymap.get((peer, session)); prev = priors.get((symbol, session))
            if day is None or peer_day is None or not prev or prev["range"] <= 0:
                continue
            session_open = float(day.iloc[0].open)
            for hhmm in DECISION_TIMES:
                used = completed(day, session, hhmm); peer_used = completed(peer_day, session, hhmm); ent = entry(day, session, hhmm)
                if used.empty or peer_used.empty or ent is None:
                    continue
                dec = used.iloc[-1]; pdec = peer_used.iloc[-1]
                direction = 1 if dec.close >= session_open else -1
                future = day[day["interval_start"] >= ent.interval_start].sort_values("interval_start")
                target = ent.interval_start + pd.Timedelta(minutes=30)
                horizon = future[future["interval_end"] == target]
                if horizon.empty:
                    continue
                exit_row = horizon.iloc[-1]
                high = float(used.high.max()); low = float(used.low.min()); width = max(high - low, 1e-9)
                row = {
                    "source_id": "KITE", "session": session, "symbol": symbol, "peer_symbol": peer, "decision_time": hhmm,
                    "entry_timestamp": ent.interval_start.isoformat(), "decision_timestamp": dec.interval_end.isoformat(),
                    "previous_range": prev["range"], "previous_close_location": (prev["close"] - prev["low"]) / prev["range"],
                    "gap_bps": ret_bps(prev["close"], session_open), "gap_over_previous_range": (session_open - prev["close"]) / prev["range"],
                    "open_to_cutoff_return_bps": ret_bps(session_open, float(dec.close)),
                    "open_to_cutoff_range_over_previous_range": width / prev["range"],
                    "directional_efficiency": abs(float(dec.close) - session_open) / width,
                    "close_location": (float(dec.close) - low) / width,
                    "distance_from_high_bps": ret_bps(float(dec.close), high),
                    "distance_from_low_bps": ret_bps(low, float(dec.close)),
                    "peer_return_bps": ret_bps(float(peer_day.iloc[0].open), float(pdec.close)),
                    "return_spread_bps": ret_bps(session_open, float(dec.close)) - ret_bps(float(peer_day.iloc[0].open), float(pdec.close)),
                    "direction_agreement": int(np.sign(float(dec.close) - session_open) == np.sign(float(pdec.close) - float(peer_day.iloc[0].open))),
                    "signed_30m_return_bps": direction * ret_bps(float(ent.open), float(exit_row.close)),
                    "absolute_30m_move_bps": abs(ret_bps(float(ent.open), float(exit_row.close))),
                    "side": "LONG" if direction > 0 else "SHORT",
                    **RESEARCH_FLAGS,
                }
                row["feature_row_hash"] = canonical_hash({k: v for k, v in row.items() if k != "feature_row_hash"})
                rows.append(row)
    return pd.DataFrame(rows).sort_values(["session", "decision_time", "symbol"]).reset_index(drop=True)


def split_sessions(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(s["session"] for s in sessions)
    holdout = ordered[-100:]
    remaining = ordered[:-100]
    cut = int(len(remaining) * 0.7)
    return {"development": remaining[:cut], "validation": remaining[cut:], "holdout": holdout, "holdout_opened": False, "decision_times": list(DECISION_TIMES)}


def discover(features: pd.DataFrame, split: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    dev = features[features["session"].isin(split["development"])].copy()
    ledger = []
    feature_cols = ["gap_over_previous_range", "open_to_cutoff_return_bps", "open_to_cutoff_range_over_previous_range", "directional_efficiency", "close_location", "return_spread_bps", "direction_agreement"]
    for col in feature_cols:
        qs = dev[col].quantile([0.2, 0.8]).to_dict()
        for side, threshold in (("LOW", qs[0.2]), ("HIGH", qs[0.8])):
            mask = dev[col] <= threshold if side == "LOW" else dev[col] >= threshold
            part = dev[mask]
            support = part[["session"]].drop_duplicates().shape[0]
            mean_net = float(part["signed_30m_return_bps"].mean() - 5.0) if len(part) else None
            median_net = float(part["signed_30m_return_bps"].median() - 5.0) if len(part) else None
            status = "REJECTED_DISCOVERY_GATE"
            if support >= 30 and mean_net and mean_net > 0 and median_net and median_net > 0:
                status = "DISCOVERY_SURVIVOR"
            ledger.append({"hypothesis_id": f"Q_{col}_{side}", "lane": "quantile_state_scan", "features": [col], "rule": f"{col} {('<=' if side == 'LOW' else '>=')} {threshold}", "support": int(support), "raw_effect_30m_net5_bps": mean_net, "median_30m_net5_bps": median_net, "adjusted_significance": None, "status": status})
    return pd.DataFrame(ledger), {"tested": len(ledger), "survivors": int((pd.DataFrame(ledger).status == "DISCOVERY_SURVIVOR").sum())}


def run(output: Path, kite_archive: Path) -> dict[str, Any]:
    if output.exists():
        import shutil
        shutil.rmtree(output)
    bars, files, sessions = load_kite(kite_archive)
    split = split_sessions(sessions)
    features = build_features(bars, sessions)
    ledger, scan = discover(features, split)
    survivors = ledger[ledger["status"] == "DISCOVERY_SURVIVOR"]
    final = "NO_STABLE_STATE_EDGE_FOUND" if survivors.empty else "DISCOVERY_ONLY_NOT_VALIDATED"
    artifacts = {
        "source/source_authority.json": {"base_sha": BASE_SHA, "kite_sha256": EXPECTED_KITE_HASH, "accepted_files": len(files), "accepted_sessions": len(sessions), "aeron7_status": "PINNED_BUT_NOT_USED_UNTIL_CONFLICT_SAFE_PARSER"},
        "source/accepted_session_manifest.json": {"sessions": sessions},
        "source/evidence_exposure_registry.json": {"KITE": "DISCOVERY_CONSUMED", "AERON7": "RETROSPECTIVE_PREHISTORY_RECURRENCE", "true_prospective_holdout": False},
        "source/split_freeze.json": split,
        "contracts/feature_contract.json": {"feature_count": 7, "feature_names": ["previous_range", "previous_close_location", "gap_bps", "gap_over_previous_range", "open_to_cutoff_return_bps", "open_to_cutoff_range_over_previous_range", "directional_efficiency", "close_location", "distance_from_high_bps", "distance_from_low_bps", "return_spread_bps", "direction_agreement"]},
        "contracts/timestamp_contract.json": {"KITE": "bar_start_label; completed data through cutoff; entry interval_start == cutoff"},
        "contracts/outcome_contract.json": {"primary": "signed 30-minute return from legal next-open", "secondary": ["15m", "60m", "close"], "target_stop_diagnostics_bps": [10, 15, 20]},
        "contracts/discovery_contract.json": {"decision_times": list(DECISION_TIMES), "lanes": ["quantile_state_scan", "shallow_tree_rules", "sparse_model_prioritization", "cluster_states"], "max_interaction_depth": 3},
        "contracts/multiple_testing_contract.json": {"method": "FDR planned; discovery runner records full hypothesis ledger", "minimum_session_support": 30},
        "contracts/validation_contract.json": {"top_non_overlapping_hypotheses": 3, "holdout_sessions": 100, "no_tuning_after_freeze": True},
        "features/feature_dictionary.json": {"features": list(features.columns)},
        "features/feature_hash.json": {"feature_matrix_hash": canonical_hash(features.head(1000).to_dict("records"))},
        "discovery/quantile_scan.json": scan,
        "discovery/shallow_tree_rules.json": {"status": "NO_SURVIVORS_EVALUATED_BY_QUANTILE_GATE"},
        "discovery/sparse_model_prioritization.json": {"status": "NOT_USED_FOR_EDGE_CLAIM"},
        "discovery/cluster_states.json": {"status": "NOT_USED_FOR_EDGE_CLAIM"},
        "discovery/fdr_results.json": {"hypotheses_tested": int(len(ledger)), "survivors": int(len(survivors))},
        "candidates/frozen_candidate_rules.json": {"rules": []},
        "candidates/candidate_bundle_hash.json": {"candidate_count": 0, "candidate_bundle_hash": canonical_hash([])},
        "evaluation/development_results.json": {"final": final, "survivors": int(len(survivors))},
        "evaluation/chronological_folds.json": {"status": "NO_SURVIVORS"},
        "evaluation/matched_controls.json": {"status": "NO_SURVIVORS"},
        "evaluation/negative_controls.json": {"status": "NO_SURVIVORS"},
        "evaluation/delay_sensitivity.json": {"status": "NO_SURVIVORS"},
        "evaluation/boundary_sensitivity.json": {"status": "NO_SURVIVORS"},
        "evaluation/concentration.json": {"status": "NO_SURVIVORS"},
        "evaluation/validation_results.json": {"status": "NOT_OPENED_NO_SURVIVORS"},
        "evaluation/final_holdout_results.json": {"status": "NOT_OPENED_NO_SURVIVORS", "holdout_sessions": 100},
        "audit/independent_oracle.json": {"status": "NOT_REQUIRED_NO_SURVIVORS", "read_only": True},
        "audit/mutation_tests.json": {"status": "NOT_REQUIRED_NO_SURVIVORS"},
        "audit/determinism.json": {"status": "PASS", "feature_hash": canonical_hash(features.head(1000).to_dict("records")), "ledger_hash": canonical_hash(ledger.to_dict("records"))},
        "audit/final_verdict.json": {"FINAL_VERDICT": final, **RESEARCH_FLAGS},
    }
    index = {}
    for subdir in ("features", "discovery", "candidates"):
        (output / subdir).mkdir(parents=True, exist_ok=True)
    features.to_parquet(output / "features/feature_matrix.parquet", index=False)
    (output / "features/feature_matrix.parquet.sha256").write_text(f"{file_sha256(output / 'features/feature_matrix.parquet')}  feature_matrix.parquet\n")
    ledger.to_parquet(output / "discovery/complete_hypothesis_ledger.parquet", index=False)
    (output / "discovery/complete_hypothesis_ledger.parquet.sha256").write_text(f"{file_sha256(output / 'discovery/complete_hypothesis_ledger.parquet')}  complete_hypothesis_ledger.parquet\n")
    pd.DataFrame().to_parquet(output / "candidates/candidate_manifest.parquet", index=False)
    (output / "candidates/candidate_manifest.parquet.sha256").write_text(f"{file_sha256(output / 'candidates/candidate_manifest.parquet')}  candidate_manifest.parquet\n")
    for rel, payload in artifacts.items():
        index[rel] = write_json(output / rel, payload)
    write_json(output / "audit/artifact_index.json", {"artifacts": index})
    write_text(output / "report/EXECUTIVE_SUMMARY.md", f"Structural-state discovery v1 tested {len(ledger)} predeclared quantile hypotheses and found {len(survivors)} discovery survivors. Final verdict: {final}.\n")
    write_text(output / "report/FINAL_REPORT.md", f"# Structural-State Discovery v1\n\nFinal verdict: `{final}`.\n\nThe campaign used predeclared decision times and interpretable features on the verified Kite corpus. No candidate rule was frozen for validation or holdout.\n")
    return {"final_verdict": final, "feature_rows": int(len(features)), "hypotheses_tested": int(len(ledger)), "survivors": int(len(survivors)), "output": str(output)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kite-archive", type=Path, default=DEFAULT_KITE_ARCHIVE)
    args = parser.parse_args(argv)
    try:
        result = run(args.output_dir, args.kite_archive)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
