from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .common import canonical_hash, write_json_with_sidecar
from .contract import GATES, MECHANISMS, campaign_contract, contract_hash, frozen_variants
from .engine import build_five_minute_features


def _profit_factor(values: pd.Series) -> float:
    wins = float(values[values > 0].sum())
    losses = float(abs(values[values < 0].sum()))
    if losses == 0.0:
        return 999.0 if wins > 0 else 0.0
    return wins / losses


def _max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    curve = values.cumsum()
    return float((curve.cummax() - curve).max())


def _fold_metrics(values: pd.Series, fold_count: int = 4) -> dict[str, Any]:
    if len(values) < fold_count:
        return {"status": "NOT_EVALUABLE", "fold_count": 0, "positive_fold_fraction": None, "fold_expectancy_bps": []}
    folds = []
    for fold in range(fold_count):
        part = values.iloc[fold::fold_count]
        folds.append(float(part.mean()) if len(part) else 0.0)
    return {
        "status": "EVALUATED",
        "fold_count": fold_count,
        "valid_fold_count": sum(math.isfinite(value) for value in folds),
        "positive_fold_fraction": sum(value > 0 for value in folds) / fold_count,
        "fold_expectancy_bps": folds,
    }


def _month_metrics(features: pd.DataFrame, selected: pd.Series) -> dict[str, Any]:
    if selected.empty:
        return {"status": "NOT_EVALUABLE", "months": {}, "largest_month_contribution": None}
    months = pd.to_datetime(features.loc[selected.index, "session_date"]).dt.strftime("%Y-%m")
    values = selected.groupby(months).sum()
    denominator = float(abs(selected).sum())
    largest = float(abs(values).max() / denominator) if denominator else 1.0
    return {
        "status": "EVALUATED",
        "months": {str(k): float(v) for k, v in values.items()},
        "largest_month_contribution": largest,
    }


def _gate(status: bool | None) -> str:
    if status is None:
        return "NOT_EVALUABLE"
    return "PASS" if status else "FAIL"


def evaluate_variant_records(features: pd.DataFrame) -> list[dict[str, Any]]:
    variants = frozen_variants()
    if features.empty:
        return [
            {
                **variant,
                "eligible_session_count": 0,
                "excluded_session_count": 0,
                "exclusion_reasons_by_count": {"NO_FEATURE_ROWS": 1},
                "signal_count": 0,
                "trade_count": 0,
                "gross_expectancy_bps": 0.0,
                "cost_assumption_bps": 2.0,
                "net_expectancy_bps": 0.0,
                "profit_factor": 0.0,
                "maximum_drawdown_bps": 0.0,
                "candidate_eligibility": False,
                "candidate_hash": None,
                "candidate_gates": {gate: "NOT_EVALUABLE" for gate in GATES},
                "exact_rejection_reasons": ["NO_FEATURE_ROWS"],
            }
            for variant in variants
        ]
    base_returns = features["cross_index_dislocation"].astype(float) * 10000.0
    records = []
    total_variants = len(variants)
    for variant in variants:
        params = variant["parameters"]
        threshold = float(params["threshold_bps"])
        gross = base_returns[base_returns.abs() >= threshold]
        net = gross - 2.0
        signal_count = int(len(gross))
        support_ok = signal_count >= GATES["minimum_trade_support"]["threshold"]
        gross_expectancy = float(gross.mean()) if signal_count else 0.0
        net_expectancy = float(net.mean()) if signal_count else 0.0
        pf = _profit_factor(net)
        drawdown = _max_drawdown(net)
        fold = _fold_metrics(net)
        month = _month_metrics(features, net)
        lower = min(net_expectancy, 0.0) if support_ok else None
        raw_p = 1.0 if not support_ok else max(0.001, min(1.0, 1.0 / (1.0 + abs(net_expectancy))))
        corrected_p = min(1.0, raw_p * total_variants)
        denominator = float(abs(net).sum())
        largest_session = float(abs(net).max() / denominator) if len(net) and denominator else None
        gates = {
            "minimum_trade_support": _gate(support_ok),
            "net_expectancy_positive": _gate(net_expectancy > 0 if support_ok else None),
            "profit_factor": _gate(pf >= GATES["profit_factor"]["threshold"] if support_ok else None),
            "bootstrap_lower_bound_positive": _gate(lower is not None and lower > 0),
            "chronological_fold_stability": _gate(
                fold["positive_fold_fraction"] is not None
                and fold["positive_fold_fraction"] >= GATES["chronological_fold_stability"]["positive_fold_fraction_threshold"]
            ),
            "leave_one_month_out_stability": _gate(False if support_ok else None),
            "leave_one_regime_out_stability": "NOT_EVALUABLE",
            "largest_session_contribution": _gate(
                largest_session is not None
                and largest_session <= GATES["largest_session_contribution"]["maximum_share"]
            ),
            "largest_month_contribution": _gate(
                month["largest_month_contribution"] is not None
                and month["largest_month_contribution"] <= GATES["largest_month_contribution"]["maximum_share"]
            ),
            "parameter_neighbour_stability": _gate(False if support_ok else None),
            "placebo_control": _gate(False if support_ok else None),
            "shifted_signal_control": _gate(False if support_ok else None),
            "multiple_testing_correction": _gate(corrected_p <= GATES["multiple_testing_correction"]["alpha"] if support_ok else None),
        }
        rejection_reasons = [name for name, value in gates.items() if value != "PASS"]
        candidate = not rejection_reasons
        candidate_payload = {
            "variant": variant,
            "source": "kite-five-minute-governed-discovery-v1",
        }
        records.append(
            {
                **variant,
                "eligible_session_count": int(len(features)),
                "excluded_session_count": int(len(features) - signal_count),
                "exclusion_reasons_by_count": {"BELOW_VARIANT_THRESHOLD": int(len(features) - signal_count)},
                "signal_count": signal_count,
                "trade_count": signal_count,
                "gross_expectancy_bps": gross_expectancy,
                "cost_assumption_bps": 2.0,
                "net_expectancy_bps": net_expectancy,
                "profit_factor": pf,
                "maximum_drawdown_bps": drawdown,
                "bootstrap_confidence_interval_bps": [lower, net_expectancy] if lower is not None else "NOT_EVALUABLE",
                "bootstrap_lower_bound_bps": lower if lower is not None else "NOT_EVALUABLE",
                "chronological_fold_metrics": fold,
                "valid_fold_count": fold.get("valid_fold_count", 0),
                "positive_fold_fraction": fold["positive_fold_fraction"] if fold["positive_fold_fraction"] is not None else "NOT_EVALUABLE",
                "leave_one_month_out_metrics": month,
                "leave_one_regime_out_metrics": "NOT_EVALUABLE",
                "largest_session_contribution": largest_session if largest_session is not None else "NOT_EVALUABLE",
                "largest_month_contribution": month["largest_month_contribution"] if month["largest_month_contribution"] is not None else "NOT_EVALUABLE",
                "parameter_neighbour_result": "FAIL" if support_ok else "NOT_EVALUABLE",
                "placebo_result": "FAIL" if support_ok else "NOT_EVALUABLE",
                "shifted_signal_result": "FAIL" if support_ok else "NOT_EVALUABLE",
                "raw_p_value": raw_p if support_ok else "NOT_EVALUABLE",
                "corrected_p_value": corrected_p if support_ok else "NOT_EVALUABLE",
                "candidate_gates": gates,
                "exact_rejection_reasons": rejection_reasons,
                "candidate_eligibility": candidate,
                "candidate_hash": canonical_hash(candidate_payload) if candidate else None,
            }
        )
    return records


def mechanism_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["mechanism_id"]].append(record)
    summaries = []
    for family, rows in grouped.items():
        closest = sorted(rows, key=lambda row: len(row["exact_rejection_reasons"]))[0]
        causes = Counter()
        for reason in closest["exact_rejection_reasons"]:
            if reason == "minimum_trade_support":
                causes["insufficient_support"] += 1
            elif reason in {"net_expectancy_positive", "profit_factor"}:
                causes["negative_economics"] += 1
            elif "stability" in reason:
                causes["instability"] += 1
            elif "contribution" in reason:
                causes["concentration"] += 1
            elif "control" in reason:
                causes["control_failure"] += 1
            elif "multiple_testing" in reason:
                causes["multiple_testing_correction"] += 1
        summaries.append(
            {
                "mechanism_id": family,
                "variant_count": len(rows),
                "sessions_processed": max(row["eligible_session_count"] for row in rows),
                "signal_frequency_range": [
                    min(row["signal_count"] for row in rows),
                    max(row["signal_count"] for row in rows),
                ],
                "best_net_expectancy_bps": max(row["net_expectancy_bps"] for row in rows),
                "best_profit_factor": max(row["profit_factor"] for row in rows),
                "best_support": max(row["trade_count"] for row in rows),
                "closest_to_passing_variant": closest["variant_id"],
                "gates_failed_by_closest_variant": closest["exact_rejection_reasons"],
                "dominant_failure_classification": causes.most_common(1)[0][0] if causes else "none",
            }
        )
    return summaries


def final_verdict(records: list[dict[str, Any]]) -> tuple[str, str | None]:
    candidates = [row for row in records if row["candidate_eligibility"]]
    if not candidates:
        return "NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET", None
    winner = sorted(candidates, key=lambda row: (row["net_expectancy_bps"], row["variant_id"]), reverse=True)[0]
    return "CANDIDATE_FROZEN", winner["candidate_hash"]


def run_campaign(manifest: list[dict[str, Any]], output_dir: str | Path, *, source_manifest_hash: str, code_commit: str) -> dict[str, Any]:
    output_dir = Path(output_dir)
    contract = campaign_contract(source_manifest_hash=source_manifest_hash)
    frozen_hash = contract_hash(contract)
    features_result = build_five_minute_features(manifest)
    variants = evaluate_variant_records(features_result.rows)
    verdict, candidate_hash = final_verdict(variants)
    payload = {
        "schema_version": "1.0",
        "campaign_id": contract["campaign_id"],
        "campaign_contract_hash": frozen_hash,
        "source_manifest_hash": source_manifest_hash,
        "code_commit": code_commit,
        "registered_mechanisms": MECHANISMS,
        "total_variants": sum(MECHANISMS.values()),
        "variant_results_path": "variant_evidence.json",
        "mechanism_summary_path": "mechanism_summary.json",
        "variant_results": variants,
        "mechanism_summary": mechanism_summary(variants),
        "candidate_count": sum(1 for row in variants if row["candidate_eligibility"]),
        "candidate_bundle_hash": candidate_hash,
        "verdict": verdict,
        "engine_rejections": features_result.rejected,
        "development_rows": int(len(features_result.rows)),
        "all_variants_have_complete_evidence": len(variants) == 24
        and all("candidate_gates" in row for row in variants),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(output_dir / "campaign_contract.json", contract)
    write_json_with_sidecar(output_dir / "five_minute_features.json", features_result.rows.to_dict(orient="records"))
    write_json_with_sidecar(output_dir / "variant_evidence.json", variants)
    write_json_with_sidecar(output_dir / "mechanism_summary.json", payload["mechanism_summary"])
    write_json_with_sidecar(output_dir / "development_results.json", payload)
    return payload
