from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

import numpy as np
import pandas as pd

from .contracts import StabilityConfig, canonical_hash, require_causal_features
from .controls import run_negative_controls
from .folds import fold_manifest_hash, generate_nested_folds
from .gates import (
    base_rate_gate,
    bootstrap_gate,
    concentration_gate,
    concentration_metrics,
    fold_gate,
    imputation_dependence,
    imputation_gate,
    performance_metrics,
    session_bootstrap_expectancy,
    support_gate,
)
from .model import generate_candidates, rule_mask, semantic_frame_hash
from .stability import max_statistic_test, recurrence_summary, rule_similarity


def _candidate_medoid(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    scores: list[tuple[float, str, dict[str, Any]]] = []
    for candidate in candidates:
        similarities = [rule_similarity(candidate, other) for other in candidates]
        scores.append((float(np.mean(similarities)), candidate["rule_hash"], candidate))
    return max(scores, key=lambda item: (item[0], item[1]))[2]


def _adaptive_inner_config(config: StabilityConfig, train: pd.DataFrame) -> StabilityConfig:
    session_count = int(train["session_date"].nunique())
    return replace(
        config,
        min_rows=min(config.min_rows, max(20, len(train) // 100)),
        min_sessions=min(config.min_sessions, max(5, session_count // 3)),
    )


def _select_candidate_on_inner_folds(
    frame: pd.DataFrame,
    inner_folds: list[dict[str, Any]],
    *,
    features: tuple[str, ...],
    config: StabilityConfig,
    seed_offset: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    hypothesis_count = 0
    for inner_index, fold in enumerate(inner_folds):
        train = frame[frame["session_date"].isin(fold["train_sessions"])].copy()
        validation = frame[
            frame["session_date"].isin(fold["validation_sessions"])
        ].copy()
        if train.empty or validation.empty:
            continue
        inner_config = _adaptive_inner_config(config, train)
        candidates = generate_candidates(
            train,
            features=features,
            min_samples_leaf=max(20, min(inner_config.min_rows // 2, len(train) // 10)),
            seed=config.seed + seed_offset + inner_index,
        )
        hypothesis_count += len(candidates)
        base_validation = performance_metrics(
            validation, pd.Series(True, index=validation.index, dtype=bool)
        )
        eligible: list[tuple[float, int, str, dict[str, Any]]] = []
        for candidate in candidates:
            train_metrics = performance_metrics(train, rule_mask(train, candidate))
            support_ok, _ = support_gate(train_metrics, inner_config)
            if not support_ok:
                continue
            validation_metrics = performance_metrics(
                validation, rule_mask(validation, candidate)
            )
            lift_ok, _ = base_rate_gate(validation_metrics, base_validation)
            if validation_metrics["rows"] == 0 or not lift_ok:
                continue
            enriched = {
                **candidate,
                "inner_validation_metrics": validation_metrics,
                "inner_train_metrics": train_metrics,
                "origin_inner_fold": int(fold["fold"]),
            }
            eligible.append(
                (
                    validation_metrics["expectancy_r"],
                    validation_metrics["rows"],
                    candidate["rule_hash"],
                    enriched,
                )
            )
        if eligible:
            selected.append(max(eligible, key=lambda item: (item[0], item[1], item[2]))[3])
    medoid = _candidate_medoid(selected)
    if medoid is None:
        return None, selected, hypothesis_count
    recurrence = recurrence_summary(
        frame,
        medoid,
        [[candidate] for candidate in selected],
        minimum_similarity=config.min_rule_similarity,
        minimum_jaccard=config.min_selected_row_jaccard,
        minimum_fraction=config.min_recurrence_fraction,
    )
    if not recurrence["passes_recurrence"]:
        return None, selected, hypothesis_count
    return medoid, selected, hypothesis_count


def _empty_result(
    *,
    side: str,
    frame: pd.DataFrame,
    features: tuple[str, ...],
    folds: list[dict[str, Any]],
    outer_records: list[dict[str, Any]],
    funnel: dict[str, Any],
    config: StabilityConfig,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "side": side,
        "verdict": "NO_STABLE_CANDIDATE",
        "candidate": None,
        "screened_consensus_candidate": None,
        "development_dataset_hash": semantic_frame_hash(
            frame, ["session_date", "label_return_r", *features]
        ),
        "feature_schema_hash": canonical_hash(features),
        "search_space_hash": canonical_hash(
            {"features": features, "config": asdict(config), "hypothesis_rule_hashes": []}
        ),
        "fold_manifest_hash": fold_manifest_hash(folds),
        "folds": folds,
        "outer_fold_results": outer_records,
        "fold_summary": fold_gate(outer_records, config)[2],
        "candidate_funnel": funnel,
        "candidate_metrics": {},
        "base_metrics": {},
        "multiple_testing": max_statistic_test(
            frame,
            [],
            iterations=config.permutation_iterations,
            seed=config.seed,
            alpha=config.adjusted_alpha,
        ),
        "candidate_significance": None,
        "recurrence": None,
        "concentration": {},
        "bootstrap": {},
        "imputation_dependence": {},
        "negative_controls": {
            "passes": False,
            "rejection_reasons": ["NO_CANDIDATE_TO_CONTROL"],
        },
        "gate_results": {},
        "rejection_reasons": sorted(set(reasons)),
    }


def run_stability_first_discovery(
    development: pd.DataFrame,
    *,
    side: str,
    features: tuple[str, ...] | list[str],
    config: StabilityConfig | None = None,
) -> dict[str, Any]:
    config = config or StabilityConfig()
    if side not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")
    feature_names = require_causal_features(features)
    required = {"session_date", "label_return_r", *feature_names}
    missing = required.difference(development.columns)
    if missing:
        raise ValueError(f"development dataset missing columns: {sorted(missing)}")
    sort_columns = ["session_date"]
    if "decision_timestamp" in development.columns:
        sort_columns.append("decision_timestamp")
    frame = development.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)
    folds = generate_nested_folds(
        frame,
        outer_folds=config.outer_folds,
        inner_folds=config.inner_folds,
        embargo_sessions=config.embargo_sessions,
    )
    outer_records: list[dict[str, Any]] = []
    outer_candidates: list[dict[str, Any]] = []
    all_inner_candidates: list[list[dict[str, Any]]] = []
    total_hypotheses = 0
    for outer_index, nested in enumerate(folds):
        outer = nested["outer"]
        outer_train = frame[frame["session_date"].isin(outer["train_sessions"])].copy()
        outer_validation = frame[
            frame["session_date"].isin(outer["validation_sessions"])
        ].copy()
        selected, inner_selected, count = _select_candidate_on_inner_folds(
            outer_train,
            nested["inner"],
            features=feature_names,
            config=config,
            seed_offset=1000 * outer_index,
        )
        total_hypotheses += count
        all_inner_candidates.append(inner_selected)
        if selected is None:
            outer_records.append(
                {
                    "fold": outer["fold"],
                    "candidate": None,
                    "metrics": performance_metrics(
                        outer_validation,
                        pd.Series(False, index=outer_validation.index, dtype=bool),
                    ),
                    "reason": "NO_RECURRING_INNER_CANDIDATE",
                }
            )
            continue
        validation_metrics = performance_metrics(
            outer_validation, rule_mask(outer_validation, selected)
        )
        outer_candidates.append(selected)
        outer_records.append(
            {
                "fold": outer["fold"],
                "candidate": {
                    "rule_hash": selected["rule_hash"],
                    "conditions": selected["conditions"],
                    "origin_inner_fold": selected.get("origin_inner_fold"),
                },
                "metrics": validation_metrics,
                "reason": "SCORED_ON_OUTER_VALIDATION",
            }
        )

    funnel = {
        "outer_folds": len(folds),
        "outer_folds_with_candidate": len(outer_candidates),
        "total_inner_hypotheses": total_hypotheses,
    }
    consensus = _candidate_medoid(outer_candidates)
    if consensus is None:
        funnel.update(
            {
                "unique_hypotheses": 0,
                "consensus_candidate_identified": 0,
                "surviving_candidates": 0,
            }
        )
        return _empty_result(
            side=side,
            frame=frame,
            features=feature_names,
            folds=folds,
            outer_records=outer_records,
            funnel=funnel,
            config=config,
            reasons=["NO_OUTER_CONSENSUS_CANDIDATE"],
        )

    unique_hypotheses: dict[str, dict[str, Any]] = {}
    for group in all_inner_candidates:
        for candidate in group:
            unique_hypotheses[candidate["rule_hash"]] = candidate
    for candidate in outer_candidates:
        unique_hypotheses[candidate["rule_hash"]] = candidate
    hypotheses = [unique_hypotheses[key] for key in sorted(unique_hypotheses)]
    multiple_testing = max_statistic_test(
        frame,
        hypotheses,
        iterations=config.permutation_iterations,
        seed=config.seed,
        alpha=config.adjusted_alpha,
    )
    significance_by_hash = {
        item["rule_hash"]: item for item in multiple_testing["candidates"]
    }
    significance = significance_by_hash.get(consensus["rule_hash"])
    if significance is None:
        raise AssertionError("consensus candidate missing from multiple-testing family")

    recurrence = recurrence_summary(
        frame,
        consensus,
        [[candidate] for candidate in outer_candidates],
        minimum_similarity=config.min_rule_similarity,
        minimum_jaccard=config.min_selected_row_jaccard,
        minimum_fraction=config.min_recurrence_fraction,
    )
    full_mask = rule_mask(frame, consensus)
    candidate_metrics = performance_metrics(frame, full_mask)
    base_metrics = performance_metrics(
        frame, pd.Series(True, index=frame.index, dtype=bool)
    )
    concentration = concentration_metrics(frame, full_mask)
    bootstrap = session_bootstrap_expectancy(
        frame,
        full_mask,
        iterations=config.bootstrap_iterations,
        seed=config.seed,
    )
    imputation = imputation_dependence(frame, consensus)
    controls = run_negative_controls(frame, consensus, seed=config.seed)

    fold_result = fold_gate(outer_records, config)
    checks = {
        "support": support_gate(candidate_metrics, config),
        "base_rate": base_rate_gate(candidate_metrics, base_metrics),
        "folds": fold_result[:2],
        "concentration": concentration_gate(concentration, config),
        "bootstrap": bootstrap_gate(bootstrap),
        "imputation": imputation_gate(imputation, config),
    }
    gate_results = {
        name: {"passes": bool(result[0]), "reasons": list(result[1])}
        for name, result in checks.items()
    }
    gate_results["adjusted_significance"] = {
        "passes": bool(significance["passes_adjusted_significance"]),
        "reasons": []
        if significance["passes_adjusted_significance"]
        else ["ADJUSTED_SIGNIFICANCE_FAILED"],
    }
    gate_results["recurrence"] = {
        "passes": bool(recurrence["passes_recurrence"]),
        "reasons": [] if recurrence["passes_recurrence"] else ["RECURRENCE_FAILED"],
    }
    gate_results["negative_controls"] = {
        "passes": bool(controls["passes"]),
        "reasons": list(controls["rejection_reasons"]),
    }
    rejection_reasons = sorted(
        reason for result in gate_results.values() for reason in result["reasons"]
    )
    passes = all(result["passes"] for result in gate_results.values())
    funnel.update(
        {
            "unique_hypotheses": len(hypotheses),
            "consensus_candidate_identified": 1,
            "surviving_candidates": int(passes),
        }
    )
    return {
        "side": side,
        "verdict": f"ONE_{side}_V2_CANDIDATE_FROZEN" if passes else "NO_STABLE_CANDIDATE",
        "candidate": consensus if passes else None,
        "screened_consensus_candidate": consensus,
        "development_dataset_hash": semantic_frame_hash(
            frame, ["session_date", "label_return_r", *feature_names]
        ),
        "feature_schema_hash": canonical_hash(feature_names),
        "search_space_hash": canonical_hash(
            {
                "features": feature_names,
                "config": asdict(config),
                "hypothesis_rule_hashes": sorted(unique_hypotheses),
            }
        ),
        "fold_manifest_hash": fold_manifest_hash(folds),
        "folds": folds,
        "outer_fold_results": outer_records,
        "fold_summary": fold_result[2],
        "candidate_funnel": funnel,
        "candidate_metrics": candidate_metrics,
        "base_metrics": base_metrics,
        "multiple_testing": multiple_testing,
        "candidate_significance": significance,
        "recurrence": recurrence,
        "concentration": concentration,
        "bootstrap": bootstrap,
        "imputation_dependence": imputation,
        "negative_controls": controls,
        "gate_results": gate_results,
        "rejection_reasons": rejection_reasons,
    }
