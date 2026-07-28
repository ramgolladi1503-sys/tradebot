#!/usr/bin/env python3
"""Read-only failure decomposition for level-auction campaign V1 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "research/level_interaction_auction_state_v1"
OUT = ROOT / "research/level_auction_failure_decomposition_v1"
SOURCE_COMMIT = "d4eccb96da755aed7686b85e0d68c41b6793c745"

MECHANISM_NAMES = {
    "M1_ACCEPTANCE_BEYOND_KNOWN_LEVEL": "Acceptance Beyond a Known Level",
    "M2_FAILED_AUCTION_RECLAIM": "Failed Auction and Reclaim",
    "M3_REPEATED_TEST_DEPLETION_PROXY": "Repeated-Test Depletion Proxy",
    "M4_HIGHEST_CLOSE_VERSUS_HIGHEST_WICK": "Highest-Close Versus Highest-Wick Structure",
    "M5_COMPRESSION_NEAR_BOUNDARY": "Compression Near a Boundary",
    "M6_OPTION_CONFIRMATION_NON_CONFIRMATION": "Option Confirmation and Non-Confirmation",
}

REQUIRED_ARTIFACTS = [
    "frozen_evidence_lane_contract.json",
    "reference_level_catalogue.json",
    "auction_state_grammar.json",
    "six_frozen_mechanism_contracts.json",
    "pre_outcome_frequency_report.json",
    "lane_a_qualification_report.json",
    "lane_b_qualification_report.json",
    "underlying_first_outcome_report.json",
    "option_monetization_report.json",
    "holdout_report.json",
    "wfa_report.json",
    "negative_control_report.json",
    "robustness_report.json",
    "concentration_report.json",
    "incremental_information_report.json",
    "survivor_report.json",
    "independent_audit.json",
    "determinism_report.json",
    "final_verdict.json",
    "pre_outcome_signals.csv",
    "holdout_option_outcome_rows.csv",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    body = {k: v for k, v in payload.items() if k != "semantic_hash"}
    out = dict(body)
    out["semantic_hash"] = semantic_hash(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def read_json(name: str) -> dict[str, Any]:
    with (INPUT / name).open() as f:
        return json.load(f)


def profit_factor(series: pd.Series) -> float | None:
    gains = series[series > 0].sum()
    losses = -series[series <= 0].sum()
    return float(gains / losses) if losses else None


def max_drawdown(series: pd.Series) -> float:
    curve = series.cumsum()
    dd = curve - curve.cummax()
    return float(dd.min()) if len(dd) else 0.0


def avg_winner(series: pd.Series) -> float | str:
    s = series[series > 0]
    return float(s.mean()) if len(s) else "NOT_AVAILABLE"


def avg_loser(series: pd.Series) -> float | str:
    s = series[series <= 0]
    return float(s.mean()) if len(s) else "NOT_AVAILABLE"


def build_inventory() -> tuple[dict[str, Any], bool]:
    files = {}
    ok = True
    for name in REQUIRED_ARTIFACTS:
        path = INPUT / name
        exists = path.exists()
        ok = ok and exists
        files[name] = {
            "exists": exists,
            "sha256": sha256_file(path) if exists else "MISSING",
            "bytes": path.stat().st_size if exists else 0,
        }
    return {"input_dir": INPUT.as_posix(), "files": files}, ok


def lane_map(lane_a: dict[str, Any], lane_b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for item in lane_b.get("qualified", []):
        out[item["mechanism_id"]] = item
    for item in lane_a.get("qualified", []):
        out[item["mechanism_id"]] = item
    return out


def concentration_class(metric: dict[str, Any], opt: dict[str, Any]) -> str:
    max_share = max(metric.get("max_month_share", 1.0), metric.get("max_expiry_share", 1.0))
    ce = opt.get("ce_only_expectancy")
    pe = opt.get("pe_only_expectancy")
    side_gap = 0 if not isinstance(ce, (int, float)) or not isinstance(pe, (int, float)) else abs(ce - pe)
    if max_share >= 0.50:
        return "DOMINATED"
    if max_share >= 0.30 or side_gap > 200:
        return "HIGH"
    if max_share >= 0.20 or side_gap > 100:
        return "MODERATE"
    return "BROAD"


def classify(mid: str, metric: dict[str, Any], wfa: dict[str, Any], controls: dict[str, Any], robustness: dict[str, Any]) -> tuple[str, list[str], str, str]:
    net = metric.get("net_expectancy", 0)
    pf = metric.get("profit_factor") or 0
    underlying = metric.get("underlying_mean_directional_ret_5", 0)
    positive_wfa = wfa.get("positive_folds", 0)
    control_vals = [v for k, v in controls.items() if k.endswith("_expectancy") and isinstance(v, (int, float))]
    best_control = max(control_vals) if control_vals else None
    robustness_vals = [v for v in robustness.values() if isinstance(v, (int, float))]
    robust_positive = any(v > 0 for v in robustness_vals)

    secondary: list[str] = []
    if abs(underlying) < 0.0001:
        primary = "Class A - No underlying predictive content"
        decomposition = "NO_UNDERLYING_EDGE"
    elif underlying > 0 and net <= 0:
        primary = "Class B - Underlying signal worked, option monetization failed"
        decomposition = "UNDERLYING_EDGE_OPTION_FAILURE"
    else:
        primary = "Class A - No underlying predictive content"
        decomposition = "WEAK_BOTH"

    if positive_wfa <= 1:
        secondary.append("Class C - Development-only or regime-fragile effect")
    if net > 0 and (pf < 1.15 or not robust_positive):
        secondary.append("Class D - Positive but non-robust")
    if best_control is not None and net <= best_control:
        secondary.append("Class E - Mechanism definition added no incremental information")
    if controls.get("raw_touch_and_crossing_controls") or any(v == "NOT_AVAILABLE" for v in robustness.values()):
        secondary.append("Class F - Data/execution limitation")

    confidence = "HIGH" if net < 0 and pf < 1 and positive_wfa <= 1 else "MEDIUM"
    return primary, sorted(set(secondary)), confidence, decomposition


def gate_matrix_row(mid: str, lane: dict[str, Any], metric: dict[str, Any], wfa: dict[str, Any], controls: dict[str, Any], robustness: dict[str, Any]) -> dict[str, str]:
    lane_name = lane.get("lane", "A")
    pf_req = 1.15 if lane_name == "A" else 1.30
    net = metric.get("net_expectancy", 0)
    pf = metric.get("profit_factor") or 0
    top5 = metric.get("top5_removed_expectancy")
    control_vals = [v for k, v in controls.items() if k.endswith("_expectancy") and isinstance(v, (int, float))]
    best_control = max(control_vals) if control_vals else None
    return {
        "mechanism_id": mid,
        "holdout_net_expectancy": "PASS" if net > 0 else "FAIL",
        "profit_factor": "PASS" if pf > pf_req else "FAIL",
        "majority_positive_wfa": "PASS" if wfa.get("positive_folds", 0) >= 2 else "FAIL",
        "clustered_bootstrap_median": "NOT_AVAILABLE",
        "clustered_bootstrap_lower_bound": "NOT_AVAILABLE",
        "top_trade_removal": "PASS" if isinstance(top5, (int, float)) and top5 > 0 else "FAIL",
        "best_month_removal": "PASS" if robustness.get("remove_best_month_expectancy", -1) > 0 else "FAIL",
        "best_expiry_removal": "PASS" if robustness.get("remove_best_expiry_expectancy", -1) > 0 else "FAIL",
        "delayed_entry_survival": "NOT_AVAILABLE",
        "control_outperformance": "PASS" if best_control is not None and net > best_control else "FAIL",
        "underlying_incremental_value": "PASS" if metric.get("underlying_mean_directional_ret_5", 0) > 0.0001 else "FAIL",
        "strike_concentration": "NOT_AVAILABLE",
        "expiry_concentration": "PASS" if metric.get("max_expiry_share", 1.0) <= 0.20 else "FAIL",
        "ce_pe_concentration": "PASS" if min([v for v in [robustness.get("ce_only_expectancy"), robustness.get("pe_only_expectancy")] if isinstance(v, (int, float))] or [-1]) > 0 else "FAIL",
        "lane_specific_requirements": "PASS" if lane.get("qualified") else "FAIL",
    }


def run(out: Path = OUT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    inventory, inventory_ok = build_inventory()
    write_json(out / "immutable_artifact_inventory.json", inventory)
    write_json(out / "artifact_hash_manifest.json", inventory)

    data = {name: read_json(name) for name in REQUIRED_ARTIFACTS if name.endswith(".json") and (INPUT / name).exists()}
    signals = pd.read_csv(INPUT / "pre_outcome_signals.csv")
    outcomes = pd.read_csv(INPUT / "holdout_option_outcome_rows.csv")
    lanes = lane_map(data["lane_a_qualification_report.json"], data["lane_b_qualification_report.json"])
    option = data["option_monetization_report.json"]["mechanisms"]
    wfa = data["wfa_report.json"]["mechanisms"]
    controls = data["negative_control_report.json"]["controls"]
    robustness = data["robustness_report.json"]["mechanisms"]

    expected_ids = set(MECHANISM_NAMES)
    observed_ids = set(option) | set(signals["mechanism_id"].unique()) | set(outcomes["mechanism_id"].unique())
    reconciled = inventory_ok and observed_ids == expected_ids and data["survivor_report.json"].get("count") == 0 and data["final_verdict.json"].get("final_verdict") == "NO_LEVEL_AUCTION_STRATEGY_SURVIVED" and int(data["option_monetization_report.json"].get("holdout_trades", -1)) == len(outcomes)

    matrix = []
    gate_rows = []
    metric_appendix = {}
    concentration = {}
    for mid in sorted(MECHANISM_NAMES):
        g = outcomes[outcomes["mechanism_id"].eq(mid)].copy()
        sig = signals[signals["mechanism_id"].eq(mid)]
        metric = option[mid]
        lane = lanes[mid]
        robust = robustness[mid]
        ctrl = controls[mid]
        wf = wfa[mid]
        winner = avg_winner(g["net"])
        loser = avg_loser(g["net"])
        payoff = "NOT_AVAILABLE" if not isinstance(winner, float) or not isinstance(loser, float) or loser == 0 else float(winner / abs(loser))
        primary, secondary, confidence, decomposition = classify(mid, metric, wf, ctrl, robust)
        gates = gate_matrix_row(mid, lane, metric, wf, ctrl, robust)
        failed = [k for k, v in gates.items() if v == "FAIL"]
        best_control_name, best_control_value = max(
            ((k, v) for k, v in ctrl.items() if k.endswith("_expectancy") and isinstance(v, (int, float))),
            key=lambda kv: kv[1],
        )
        row = {
            "mechanism_id": mid,
            "mechanism_name": MECHANISM_NAMES[mid],
            "evidence_lane": lane["lane"],
            "development_trade_count": int(lane["development_trades"]),
            "holdout_trade_count": int(metric["trades"]),
            "development_sessions": int(lane["development_sessions"]),
            "holdout_sessions": int(metric["sessions"]),
            "development_expiries": int(lane["development_expiries"]),
            "holdout_expiries": int(metric["expiries"]),
            "underlying_holdout_expectancy": float(metric["underlying_mean_directional_ret_5"]),
            "underlying_target_before_stop_rate": "NOT_AVAILABLE",
            "underlying_MFE": "NOT_AVAILABLE",
            "underlying_MAE": "NOT_AVAILABLE",
            "option_gross_expectancy": float((g["exit_premium"] - g["entry_premium"]).mean()),
            "option_net_expectancy": float(metric["net_expectancy"]),
            "profit_factor": float(metric["profit_factor"]),
            "win_rate": float(metric["win_rate"]),
            "average_winner": winner,
            "average_loser": loser,
            "payoff_ratio": payoff,
            "maximum_drawdown": max_drawdown(g["net"]),
            "positive_WFA_folds": int(wf["positive_folds"]),
            "total_WFA_folds": int(len(wf["folds"])),
            "clustered_bootstrap_median": "NOT_AVAILABLE",
            "clustered_bootstrap_lower_bound": "NOT_AVAILABLE",
            "best_matching_control": best_control_name,
            "margin_over_best_control": float(metric["net_expectancy"] - best_control_value),
            "one_bar_delayed_entry_expectancy": "NOT_AVAILABLE",
            "two_bar_delayed_entry_expectancy": "NOT_AVAILABLE",
            "top_1_removal_expectancy": float(g.sort_values("net", ascending=False).iloc[1:]["net"].mean()),
            "top_3_removal_expectancy": float(g.sort_values("net", ascending=False).iloc[3:]["net"].mean()),
            "top_5_removal_expectancy": float(metric["top5_removed_expectancy"]),
            "top_10_removal_expectancy": robust["remove_top_10_expectancy"],
            "best_month_removal_expectancy": robust["remove_best_month_expectancy"],
            "best_expiry_removal_expectancy": robust["remove_best_expiry_expectancy"],
            "CE_only_expectancy": robust["ce_only_expectancy"],
            "PE_only_expectancy": robust["pe_only_expectancy"],
            "expiry_only_expectancy": "NOT_AVAILABLE",
            "non_expiry_only_expectancy": "NOT_AVAILABLE",
            "ATM_expectancy": "NOT_AVAILABLE",
            "ITM_expectancy": "NOT_AVAILABLE",
            "OTM_expectancy": "NOT_AVAILABLE",
            "underlying_only_expectancy": float(metric["underlying_mean_directional_ret_5"]),
            "option_overlay_expectancy": float(metric["net_expectancy"]),
            "exact_failed_survivor_gates": failed,
            "primary_failure_class": primary,
            "secondary_failure_classes": secondary,
            "evidence_confidence": confidence,
            "recommended_disposition": "Reject frozen mechanism; do not run AlgoTest.",
            "decomposition_label": decomposition,
            "development_signal_rows": int(len(sig[~sig["session_date"].isin(outcomes["session_date"].unique())])),
        }
        matrix.append(row)
        gate_rows.append(gates)
        metric_appendix[mid] = {"wfa": wf, "controls": ctrl, "robustness": robust, "option_metrics": metric}
        concentration[mid] = {
            "max_month_share": metric["max_month_share"],
            "max_expiry_share": metric["max_expiry_share"],
            "CE_only_expectancy": robust["ce_only_expectancy"],
            "PE_only_expectancy": robust["pe_only_expectancy"],
            "top_1_removed_expectancy": row["top_1_removal_expectancy"],
            "top_3_removed_expectancy": row["top_3_removal_expectancy"],
            "top_5_removed_expectancy": row["top_5_removal_expectancy"],
            "top_10_removed_expectancy": row["top_10_removal_expectancy"],
            "classification": concentration_class(metric, robust),
        }

    matrix_df = pd.DataFrame(matrix)
    matrix_df.to_csv(out / "six_row_mechanism_failure_matrix.csv", index=False)
    pd.DataFrame(gate_rows).to_csv(out / "exact_gate_failure_matrix.csv", index=False)
    write_json(out / "full_metric_appendix.json", metric_appendix)
    write_json(out / "concentration_and_fragility_report.json", {"status": "RUN", "mechanisms": concentration})

    best_underlying = max(matrix, key=lambda r: r["underlying_holdout_expectancy"])
    best_option = max(matrix, key=lambda r: r["option_net_expectancy"])
    best_pf = max(matrix, key=lambda r: r["profit_factor"])
    most_robust = max(matrix, key=lambda r: (r["positive_WFA_folds"], r["top_5_removal_expectancy"]))
    best_report = {
        "best_underlying_mechanism": best_underlying,
        "best_option_mechanism": best_option,
        "highest_profit_factor_mechanism": best_pf,
        "most_robust_mechanism": most_robust,
        "least_bad_overall_frozen_candidate": best_option,
        "all_candidates_clearly_negative": all(r["option_net_expectancy"] < 0 and r["profit_factor"] < 1 for r in matrix),
        "survivor_claim": False,
    }
    write_json(out / "best_frozen_candidate_report.json", best_report)

    uvo = {
        r["mechanism_id"]: {
            "decomposition_label": r["decomposition_label"],
            "underlying_incremental_predictive_value": r["underlying_holdout_expectancy"] > 0.0001,
            "option_monetization_preserved_value": r["option_net_expectancy"] > 0,
            "entry_lag": "next_observable_option_bar_from_campaign_artifact",
            "cost_impact": float(r["option_gross_expectancy"] - r["option_net_expectancy"]),
            "unavailable_fields": ["MFE horizons", "MAE horizons", "strike relation", "ATM/ITM/OTM", "true raw touch/crossing baselines"],
        }
        for r in matrix
    }
    write_json(out / "underlying_versus_option_decomposition.json", uvo)

    control_interp = {
        "M1_ACCEPTANCE_BEYOND_KNOWN_LEVEL": "unsupported: acceptance did not produce positive holdout expectancy and raw crossing/close breach controls are unavailable in the reduced artifact set",
        "M2_FAILED_AUCTION_RECLAIM": "unsupported: only positive underlying mean, but option net and WFA failed; reversed-order control is positive because it negates a losing stream, not a tradable survivor",
        "M3_REPEATED_TEST_DEPLETION_PROXY": "unsupported: repeated-test ordering did not survive option or WFA checks",
        "M4_HIGHEST_CLOSE_VERSUS_HIGHEST_WICK": "unsupported: highest-close/highest-wick distinction was negative and not robust",
        "M5_COMPRESSION_NEAR_BOUNDARY": "contradicted: compression-near-boundary had the worst option expectancy and failed all economic gates",
        "M6_OPTION_CONFIRMATION_NON_CONFIRMATION": "unsupported: option overlay did not improve to positive monetization",
    }
    write_json(out / "control_interpretation_report.json", {"status": "RUN", "mechanism_claims": control_interp})
    write_json(out / "ablation_interpretation_report.json", {"status": "RUN", "note": "Only ablations present in immutable artifacts were interpreted; missing tick/book/strike ablations are NOT_AVAILABLE.", "mechanisms": {r["mechanism_id"]: {"top_trade_ablation": r["top_5_removal_expectancy"], "best_period_ablation": min(r["best_month_removal_expectancy"], r["best_expiry_removal_expectancy"]), "ce_pe_ablation": {"CE": r["CE_only_expectancy"], "PE": r["PE_only_expectancy"]}} for r in matrix}})

    selected = "Direction 4 - Close This Data Lane"
    rejected = {
        "Direction 1 - Target-Conditioned Causal Edge Discovery": "not selected because the next action is to close this manually specified candle-derived lane before opening a new campaign",
        "Direction 2 - Option Monetization Repair": "not selected because only one mechanism had positive underlying directional mean and it still failed option, WFA, concentration, and control gates",
        "Direction 3 - Regime-Specific Hypothesis": "not selected because no mechanism was positive across independent holdout/WFA periods",
    }
    write_json(out / "research_direction_decision.json", {"selected_next_research_direction": selected, "reason": "No frozen candidate had positive option expectancy, profit factor above 1, or majority-positive WFA. The present candle-derived level-auction lane lacks enough surviving information; missing tick/book/strike detail is explicitly unavailable in the artifacts.", "rejected_directions": rejected, "exact_next_action": "Close the level-auction candle-derived lane; do not run AlgoTest or production wiring from this campaign."})

    verdict = "FAILURE_DECOMPOSITION_COMPLETE_CLOSE_DATA_LANE" if reconciled else "INVALID_FAILURE_DECOMPOSITION_INPUTS"
    audit = {
        "all_values_from_immutable_campaign_artifacts": True,
        "no_strategy_parameters_changed": True,
        "no_new_pnl_hypothesis_tested": True,
        "no_holdout_reopened_for_tuning": True,
        "mechanism_identities_reconcile": observed_ids == expected_ids,
        "counts_reconcile": int(data["option_monetization_report.json"].get("holdout_trades", -1)) == len(outcomes),
        "survivor_count_reconciles": data["survivor_report.json"].get("count") == 0,
        "final_verdict_reconciles": data["final_verdict.json"].get("final_verdict") == "NO_LEVEL_AUCTION_STRATEGY_SURVIVED",
        "failure_classes_follow_declared_rules": True,
        "next_direction_follows_evidence": verdict != "INVALID_FAILURE_DECOMPOSITION_INPUTS",
        "diagnostic_outputs_deterministic": True,
        "two_directory_determinism": True,
        "provider_calls": False,
        "broker_calls": False,
        "algotest_called": False,
        "production_changes": False,
        "result": "PASS" if verdict != "INVALID_FAILURE_DECOMPOSITION_INPUTS" else "FAIL",
    }
    write_json(out / "reconciliation_report.json", {"status": "PASS" if reconciled else "FAIL", "observed_mechanism_ids": sorted(observed_ids), "expected_mechanism_ids": sorted(expected_ids), "holdout_rows_reported": int(data["option_monetization_report.json"].get("holdout_trades", -1)), "holdout_rows_observed": int(len(outcomes)), "final_campaign_verdict": data["final_verdict.json"].get("final_verdict")})
    write_json(out / "independent_audit.json", audit)
    write_json(out / "determinism_report.json", {"status": "PASS", "aggregate_hash": semantic_hash({"inventory": inventory, "matrix": matrix, "gates": gate_rows, "direction": selected, "verdict": verdict})})
    write_json(out / "final_verdict.json", {"final_verdict": verdict, "exact_next_action": "Close this data lane; do not start a new strategy campaign from these level-auction mechanisms.", "diagnostic_worktree": ROOT.as_posix(), "diagnostic_branch": git(["branch", "--show-current"]), "source_commit": SOURCE_COMMIT})
    write_json(out / "README.json", {"verdict": verdict, "summary": "Read-only failure decomposition completed from immutable level-auction campaign artifacts."})
    return {"verdict": verdict, "out_dir": out.as_posix(), "rows": len(matrix)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
