#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import subprocess
from pathlib import Path
from typing import Any


AUDIT_SPECS = (
    (
        "scripts/audit_phase4_truth.py",
        "phase_4_5_truth_audit.json",
        "PHASE_4_5_TRUTH_AUDIT_PASSED",
    ),
    (
        "scripts/audit_phase4_7_integrity.py",
        "phase_4_7_integrity_audit.json",
        "PHASE_4_7_INTEGRITY_AUDIT_PASSED",
    ),
    (
        "scripts/audit_phase4_8_selection_quality.py",
        "phase_4_8_selection_quality_audit.json",
        "PHASE_4_8_SELECTION_QUALITY_PASSED",
    ),
    (
        "scripts/audit_phase4_10_accounting.py",
        "phase_4_10_accounting_audit.json",
        "PHASE_4_10_ACCOUNTING_PASSED",
    ),
    (
        "scripts/audit_phase4_v2_structural.py",
        "phase_4_v2_structural_audit.json",
        "V2_STRUCTURAL_AUDIT_PASSED",
    ),
)


def _run_command(command: list[str]) -> tuple[bool, str | None]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        return True, None
    detail = result.stderr.strip() or result.stdout.strip() or "unknown failure"
    return False, detail


def run_audits(strategy_id: str) -> list[str]:
    blockers: list[str] = []
    for script, _, _ in AUDIT_SPECS:
        ok, detail = _run_command(["python", script, "--strategy", strategy_id])
        if not ok:
            blockers.append(
                f"AUDIT_COMMAND_FAILED:{Path(script).name}:{detail}"
            )
    return blockers


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def _ledger_profit_factor(
    base_dir: Path,
    pnl_model: str | None,
) -> tuple[float | None, str]:
    if pnl_model == "UNDERLYING_INDEX_PROXY_FIXED_HURDLE":
        pnl_field = "underlying_net_pnl_after_index_cost"
    elif pnl_model == "DELTA_PROXY_OPTION":
        pnl_field = "proxy_option_net_pnl"
    else:
        return None, "PNL_MODEL_UNRESOLVED"

    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    if not ledger_path.exists():
        return None, "NO_TRADES"
    wins = 0.0
    losses = 0.0
    trade_count = 0
    for line in ledger_path.read_text().splitlines():
        if not line.strip():
            continue
        trade = json.loads(line)
        if pnl_field not in trade:
            return None, "GATED_PNL_FIELD_MISSING"
        trade_count += 1
        pnl = float(trade[pnl_field])
        if pnl > 0:
            wins += pnl
        elif pnl < 0:
            losses += abs(pnl)
    if trade_count == 0:
        return None, "NO_TRADES"
    if losses > 0:
        return wins / losses, "FINITE"
    if wins > 0:
        return None, "NO_LOSING_TRADES"
    return 0.0, "NO_WINNING_TRADES"


def get_metrics(
    strategy_id: str,
    *,
    command_blockers: list[str] | None = None,
) -> dict[str, Any]:
    base_dir = Path(f"runtime/strategy_validation/{strategy_id}")
    accounting = _load_json(base_dir / "phase_4_10_accounting_audit.json")
    quality = _load_json(base_dir / "phase_4_8_selection_quality_audit.json")

    blockers = list(command_blockers or [])
    audit_status: dict[str, str | None] = {}
    for _, report_name, expected_classification in AUDIT_SPECS:
        report = _load_json(base_dir / report_name)
        classification = report.get("classification")
        audit_status[report_name] = classification
        if not report:
            blockers.append(f"AUDIT_REPORT_MISSING:{report_name}")
        elif classification != expected_classification:
            blockers.append(
                f"AUDIT_NOT_PASSED:{report_name}:{classification or 'MISSING'}"
            )
        for blocker in report.get("blockers", []):
            if blocker not in blockers:
                blockers.append(str(blocker))
        for blocker in report.get("failed_blockers", []):
            if blocker not in blockers:
                blockers.append(str(blocker))
        for blocker in report.get("suspicious_blockers", []):
            if blocker not in blockers:
                blockers.append(str(blocker))

    accounting_metrics = accounting.get("metrics", {})
    pnl_model = accounting_metrics.get("pnl_model_used_for_gate")
    gated_expectancy_raw = accounting_metrics.get("gated_expectancy")
    if gated_expectancy_raw is None:
        blockers.append("GATED_EXPECTANCY_MISSING")
        gated_expectancy = 0.0
    else:
        gated_expectancy = float(gated_expectancy_raw)

    profit_factor, profit_factor_state = _ledger_profit_factor(
        base_dir, str(pnl_model) if pnl_model is not None else None
    )
    if profit_factor_state in {
        "PNL_MODEL_UNRESOLVED",
        "GATED_PNL_FIELD_MISSING",
        "NO_TRADES",
    }:
        blockers.append(f"GATED_PROFIT_FACTOR_UNAVAILABLE:{profit_factor_state}")

    metrics = {
        "selected_trades": int(accounting_metrics.get("total_trades", 0) or 0),
        "pnl_model_used_for_gate": pnl_model,
        "gated_expectancy": gated_expectancy,
        "underlying_net_expectancy_after_index_cost": float(
            accounting_metrics.get(
                "underlying_net_expectancy_after_index_cost", 0.0
            )
            or 0.0
        ),
        "proxy_option_net_expectancy": float(
            accounting_metrics.get("proxy_option_net_expectancy", 0.0) or 0.0
        ),
        "cap_saturation_ratio": quality.get("metrics", {}).get(
            "cap_saturation_ratio"
        ),
        "profit_factor": profit_factor,
        "profit_factor_state": profit_factor_state,
        "audit_status": audit_status,
        "audits_passed": len(blockers) == 0,
        "blockers": sorted(set(blockers)),
    }
    return metrics


def run_pass(
    strategy_id: str,
    start_date: str,
    end_date: str,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    ok, detail = _run_command(
        [
            "python",
            "scripts/generate_mean_reversion_trade_ledger.py",
            "--start-date",
            start_date,
            "--end-date",
            end_date,
            "--config-override",
            json.dumps(overrides, sort_keys=True),
        ]
    )
    command_blockers: list[str] = []
    if not ok:
        command_blockers.append(f"LEDGER_COMMAND_FAILED:{detail}")
    command_blockers.extend(run_audits(strategy_id))
    return get_metrics(strategy_id, command_blockers=command_blockers)


def _positive(metrics: dict[str, Any]) -> bool:
    return bool(metrics.get("audits_passed")) and float(
        metrics.get("gated_expectancy", 0.0) or 0.0
    ) > 0


def _passes_pf(metrics: dict[str, Any], minimum: float) -> bool:
    value = metrics.get("profit_factor")
    return (
        metrics.get("profit_factor_state") == "FINITE"
        and value is not None
        and float(value) > minimum
    )


def check_region_stability(
    combo: tuple[Any, ...],
    grid: dict[str, list[Any]],
    all_results: dict[tuple[Any, ...], dict[str, Any]],
    keys: list[str],
) -> bool:
    neighbors_evaluated = 0
    neighbors_positive = 0
    for index, key in enumerate(keys):
        values = grid[key]
        current_index = values.index(combo[index])
        adjacent: list[Any] = []
        if current_index > 0:
            adjacent.append(values[current_index - 1])
        if current_index < len(values) - 1:
            adjacent.append(values[current_index + 1])
        for adjacent_value in adjacent:
            neighbor = list(combo)
            neighbor[index] = adjacent_value
            neighbor_tuple = tuple(neighbor)
            record = all_results.get(neighbor_tuple)
            if record is None:
                continue
            neighbors_evaluated += 1
            if _positive(record["train_metrics"]):
                neighbors_positive += 1
    return neighbors_evaluated > 0 and neighbors_positive > 0


def _stable_parameter_id(params: dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _overrides(combo: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "entry": {
            "opening_range_minutes": combo[0],
            "min_wick_rejection_ratio": combo[1],
            "max_trades_per_symbol_day": combo[5],
        },
        "htf_filter": {"period_minutes": combo[2]},
        "stop_loss": {"atr_multiple": combo[3]},
        "target": {"minimum_rr": combo[4]},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="MEAN_REVERSION_EXTENSION")
    parser.add_argument("--train-start", default="20240701")
    parser.add_argument("--train-end", default="20250331")
    parser.add_argument("--val-start", default="20250401")
    parser.add_argument("--val-end", default="20251231")
    parser.add_argument("--holdout-start", default="20260101")
    parser.add_argument("--holdout-end", default="20260703")
    parser.add_argument("--max-combinations", type=int, default=None)
    args = parser.parse_args()

    grid = {
        "opening_range_minutes": [30, 45, 60],
        "min_wick_rejection_ratio": [0.4, 0.5, 0.6],
        "htf_period_minutes": [15, 30],
        "stop_atr": [0.8, 1.0, 1.2],
        "target_rr": [1.5, 2.0, 2.5],
        "max_trades_per_symbol_day": [2, 3, 4],
    }
    keys = list(grid)
    combinations = list(itertools.product(*(grid[key] for key in keys)))
    random.Random(42).shuffle(combinations)
    if args.max_combinations is not None:
        combinations = combinations[: max(args.max_combinations, 0)]

    print(f"Phase 4.11B Nested Discovery. Total combos: {len(combinations)}")
    all_results: dict[tuple[Any, ...], dict[str, Any]] = {}
    train_survivors: list[tuple[Any, ...]] = []
    for combo in combinations:
        overrides = _overrides(combo)
        train_metrics = run_pass(
            args.strategy, args.train_start, args.train_end, overrides
        )
        all_results[combo] = {
            "train_metrics": train_metrics,
            "overrides": overrides,
        }
        if _positive(train_metrics):
            train_survivors.append(combo)

    val_survivors: list[tuple[Any, ...]] = []
    for combo in train_survivors:
        validation_metrics = run_pass(
            args.strategy,
            args.val_start,
            args.val_end,
            all_results[combo]["overrides"],
        )
        all_results[combo]["val_metrics"] = validation_metrics
        if _positive(validation_metrics) and _passes_pf(validation_metrics, 1.15):
            val_survivors.append(combo)

    val_survivors.sort(
        key=lambda combo: float(
            all_results[combo]["val_metrics"].get("profit_factor") or 0.0
        ),
        reverse=True,
    )
    stable_candidates = [
        combo
        for combo in val_survivors
        if check_region_stability(combo, grid, all_results, keys)
    ]
    top_candidates = stable_candidates[:10]

    final_results: list[dict[str, Any]] = []
    for combo in combinations:
        params = {keys[index]: combo[index] for index in range(len(keys))}
        record: dict[str, Any] = {
            "parameter_set_id": _stable_parameter_id(params),
            "params": params,
            "train": all_results[combo]["train_metrics"],
            "validation": all_results[combo].get("val_metrics"),
            "final_holdout": None,
            "blockers": [],
            "pass_fail_reason": [],
        }
        if combo not in train_survivors:
            record["pass_fail_reason"].append("FAILED_TRAIN")
        elif combo not in val_survivors:
            record["pass_fail_reason"].append("FAILED_VALIDATION")
        elif combo not in stable_candidates:
            record["blockers"].append("PARAMETER_REGION_NOT_STABLE")
            record["pass_fail_reason"].append("FAILED_REGION_STABILITY")
        elif combo not in top_candidates:
            record["blockers"].append("FINAL_HOLDOUT_NOT_EVALUATED")
            record["pass_fail_reason"].append("NOT_IN_TOP_CANDIDATES")
        else:
            holdout_metrics = run_pass(
                args.strategy,
                args.holdout_start,
                args.holdout_end,
                all_results[combo]["overrides"],
            )
            record["final_holdout"] = holdout_metrics
            passed = _positive(holdout_metrics) and _passes_pf(
                holdout_metrics, 1.15
            )
            if not holdout_metrics.get("audits_passed"):
                record["pass_fail_reason"].append("HOLDOUT_AUDIT_FAILED")
            if float(holdout_metrics.get("gated_expectancy", 0.0) or 0.0) <= 0:
                record["pass_fail_reason"].append("HOLDOUT_EXPECTANCY_NEGATIVE")
            if not _passes_pf(holdout_metrics, 1.15):
                record["pass_fail_reason"].append("HOLDOUT_PROFIT_FACTOR_LOW")
            if int(holdout_metrics.get("selected_trades", 0) or 0) < 100:
                passed = False
                record["pass_fail_reason"].append("HOLDOUT_TRADE_COUNT_TOO_LOW")
            cap_ratio = holdout_metrics.get("cap_saturation_ratio")
            if cap_ratio is None or float(cap_ratio) > 0.70:
                passed = False
                record["pass_fail_reason"].append(
                    "HOLDOUT_CAP_SATURATION_INVALID"
                )
            if passed:
                record["pass_fail_reason"].append("PASSED")
        final_results.append(record)

    if not val_survivors:
        conclusion = "MRE_V1_PARAMETER_SPACE_FAILED"
    elif not stable_candidates:
        conclusion = "MRE_V1_OVERFIT_REGION_FAILED"
    else:
        conclusion = "MRE_V1_HOLDOUT_EVALUATED"

    def summarized(stage: str) -> list[dict[str, Any]]:
        values = []
        metrics_key = "train_metrics" if stage == "train" else "val_metrics"
        for record in all_results.values():
            if metrics_key not in record:
                continue
            metrics = record[metrics_key]
            values.append(
                {
                    "params": record["overrides"],
                    "pnl_model_used_for_gate": metrics[
                        "pnl_model_used_for_gate"
                    ],
                    "gated_expectancy": metrics["gated_expectancy"],
                    "profit_factor": metrics["profit_factor"],
                    "profit_factor_state": metrics["profit_factor_state"],
                    "audits_passed": metrics["audits_passed"],
                }
            )
        values.sort(key=lambda item: item["gated_expectancy"], reverse=True)
        return values[:10]

    report = {
        "configured_grid_size": len(combinations),
        "executed_grid_size": len(combinations),
        "train_pass_count": len(train_survivors),
        "validation_pass_count": len(val_survivors),
        "region_stable_count": len(stable_candidates),
        "final_holdout_evaluated_count": len(top_candidates),
        "rejected_train_count": len(combinations) - len(train_survivors),
        "rejected_validation_count": len(train_survivors) - len(val_survivors),
        "rejected_region_instability_count": len(val_survivors)
        - len(stable_candidates),
        "top_10_train_results": summarized("train"),
        "top_10_validation_results": summarized("validation"),
        "all_blockers_summary": sorted(
            {
                blocker
                for result in final_results
                for blocker in (
                    result.get("blockers", [])
                    + result.get("train", {}).get("blockers", [])
                    + (result.get("validation") or {}).get("blockers", [])
                    + (result.get("final_holdout") or {}).get("blockers", [])
                )
            }
        ),
        "conclusion": conclusion,
        "final_results": final_results,
    }
    output_path = Path(
        f"runtime/strategy_validation/{args.strategy}/"
        "phase_4_11b_v2_full_grid_report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))
    print(f"Phase 4.11B Full Grid run complete. Conclusion: {conclusion}")


if __name__ == "__main__":
    main()
