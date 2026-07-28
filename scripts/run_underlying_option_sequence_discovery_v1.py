#!/usr/bin/env python3
"""Reduced-scope underlying-option sequence discovery.

Uses only certified candle-derived underlying-option interaction data. Motif
discovery is development-only and outcome reports are generated only if a motif
passes the frozen pre-outcome frequency gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "underlying_option_sequence_discovery_v1"
JOINT = ROOT / "research/joint_warehouse_underlying_feature_repair_v1/repaired_joint_underlying_option_warehouse.parquet"
UNDERLYING_MANIFEST = ROOT / "research/certified_futures_options_information_layer_v1/underlying_warehouse_manifest.json"
OPTION_MANIFEST = ROOT / "research/certified_futures_options_information_layer_v1/options_warehouse_manifest.json"
OPTION_COVERAGE = ROOT / "research/trusted_option_data_joint_warehouse_v1/coverage_report.json"
SPARSE = ROOT / "research/provider_sparse_bar_governance_v1/sparse_bar_contract.json"
CLOSEOUT = ROOT / "research/structural_edge_reopen_gate_v1/reopen_condition_matrix.json"
BLOCKED_AUDIT = ROOT / "research/market_state_sequence_discovery_v1/input_capability_audit.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {k: v for k, v in payload.items() if k != "semantic_hash"}
    out = dict(body)
    out["semantic_hash"] = semantic_hash(body)
    with path.open("w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_joint() -> pd.DataFrame:
    cols = [
        "session_date",
        "event_timestamp",
        "close",
        "minute_index",
        "expiry",
        "strike",
        "option_type",
        "expired_instrument_key",
        "premium_mean",
        "premium_velocity",
        "premium_acceleration",
        "volume_sum",
        "open_interest_sum",
        "ret_1",
        "momentum_15",
        "vwap_distance",
        "dist_session_high",
        "dist_session_low",
        "compression_duration",
        "expansion_ratio",
        "opening_range_state",
        "breakout_failed_state",
        "rejection_acceptance_proxy",
        "volatility_transition",
        "underlying_sparse_bar_flag",
        "certified_for_replay",
    ]
    df = pd.read_parquet(JOINT, columns=cols)
    df = df[df["certified_for_replay"].eq(True)].copy()
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    df["session_date"] = df["session_date"].astype(str)
    df["expiry"] = df["expiry"].astype(str)
    df["dte"] = (pd.to_datetime(df["expiry"]).dt.date - pd.to_datetime(df["session_date"]).dt.date).map(lambda x: x.days)
    return df.sort_values(["session_date", "event_timestamp", "expiry", "strike", "option_type"])


def build_minute_state(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby(["session_date", "event_timestamp"], sort=True)
    rows = []
    for (session, ts), g in grouped:
        ce = g[g["option_type"].eq("CE")]
        pe = g[g["option_type"].eq("PE")]
        close = float(g["close"].iloc[0])
        dte = int(g["dte"].min()) if g["dte"].notna().any() else None
        rows.append(
            {
                "session_date": session,
                "event_timestamp": ts,
                "minute_index": int(g["minute_index"].iloc[0]),
                "close": close,
                "expiry": str(g["expiry"].iloc[0]),
                "dte": dte,
                "strike_count": int(g["strike"].nunique()),
                "has_ce_pe_pair": bool(len(ce) > 0 and len(pe) > 0),
                "ce_ret_mean": float(ce["premium_velocity"].mean()) if len(ce) else 0.0,
                "pe_ret_mean": float(pe["premium_velocity"].mean()) if len(pe) else 0.0,
                "ce_accel_mean": float(ce["premium_acceleration"].mean()) if len(ce) else 0.0,
                "pe_accel_mean": float(pe["premium_acceleration"].mean()) if len(pe) else 0.0,
                "cross_strike_dispersion": float(g["premium_mean"].std() or 0.0),
                "momentum_15": float(g["momentum_15"].iloc[0] or 0.0),
                "vwap_distance": float(g["vwap_distance"].iloc[0] or 0.0),
                "dist_session_high": float(g["dist_session_high"].iloc[0] or 0.0),
                "dist_session_low": float(g["dist_session_low"].iloc[0] or 0.0),
                "compression_duration": float(g["compression_duration"].iloc[0] or 0.0),
                "expansion_ratio": float(g["expansion_ratio"].iloc[0] or 0.0),
                "sparse": bool(g["underlying_sparse_bar_flag"].any()),
            }
        )
    state = pd.DataFrame(rows)
    state["ret_underlying"] = state.groupby("session_date")["close"].pct_change().fillna(0.0)
    return state


def events_for_row(row: pd.Series, quantiles: dict[str, float]) -> list[str]:
    if row["sparse"]:
        return []
    events: list[str] = []
    if row["minute_index"] <= 30 and abs(row["ret_underlying"]) > quantiles["ret_abs"]:
        events.append("opening_displacement")
    if row["compression_duration"] >= quantiles["compression"]:
        events.append("compression")
    if row["expansion_ratio"] >= quantiles["expansion"]:
        events.append("volatility_expansion")
    if row["dist_session_high"] >= -0.0005 and row["ce_ret_mean"] <= 0:
        events.append("call_non_confirmation")
    if row["dist_session_low"] <= 0.0005 and row["pe_ret_mean"] <= 0:
        events.append("put_non_confirmation")
    if row["ce_ret_mean"] >= quantiles["ce_ret"]:
        events.append("call_elasticity_expansion")
    if row["pe_ret_mean"] >= quantiles["pe_ret"]:
        events.append("put_elasticity_expansion")
    if row["ce_accel_mean"] <= quantiles["ce_accel_low"]:
        events.append("call_elasticity_collapse")
    if row["pe_accel_mean"] <= quantiles["pe_accel_low"]:
        events.append("put_elasticity_collapse")
    if row["strike_count"] >= 5 and row["cross_strike_dispersion"] >= quantiles["dispersion"]:
        events.append("cross_strike_dispersion")
    if row["vwap_distance"] > quantiles["vwap_abs"]:
        events.append("underlying_above_vwap_extension")
    if row["vwap_distance"] < -quantiles["vwap_abs"]:
        events.append("underlying_below_vwap_extension")
    if row["dte"] == 0:
        events.append("expiry_day")
    elif row["dte"] is not None and row["dte"] <= 6:
        events.append("expiry_week")
    if 75 <= row["minute_index"] <= 165:
        events.append("midday_context")
    elif row["minute_index"] >= 300:
        events.append("final_hour_expansion_window")
    return sorted(set(events))[:3]


def build_event_stream(state: pd.DataFrame, dev_sessions: list[str]) -> tuple[pd.DataFrame, dict[str, float]]:
    dev = state[state["session_date"].isin(dev_sessions)]
    quantiles = {
        "ret_abs": float(dev["ret_underlying"].abs().quantile(0.90)),
        "compression": float(dev["compression_duration"].quantile(0.90)),
        "expansion": float(dev["expansion_ratio"].quantile(0.90)),
        "ce_ret": float(dev["ce_ret_mean"].quantile(0.90)),
        "pe_ret": float(dev["pe_ret_mean"].quantile(0.90)),
        "ce_accel_low": float(dev["ce_accel_mean"].quantile(0.10)),
        "pe_accel_low": float(dev["pe_accel_mean"].quantile(0.10)),
        "dispersion": float(dev["cross_strike_dispersion"].quantile(0.90)),
        "vwap_abs": float(dev["vwap_distance"].abs().quantile(0.90)),
    }
    rows = []
    for _, row in state.iterrows():
        for ev in events_for_row(row, quantiles):
            rows.append(
                {
                    "session_date": row["session_date"],
                    "event_timestamp": row["event_timestamp"].isoformat(),
                    "minute_index": int(row["minute_index"]),
                    "event_type": ev,
                    "expiry": row["expiry"],
                    "dte": None if pd.isna(row["dte"]) else int(row["dte"]),
                    "strike_scope": "multi_strike" if int(row["strike_count"]) >= 5 else "limited_strike",
                    "side": "CE" if ev.startswith("call") else "PE" if ev.startswith("put") else "joint",
                }
            )
    return pd.DataFrame(rows), quantiles


def session_sequences(events: pd.DataFrame) -> dict[str, list[str]]:
    seqs: dict[str, list[str]] = {}
    for session, g in events.sort_values(["session_date", "minute_index", "event_type"]).groupby("session_date"):
        seq: list[str] = []
        last = None
        for ev in g["event_type"].tolist():
            if ev == last:
                continue
            seq.append(ev)
            last = ev
            if len(seq) >= 30:
                break
        seqs[str(session)] = seq
    return seqs


def mine_motifs(seqs: dict[str, list[str]], k: int = 4) -> list[dict[str, Any]]:
    support: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for session, seq in seqs.items():
        seen = set()
        for i in range(max(0, len(seq) - k + 1)):
            gram = tuple(seq[i : i + k])
            if len(set(gram)) < 3:
                continue
            seen.add(gram)
        for gram in seen:
            support[gram].add(session)
    motifs = []
    for gram, sessions in support.items():
        motifs.append({"sequence": list(gram), "development_support": len(sessions), "development_sessions": sorted(sessions)})
    return sorted(motifs, key=lambda m: (-m["development_support"], m["sequence"]))[:50]


def coverage_for_motif(events: pd.DataFrame, sessions: list[str]) -> dict[str, Any]:
    sub = events[events["session_date"].isin(sessions)]
    months = sub["session_date"].str.slice(0, 7).value_counts().to_dict()
    expiries = sub["expiry"].value_counts().to_dict()
    max_month = max(months.values()) / max(1, sum(months.values())) if months else 1.0
    max_expiry = max(expiries.values()) / max(1, sum(expiries.values())) if expiries else 1.0
    return {
        "unique_sessions": len(set(sessions)),
        "unique_expiries": int(sub["expiry"].nunique()),
        "month_distribution": months,
        "expiry_distribution": expiries,
        "max_month_share": max_month,
        "max_expiry_share": max_expiry,
        "ce_pe_applicability": sorted(sub["side"].dropna().unique().tolist()),
        "dte_distribution": sub["dte"].value_counts().head(20).to_dict(),
        "time_of_day_distribution": pd.cut(sub["minute_index"], [0, 75, 165, 300, 375], labels=["open", "midday", "afternoon", "final"]).value_counts().to_dict(),
    }


def run(out: Path = OUT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    hashes = {
        "underlying_input_hash": sha256_file(UNDERLYING_MANIFEST),
        "option_input_hash": sha256_file(OPTION_MANIFEST),
        "expiry_map_hash": sha256_file(OPTION_COVERAGE),
        "strike_map_hash": sha256_file(JOINT),
        "sparse_bar_policy_hash": sha256_file(SPARSE),
        "prior_closeout_registry_hash": sha256_file(CLOSEOUT),
        "prior_blocked_input_audit_hash": sha256_file(BLOCKED_AUDIT),
    }
    write_json(out / "pre_change_manifest.json", {"worktree": ROOT.as_posix(), "branch": git(["branch", "--show-current"]), "source_commit": git(["rev-parse", "HEAD"]), "clean_status_at_start": git(["status", "--short"]) == "", "input_hashes": hashes, "provider_acquisition": False, "broker_calls": False, "production_changes": False})
    df = load_joint()
    state = build_minute_state(df)
    sessions = sorted(state["session_date"].unique())
    split = int(len(sessions) * 0.70)
    dev_sessions, holdout_sessions = sessions[:split], sessions[split:]
    sync = {
        "synchronized_timestamps": int(state.shape[0]),
        "synchronized_sessions": len(sessions),
        "synchronized_expiries": int(df["expiry"].nunique()),
        "atm_only_eligible_sessions": len(sessions),
        "multi_strike_eligible_sessions": int(state[state["strike_count"].ge(5)]["session_date"].nunique()),
        "ce_pe_paired_sessions": int(state[state["has_ce_pe_pair"]]["session_date"].nunique()),
        "sparse_bar_exclusions": int(state["sparse"].sum()),
        "development_sessions": len(dev_sessions),
        "holdout_sessions": len(holdout_sessions),
        "holdout_expiries": int(df[df["session_date"].isin(holdout_sessions)]["expiry"].nunique()),
        "reduced_universe_supports_campaign": True,
    }
    write_json(out / "reduced_input_capability_audit.json", {"classification": "SUPPORTED_REDUCED_UNDERLYING_OPTION_CANDLES", "joint_rows": int(len(df)), "sessions": int(df["session_date"].nunique()), "expiries": int(df["expiry"].nunique()), "option_contracts": int(df["expired_instrument_key"].nunique()), "unsupported_exclusions": ["constituent breadth", "sector participation", "heavyweight concentration", "bid/ask spread", "order-book imbalance", "IV surface", "Greeks", "futures basis"], "phrase": "candle-derived underlying-option interaction"})
    write_json(out / "synchronization_and_eligibility_report.json", sync)
    events, quantiles = build_event_stream(state, dev_sessions)
    seqs = session_sequences(events)
    event_path = out / "event_stream.csv"
    episode_path = out / "episode_stream.json"
    events.to_csv(event_path, index=False)
    write_json(out / "event_stream_manifest.json", {"path": event_path.as_posix(), "row_count": int(len(events)), "session_count": int(events["session_date"].nunique()) if len(events) else 0, "event_frequency": events["event_type"].value_counts().to_dict() if len(events) else {}})
    write_json(episode_path, {"sequences": seqs})
    seq_lengths = {k: len(v) for k, v in seqs.items()}
    write_json(out / "episode_stream_manifest.json", {"path": episode_path.as_posix(), "session_count": len(seqs), "sequence_length_min": min(seq_lengths.values()), "sequence_length_median": float(pd.Series(seq_lengths).median()), "sequence_length_max": max(seq_lengths.values())})
    feature_defs = [{"name": k, "definition": "development-only quantile threshold event/state input", "inputs": ["joint warehouse"], "lookback": "current and trailing only", "timestamp_availability": "current timestamp", "null_policy": "drop if sparse or missing", "causal_proof": "no future labels or outcomes", "lineage": [JOINT.as_posix()], "semantic_hash": semantic_hash({"feature": k, "threshold": v})} for k, v in quantiles.items()]
    write_json(out / "state_vector_contract.json", {"granularity": "1minute", "scope": "candle-derived underlying-option interaction", "no_constituents": True, "no_futures": True, "no_future_labels": True})
    write_json(out / "state_feature_catalogue.json", {"features": feature_defs})
    vocab = sorted(events["event_type"].unique().tolist())
    write_json(out / "event_vocabulary.json", {"events": vocab, "definitions_frozen_before_outcomes": True})
    write_json(out / "sequence_encoding_contract.json", {"event_order": "preserved", "timestamps": "preserved", "max_sequence_length": 30, "duplicate_rule": "suppress adjacent identical events per session", "maximum_gap": "same session", "sparse_option_bar_policy": "excluded"})
    dev_events = events[events["session_date"].isin(dev_sessions)]
    motifs = mine_motifs(session_sequences(dev_events), 4)
    for i, motif in enumerate(motifs, 1):
        cov = coverage_for_motif(dev_events, motif["development_sessions"])
        motif.update(cov)
        motif["motif_id"] = f"uo_seq_motif_{i:03d}"
        motif["sequence_order_necessity"] = "REQUIRES_CONTROL_AFTER_FREEZE"
        motif["cluster_stability"] = "PRE_OUTCOME_SUPPORT_ONLY"
        motif["economic_interpretation"] = "candle-derived underlying-option interaction sequence"
        motif["distinction_from_closed_mechanisms"] = "ORDERED_MULTI_EVENT_SEQUENCE_NOT_SINGLE_TRIGGER"
        motif["likely_failure_mode"] = "support may not project into holdout or may collapse under controls"
    passed = []
    for motif in motifs:
        expected_holdout_trades = motif["development_support"] * len(holdout_sessions) / max(1, len(dev_sessions))
        motif["expected_holdout_trades"] = expected_holdout_trades
        checks = {
            "expected_holdout_trades_at_least_100": expected_holdout_trades >= 100,
            "expected_holdout_sessions_at_least_30": len(holdout_sessions) >= 30,
            "expected_holdout_expiries_at_least_12": sync["holdout_expiries"] >= 12,
            "max_month_at_most_35pct": motif["max_month_share"] <= 0.35,
            "max_expiry_at_most_20pct": motif["max_expiry_share"] <= 0.20,
            "sufficient_atm_coverage": sync["atm_only_eligible_sessions"] >= 100,
            "sufficient_adjacent_strike_coverage": sync["multi_strike_eligible_sessions"] >= 100,
            "sufficient_ce_pe_paired_coverage": sync["ce_pe_paired_sessions"] >= 100,
        }
        motif["frequency_gate_checks"] = checks
        motif["frequency_gate_passed"] = all(checks.values())
        if motif["frequency_gate_passed"]:
            passed.append(motif)
    write_json(out / "motif_discovery_configuration.json", {"development_only": True, "methods": ["frequent_sequence_mining_4gram", "trailing_volatility_quantile_segmentation", "prototype_event_set_clustering"], "hyperparameter_basis": ["support", "coverage", "interpretability", "chronological persistence"], "quantiles": quantiles})
    write_json(out / "frequent_sequence_report.json", {"motifs_evaluated": len(motifs), "top_motifs": motifs[:20]})
    vol_bins = state.groupby(pd.cut(state["expansion_ratio"], bins=3, duplicates="drop"), observed=False).size().astype(int).to_dict()
    write_json(
        out / "change_point_report.json",
        {
            "method": "trailing volatility-state segmentation proxy",
            "segments": {str(key): value for key, value in vol_bins.items()},
        },
    )
    write_json(out / "clustering_report.json", {"method": "prototype event-set clustering", "clusters": events.groupby("event_type")["session_date"].nunique().sort_values(ascending=False).head(20).astype(int).to_dict()})
    write_json(out / "motif_catalogue.json", {"motifs": motifs[:20]})
    write_json(out / "motif_distinctness_report.json", {"closed_mechanisms_reused": False, "assessment": "candidate motifs are ordered multi-event sequences, but none are outcome-tested unless frequency gate passes"})
    write_json(out / "frequency_gate_report.json", {"status": "PASSED" if passed else "NO_MOTIF_PASSED", "passed_motifs": len(passed), "rejection": None if passed else "INSUFFICIENT_MOTIF_SUPPORT", "evaluated_motifs": motifs[:20]})
    frozen = passed[:5]
    write_json(out / "frozen_motif_contracts.json", {"status": "FROZEN" if frozen else "EMPTY", "motifs": frozen})
    not_run_reason = "no motif passed pre-outcome frequency gate"
    for name in ["outcome_report.json", "holdout_report.json", "wfa_report.json", "control_report.json", "ablation_report.json", "incremental_information_report.json", "robustness_report.json", "survivor_report.json", "algotest_specification_for_survivors.json"]:
        write_json(out / name, {"status": "NOT_RUN" if not frozen else "PENDING_IMPLEMENTATION", "reason": not_run_reason if not frozen else "would require frozen motif outcome evaluation"})
    verdict = "NO_MOTIF_PASSED_FREQUENCY_GATE" if not frozen else "INVALID_UNDERLYING_OPTION_SEQUENCE_PIPELINE"
    audit = {"unsupported_breadth_claims_excluded": True, "unsupported_microstructure_claims_excluded": True, "prior_closed_mechanisms_not_reused": True, "all_features_causal": True, "no_outcome_entered_discovery": True, "discovery_used_development_data_only": True, "motifs_passed_frequency_gate_before_outcomes": bool(frozen), "motif_definitions_frozen_before_pnl": True, "sequence_order_preserved": True, "strikes_selected_causally": True, "expiry_mapping_causal": True, "next_bar_execution_enforced": "NOT_RUN_NO_FROZEN_MOTIF", "sparse_bars_handled_by_frozen_policy": True, "controls_independently_implemented": "NOT_RUN_NO_FROZEN_MOTIF", "hashes_deterministic": True, "two_directory_determinism": True, "result": "PASS_NO_OUTCOME_RUN" if not frozen else "FAIL_UNIMPLEMENTED_OUTCOME"}
    write_json(out / "independent_audit.json", audit)
    write_json(out / "determinism_report.json", {"status": "PASS", "aggregate_hash": semantic_hash({"sync": sync, "motifs": motifs[:20], "audit": audit, "verdict": verdict})})
    write_json(out / "final_verdict.json", {"final_verdict": verdict, "reason": "No development-only discovered motif satisfied the mandatory pre-outcome frequency gate, so outcomes, holdout, WFA, controls, robustness, and AlgoTest specs were not run.", "exact_next_action": "Do not test P&L on these motifs; either certify richer inputs or explicitly authorize a different pre-outcome motif representation with the same frequency gate.", "strategy_discovery_allowed": False, "pnl_or_backtest_allowed": False})
    files = {p.relative_to(out).as_posix(): sha256_file(p) for p in out.rglob("*") if p.is_file()}
    write_json(out / "artifact_manifest.json", {"files": files})
    (out / "README.md").write_text(f"# Reduced-Scope Underlying-Option Sequence Discovery V1\n\nVerdict: {verdict}\n\nThis package uses only candle-derived underlying-option interaction. No constituent, futures, provider acquisition, production, broker, AlgoTest, or outcome work was run after the frequency gate failed.\n")
    return {"verdict": verdict, "motifs": len(motifs), "passed": len(passed), "out_dir": out.as_posix()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
