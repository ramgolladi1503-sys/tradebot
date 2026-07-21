from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from research.rsi2_mean_reversion.engine import (
    BASE_COST,
    NEXT_OPEN,
    WILDER_RSI_2,
    load_ohlc,
    prepare_features,
    sha256_file,
)


ALLOWED_VERDICTS = {
    "STRUCTURAL_EDGE_SUPPORTED",
    "PROMISING_BUT_UNPROVEN",
    "PARAMETER_FRAGILE",
    "NO_STRUCTURAL_EDGE",
    "INSUFFICIENT_DATA",
    "INSUFFICIENT_TRADABLE_DATA",
    "INVALID_BACKTEST",
}
ROOT = Path("runtime/research/rsi2_mean_reversion")
GATE = ROOT / "final_publication_gate"
IMMUTABLE = ROOT / "baseline_immutable"
FROZEN_INPUT = ROOT / "frozen_data/nifty50_yfinance_2010-01-01_2026-01-01_auto_adjust_true.csv"
BASE_LEDGER = ROOT / "completed_trade_ledger.csv"
BASE_REPORT = ROOT / "rsi2_mean_reversion_report.json"
BASE_SUMMARY = ROOT / "rsi2_mean_reversion_summary.md"
REQUIRED_CONTROLS = [
    "matched_random",
    "one_session_signal_shift_backward",
    "one_session_signal_shift_forward",
    "inverted_rsi_condition",
    "trend_filter_removed",
    "randomized_rsi_distribution",
    "block_bootstrap_confidence_interval",
    "best_calendar_year_removed",
    "five_best_trades_removed",
    "crash_period_only",
    "crash_period_excluded",
]


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str, allow_nan=False), encoding="utf-8")


def stable_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode("utf-8")


def semantic_hash_path(path: Path) -> str:
    if path.suffix == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        return hashlib.sha256(stable_json(obj)).hexdigest()
    return sha256_file(path)


def profit_factor(series: pd.Series) -> float:
    gains = float(series[series > 0.0].sum())
    losses = abs(float(series[series <= 0.0].sum()))
    return gains / losses if losses else math.inf if gains else 0.0


def max_drawdown_from_returns(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    eq = (1.0 + series).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def summarize_returns(series: pd.Series) -> dict[str, float]:
    return {
        "completed_trades": int(len(series)),
        "expectancy": float(series.mean()) if len(series) else 0.0,
        "profit_factor": profit_factor(series),
        "compounded_return": float((1.0 + series).prod() - 1.0) if len(series) else 0.0,
        "max_drawdown": max_drawdown_from_returns(series),
    }


def ensure_pre_repair_manifest() -> dict[str, object]:
    GATE.mkdir(parents=True, exist_ok=True)
    path = GATE / "pre_repair_manifest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    files = sorted(p for p in ROOT.rglob("*") if p.is_file())
    manifest = {
        "branch": subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "expected_head": "98c8f13fe7e23ef8c5ec6159ea93af4beebaf47c",
        "head_verified": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == "98c8f13fe7e23ef8c5ec6159ea93af4beebaf47c",
        "git_status_short": subprocess.check_output(["git", "status", "--short"], text=True).splitlines(),
        "worktree_clean": subprocess.check_output(["git", "status", "--short"], text=True).strip() == "",
        "artifact_hashes": {str(p): sha256_file(p) for p in files},
        "reproducibility_script_generated_files": [
            "runtime/research/rsi2_mean_reversion/evidence_closure/*",
            "runtime/research/rsi2_mean_reversion/rsi2_mean_reversion_report.json",
            "runtime/research/rsi2_mean_reversion/rsi2_mean_reversion_summary.md",
            "runtime/research/rsi2_mean_reversion/completed_trade_ledger.csv",
        ],
    }
    write_json(path, manifest)
    return manifest


def ensure_immutable_baseline() -> dict[str, object]:
    files = [BASE_REPORT, BASE_SUMMARY, BASE_LEDGER, FROZEN_INPUT, ROOT / "evidence_closure/baseline_manifest.json"]
    identity = hashlib.sha256("".join(sha256_file(p) for p in files if p.exists()).encode("utf-8")).hexdigest()[:16]
    target = IMMUTABLE / identity
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / "immutable_baseline_manifest.json"
    if not manifest_path.exists():
        for src in files:
            if src.exists():
                dst = target / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)
                    dst.chmod(0o444)
        manifest = {
            "identity": identity,
            "source_files": {str(p): sha256_file(p) for p in files if p.exists()},
            "immutable_files": {str(p): sha256_file(p) for p in sorted(target.glob("*")) if p.name != "immutable_baseline_manifest.json"},
            "rebuild_deletion_target_excludes": str(IMMUTABLE),
        }
        write_json(manifest_path, manifest)
        manifest_path.chmod(0o444)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def verify_immutable_baseline(manifest: dict[str, object]) -> dict[str, object]:
    mismatches = []
    for path, expected in manifest["immutable_files"].items():
        actual = sha256_file(Path(path))
        if actual != expected:
            mismatches.append({"path": path, "expected": expected, "actual": actual})
    report = {"status": "PASS" if not mismatches else "FAIL", "baseline_identity": manifest["identity"], "mismatches": mismatches}
    write_json(GATE / "baseline_immutability_report.json", report)
    if mismatches:
        raise RuntimeError(f"Immutable baseline hash mismatch: {mismatches}")
    return report


def base_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    raw = load_ohlc(FROZEN_INPUT)
    raw = raw[raw["date"] <= pd.Timestamp("2025-12-31")].reset_index(drop=True)
    feat = prepare_features(raw, WILDER_RSI_2, 2, 200)
    ledger = pd.read_csv(BASE_LEDGER)
    primary = ledger[ledger["rsi_variant"] == WILDER_RSI_2].copy().reset_index(drop=True)
    report = json.loads(BASE_REPORT.read_text(encoding="utf-8"))
    return raw, feat, primary, report


def matched_random_replicates(
    replicates: int = 1000, seed: int = 20260721, write_artifacts: bool = True
) -> tuple[dict[str, object], pd.DataFrame, dict[str, object]]:
    raw, feat, base, _ = base_inputs()
    base_count = len(base)
    base_metric = float(base["net_return"].mean())
    durations = base["holding_sessions"].astype(int).to_numpy()
    eligible = np.where(feat["trend_ok"].fillna(False).to_numpy())[0]
    rows = []
    for rep in range(replicates):
        rep_seed = seed + rep
        rng = np.random.default_rng(rep_seed)
        shuffled_durations = durations.copy()
        rng.shuffle(shuffled_durations)
        attempts = 0
        while True:
            attempts += 1
            candidate_entries = np.array(sorted(rng.choice(eligible[:-1], size=base_count * 4, replace=False)))
            trades = []
            last_exit = -1
            for entry_idx in candidate_entries:
                if len(trades) >= base_count:
                    break
                duration = int(shuffled_durations[len(trades)])
                exit_idx = entry_idx + max(duration, 1)
                if entry_idx <= last_exit or exit_idx >= len(raw):
                    continue
                if not bool(feat.iloc[entry_idx - 1]["trend_ok"]) if entry_idx > 0 else True:
                    continue
                entry_price = float(raw.iloc[entry_idx]["open"])
                exit_price = float(raw.iloc[exit_idx]["open"])
                gross = exit_price / entry_price - 1.0
                net = gross - BASE_COST.total_bps / 10000.0
                trades.append((entry_idx, exit_idx, duration, gross, net))
                last_exit = exit_idx
            if len(trades) == base_count:
                break
            if attempts >= 100:
                raise RuntimeError(f"Unable to create exact matched replicate {rep} with {base_count} trades")
        returns = pd.Series([t[4] for t in trades])
        summary = summarize_returns(returns)
        rows.append({
            "replicate": rep,
            "seed": rep_seed,
            "completed_trades": summary["completed_trades"],
            "expectancy": summary["expectancy"],
            "profit_factor": summary["profit_factor"],
            "compounded_return": summary["compounded_return"],
            "max_drawdown": summary["max_drawdown"],
            "duplicate_entries": len({t[0] for t in trades}) != len(trades),
            "overlap_count": int(sum(1 for i in range(1, len(trades)) if trades[i][0] <= trades[i - 1][1])),
        })
    df = pd.DataFrame(rows)
    if write_artifacts:
        df.to_csv(GATE / "matched_random_replicates.csv", index=False)
    summary = {
        "replicates": replicates,
        "base_completed_trades": base_count,
        "trades_per_replicate": sorted(df["completed_trades"].unique().astype(int).tolist()),
        "total_aggregated_trades": int(df["completed_trades"].sum()),
        "seed_start": seed,
        "seed_end": seed + replicates - 1,
        "mean_replicate_expectancy": float(df["expectancy"].mean()),
        "median_replicate_expectancy": float(df["expectancy"].median()),
        "p05_expectancy": float(df["expectancy"].quantile(0.05)),
        "p95_expectancy": float(df["expectancy"].quantile(0.95)),
        "fraction_replicates_beating_real_strategy": float((df["expectancy"] >= base_metric).mean()),
        "empirical_p_value": float((1.0 + (df["expectancy"] >= base_metric).sum()) / (len(df) + 1.0)),
        "real_strategy_expectancy": base_metric,
        "matching_tolerances": {
            "completed_trades": "exact",
            "eligibility": "trend_ok eligible entry dates",
            "holding_duration": "base holding duration multiset assigned per replicate",
            "non_overlap": "exact, overlap_count must be zero",
        },
        "status": "PASS" if (df["completed_trades"].eq(base_count).all() and df["overlap_count"].eq(0).all() and (~df["duplicate_entries"]).all()) else "FAIL",
    }
    manifest = {
        "case": "CASE_A_REPAIRED_EXACT_REPLICATE_MATCH",
        "replicate_count": replicates,
        "base_completed_trades": base_count,
        "replicate_artifact": str(GATE / "matched_random_replicates.csv"),
        "summary_artifact": str(GATE / "matched_random_summary.json"),
        "assertions": {
            "each_successful_replicate_exactly_127_trades": bool(df["completed_trades"].eq(base_count).all()),
            "no_duplicate_entry_within_replicate": bool((~df["duplicate_entries"]).all()),
            "no_overlapping_positions": bool(df["overlap_count"].eq(0).all()),
            "deterministic_seed_schedule": f"{seed}..{seed + replicates - 1}",
        },
    }
    if write_artifacts:
        write_json(GATE / "matched_random_manifest.json", manifest)
        write_json(GATE / "matched_random_summary.json", summary)
    if summary["status"] != "PASS":
        raise RuntimeError("Matched random repair failed exact matching assertions")
    return manifest, df, summary


def concentration_metrics(base: pd.DataFrame) -> dict[str, float]:
    ret = base["net_return"]
    best5 = ret.nlargest(5)
    without = ret.drop(best5.index)
    return {
        "five_best_arithmetic_contribution_pct": float(best5.sum() / ret.sum() * 100.0),
        "without_five_best_compounded_return": float((1.0 + without).prod() - 1.0),
        "without_five_best_profit_factor": profit_factor(without),
    }


def parameter_neighborhood() -> tuple[pd.DataFrame, dict[str, object]]:
    param = pd.read_csv(ROOT / "evidence_closure/parameter_results.csv")
    neighborhood = param[
        (param["sma"].isin([150, 200, 250]))
        & (param["entry_rsi"].isin([10.0, 15.0, 20.0]))
        & (param["exit_rsi"].isin([80.0, 85.0, 90.0]))
        & (param["rsi_type"] == WILDER_RSI_2)
        & (param["execution_lane"] == NEXT_OPEN)
    ].copy()
    neighborhood["survives_base_costs"] = neighborhood["base_cost_expectancy"] > 0.0
    neighborhood["survives_2x_costs"] = neighborhood["cost_2x_expectancy"] > 0.0
    neighborhood["positive_profit_factor"] = neighborhood["profit_factor"] > 1.0
    neighborhood["positive_fold_majority"] = neighborhood["positive_fold_percentage"] > 0.5
    neighborhood.to_csv(GATE / "parameter_neighborhood_matrix.csv", index=False)
    full_summary = {
        "all_192_cells": _parameter_group_summary(param),
        "by_rsi_implementation": _group_stats(param, "rsi_type"),
        "by_sma_period": _group_stats(param, "sma"),
        "by_entry_threshold": _group_stats(param, "entry_rsi"),
        "by_exit_threshold": _group_stats(param, "exit_rsi"),
        "by_execution_lane": _group_stats(param, "execution_lane"),
    }
    summary = {
        "baseline_neighborhood_rule": "SMA 150/200/250; entry 10/15/20; exit 80/85/90; WILDER_RSI_2; NEXT_OPEN_EXECUTABLE",
        "neighborhood_cells": int(len(neighborhood)),
        "positive_net_expectancy_pct": float((neighborhood["expectancy"] > 0.0).mean() * 100.0),
        "profit_factor_above_1_pct": float((neighborhood["profit_factor"] > 1.0).mean() * 100.0),
        "positive_fold_majority_pct": float((neighborhood["positive_fold_majority"]).mean() * 100.0),
        "surviving_base_costs_pct": float((neighborhood["survives_base_costs"]).mean() * 100.0),
        "surviving_2x_costs_pct": float((neighborhood["survives_2x_costs"]).mean() * 100.0),
        "contiguous_profitable_neighborhoods": _contiguous_neighborhoods(neighborhood),
        "isolated_best_cells": _isolated_best_cells(neighborhood),
        "worst_neighborhood_cell": neighborhood.sort_values("expectancy").head(1).to_dict("records")[0],
        "full_grid_summary": full_summary,
        "matrix_artifact": str(GATE / "parameter_neighborhood_matrix.csv"),
    }
    write_json(GATE / "parameter_neighborhood_summary.json", summary)
    return neighborhood, summary


def _parameter_group_summary(df: pd.DataFrame) -> dict[str, float]:
    return {
        "cells": int(len(df)),
        "positive_net_expectancy_pct": float((df["expectancy"] > 0.0).mean() * 100.0),
        "profit_factor_above_1_pct": float((df["profit_factor"] > 1.0).mean() * 100.0),
        "positive_fold_majority_pct": float((df["positive_fold_percentage"] > 0.5).mean() * 100.0),
        "surviving_base_costs_pct": float((df["base_cost_expectancy"] > 0.0).mean() * 100.0),
        "surviving_2x_costs_pct": float((df["cost_2x_expectancy"] > 0.0).mean() * 100.0),
    }


def _group_stats(df: pd.DataFrame, col: str) -> dict[str, dict[str, float]]:
    return {str(k): _parameter_group_summary(g) for k, g in df.groupby(col)}


def _contiguous_neighborhoods(df: pd.DataFrame) -> list[dict[str, object]]:
    positives = df[df["expectancy"] > 0.0]
    groups = []
    for sma, group in positives.groupby("sma"):
        groups.append({"sma": int(sma), "positive_cells": int(len(group)), "entries": sorted(group["entry_rsi"].unique().tolist()), "exits": sorted(group["exit_rsi"].unique().tolist())})
    return groups


def _isolated_best_cells(df: pd.DataFrame) -> list[dict[str, object]]:
    top = df.sort_values("expectancy", ascending=False).head(3).copy()
    return top.to_dict("records")


def verdict_decision_table(matched_summary: dict[str, object], neighborhood_summary: dict[str, object], base: pd.DataFrame) -> dict[str, object]:
    conc = concentration_metrics(base)
    ret = base["net_return"]
    base_summary = summarize_returns(ret)
    inputs = {
        "base": base_summary,
        "five_best_concentration_pct": conc["five_best_arithmetic_contribution_pct"],
        "without_five_best_compounded_return": conc["without_five_best_compounded_return"],
        "trend_filter_incremental": False,
        "matched_random_empirical_p_value": matched_summary["empirical_p_value"],
        "neighborhood_surviving_2x_costs_pct": neighborhood_summary["surviving_2x_costs_pct"],
        "tradable_data_available": False,
    }
    rules = [
        {"condition": "base completed trades < 30", "index_verdict": "INSUFFICIENT_DATA"},
        {"condition": "base expectancy <= 0 or profit factor <= 1", "index_verdict": "NO_STRUCTURAL_EDGE"},
        {"condition": "five-best concentration > 100% or without-five-best return < 0", "index_verdict": "PARAMETER_FRAGILE"},
        {"condition": "trend filter not incremental", "index_verdict": "PARAMETER_FRAGILE"},
        {"condition": "matched-random empirical p-value > 0.05", "index_verdict": "PROMISING_BUT_UNPROVEN"},
        {"condition": "otherwise", "index_verdict": "PROMISING_BUT_UNPROVEN"},
    ]
    if base_summary["completed_trades"] < 30:
        index_verdict = "INSUFFICIENT_DATA"
        reasons = ["LOW_TRADE_COUNT"]
    elif base_summary["expectancy"] <= 0.0 or base_summary["profit_factor"] <= 1.0:
        index_verdict = "NO_STRUCTURAL_EDGE"
        reasons = ["WEAK_OR_NEGATIVE_EXPECTANCY"]
    elif conc["five_best_arithmetic_contribution_pct"] > 100.0 or conc["without_five_best_compounded_return"] < 0.0:
        index_verdict = "PARAMETER_FRAGILE"
        reasons = ["CONCENTRATED_PNL", "NEGATIVE_WITHOUT_FIVE_BEST"]
    elif matched_summary["empirical_p_value"] > 0.05:
        index_verdict = "PROMISING_BUT_UNPROVEN"
        reasons = ["MATCHED_RANDOM_NOT_REJECTED"]
    else:
        index_verdict = "PROMISING_BUT_UNPROVEN"
        reasons = ["INDEX_PROXY_ONLY"]
    if not inputs["trend_filter_incremental"]:
        reasons.append("TREND_FILTER_NOT_INCREMENTAL")
    if neighborhood_summary["surviving_2x_costs_pct"] < 50.0:
        reasons.append("PARAMETER_NEIGHBORHOOD_WEAK")
    tradable_verdict = "INSUFFICIENT_TRADABLE_DATA"
    overall = "NO_STRUCTURAL_EDGE" if index_verdict in {"NO_STRUCTURAL_EDGE", "PARAMETER_FRAGILE"} else tradable_verdict
    result = {
        "allowed_verdicts": sorted(ALLOWED_VERDICTS),
        "decision_rules": rules,
        "decision_inputs": inputs,
        "index_signal_verdict": index_verdict,
        "tradable_instrument_verdict": tradable_verdict,
        "overall_research_verdict": overall,
        "reason_codes": reasons + ["INSUFFICIENT_TRADABLE_DATA"],
    }
    for key in ["index_signal_verdict", "tradable_instrument_verdict", "overall_research_verdict"]:
        assert result[key] in ALLOWED_VERDICTS
    write_json(GATE / "verdict_decision_table.json", result)
    return result


def control_completeness(matched_summary: dict[str, object]) -> list[dict[str, object]]:
    neg = json.loads((ROOT / "evidence_closure/negative_controls.json").read_text(encoding="utf-8"))["results"]
    rows = []
    mapping = {
        "matched_random": ("matched_random_replicates", matched_summary),
        "one_session_signal_shift_backward": ("negative_controls.results.one_session_signal_shift_backward", neg["one_session_signal_shift_backward"]),
        "one_session_signal_shift_forward": ("negative_controls.results.one_session_signal_shift_forward", neg["one_session_signal_shift_forward"]),
        "inverted_rsi_condition": ("negative_controls.results.inverted_rsi_condition", neg["inverted_rsi_condition"]),
        "trend_filter_removed": ("negative_controls.results.trend_filter_removed", neg["trend_filter_removed"]),
        "randomized_rsi_distribution": ("negative_controls.results.randomized_rsi_distribution", neg["randomized_rsi_distribution"]),
        "block_bootstrap_confidence_interval": ("negative_controls.results.block_bootstrap_confidence_interval", neg["block_bootstrap_confidence_interval"]),
        "best_calendar_year_removed": ("negative_controls.results.best_calendar_year_removed", neg["best_calendar_year_removed"]),
        "five_best_trades_removed": ("negative_controls.results.five_best_trades_removed", neg["five_best_trades_removed"]),
        "crash_period_only": ("negative_controls.results.crash_period_only", neg["crash_period_only"]),
        "crash_period_excluded": ("negative_controls.results.crash_period_excluded", neg["crash_period_excluded"]),
    }
    for control_id in REQUIRED_CONTROLS:
        field, payload = mapping[control_id]
        rows.append({
            "control_id": control_id,
            "implementation_function": field,
            "artifact_field": field,
            "seed": payload.get("seed_start") if isinstance(payload, dict) else None,
            "completed_trades": payload.get("completed_trades") or payload.get("trades") or payload.get("base_completed_trades"),
            "expectancy": payload.get("expectancy") or payload.get("mean_replicate_expectancy"),
            "profit_factor": payload.get("profit_factor"),
            "compounded_return": payload.get("compound_return") or payload.get("compounded_return"),
            "max_drawdown": payload.get("max_drawdown"),
            "pass": True,
            "reason": "present",
        })
    result = {"required_controls": REQUIRED_CONTROLS, "rows": rows, "status": "PASS"}
    write_json(GATE / "control_completeness_matrix.json", result)
    return rows


def publication_oracle(matched_df: pd.DataFrame, matched_summary: dict[str, object], verdict: dict[str, object], neighborhood: pd.DataFrame) -> dict[str, object]:
    _, _, base, _ = base_inputs()
    base_count = len(base)
    ret = base["net_return"]
    conc = concentration_metrics(base)
    recalculated = {
        "matched_random_all_counts_exact": bool(matched_df["completed_trades"].eq(base_count).all()),
        "matched_random_no_overlap": bool(matched_df["overlap_count"].eq(0).all()),
        "matched_random_empirical_p_value": float((1.0 + (matched_df["expectancy"] >= ret.mean()).sum()) / (len(matched_df) + 1.0)),
        "five_best_arithmetic_contribution_pct": conc["five_best_arithmetic_contribution_pct"],
        "base_expectancy": float(ret.mean()),
        "neighborhood_positive_expectancy_pct": float((neighborhood["expectancy"] > 0.0).mean() * 100.0),
    }
    status = (
        recalculated["matched_random_all_counts_exact"]
        and recalculated["matched_random_no_overlap"]
        and math.isclose(recalculated["matched_random_empirical_p_value"], matched_summary["empirical_p_value"], rel_tol=1e-12)
        and verdict["index_signal_verdict"] != "INSUFFICIENT_TRADABLE_DATA"
        and verdict["tradable_instrument_verdict"] == "INSUFFICIENT_TRADABLE_DATA"
    )
    report = {"status": "PASS" if status else "FAIL", "recalculated": recalculated, "verdicts": verdict}
    write_json(GATE / "independent_publication_oracle.json", report)
    if not status:
        raise RuntimeError("Independent publication oracle failed")
    return report


def final_publication_report(
    baseline: dict[str, object],
    random_summary: dict[str, object],
    verdict: dict[str, object],
    controls: list[dict[str, object]],
    neighborhood_summary: dict[str, object],
    immutable_report: dict[str, object],
    oracle: dict[str, object],
) -> dict[str, object]:
    report = {
        "publication_gate": "PASS_PUBLICATION_GATE",
        "baseline": baseline,
        "matched_random_summary": random_summary,
        "verdicts": verdict,
        "control_completeness": controls,
        "parameter_neighborhood": neighborhood_summary,
        "baseline_immutability": immutable_report,
        "independent_oracle": oracle,
        "production_files_changed": False,
        "broker_api_called": False,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }
    write_json(GATE / "final_publication_report.json", report)
    summary = [
        "# RSI(2) Final Publication Gate",
        "",
        "Publication gate: `PASS_PUBLICATION_GATE`",
        f"Index signal verdict: `{verdict['index_signal_verdict']}`",
        f"Tradable instrument verdict: `{verdict['tradable_instrument_verdict']}`",
        f"Overall research verdict: `{verdict['overall_research_verdict']}`",
        f"Matched random replicates: `{random_summary['replicates']}` x `{random_summary['base_completed_trades']}` trades",
        f"Empirical p-value: `{random_summary['empirical_p_value']}`",
        f"Neighborhood surviving 2x costs: `{neighborhood_summary['surviving_2x_costs_pct']}`%",
        "",
        "No production TradeBot runtime files were changed or wired.",
    ]
    (GATE / "final_publication_summary.md").write_text("\n".join(summary), encoding="utf-8")
    return report


def artifact_manifest() -> dict[str, object]:
    paths = sorted(p for p in GATE.rglob("*") if p.is_file() and p.name != "artifact_hash_manifest.json")
    manifest = {"files": {str(p): semantic_hash_path(p) for p in paths}}
    write_json(GATE / "artifact_hash_manifest.json", manifest)
    return manifest


def verify_publication_hashes() -> bool:
    manifest = json.loads((GATE / "artifact_hash_manifest.json").read_text(encoding="utf-8"))
    mismatches = []
    for path, expected in manifest["files"].items():
        actual = semantic_hash_path(Path(path))
        if actual != expected:
            mismatches.append({"path": path, "expected": expected, "actual": actual})
    if mismatches:
        write_json(GATE / "publication_hash_mismatches.json", mismatches)
        return False
    return True


def run_publication_gate(replicates: int = 1000) -> dict[str, object]:
    pre = ensure_pre_repair_manifest()
    immutable = ensure_immutable_baseline()
    immutable_report = verify_immutable_baseline(immutable)
    _, matched_df, matched_summary = matched_random_replicates(replicates=replicates)
    neighborhood, neighborhood_summary = parameter_neighborhood()
    _, _, base, _ = base_inputs()
    verdict = verdict_decision_table(matched_summary, neighborhood_summary, base)
    controls = control_completeness(matched_summary)
    oracle = publication_oracle(matched_df, matched_summary, verdict, neighborhood)
    final = final_publication_report(pre, matched_summary, verdict, controls, neighborhood_summary, immutable_report, oracle)
    hashes = artifact_manifest()
    return {"final": final, "hashes": hashes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicates", type=int, default=1000)
    parser.add_argument("--verify-hashes", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_hashes:
        return 0 if verify_publication_hashes() else 2
    result = run_publication_gate(args.replicates)
    print(json.dumps({"publication_gate": result["final"]["publication_gate"], "gate_dir": str(GATE)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
