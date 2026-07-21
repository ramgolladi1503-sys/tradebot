from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import DiscoveryConfig, StrategyCandidate
from .dataset import (
    build_discovery_dataset,
    model_feature_names,
    normalize_bars,
    provenance_payload,
)
from .evaluation import candidate_mask


def candidate_semantic_hash(candidate: StrategyCandidate) -> str:
    payload = json.dumps(
        candidate.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assert_future_mutation_does_not_change_features(
    bars: pd.DataFrame,
    *,
    decision_row: int,
    config: DiscoveryConfig,
) -> dict[str, Any]:
    if not 0 <= decision_row < len(bars) - config.barrier_horizon_bars - 1:
        raise ValueError("decision_row must leave room for future mutation and labels")
    normalized = normalize_bars(bars, config)
    decision_timestamp = normalized["bar_end_timestamp"].iloc[decision_row]

    baseline = build_discovery_dataset(bars, config=config)
    mutated_bars = bars.copy()
    future_positions = np.arange(len(mutated_bars)) > decision_row
    mutated_bars.loc[future_positions, "high"] *= 1.05
    mutated_bars.loc[future_positions, "low"] *= 0.95
    mutated_bars.loc[future_positions, "close"] *= 1.02
    mutated_bars.loc[future_positions, "volume"] *= 3.0
    mutated = build_discovery_dataset(mutated_bars, config=config)

    baseline_row = baseline.loc[
        baseline["decision_timestamp"] == decision_timestamp
    ]
    mutated_row = mutated.loc[mutated["decision_timestamp"] == decision_timestamp]
    if len(baseline_row) != 1 or len(mutated_row) != 1:
        raise AssertionError("decision row not present in both datasets")

    features = model_feature_names(baseline)
    left = baseline_row.loc[:, features].reset_index(drop=True)
    right = mutated_row.loc[:, features].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        left,
        right,
        check_dtype=False,
        rtol=0,
        atol=0,
    )

    label_columns = [
        "barrier_outcome",
        "bars_to_event",
        "mfe_atr",
        "mae_atr",
        "future_close_return_atr",
        "label_return_r",
    ]
    label_changed = not baseline_row[label_columns].reset_index(drop=True).equals(
        mutated_row[label_columns].reset_index(drop=True)
    )
    return {
        "decision_timestamp": str(decision_timestamp),
        "feature_columns_checked": len(features),
        "features_unchanged": True,
        "labels_changed": label_changed,
    }


def independent_rule_mask(
    dataset: pd.DataFrame,
    candidate: StrategyCandidate,
) -> pd.Series:
    selected = np.ones(len(dataset), dtype=bool)
    imputation = candidate.imputation_map()
    for condition in candidate.conditions:
        if condition.feature not in dataset.columns:
            raise ValueError(
                f"candidate feature missing from dataset: {condition.feature}"
            )
        column = pd.to_numeric(
            dataset[condition.feature],
            errors="coerce",
        ).to_numpy(dtype=float)
        if condition.feature in imputation:
            column = np.where(
                np.isfinite(column),
                column,
                imputation[condition.feature],
            )
        if condition.operator == "<=":
            current = column <= condition.threshold
        elif condition.operator == ">":
            current = column > condition.threshold
        else:
            raise ValueError(condition.operator)
        current &= np.isfinite(column)
        selected &= current
    return pd.Series(selected, index=dataset.index)


def assert_rule_oracle_agreement(
    dataset: pd.DataFrame,
    candidate: StrategyCandidate,
) -> dict[str, Any]:
    primary = candidate_mask(dataset, candidate)
    oracle = independent_rule_mask(dataset, candidate)
    if not primary.equals(oracle):
        disagreement = int((primary != oracle).sum())
        raise AssertionError(f"rule oracle disagreement on {disagreement} rows")
    return {
        "rows_checked": len(dataset),
        "agreement": True,
        "imputation_values_checked": len(candidate.imputation_values),
    }


def build_evidence_manifest(
    *,
    config: DiscoveryConfig,
    dataset: pd.DataFrame,
    candidate: StrategyCandidate | None,
    validation_metrics: dict[str, Any],
    validation_evidence: dict[str, Any] | None = None,
    source_adapter_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_id = candidate.candidate_id if candidate else "NO_CANDIDATE_EXTRACTED"
    return {
        "mode": "ML_STRATEGY_DISCOVERY_EVIDENCE_V2",
        "candidate_id": candidate_id,
        "decision": "RESEARCH_DISCOVERY_EVIDENCE_GENERATED",
        "reason": (
            "causal completed-bar dataset, development-only fitting, frozen-rule "
            "validation, and explicit claim boundaries were evaluated"
        ),
        "timestamp": str(dataset["decision_timestamp"].max()),
        "source": "research/ml_strategy_discovery",
        "status": "RESEARCH_ONLY_NOT_PRODUCTION_APPROVED",
        "claim_boundary": "UNDERLYING_RESEARCH_LABELS_NOT_OPTION_PNL",
        "dataset": provenance_payload(config, dataset),
        "source_adapter": source_adapter_manifest,
        "candidate": candidate.to_dict() if candidate else None,
        "candidate_semantic_hash": (
            candidate_semantic_hash(candidate) if candidate else None
        ),
        "validation_metrics": validation_metrics,
        "validation_evidence": validation_evidence or {},
        "holdout_policy": {
            "state": "LOCKED",
            "required_acknowledgement": "EVALUATE_FROZEN_CANDIDATE_ONCE",
            "one_time_enforcement": "CALLER_MUST_PRESERVE_EXTERNAL_CONSUMPTION_RECORD",
        },
        "limitations": [
            "Option profitability is not inferred from underlying returns.",
            "Missing historical bid/ask paths remain explicitly unavailable.",
            "A discovered rule is a research hypothesis, not structural-edge proof.",
            "Validation-session slices are not the strict option-replay WFA authority.",
        ],
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "allowed_for_live_execution": False,
        "append": False,
    }


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
