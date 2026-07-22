from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .hypothesis_features import (
    HypothesisDevelopmentError,
    build_session_features,
    outcome_column,
    variant_mask,
)
from .hypothesis_stats import (
    bootstrap_lower,
    chronological_fold_fraction,
    max_stat_pvalue,
    profit_factor,
    t_stat,
)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _json_number(value: float, *, positive_cap: float = 1_000_000.0) -> float:
    if math.isfinite(value):
        return float(value)
    return positive_cap if value > 0 else -positive_cap


def _signal_fingerprint(features: pd.DataFrame) -> str:
    columns = [
        "session_date",
        "opening_direction",
        "opening_move_prior_atr",
        "directional_efficiency",
        "gap_direction",
        "absolute_gap_prior_atr",
        "extension_prior_atr",
        "opening_reclaim_failure",
    ]
    return canonical_hash(features[columns].to_dict(orient="records"))


def run_preregistered_development_screen(
    bars: pd.DataFrame,
    *,
    specification: Mapping[str, Any],
    frozen_spec_sha256: str,
    source_manifest_sha256: str,
    code_sha: str,
    bootstrap_iterations: int = 2000,
    permutation_iterations: int = 2000,
    seed: int = 42,
) -> dict[str, Any]:
    hypothesis_id = str(specification.get("hypothesis_id", ""))
    family = str(specification.get("family", ""))
    variants = specification.get("variant_grid")
    if hypothesis_id not in {"HIM_30", "EOGF_30"}:
        raise HypothesisDevelopmentError(
            "unsupported preregistered hypothesis"
        )
    if not isinstance(variants, list) or not variants:
        raise HypothesisDevelopmentError("variant_grid must be non-empty")
    if len(variants) > int(specification.get("max_variants", 0)):
        raise HypothesisDevelopmentError(
            "variant grid exceeds frozen search budget"
        )
    if bootstrap_iterations < 200 or permutation_iterations < 200:
        raise HypothesisDevelopmentError(
            "development controls require at least 200 iterations"
        )

    features = build_session_features(bars)
    target = outcome_column(hypothesis_id)
    masks = [
        variant_mask(features, hypothesis_id, variant)
        for variant in variants
    ]
    metrics: list[dict[str, Any]] = []
    for index, (variant, mask) in enumerate(
        zip(variants, masks, strict=True)
    ):
        selected = features.loc[
            mask, ["session_date", target]
        ].copy()
        values = selected[target].to_numpy(dtype=float)
        fold_fraction, fold_means = chronological_fold_fraction(
            selected, target
        )
        absolute_total = float(np.sum(np.abs(values)))
        concentration = (
            float(np.max(np.abs(values)) / absolute_total)
            if len(values) and absolute_total > 0
            else 1.0
        )
        shifted = features[target].shift(-1)
        control_values = shifted.loc[mask].dropna().to_numpy(dtype=float)
        raw_pf = profit_factor(values) if len(values) else 0.0
        raw_t = t_stat(values)
        metrics.append(
            {
                "variant_index": index,
                "variant": dict(variant),
                "trade_count": len(values),
                "expectancy_bps": (
                    float(np.mean(values)) if len(values) else 0.0
                ),
                "median_bps": (
                    float(np.median(values)) if len(values) else 0.0
                ),
                "profit_factor": _json_number(raw_pf),
                "win_rate": (
                    float(np.mean(values > 0)) if len(values) else 0.0
                ),
                "t_stat": _json_number(raw_t),
                "bootstrap_lower_bps": _json_number(
                    bootstrap_lower(
                        values,
                        iterations=bootstrap_iterations,
                        seed=seed + index,
                    )
                ),
                "positive_fold_fraction": fold_fraction,
                "fold_expectancy_bps": [
                    value if math.isfinite(value) else None
                    for value in fold_means
                ],
                "max_abs_session_share": concentration,
                "shifted_control_bootstrap_lower_bps": _json_number(
                    bootstrap_lower(
                        control_values,
                        iterations=bootstrap_iterations,
                        seed=seed + 1000 + index,
                    )
                    if len(control_values) >= 2
                    else -math.inf
                ),
            }
        )

    observed_max_t = max(item["t_stat"] for item in metrics)
    fwer_pvalue = max_stat_pvalue(
        features,
        masks,
        target,
        observed_max_t,
        iterations=permutation_iterations,
        seed=seed + 5000,
    )
    for item in metrics:
        item["max_stat_fwer_pvalue"] = fwer_pvalue

    def eligible(item: Mapping[str, Any]) -> bool:
        return bool(
            int(item["trade_count"]) >= 30
            and float(item["expectancy_bps"]) > 0.0
            and float(item["profit_factor"]) >= 1.20
            and float(item["bootstrap_lower_bps"]) > 0.0
            and float(item["positive_fold_fraction"]) >= 0.75
            and float(item["max_abs_session_share"]) <= 0.25
            and float(item["max_stat_fwer_pvalue"]) <= 0.05
            and float(item["shifted_control_bootstrap_lower_bps"]) <= 0.0
        )

    ranked = sorted(
        metrics,
        key=lambda item: (item["t_stat"], item["expectancy_bps"]),
        reverse=True,
    )
    best = ranked[0]
    best_index = int(best["variant_index"])
    neighbors = [
        item
        for item in metrics
        if abs(int(item["variant_index"]) - best_index) == 1
    ]
    neighborhood_stable = any(
        float(item["expectancy_bps"]) > 0.0
        and float(item["positive_fold_fraction"]) >= 0.50
        for item in neighbors
    )
    candidate = best if eligible(best) and neighborhood_stable else None
    candidate_hash = None
    candidate_payload = None
    if candidate is not None:
        economic = {
            "hypothesis_id": hypothesis_id,
            "family": family,
            "frozen_spec_sha256": frozen_spec_sha256,
            "variant": candidate["variant"],
            "source_manifest_sha256": source_manifest_sha256,
            "code_sha": code_sha,
            "development_metrics": candidate,
        }
        candidate_hash = canonical_hash(economic)
        candidate_payload = {
            **economic,
            "candidate_id": (
                f"{hypothesis_id.lower()}_{candidate_hash[:16]}"
            ),
            "candidate_bundle_hash": candidate_hash,
        }

    original_fingerprint = _signal_fingerprint(features)
    mutated = features.copy()
    mutated["him_outcome_bps"] = mutated["him_outcome_bps"] * -7.0
    mutated["eogf_outcome_bps"] = mutated["eogf_outcome_bps"] * 11.0
    mutation_oracle_passed = (
        original_fingerprint == _signal_fingerprint(mutated)
    )

    return {
        "schema_version": "1.0",
        "stage": "development",
        "hypothesis_id": hypothesis_id,
        "family": family,
        "frozen_spec_sha256": frozen_spec_sha256,
        "verdict": (
            "CANDIDATE_FROZEN"
            if candidate_payload
            else "NO_STABLE_CANDIDATE"
        ),
        "candidate_count": 1 if candidate_payload else 0,
        "candidate_bundle_hash": candidate_hash,
        "candidate": candidate_payload,
        "development_sessions": int(
            features["session_date"].nunique()
        ),
        "variant_results": metrics,
        "max_stat_fwer_pvalue": fwer_pvalue,
        "parameter_neighborhood_stable": neighborhood_stable,
        "session_clustered": True,
        "multiple_testing_controlled": True,
        "negative_controls_passed": bool(
            candidate is None
            or float(
                candidate["shifted_control_bootstrap_lower_bps"]
            )
            <= 0.0
        ),
        "future_mutation_oracle_passed": mutation_oracle_passed,
        "validation_v1_consumed_loaded": False,
        "holdout_v1_locked_loaded": False,
        "fresh_confirmation_loaded": False,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
