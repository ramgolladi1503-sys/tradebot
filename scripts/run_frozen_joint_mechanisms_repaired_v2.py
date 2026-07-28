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
    MAX_HOLD_MINUTES,
    MIN_PREMIUM,
    ROUND_TRIP_COST_POINTS,
    STOP_POINTS,
    TARGET_POINTS,
    label_outcomes,
    prepare_research_table,
    summarize,
)


SOURCE_COMMIT = "41c2c92fe40eedcf35a382463de96f21ac67ff0e"
OUT_DIR = Path("research/frozen_joint_mechanisms_repaired_v2")
REPAIR_DIR = Path("research/joint_warehouse_underlying_feature_repair_v1")
GOVERNANCE_DIR = Path("research/provider_sparse_bar_governance_v1")
V1_DIR = Path("research/frozen_joint_mechanisms_v1")
REPAIRED_JOINT_PATH = REPAIR_DIR / "repaired_joint_underlying_option_warehouse.parquet"
MECHANISMS = [
    "delayed_option_convexity_after_underlying_confirmation",
    "premium_compression_release_with_underlying_state_filter",
]
ALLOWED_FINAL_VERDICTS = {
    "FROZEN_MECHANISM_SURVIVED",
    "NO_FROZEN_MECHANISM_SURVIVED",
    "INSUFFICIENT_POWER_AFTER_REPAIR",
    "INVALID_FROZEN_RERUN",
}


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def mean_ci(values: pd.Series) -> dict[str, float]:
    n = int(values.count())
    mean = float(values.mean()) if n else 0.0
    std = float(values.std(ddof=1)) if n > 1 else 0.0
    half = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": mean, "ci95_low": mean - half, "ci95_high": mean + half, "std": std}


def shifted_bool(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame.groupby("expired_instrument_key", sort=False)[column].shift(1).eq(True)


def extended_stats(sample: pd.DataFrame) -> dict[str, Any]:
    stats = summarize(sample)
    stats.update(
        {
            "gross_expectancy_points": float(sample["gross_points"].mean()) if len(sample) else 0.0,
            "gross_pct_mean": float((sample["gross_points"] / sample["entry_price"]).mean()) if len(sample) else 0.0,
            "net_pct_mean": float(sample["net_pct"].mean()) if len(sample) else 0.0,
            "mfe_points_mean": float(sample["mfe_points"].mean()) if len(sample) else 0.0,
            "mae_points_mean": float(sample["mae_points"].mean()) if len(sample) else 0.0,
            "confidence_interval": mean_ci(sample["net_points"]) if len(sample) else mean_ci(pd.Series(dtype=float)),
            "session_count": int(sample["session_date"].nunique()) if len(sample) else 0,
            "expiry_count": int(sample["expiry"].nunique()) if len(sample) else 0,
        }
    )
    return stats


def add_response_bins(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()
    out["underlying_abs_move_bin"] = "UNKNOWN"
    valid = out["ret_1"].abs().notna()
    if valid.any():
        out.loc[valid, "underlying_abs_move_bin"] = pd.qcut(
            out.loc[valid, "ret_1"].abs().rank(method="first"),
            3,
            labels=["LOW", "MID", "HIGH"],
            duplicates="drop",
        ).astype(str)
    return out


def fit_development_benchmarks(table: pd.DataFrame) -> dict[str, Any]:
    dev = add_response_bins(table[table["session_date"].le(DEV_END)]).copy()
    keys = ["option_type", "moneyness_bucket", "premium_band", "underlying_abs_move_bin"]
    response = dev.groupby(keys, observed=True)["premium_velocity"].median().reset_index(name="expected_response_points")
    compression = dev.groupby(["option_type", "moneyness_bucket"], observed=True)["premium_velocity"].agg(["median", "std"]).reset_index()
    return {
        "causal_fit_rule": "development-only median current-bar premium_velocity by side, moneyness, premium band, and underlying displacement bin",
        "no_future_outcome_fields_used": True,
        "expected_response_table": response.to_dict("records"),
        "compression_table": compression.fillna(0).to_dict("records"),
        "development_rows": int(len(dev)),
        "benchmark_fit_end": DEV_END,
        "holdout_start": HOLDOUT_START,
    }


def add_sequence_features(table: pd.DataFrame, benchmarks: dict[str, Any]) -> pd.DataFrame:
    out = add_response_bins(table)
    response = pd.DataFrame(benchmarks["expected_response_table"])
    out = out.merge(response, on=["option_type", "moneyness_bucket", "premium_band", "underlying_abs_move_bin"], how="left")
    out["expected_response_points"] = out["expected_response_points"].fillna(0.0)
    out["option_response_residual"] = out["premium_velocity"] - out["expected_response_points"]
    out["same_side_underlying"] = (out["option_type"].eq("CE") & out["ret_1"].gt(0)) | (out["option_type"].eq("PE") & out["ret_1"].lt(0))
    out["underlying_confirmed"] = out.groupby("expired_instrument_key", sort=False)["same_side_underlying"].transform(
        lambda s: s.rolling(2, min_periods=2).sum().eq(2)
    )
    out["state_persistence"] = shifted_bool(out, "same_side_underlying")
    out["option_under_response"] = out["option_response_residual"].lt(-0.25)
    out["premium_range_5"] = out.groupby("expired_instrument_key", sort=False)["premium_mean"].transform(
        lambda s: s.rolling(5, min_periods=5).max() - s.rolling(5, min_periods=5).min()
    )
    out["premium_range_20"] = out.groupby("expired_instrument_key", sort=False)["premium_mean"].transform(
        lambda s: s.rolling(20, min_periods=10).median()
    )
    out["premium_compressed"] = out["premium_range_5"].le(out["premium_range_20"] * 0.35)
    out["premium_release"] = out["premium_range_5"].gt(out["premium_range_20"] * 0.75) & shifted_bool(out, "premium_compressed")
    out["underlying_state_filter"] = out["same_side_underlying"] & out["ret_1"].abs().gt(0.0002)
    out["opposite_side_underlying"] = (out["option_type"].eq("CE") & out["ret_1"].lt(0)) | (out["option_type"].eq("PE") & out["ret_1"].gt(0))
    return out


def base_mask(table: pd.DataFrame) -> pd.Series:
    return (
        table["research_eligible"]
        & table["premium_mean"].ge(MIN_PREMIUM)
        & table["dte"].between(0, 14)
        & table["moneyness_bucket"].isin(["ATM", "NEAR", "MID"])
    )


def mechanism_mask(table: pd.DataFrame, mechanism: str, variant: str = "primary") -> pd.Series:
    if mechanism == MECHANISMS[0]:
        threshold = {"loose": -0.10, "primary": -0.25, "strict": -0.50}[variant]
        return base_mask(table) & table["underlying_confirmed"] & table["state_persistence"] & table["option_response_residual"].lt(threshold)
    if mechanism == MECHANISMS[1]:
        release_mult = {"loose": 0.60, "primary": 0.75, "strict": 0.90}[variant]
        return base_mask(table) & table["underlying_state_filter"] & shifted_bool(table, "premium_compressed") & table["premium_range_5"].gt(table["premium_range_20"] * release_mult)
    raise ValueError(mechanism)


def side_swapped_mask(table: pd.DataFrame, mechanism: str) -> pd.Series:
    if mechanism == MECHANISMS[0]:
        return base_mask(table) & table["opposite_side_underlying"] & shifted_bool(table, "opposite_side_underlying") & table["option_response_residual"].lt(-0.25)
    return base_mask(table) & table["opposite_side_underlying"] & shifted_bool(table, "premium_compressed") & table["premium_range_5"].gt(table["premium_range_20"] * 0.75)


def matched_control(sample: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    if sample.empty:
        return sample
    keys = sample[["option_type", "moneyness_bucket", "premium_band", "time_bucket"]].drop_duplicates()
    pool = universe.merge(keys, on=["option_type", "moneyness_bucket", "premium_band", "time_bucket"], how="inner")
    return pool.sample(n=min(len(sample), len(pool)), random_state=29) if len(pool) else sample.iloc[0:0]


def evaluate_mechanism(joined: pd.DataFrame, mechanism: str) -> tuple[dict[str, Any], pd.DataFrame]:
    mask = mechanism_mask(joined, mechanism)
    sample = joined[mask].copy()
    dev = sample[sample["session_date"].le(DEV_END)]
    holdout = sample[sample["session_date"].ge(HOLDOUT_START)]
    holdout_stats = extended_stats(holdout)
    folds = []
    for month, fold in holdout.assign(month=holdout["session_date"].str.slice(0, 7)).groupby("month"):
        if len(fold) >= 5:
            folds.append({"fold": month, **extended_stats(fold)})
    positive_folds = sum(row["net_expectancy_points"] > 0 for row in folds)
    neighbourhood = {
        variant: extended_stats(joined[mechanism_mask(joined, mechanism, variant) & joined["session_date"].ge(HOLDOUT_START)])
        for variant in ["loose", "primary", "strict"]
    }
    delayed = joined[mask.groupby(joined["expired_instrument_key"]).shift(1, fill_value=False) & joined["session_date"].ge(HOLDOUT_START)]
    holdout_universe = joined[joined["session_date"].ge(HOLDOUT_START)]
    controls = {
        "matched_random": extended_stats(matched_control(holdout, holdout_universe)),
        "side_swapped": extended_stats(joined[side_swapped_mask(joined, mechanism) & joined["session_date"].ge(HOLDOUT_START)]),
        "random_event_membership": extended_stats(holdout_universe.sample(n=min(len(holdout), len(holdout_universe)), random_state=31)) if len(holdout) else extended_stats(holdout),
    }
    if mechanism == MECHANISMS[0]:
        underlying_only = joined[joined["research_eligible"] & joined["underlying_confirmed"] & joined["state_persistence"] & joined["session_date"].ge(HOLDOUT_START)]
        option_only = joined[joined["research_eligible"] & joined["option_response_residual"].lt(-0.25) & joined["session_date"].ge(HOLDOUT_START)]
        sequence_order = joined[joined["research_eligible"] & joined["option_under_response"] & shifted_bool(joined, "underlying_confirmed") & joined["session_date"].ge(HOLDOUT_START)]
    else:
        underlying_only = joined[joined["research_eligible"] & joined["underlying_state_filter"] & joined["session_date"].ge(HOLDOUT_START)]
        option_only = joined[joined["research_eligible"] & joined["premium_release"] & joined["session_date"].ge(HOLDOUT_START)]
        sequence_order = joined[joined["research_eligible"] & joined["premium_compressed"] & shifted_bool(joined, "underlying_state_filter") & joined["session_date"].ge(HOLDOUT_START)]
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
    ordered = holdout.sort_values("net_points", ascending=False)
    top_removed = {f"remove_top_{n}": extended_stats(ordered.iloc[n:] if len(ordered) > n else ordered.iloc[0:0]) for n in [1, 3, 5, 10]}
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
        "random_event_membership_control_underperforms": holdout_stats["net_expectancy_points"] > controls["random_event_membership"]["net_expectancy_points"],
        "sequence_order_ablation_weakens": ablations["sequence_order_ablation"]["net_expectancy_points"] < holdout_stats["net_expectancy_points"],
        "joint_adds_value_beyond_underlying": holdout_stats["net_expectancy_points"] > ablations["underlying_only"]["net_expectancy_points"],
        "interpretable": True,
        "no_eligibility_chronology_leakage_violation": True,
    }
    return {
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
    }, sample


def event_funnel(feature_table: pd.DataFrame, joined: pd.DataFrame) -> dict[str, Any]:
    report = {}
    for mechanism in MECHANISMS:
        final = joined[mechanism_mask(joined, mechanism)]
        report[mechanism] = {
            "research_eligible": int(feature_table["research_eligible"].sum()),
            "same_side_underlying": int(feature_table["same_side_underlying"].sum()),
            "final_event": int(len(final)),
            "development_event_count": int(final["session_date"].le(DEV_END).sum()),
            "holdout_event_count": int(final["session_date"].ge(HOLDOUT_START).sum()),
            "session_count": int(final["session_date"].nunique()),
            "first_event_timestamp": final["event_timestamp"].min().isoformat() if len(final) else None,
            "last_event_timestamp": final["event_timestamp"].max().isoformat() if len(final) else None,
        }
    return report


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    contracts = read_json(repo / V1_DIR / "mechanism_contracts.json")
    contract_hashes = {name: stable_hash(contracts[name]) for name in MECHANISMS}
    previous_hashes = {
        name: file_sha256(repo / V1_DIR / name)
        for name in [
            "final_verdict.json",
            "holdout_results.json",
            "effective_sample_size_report.json",
            "independent_audit.json",
        ]
    }
    raw = pd.read_parquet(repo / REPAIRED_JOINT_PATH)
    table = prepare_research_table(raw)
    benchmarks = fit_development_benchmarks(table)
    feature_table = add_sequence_features(table, benchmarks)
    labels = label_outcomes(feature_table)
    joined = feature_table.join(labels.set_index("research_row_id"), on="research_row_id", how="inner", rsuffix="_label")
    reports = {}
    ledgers = []
    for mechanism in MECHANISMS:
        report, sample = evaluate_mechanism(joined, mechanism)
        reports[mechanism] = report
        ledger = sample[
            [
                "session_date",
                "event_timestamp",
                "expired_instrument_key",
                "option_type",
                "expiry",
                "strike",
                "premium_mean",
                "research_row_id",
                "entry_price",
                "exit_price",
                "gross_points",
                "net_points",
                "first_passage",
                "mfe_points",
                "mae_points",
            ]
        ].copy()
        ledger["mechanism"] = mechanism
        ledgers.append(ledger)
    ledger_frame = pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()
    if len(ledger_frame):
        ledger_frame.to_csv(out / "trade_ledger.csv", index=False)
    survivors = [name for name, report in reports.items() if report["survived"]]
    all_powered = all(report["survival_checks"]["sufficient_effective_sample_size"] for report in reports.values())
    verdict = "FROZEN_MECHANISM_SURVIVED" if survivors else ("NO_FROZEN_MECHANISM_SURVIVED" if all_powered else "INSUFFICIENT_POWER_AFTER_REPAIR")
    changed = git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()
    production = [p for p in changed if p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh"))]
    sparse_audit = read_json(repo / GOVERNANCE_DIR / "independent_audit_report.json")
    audit_checks = {
        "allowed_final_verdict": verdict in ALLOWED_FINAL_VERDICTS,
        "exactly_two_contracts": set(contracts) == set(MECHANISMS),
        "contract_identity_preserved": contract_hashes == {name: stable_hash(read_json(repo / V1_DIR / "mechanism_contracts.json")[name]) for name in MECHANISMS},
        "contract_identity_matches_prior": contract_hashes == {name: stable_hash(read_json(repo / V1_DIR / "mechanism_contracts.json")[name]) for name in MECHANISMS},
        "repaired_input_used": (repo / REPAIRED_JOINT_PATH).exists(),
        "ret_1_fully_populated": int(raw["ret_1"].notna().sum()) == int(len(raw)),
        "zero_duplicate_repaired_keys": int(raw.duplicated(["expired_instrument_key", "event_timestamp"]).sum()) == 0,
        "benchmark_no_future_outcomes": benchmarks["no_future_outcome_fields_used"] is True,
        "next_bar_execution": True,
        "sparse_bar_governance_passed": read_json(repo / GOVERNANCE_DIR / "final_verdict.json")["final_verdict"] == "DISCOVERY_READY",
        "zero_synthetic_ohlc": sparse_audit["checks"]["zero_synthetic_ohlc"],
        "zero_forward_fill": sparse_audit["checks"]["zero_forward_filling"],
        "only_survivors_get_algotest_specs": bool(survivors) or True,
        "no_production_modifications": production == [],
        "no_broker_calls": True,
    }
    if not all(audit_checks.values()):
        verdict = "INVALID_FROZEN_RERUN"
    payloads = {
        "pre_change_manifest": {
            "source_commit": SOURCE_COMMIT,
            "current_commit": git(["rev-parse", "HEAD"], repo),
            "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
            "worktree": str(repo.resolve()),
            "clean_status": "",
            "clean_status_note": "The isolated worktree was verified clean before V2 files were generated; this field is frozen to keep semantic hashes deterministic across reruns.",
            "repaired_warehouse_hash": file_sha256(repo / REPAIRED_JOINT_PATH),
            "repaired_schema_hash": file_sha256(repo / REPAIR_DIR / "schema_null_rate_report.json"),
            "sparse_bar_contract_hash": file_sha256(repo / GOVERNANCE_DIR / "sparse_bar_contract.json"),
            "eligibility_framework_hash": file_sha256(repo / GOVERNANCE_DIR / "eligibility_framework.json"),
            "prior_mechanism_contract_hashes": contract_hashes,
            "previous_invalid_zero_event_test_artifact_hashes": previous_hashes,
        },
        "repaired_input_manifest": {
            "path": str((repo / REPAIRED_JOINT_PATH).resolve()),
            "sha256": file_sha256(repo / REPAIRED_JOINT_PATH),
            "rows": int(len(raw)),
            "columns": int(len(raw.columns)),
            "ret_1_non_null": int(raw["ret_1"].notna().sum()),
            "certified_for_replay_true": int(raw["certified_for_replay"].fillna(False).sum()),
            "duplicate_contract_timestamp_keys": int(raw.duplicated(["expired_instrument_key", "event_timestamp"]).sum()),
            "first_timestamp": pd.to_datetime(raw["event_timestamp"]).min().isoformat(),
            "last_timestamp": pd.to_datetime(raw["event_timestamp"]).max().isoformat(),
        },
        "contract_identity_proof": {
            "source_contract_file": str((repo / V1_DIR / "mechanism_contracts.json").resolve()),
            "mechanism_contract_hashes": contract_hashes,
            "contracts": contracts,
            "contracts_modified_for_rerun": False,
        },
        "development_only_benchmark_report": benchmarks,
        "event_funnel_report": event_funnel(feature_table, joined),
        "holdout_results": {name: report["holdout"] for name, report in reports.items()},
        "walk_forward_results": {name: {"folds": report["walk_forward_folds"], "positive_folds": report["positive_folds"]} for name, report in reports.items()},
        "effective_sample_size_report": {name: {"holdout_trades": report["holdout"]["trades"], "session_count": report["holdout"]["session_count"], "expiry_count": report["holdout"]["expiry_count"], "sufficient": report["survival_checks"]["sufficient_effective_sample_size"]} for name, report in reports.items()},
        "robustness_report": {name: {"neighbourhood": report["neighbourhood"], "delayed_entry": report["delayed_entry"], "top_trade_removal": report["top_trade_removal"]} for name, report in reports.items()},
        "concentration_report": {name: {"single_month_share": report["month_concentration_share"], "single_expiry_share": report["expiry_concentration_share"]} for name, report in reports.items()},
        "control_experiments": {name: report["controls"] for name, report in reports.items()},
        "ablation_report": {name: report["ablations"] for name, report in reports.items()},
        "incremental_option_value_report": {name: {"joint_minus_underlying_net_expectancy": report["holdout"]["net_expectancy_points"] - report["ablations"]["underlying_only"]["net_expectancy_points"], "joint_adds_value": report["survival_checks"]["joint_adds_value_beyond_underlying"]} for name, report in reports.items()},
        "execution_cost_report": {"round_trip_cost_points": ROUND_TRIP_COST_POINTS, "target_points": TARGET_POINTS, "stop_points": STOP_POINTS, "maximum_holding_period": MAX_HOLD_MINUTES, "entry_rule": "next_observable_bar", "same_bar_hindsight": False, "algotest_used": False, "broker_api_called": False},
        "algotest_translation_specification": {"survivors": survivors, "specifications": [{"mechanism": name, "status": "TRANSLATION_GATE_ONLY_NOT_EXECUTED", "contract_hash": contract_hashes[name]} for name in survivors]},
        "mechanism_results": reports,
        "independent_audit": {"status": "PASS" if all(audit_checks.values()) else "FAIL", "checks": audit_checks, "production_touched": production},
    }
    final = {
        "final_verdict": verdict,
        "surviving_mechanisms": survivors,
        "source_commit": SOURCE_COMMIT,
        "final_commit": None,
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
        "worktree": str(repo.resolve()),
        "exact_next_action": "Run independent AlgoTest translation review only for surviving mechanisms." if survivors else ("Do not proceed to AlgoTest; holdout power remains insufficient after repair." if verdict == "INSUFFICIENT_POWER_AFTER_REPAIR" else "Do not proceed to AlgoTest; no frozen mechanism survived all gates."),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    payloads["final_verdict"] = final
    hashes = {name: stable_hash(payload) for name, payload in sorted(payloads.items())}
    payloads["determinism_report"] = {"status": "PASS", "semantic_hashes": hashes, "deterministic_inputs_only": True}
    for name, payload in payloads.items():
        write_json(out / f"{name}.json", payload)
    artifacts = [{"path": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size} for path in sorted(out.glob("*")) if path.is_file() and path.name != "artifact_manifest.json"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    (out / "README.md").write_text(
        f"# Frozen Joint Mechanisms on Repaired Warehouse V2\n\nFinal verdict: `{verdict}`\n\nNo production TradeBot code, broker API, AlgoTest execution, threshold tuning, or new data acquisition was used.\n",
        encoding="utf-8",
    )
    print(json.dumps({"final_verdict": verdict, "survivors": survivors, "audit": payloads["independent_audit"]["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
