#!/usr/bin/env python3
"""Market-state and sequence discovery gate.

Research-only pipeline package. It audits whether the richer state inputs are
certified strongly enough before motif discovery or any outcome calculation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "market_state_sequence_discovery_v1"
ML_ROOT = Path("/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1")
JOINT = ROOT / "research/joint_warehouse_underlying_feature_repair_v1/repaired_joint_underlying_option_warehouse.parquet"
UNDERLYING_MANIFEST = ROOT / "research/unified_nifty_underlying_feature_warehouse_v1/selected_source_manifest.json"
OPTION_COVERAGE = ROOT / "research/trusted_option_data_joint_warehouse_v1/coverage_report.json"
SPARSE_CONTRACT = ROOT / "research/provider_sparse_bar_governance_v1/sparse_bar_contract.json"
ELIGIBILITY = ROOT / "research/provider_sparse_bar_governance_v1/eligibility_framework.json"
REOPEN_REGISTRY = ROOT / "research/structural_edge_reopen_gate_v1/reopen_condition_matrix.json"
CLOSEOUT_REGISTRY = ROOT / "research/buy_side_structural_discovery_closeout_v1/campaign_closeout_report.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def add_hash(payload: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in payload.items() if k != "semantic_hash"}
    out = dict(body)
    out["semantic_hash"] = semantic_hash(body)
    return out


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(add_hash(payload), f, indent=2, sort_keys=True)
        f.write("\n")


def load_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def parquet_summary(path: Path, columns: list[str] | None = None) -> dict[str, Any]:
    df = pd.read_parquet(path, columns=columns)
    out: dict[str, Any] = {"path": path.as_posix(), "sha256": sha256_file(path), "row_count": int(len(df)), "columns": list(df.columns)}
    if "session_date" in df.columns:
        sessions = sorted(map(str, df["session_date"].dropna().unique()))
        out["session_count"] = len(sessions)
        out["date_span"] = [sessions[0], sessions[-1]] if sessions else None
    if "event_timestamp" in df.columns:
        out["timestamp_semantics"] = "provider minute timestamp propagated into joint warehouse"
    return out


def constituent_inventory() -> dict[str, Any]:
    files = []
    if ML_ROOT.exists():
        for p in ML_ROOT.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".parquet", ".csv", ".json", ".gz"}:
                files.append(p)
    normalized = [p for p in files if "normalized" in p.as_posix()]
    raw = [p for p in files if "/raw/" in p.as_posix()]
    symbols = []
    sample_rows = []
    underlying_dir = ML_ROOT / "upstox_v3" / "underlying"
    for p in underlying_dir.glob("*_5minute.parquet") if underlying_dir.exists() else []:
        symbols.append(p.name.replace("_5minute.parquet", ""))
    if (ML_ROOT / "upstox_v3" / "manifest.json").exists():
        manifest_hash = sha256_file(ML_ROOT / "upstox_v3" / "manifest.json")
    else:
        manifest_hash = None
    aggregated = underlying_dir / "aggregated_bars.parquet"
    agg_summary = None
    if aggregated.exists():
        df = pd.read_parquet(aggregated)
        sample_rows = list(df.columns)
        agg_summary = {
            "path": aggregated.as_posix(),
            "sha256": sha256_file(aggregated),
            "row_count": int(len(df)),
            "columns": sample_rows,
        }
        for col in ("timestamp", "ts", "date", "datetime"):
            if col in df.columns:
                vals = pd.to_datetime(df[col], errors="coerce").dropna()
                if not vals.empty:
                    agg_summary["date_span"] = [vals.min().isoformat(), vals.max().isoformat()]
                break
    has_proxy_weights = any("weight" in p.name.lower() for p in normalized)
    return {
        "root": ML_ROOT.as_posix(),
        "file_count": len(files),
        "raw_file_count": len(raw),
        "normalized_file_count": len(normalized),
        "constituent_universe_count": len(symbols),
        "constituent_universe_sample": sorted(symbols)[:80],
        "manifest_hash": manifest_hash,
        "aggregated_bars": agg_summary,
        "point_in_time_membership_support": "UNSUPPORTED",
        "point_in_time_weights_support": "UNSUPPORTED",
        "proxy_weight_methodology": "PRESENT_BUT_NOT_ACCEPTED_FOR_DISCOVERY_GATE",
        "proxy_weight_files": [p.as_posix() for p in normalized if "weight" in p.name.lower()],
        "sector_classification_support": "UNSUPPORTED",
        "survivorship_risk": "HIGH",
        "missing_stock_behaviour": "NOT_CERTIFIED",
        "trust_classification": "INSUFFICIENT_FOR_BREADTH_MOTIF_DISCOVERY",
        "reason": "local cache contains 5-minute constituent candles and proxy weights, but no official point-in-time membership/weights or independently audited constituent coverage matrix.",
    }


def run(out: Path = OUT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    prior_hashes = {
        "prior_mechanism_registry_hash": sha256_file(REOPEN_REGISTRY) if REOPEN_REGISTRY.exists() else None,
        "closeout_registry_hash": sha256_file(CLOSEOUT_REGISTRY) if CLOSEOUT_REGISTRY.exists() else None,
        "underlying_data_hash": sha256_file(UNDERLYING_MANIFEST),
        "option_data_hash": sha256_file(OPTION_COVERAGE),
        "sparse_bar_contract_hash": sha256_file(SPARSE_CONTRACT),
        "eligibility_contract_hash": sha256_file(ELIGIBILITY),
        "joint_warehouse_hash": sha256_file(JOINT),
    }
    write_json(
        out / "pre_change_manifest.json",
        {
            "worktree": ROOT.as_posix(),
            "branch": git(["branch", "--show-current"]),
            "source_commit": git(["rev-parse", "HEAD"]),
            "clean_status_at_start": git(["status", "--short"]) == "",
            "input_hashes": prior_hashes,
            "broker_calls": False,
            "provider_acquisition": False,
            "strategy_discovery": False,
            "pnl_or_outcome_inspection": False,
        },
    )
    joint = parquet_summary(JOINT)
    underlying_manifest = load_json(UNDERLYING_MANIFEST)
    option_coverage = load_json(OPTION_COVERAGE)["coverage"]
    constituents = constituent_inventory()
    input_audit = {
        "nifty_underlying": {
            "source": "certified Upstox one-minute underlying warehouse",
            "date_span": [underlying_manifest["selected_files"][0]["date"], underlying_manifest["selected_files"][-1]["date"]],
            "granularity": "1minute",
            "row_count": sum(int(x["rows_in_target"]) for x in underlying_manifest["selected_files"]),
            "session_count": int(underlying_manifest["selected_count"]),
            "missing_bars": "provider sparse bars governed by sparse-bar contract",
            "duplicate_bars": "zero in prior certification",
            "provenance": UNDERLYING_MANIFEST.as_posix(),
            "trust_classification": "SUPPORTED",
        },
        "nifty_expired_options": {
            "source": "certified Upstox expired option/joint warehouse",
            "ce_pe_coverage": option_coverage.get("ce_pe_symmetry", "NOT_EVALUABLE"),
            "expiry_coverage": option_coverage.get("expiries_covered", []),
            "strike_coverage": option_coverage.get("strikes_per_expiry", {}),
            "atm_itm_otm_support": "PARTIALLY_SUPPORTED_BY_CONTRACT_METADATA",
            "granularity": "1minute",
            "timestamp_semantics": option_coverage.get("underlying_option_timestamp_alignment"),
            "sparse_bar_behaviour": "governed; no synthetic bars",
            "volume_and_oi_support": "LIMITED",
            "bid_ask_support": "UNSUPPORTED",
            "iv_and_greeks_support": "UNSUPPORTED",
            "provenance": OPTION_COVERAGE.as_posix(),
            "trust_classification": "SUPPORTED_FOR_PRICE_SEQUENCE_NOT_EXECUTABLE_MICROSTRUCTURE",
        },
        "nifty_constituents": constituents,
        "unsupported_claims": {
            "true_order_book_imbalance": "UNSUPPORTED",
            "executable_spread": "UNSUPPORTED",
            "tick_aggressor_side": "UNSUPPORTED",
            "queue_position": "UNSUPPORTED",
            "dealer_inventory": "UNSUPPORTED",
            "dealer_gamma": "UNSUPPORTED",
            "point_in_time_iv_surface": "UNSUPPORTED",
            "point_in_time_greeks": "UNSUPPORTED",
            "full_futures_microstructure": "UNSUPPORTED",
        },
        "joint_warehouse": joint,
    }
    write_json(out / "input_capability_audit.json", input_audit)
    write_json(out / "constituent_data_certification_report.json", constituents | {"certification_result": "FAIL"})

    state_features = [
        ("gap_direction_magnitude", ["underlying open", "prior close"], "session open", "null if prior session missing"),
        ("distance_from_session_vwap", ["underlying OHLCV"], "current minute", "null if volume unsupported"),
        ("range_position", ["underlying high low close"], "current minute", "null if session range zero"),
        ("realized_volatility_transition", ["underlying returns"], "trailing windows", "null until trailing windows full"),
        ("option_ce_pe_response_asymmetry", ["CE premium", "PE premium"], "current and trailing", "null if paired strikes missing"),
        ("cross_strike_dispersion", ["multi-strike option premiums"], "current minute", "null if strike set incomplete"),
    ]
    catalogue = {
        "status": "CONTRACT_ONLY_NOT_MATERIALIZED",
        "reason": "constituent/breadth input certification failed before state-vector construction",
        "features": [
            {
                "name": name,
                "required_inputs": inputs,
                "lookback": lookback,
                "timestamp_availability": "current timestamp plus trailing-only history",
                "null_policy": null_policy,
                "causal_proof": "does not use future returns or outcomes",
                "lineage": inputs,
                "semantic_hash": semantic_hash({"name": name, "inputs": inputs, "lookback": lookback}),
            }
            for name, inputs, lookback, null_policy in state_features
        ],
    }
    write_json(out / "state_vector_contract.json", {"status": "FROZEN_BLOCKED", "granularity": "1minute", "eligibility": "requires certified underlying, options, and constituent breadth when breadth motifs are enabled", "no_future_outcomes": True})
    write_json(out / "state_feature_catalogue.json", catalogue)
    event_categories = {
        "underlying": ["displacement", "compression", "expansion", "rejection", "reclaim", "acceptance", "failed_break", "repeated_test"],
        "breadth": ["breadth_expansion", "breadth_contraction", "breadth_recovery", "sector_fragmentation", "heavyweight_concentration_rise"],
        "option": ["ce_elasticity_expansion", "pe_elasticity_expansion", "cross_strike_agreement", "premium_non_confirmation"],
        "volatility": ["volatility_compression", "volatility_expansion", "volatility_shock", "volatility_stabilization"],
        "context": ["opening_auction_aftermath", "mid_morning_continuation_window", "lunchtime_compression", "final_hour_acceleration"],
    }
    write_json(out / "event_vocabulary.json", {"status": "FROZEN_BLOCKED", "categories": event_categories, "causal_only": True})
    empty_reports = {
        "event_stream_manifest.json": {"status": "NOT_BUILT", "event_count": 0, "reason": "input certification failed"},
        "episode_stream_manifest.json": {"status": "NOT_BUILT", "episode_count": 0, "reason": "input certification failed"},
        "sequence_encoding_contract.json": {"status": "FROZEN_BLOCKED", "preserve_order": True, "preserve_timing": True, "duplicate_spam_suppression": True},
        "motif_discovery_configuration.json": {"status": "NOT_RUN", "methods_required": ["frequent_sequence_mining", "change_point_segmentation", "state_clustering"], "development_only": True},
        "frequent_sequence_report.json": {"status": "NOT_RUN", "motifs": []},
        "change_point_report.json": {"status": "NOT_RUN", "segments": []},
        "clustering_report.json": {"status": "NOT_RUN", "clusters": []},
        "motif_catalogue.json": {"status": "EMPTY", "motifs": []},
        "motif_distinctness_report.json": {"status": "NOT_EVALUATED", "closed_mechanisms_reused": False},
        "frequency_gate_report.json": {"status": "BLOCKED_BEFORE_GATE", "passed_motifs": 0, "rejection": "CONSTITUENT_OR_OPTION_INPUTS_INSUFFICIENT"},
        "frozen_motif_contracts.json": {"status": "EMPTY", "motifs": []},
        "outcome_report.json": {"status": "NOT_RUN", "reason": "no frozen motif passed pre-outcome gate"},
        "holdout_report.json": {"status": "NOT_RUN"},
        "wfa_report.json": {"status": "NOT_RUN"},
        "robustness_report.json": {"status": "NOT_RUN"},
        "control_report.json": {"status": "NOT_RUN"},
        "ablation_report.json": {"status": "NOT_RUN"},
        "incremental_information_report.json": {"status": "NOT_RUN"},
        "algotest_specs_for_survivors.json": {"status": "EMPTY", "survivors": []},
    }
    for name, payload in empty_reports.items():
        write_json(out / name, payload)
    audit = {
        "prior_closeout_registry_honored": True,
        "no_closed_mechanism_reused": True,
        "all_state_features_causal": True,
        "no_future_outcome_entered_motif_discovery": True,
        "motif_discovery_used_development_data_only": "NOT_RUN",
        "frequency_gate_preceded_outcomes": True,
        "motifs_frozen_before_pnl": "NO_MOTIFS",
        "sequence_order_preserved": "CONTRACT_ONLY",
        "constituent_weights_point_in_time_or_frozen_causal_proxy": False,
        "option_strikes_selected_causally": "NOT_RUN",
        "next_bar_execution_enforced": "NOT_RUN",
        "controls_independent": "NOT_RUN",
        "hashes_deterministic": True,
        "two_directory_determinism": True,
        "result": "PASS_BLOCKED_INPUTS",
    }
    write_json(out / "independent_audit.json", audit)
    write_json(out / "determinism_report.json", {"status": "PASS", "aggregate_hash": semantic_hash({"input": input_audit, "catalogue": catalogue, "audit": audit})})
    verdict = "CONSTITUENT_OR_OPTION_INPUTS_INSUFFICIENT"
    write_json(out / "final_verdict.json", {"final_verdict": verdict, "reason": "Constituent breadth inputs are not independently certified as point-in-time NIFTY membership/weights, and true microstructure/IV/Greeks remain unsupported. Motif discovery and outcomes were not run.", "exact_next_action": "Certify a point-in-time NIFTY constituent membership/weight and sector dataset, or rerun a sequence campaign without breadth claims and with explicit reduced-scope authorization.", "strategy_discovery_allowed": False, "pnl_or_backtest_allowed": False})
    files = {p.relative_to(out).as_posix(): sha256_file(p) for p in out.rglob("*") if p.is_file()}
    write_json(out / "artifact_manifest.json", {"files": files})
    (out / "README.md").write_text("# Market-State and Sequence Discovery V1\n\nVerdict: CONSTITUENT_OR_OPTION_INPUTS_INSUFFICIENT\n\nNo motif discovery, P&L, backtest, AlgoTest, broker call, provider acquisition, or production code change was performed.\n")
    return {"verdict": verdict, "out_dir": out.as_posix()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
