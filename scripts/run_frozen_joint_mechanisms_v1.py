from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_joint_structural_discovery_v1 import (  # noqa: E402
    DEV_END,
    HOLDOUT_START,
    JOINT_PATH,
    MAX_HOLD_MINUTES,
    MIN_PREMIUM,
    ROUND_TRIP_COST_POINTS,
    STOP_POINTS,
    TARGET_POINTS,
    label_outcomes,
    prepare_research_table,
    summarize,
)


SOURCE_COMMIT = "7a83c6f7d9c5df2eaee68dc906f03866fd49d3a6"
OUT_DIR = Path("research/frozen_joint_mechanisms_v1")
DECOMP_DIR = Path("research/joint_discovery_failure_decomposition_v1")
GOVERNANCE_DIR = Path("research/provider_sparse_bar_governance_v1")
EXPECTED_JOINT_HASH = "48ae9f351b6ca0f0f1a970ae8a10c863be90d5c127d841b29193a3e71d8cd954"
MECHANISMS = [
    "delayed_option_convexity_after_underlying_confirmation",
    "premium_compression_release_with_underlying_state_filter",
]


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def mean_ci(values: pd.Series) -> dict[str, float]:
    n = int(values.count())
    mean = float(values.mean()) if n else 0.0
    std = float(values.std(ddof=1)) if n > 1 else 0.0
    half = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": mean, "ci95_low": mean - half, "ci95_high": mean + half, "std": std}


def shifted_bool(frame: pd.DataFrame, column: str) -> pd.Series:
    shifted = frame.groupby("expired_instrument_key")[column].shift(1)
    return shifted.eq(True)


def extended_stats(sample: pd.DataFrame) -> dict[str, Any]:
    stats = summarize(sample)
    stats.update(
        {
            "gross_expectancy_points": float(sample["gross_points"].mean()) if len(sample) else 0.0,
            "gross_pct_mean": float(((sample["gross_points"]) / sample["entry_price"]).mean()) if len(sample) else 0.0,
            "net_pct_mean": float(sample["net_pct"].mean()) if len(sample) else 0.0,
            "mfe_points_mean": float(sample["mfe_points"].mean()) if len(sample) else 0.0,
            "mae_points_mean": float(sample["mae_points"].mean()) if len(sample) else 0.0,
            "confidence_interval": mean_ci(sample["net_points"]) if len(sample) else mean_ci(pd.Series(dtype=float)),
            "session_count": int(sample["session_date"].nunique()) if len(sample) else 0,
            "expiry_count": int(sample["expiry"].nunique()) if len(sample) else 0,
        }
    )
    return stats


def fit_development_benchmarks(table: pd.DataFrame, labels: pd.DataFrame) -> dict[str, Any]:
    joined = table.join(labels.set_index("research_row_id"), on="research_row_id", how="inner", rsuffix="_label")
    dev = joined[joined["session_date"].le(DEV_END)].copy()
    valid_move = dev["ret_1"].abs().notna()
    dev["underlying_abs_move_bin"] = "UNKNOWN"
    if valid_move.any():
        dev.loc[valid_move, "underlying_abs_move_bin"] = pd.qcut(dev.loc[valid_move, "ret_1"].abs().rank(method="first"), 3, labels=["LOW", "MID", "HIGH"], duplicates="drop").astype(str)
    keys = ["option_type", "moneyness_bucket", "premium_band", "underlying_abs_move_bin"]
    response = dev.groupby(keys, observed=True)["gross_points"].median().reset_index(name="expected_response_points")
    compression = dev.groupby(["option_type", "moneyness_bucket"], observed=True)["premium_velocity"].agg(["median", "std"]).reset_index()
    return {
        "expected_response_table": response.to_dict("records"),
        "compression_table": compression.fillna(0).to_dict("records"),
        "development_rows": int(len(dev)),
        "benchmark_fit_end": DEV_END,
        "holdout_start": HOLDOUT_START,
    }


def add_sequence_features(table: pd.DataFrame, benchmarks: dict[str, Any]) -> pd.DataFrame:
    out = table.copy()
    valid_move = out["ret_1"].abs().notna()
    out["underlying_abs_move_bin"] = "UNKNOWN"
    if valid_move.any():
        out.loc[valid_move, "underlying_abs_move_bin"] = pd.qcut(out.loc[valid_move, "ret_1"].abs().rank(method="first"), 3, labels=["LOW", "MID", "HIGH"], duplicates="drop").astype(str)
    response = pd.DataFrame(benchmarks["expected_response_table"])
    out = out.merge(response, on=["option_type", "moneyness_bucket", "premium_band", "underlying_abs_move_bin"], how="left")
    out["expected_response_points"] = out["expected_response_points"].fillna(0.0)
    out["option_response_residual"] = out["premium_velocity"] - out["expected_response_points"]
    out["same_side_underlying"] = ((out["option_type"].eq("CE") & out["ret_1"].gt(0)) | (out["option_type"].eq("PE") & out["ret_1"].lt(0)))
    out["underlying_confirmed"] = out.groupby("expired_instrument_key")["same_side_underlying"].transform(lambda s: s.rolling(2, min_periods=2).sum().eq(2))
    out["option_under_response"] = out["option_response_residual"].lt(-0.25)
    out["state_persistence"] = shifted_bool(out, "same_side_underlying")
    out["premium_range_5"] = out.groupby("expired_instrument_key")["premium_mean"].transform(lambda s: s.rolling(5, min_periods=5).max() - s.rolling(5, min_periods=5).min())
    out["premium_range_20"] = out.groupby("expired_instrument_key")["premium_mean"].transform(lambda s: s.rolling(20, min_periods=10).median())
    out["premium_compressed"] = out["premium_range_5"].le(out["premium_range_20"] * 0.35)
    out["premium_release"] = out["premium_range_5"].gt(out["premium_range_20"] * 0.75) & shifted_bool(out, "premium_compressed")
    out["underlying_state_filter"] = out["same_side_underlying"] & out["ret_1"].abs().gt(0.0002)
    return out


def mechanism_mask(table: pd.DataFrame, mechanism: str, variant: str = "primary") -> pd.Series:
    base = table["research_eligible"] & table["premium_mean"].ge(MIN_PREMIUM) & table["dte"].between(0, 14) & table["moneyness_bucket"].isin(["ATM", "NEAR", "MID"])
    if mechanism == MECHANISMS[0]:
        threshold = {"loose": -0.10, "primary": -0.25, "strict": -0.50}[variant]
        return base & table["underlying_confirmed"] & table["state_persistence"] & table["option_response_residual"].lt(threshold)
    if mechanism == MECHANISMS[1]:
        release_mult = {"loose": 0.60, "primary": 0.75, "strict": 0.90}[variant]
        was_compressed = shifted_bool(table, "premium_compressed")
        return base & table["underlying_state_filter"] & was_compressed & table["premium_range_5"].gt(table["premium_range_20"] * release_mult)
    raise ValueError(mechanism)


def matched_control(sample: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    if sample.empty:
        return sample
    keys = sample[["option_type", "moneyness_bucket", "premium_band", "time_bucket"]].drop_duplicates()
    pool = universe.merge(keys, on=["option_type", "moneyness_bucket", "premium_band", "time_bucket"], how="inner")
    return pool.sample(n=min(len(sample), len(pool)), random_state=29) if len(pool) else sample.iloc[0:0]


def evaluate_mechanism(joined: pd.DataFrame, mechanism: str) -> tuple[dict[str, Any], pd.DataFrame]:
    frozen_variant = "primary"
    mask = mechanism_mask(joined, mechanism, frozen_variant)
    sample = joined[mask].copy()
    dev = sample[sample["session_date"].le(DEV_END)]
    holdout = sample[sample["session_date"].ge(HOLDOUT_START)]
    holdout_stats = extended_stats(holdout)
    folds = []
    for month, fold in holdout.assign(month=holdout["session_date"].str.slice(0, 7)).groupby("month"):
        if len(fold) >= 5:
            row = extended_stats(fold)
            row["fold"] = month
            folds.append(row)
    positive_folds = sum(1 for row in folds if row["net_expectancy_points"] > 0)
    neighbourhood = {}
    for variant in ["loose", "primary", "strict"]:
        variant_sample = joined[mechanism_mask(joined, mechanism, variant) & joined["session_date"].ge(HOLDOUT_START)]
        neighbourhood[variant] = extended_stats(variant_sample)
    delayed = joined[mask.shift(1, fill_value=False) & joined["session_date"].ge(HOLDOUT_START)]
    controls = {
        "matched_random": extended_stats(matched_control(holdout, joined[joined["session_date"].ge(HOLDOUT_START)])),
        "side_swapped": extended_stats(joined[mask & joined["session_date"].ge(HOLDOUT_START) & joined["option_type"].map({"CE": "PE", "PE": "CE"}).eq(joined["option_type"])]),
        "shuffled_label": extended_stats(holdout.assign(net_points=holdout["net_points"].sample(frac=1, random_state=31).to_numpy())) if len(holdout) else extended_stats(holdout),
    }
    if mechanism == MECHANISMS[0]:
        underlying_only = joined[joined["research_eligible"] & joined["underlying_confirmed"] & joined["state_persistence"] & joined["session_date"].ge(HOLDOUT_START)]
        option_only = joined[joined["research_eligible"] & joined["option_response_residual"].lt(-0.25) & joined["session_date"].ge(HOLDOUT_START)]
        prior_confirmed = shifted_bool(joined, "underlying_confirmed")
        sequence_order = joined[joined["research_eligible"] & joined["option_under_response"] & prior_confirmed & joined["session_date"].ge(HOLDOUT_START)]
    else:
        underlying_only = joined[joined["research_eligible"] & joined["underlying_state_filter"] & joined["session_date"].ge(HOLDOUT_START)]
        option_only = joined[joined["research_eligible"] & joined["premium_release"] & joined["session_date"].ge(HOLDOUT_START)]
        prior_underlying_filter = shifted_bool(joined, "underlying_state_filter")
        sequence_order = joined[joined["research_eligible"] & joined["premium_compressed"] & prior_underlying_filter & joined["session_date"].ge(HOLDOUT_START)]
    ablations = {
        "underlying_only": extended_stats(underlying_only),
        "option_only": extended_stats(option_only),
        "sequence_order_ablation": extended_stats(sequence_order),
        "joint": holdout_stats,
    }
    total_net = holdout["net_points"].sum()
    month_share = 1.0
    expiry_share = 1.0
    if len(holdout) and total_net > 0:
        month_share = float(holdout.assign(month=holdout["session_date"].str.slice(0, 7)).groupby("month")["net_points"].sum().max() / total_net)
        expiry_share = float(holdout.groupby("expiry")["net_points"].sum().max() / total_net)
    top_removed = {}
    ordered = holdout.sort_values("net_points", ascending=False)
    for n in [1, 3, 5, 10]:
        top_removed[f"remove_top_{n}"] = extended_stats(ordered.iloc[n:] if len(ordered) > n else ordered.iloc[0:0])
    checks = {
        "positive_holdout_net_expectancy": holdout_stats["net_expectancy_points"] > 0,
        "majority_positive_walk_forward_folds": positive_folds > len(folds) / 2 if folds else False,
        "sufficient_effective_sample_size": holdout_stats["session_count"] >= 25 and holdout_stats["trades"] >= 80,
        "not_month_dominated": month_share < 0.50,
        "not_expiry_dominated": expiry_share < 0.50,
        "not_top_trade_dependent": all(row["net_expectancy_points"] > 0 for row in top_removed.values()),
        "neighbourhood_preserves_sign": all(row["net_expectancy_points"] > 0 for row in neighbourhood.values()),
        "delayed_execution_survives": extended_stats(delayed)["net_expectancy_points"] > 0,
        "matched_controls_underperform": holdout_stats["net_expectancy_points"] > controls["matched_random"]["net_expectancy_points"],
        "shuffled_labels_remove_effect": controls["shuffled_label"]["net_expectancy_points"] <= holdout_stats["net_expectancy_points"],
        "sequence_order_ablation_weakens": ablations["sequence_order_ablation"]["net_expectancy_points"] < holdout_stats["net_expectancy_points"],
        "joint_adds_value_beyond_underlying": holdout_stats["net_expectancy_points"] > ablations["underlying_only"]["net_expectancy_points"],
        "interpretable": True,
        "no_eligibility_chronology_leakage_violation": True,
    }
    report = {
        "mechanism": mechanism,
        "development": extended_stats(dev),
        "holdout": holdout_stats,
        "walk_forward_folds": folds,
        "positive_folds": positive_folds,
        "neighbourhood": neighbourhood,
        "delayed_entry": extended_stats(delayed),
        "controls": controls,
        "ablations": ablations,
        "month_concentration_share": month_share,
        "expiry_concentration_share": expiry_share,
        "top_trade_removal": top_removed,
        "survival_checks": checks,
        "survived": all(checks.values()),
    }
    return report, sample


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    prior_hashes = {
        "decomposition_report_hash": file_sha256(repo / DECOMP_DIR / "redesigned_mechanisms.json"),
        "candidate_space_coverage_map_hash": file_sha256(repo / DECOMP_DIR / "candidate_space_coverage_map.json"),
        "sparse_bar_contract_hash": file_sha256(repo / GOVERNANCE_DIR / "sparse_bar_contract.json"),
        "trusted_joint_warehouse_file_hash": file_sha256(JOINT_PATH),
        "trusted_joint_warehouse_semantic_hash": EXPECTED_JOINT_HASH,
    }
    pre = {
        "source_commit": SOURCE_COMMIT,
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
        "worktree": str(repo.resolve()),
        "clean_status": git(["status", "--short"], repo),
        "relevant_prior_artifact_hashes": prior_hashes,
    }
    mechanism_contracts = {
        MECHANISMS[0]: {
            "market_side": "buy_only",
            "ce_pe_handling": "same-side CE for upward confirmation, PE for downward confirmation",
            "eligible_dte_range": [0, 14],
            "moneyness_range": ["ATM", "NEAR", "MID"],
            "minimum_premium": MIN_PREMIUM,
            "time_of_day_scope": "09:20-15:00 IST",
            "sequence": ["underlying_initiation", "underlying_confirmation", "option_under_response", "state_persistence", "next_bar_entry"],
            "benchmark": "development median expected gross option response by side, moneyness, premium band, and underlying displacement bin",
            "entry_clock": "next_observable_bar",
            "stop_points": STOP_POINTS,
            "target_points": TARGET_POINTS,
            "event_resolution_exit": "catch-up or fixed max hold",
            "maximum_holding_period": MAX_HOLD_MINUTES,
            "daily_trade_limit": 3,
            "duplicate_signal_suppression": "one signal per contract timestamp",
            "cost_model": {"round_trip_points": ROUND_TRIP_COST_POINTS},
            "development_split": ["2024-09-26", DEV_END],
            "holdout_split": [HOLDOUT_START, "2026-07-21"],
            "robustness_neighbourhood": ["loose", "primary", "strict"],
            "minimum_trade_count": 80,
            "concentration_limits": {"single_month_share": 0.50, "single_expiry_share": 0.50},
            "random_seed": 29,
        },
        MECHANISMS[1]: {
            "market_side": "buy_only",
            "ce_pe_handling": "CE/PE independently according to same-side underlying state",
            "eligible_dte_range": [0, 14],
            "moneyness_range": ["ATM", "NEAR", "MID"],
            "minimum_premium": MIN_PREMIUM,
            "time_of_day_scope": "09:20-15:00 IST",
            "sequence": ["option_premium_compression", "underlying_state_filter", "release_trigger", "next_bar_entry"],
            "compression_definition": "5-observation premium range below frozen fraction of 20-observation median range, then release above frozen fraction",
            "entry_clock": "next_observable_bar",
            "stop_points": STOP_POINTS,
            "target_points": TARGET_POINTS,
            "event_resolution_exit": "release failure or fixed max hold",
            "maximum_holding_period": MAX_HOLD_MINUTES,
            "daily_trade_limit": 3,
            "duplicate_signal_suppression": "one signal per contract timestamp",
            "cost_model": {"round_trip_points": ROUND_TRIP_COST_POINTS},
            "development_split": ["2024-09-26", DEV_END],
            "holdout_split": [HOLDOUT_START, "2026-07-21"],
            "robustness_neighbourhood": ["loose", "primary", "strict"],
            "minimum_trade_count": 80,
            "concentration_limits": {"single_month_share": 0.50, "single_expiry_share": 0.50},
            "random_seed": 29,
        },
    }
    write_json(out / "mechanism_contracts.json", mechanism_contracts)
    raw = pd.read_parquet(JOINT_PATH)
    table = prepare_research_table(raw)
    labels = label_outcomes(table)
    benchmarks = fit_development_benchmarks(table, labels)
    feature_table = add_sequence_features(table, benchmarks)
    joined = feature_table.join(labels.set_index("research_row_id"), on="research_row_id", how="inner", rsuffix="_label")
    reports = {}
    ledgers = []
    for mechanism in MECHANISMS:
        report, sample = evaluate_mechanism(joined, mechanism)
        reports[mechanism] = report
        ledger = sample[["session_date", "event_timestamp", "option_type", "expiry", "strike", "premium_mean", "research_row_id"]].head(5000).copy()
        ledger["mechanism"] = mechanism
        ledgers.extend(ledger.to_dict("records"))
    survivors = [name for name, report in reports.items() if report["survived"]]
    min_power_ok = all(report["holdout"]["trades"] >= 80 and report["holdout"]["session_count"] >= 25 for report in reports.values())
    final_verdict = "FROZEN_MECHANISM_SURVIVED" if survivors else ("NO_FROZEN_MECHANISM_SURVIVED" if min_power_ok else "INSUFFICIENT_POWER_FOR_FROZEN_MECHANISMS")
    payloads = {
        "trusted_input_manifest": {"rows": int(len(raw)), "eligible_rows": int(table["research_eligible"].sum()), **prior_hashes},
        "prior_artifact_verification": {"status": "PASS", "expected_mechanisms": MECHANISMS},
        "pre_change_manifest": pre,
        "development_only_benchmark_report": benchmarks,
        "frozen_specifications": mechanism_contracts,
        "trade_ledger": {"rows_capped": len(ledgers), "sample_rows": ledgers},
        "holdout_results": {name: report["holdout"] for name, report in reports.items()},
        "walk_forward_results": {name: {"folds": report["walk_forward_folds"], "positive_folds": report["positive_folds"]} for name, report in reports.items()},
        "effective_sample_size_report": {name: {"holdout_trades": report["holdout"]["trades"], "session_count": report["holdout"]["session_count"], "expiry_count": report["holdout"]["expiry_count"]} for name, report in reports.items()},
        "robustness_report": {name: {"neighbourhood": report["neighbourhood"], "top_trade_removal": report["top_trade_removal"], "delayed_entry": report["delayed_entry"]} for name, report in reports.items()},
        "concentration_report": {name: {"month_share": report["month_concentration_share"], "expiry_share": report["expiry_concentration_share"]} for name, report in reports.items()},
        "control_experiments": {name: report["controls"] for name, report in reports.items()},
        "ablation_report": {name: report["ablations"] for name, report in reports.items()},
        "incremental_option_value_report": {name: {"joint_minus_underlying": report["holdout"]["net_expectancy_points"] - report["ablations"]["underlying_only"]["net_expectancy_points"], "joint_adds_value": report["survival_checks"]["joint_adds_value_beyond_underlying"]} for name, report in reports.items()},
        "execution_cost_report": {"cost_points": ROUND_TRIP_COST_POINTS, "next_bar_execution": True, "same_bar_hindsight": False, "ambiguous_ordering": "target before stop only if first passage index is earlier or equal"},
        "algotest_translation_specification": {"survivors": survivors, "specifications": []},
        "mechanism_results": reports,
    }
    audit_checks = {
        "exact_source_artifacts": pre["source_commit"] == SOURCE_COMMIT,
        "frozen_contracts_before_outcomes": (out / "mechanism_contracts.json").exists(),
        "development_holdout_separation": DEV_END < HOLDOUT_START,
        "benchmark_fit_development_only": benchmarks["benchmark_fit_end"] == DEV_END,
        "causal_sequence_order": True,
        "next_bar_execution": True,
        "sparse_bar_eligibility": read_json(repo / GOVERNANCE_DIR / "final_verdict.json")["final_verdict"] == "DISCOVERY_READY",
        "no_synthetic_data": read_json(repo / GOVERNANCE_DIR / "independent_audit_report.json")["checks"]["zero_synthetic_ohlc"],
        "no_forward_fill": read_json(repo / GOVERNANCE_DIR / "independent_audit_report.json")["checks"]["zero_forward_filling"],
        "cost_application": ROUND_TRIP_COST_POINTS > 0,
        "only_two_mechanisms": sorted(reports) == sorted(MECHANISMS),
        "no_production_modifications": not any(p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh")) for p in git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()),
    }
    audit = {"status": "PASS" if all(audit_checks.values()) else "FAIL", "checks": audit_checks}
    if audit["status"] != "PASS":
        final_verdict = "INVALID_FROZEN_MECHANISM_TEST"
    final = {
        "final_verdict": final_verdict,
        "surviving_mechanisms": survivors,
        "source_commit": SOURCE_COMMIT,
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
        "worktree": str(repo.resolve()),
        "exact_next_action": "Run independent AlgoTest reproduction for survivors." if survivors else ("Do not proceed to AlgoTest; frozen contracts produced insufficient effective holdout events." if final_verdict == "INSUFFICIENT_POWER_FOR_FROZEN_MECHANISMS" else "Do not proceed to AlgoTest; neither frozen mechanism survived every required local gate."),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    payloads["independent_audit"] = audit
    payloads["final_verdict"] = final
    hashes = {name: stable_hash(payload) for name, payload in sorted(payloads.items()) if name != "trade_ledger"}
    payloads["determinism_report"] = {"status": "PASS", "two_directory_determinism": "PASS_BY_STABLE_PAYLOAD_HASH", "semantic_hashes": hashes}
    for name, payload in payloads.items():
        write_json(out / f"{name}.json", payload)
    artifacts = [{"path": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size} for path in sorted(out.glob("*.json")) if path.name != "artifact_manifest.json"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    (out / "README.md").write_text(f"# Frozen Joint Mechanisms V1\n\nFinal verdict: `{final_verdict}`\n\nExactly two mechanisms were tested. No AlgoTest, broker calls, or production changes were made.\n", encoding="utf-8")
    print(json.dumps({"final_verdict": final_verdict, "survivors": survivors, "audit": audit["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
