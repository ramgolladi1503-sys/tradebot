from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.ml_strategy_discovery.audit import (
    assert_future_mutation_does_not_change_features,
    assert_rule_oracle_agreement,
)
from research.ml_strategy_discovery.contracts import (
    DiscoveryConfig,
    FeatureImputation,
    RuleCondition,
    StrategyCandidate,
    TimestampSemantics,
)
from research.ml_strategy_discovery.dataset import (
    build_discovery_dataset,
    chronological_split,
    model_feature_names,
    normalize_bars,
    semantic_dataset_hash,
)
from research.ml_strategy_discovery.evaluation import (
    candidate_mask,
    evaluate_candidate,
    evaluate_locked_holdout_once,
    parameter_stability,
    run_negative_controls,
)
from research.ml_strategy_discovery.labels import compute_triple_barrier_labels
from research.ml_strategy_discovery.models import train_discovery_models


def synthetic_bars(days: int = 8, bars_per_day: int = 120) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    price = 22000.0
    rng = np.random.default_rng(11)
    for day in range(days):
        start = pd.Timestamp("2026-01-05 03:45:00", tz="UTC") + pd.Timedelta(
            days=day
        )
        regime = 1.0 if day % 3 == 0 else (-0.8 if day % 3 == 1 else 0.1)
        for bar in range(bars_per_day):
            pulse = 4.5 * np.sin(bar / 8.0) + regime * (1.0 + (bar < 35))
            shock = rng.normal(0.0, 3.0)
            open_price = price
            close_price = max(100.0, open_price + pulse + shock)
            rows.append(
                {
                    "timestamp": start + pd.Timedelta(minutes=bar),
                    "open": open_price,
                    "high": max(open_price, close_price)
                    + abs(rng.normal(2.5, 1.0)),
                    "low": min(open_price, close_price)
                    - abs(rng.normal(2.5, 1.0)),
                    "close": close_price,
                    "volume": float(
                        1000
                        + 15 * bar
                        + (1200 if bar < 20 else 0)
                        + rng.integers(0, 500)
                    ),
                    "days_to_expiry": float((3 - day) % 7),
                }
            )
            price = close_price
        price += 35.0 * (1 if day % 2 == 0 else -1)
    return pd.DataFrame(rows)


def config() -> DiscoveryConfig:
    return DiscoveryConfig(
        instrument="NIFTY",
        timestamp_semantics=TimestampSemantics.START,
        source_timezone="Asia/Kolkata",
        bar_interval_minutes=1,
        strict_bar_cadence=True,
        minimum_history_bars=40,
        barrier_horizon_bars=12,
        target_atr=0.8,
        stop_atr=0.5,
        opening_range_bars=15,
    )


def test_start_and_end_labels_resolve_same_completed_interval() -> None:
    common = {
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [10.0],
    }
    start = normalize_bars(
        pd.DataFrame(
            {"timestamp": [pd.Timestamp("2026-01-05 09:15:00")], **common}
        ),
        DiscoveryConfig(
            instrument="NIFTY",
            timestamp_semantics="START",
            source_timezone="Asia/Kolkata",
        ),
    )
    end = normalize_bars(
        pd.DataFrame(
            {"timestamp": [pd.Timestamp("2026-01-05 09:16:00")], **common}
        ),
        DiscoveryConfig(
            instrument="NIFTY",
            timestamp_semantics="END",
            source_timezone="Asia/Kolkata",
        ),
    )
    expected_start = pd.Timestamp("2026-01-05 03:45:00+00:00")
    expected_end = pd.Timestamp("2026-01-05 03:46:00+00:00")
    assert start.loc[0, "bar_start_timestamp"] == expected_start
    assert start.loc[0, "bar_end_timestamp"] == expected_end
    assert end.loc[0, "bar_start_timestamp"] == expected_start
    assert end.loc[0, "bar_end_timestamp"] == expected_end
    assert start.loc[0, "timestamp"] == expected_end


def test_strict_cadence_and_duplicates_fail_closed() -> None:
    bars = synthetic_bars(days=1, bars_per_day=80)
    with pytest.raises(ValueError, match="strict bar cadence violated"):
        normalize_bars(bars.drop(index=20).reset_index(drop=True), config())
    duplicate = pd.concat([bars, bars.iloc[[10]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate timestamps fail closed"):
        normalize_bars(duplicate, config())


def test_dataset_is_deterministic_and_future_labels_are_not_features() -> None:
    bars = synthetic_bars()
    first = build_discovery_dataset(bars, config=config())
    second = build_discovery_dataset(
        bars.sample(frac=1.0, random_state=4),
        config=config(),
    )
    assert semantic_dataset_hash(first) == semantic_dataset_hash(second)
    assert set(first["option_data_availability"]) == {"UNAVAILABLE"}
    assert (first["source_data_max_timestamp"] <= first["decision_timestamp"]).all()
    assert (first["bar_start_timestamp"] < first["bar_end_timestamp"]).all()
    assert set(first["label_entry_semantics"]) == {"NEXT_LEGAL_BAR_OPEN"}
    features = set(model_feature_names(first))
    assert "label_entry_price" not in features
    assert "label_entry_timestamp" not in features
    assert "label_terminal_timestamp" not in features
    assert "label_return_r" not in features


def test_future_mutation_changes_labels_not_features() -> None:
    evidence = assert_future_mutation_does_not_change_features(
        synthetic_bars(),
        decision_row=300,
        config=config(),
    )
    assert evidence["features_unchanged"] is True
    assert evidence["labels_changed"] is True
    assert evidence["feature_columns_checked"] >= 25


def test_chronological_split_is_session_disjoint_and_ordered() -> None:
    split = chronological_split(
        build_discovery_dataset(synthetic_bars(), config=config())
    )
    dev = split.loc[split["split"] == "DEVELOPMENT"]
    validation = split.loc[split["split"] == "VALIDATION"]
    holdout = split.loc[split["split"] == "HOLDOUT_LOCKED"]
    assert dev["decision_timestamp"].max() < validation["decision_timestamp"].min()
    assert validation["decision_timestamp"].max() < holdout[
        "decision_timestamp"
    ].min()
    assert set(dev["session_date"]).isdisjoint(validation["session_date"])
    assert set(dev["session_date"]).isdisjoint(holdout["session_date"])
    assert set(validation["session_date"]).isdisjoint(holdout["session_date"])


def test_training_excludes_holdout_and_frozen_rules_reproduce_tree_leaves() -> None:
    split = chronological_split(
        build_discovery_dataset(synthetic_bars(), config=config())
    )
    artifacts = train_discovery_models(
        split,
        config=config(),
        max_tree_depth=3,
        minimum_leaf_rows=10,
    )
    mutated = split.copy()
    holdout_mask = mutated["split"] == "HOLDOUT_LOCKED"
    mutated.loc[holdout_mask, "barrier_outcome"] = "TARGET_FIRST"
    mutated.loc[holdout_mask, "label_return_r"] = 99.0
    second = train_discovery_models(
        mutated,
        config=config(),
        max_tree_depth=3,
        minimum_leaf_rows=10,
    )
    assert artifacts.validation_metrics == second.validation_metrics
    assert [item.candidate_id for item in artifacts.candidates] == [
        item.candidate_id for item in second.candidates
    ]
    assert artifacts.validation_metrics[
        "holdout_rows_excluded_from_fit_and_score"
    ] == int(holdout_mask.sum())
    for candidate in artifacts.candidates:
        assert candidate.leaf_node_id >= 0
        assert candidate.source_dataset_hash
        assert candidate.imputation_values
        assert candidate.label_entry_semantics == "NEXT_LEGAL_BAR_OPEN"
        assert_rule_oracle_agreement(split, candidate)


def test_candidate_evaluation_preserves_frozen_imputation_and_claim_boundary() -> None:
    dataset = chronological_split(
        build_discovery_dataset(synthetic_bars(), config=config())
    )
    validation_index = dataset.index[dataset["split"] == "VALIDATION"][0]
    dataset.loc[validation_index, "relative_volume_20"] = np.nan
    candidate = StrategyCandidate(
        candidate_id="manual_test_candidate",
        conditions=(RuleCondition("relative_volume_20", ">", 0.8),),
        target_atr=config().target_atr,
        stop_atr=config().stop_atr,
        maximum_holding_bars=config().barrier_horizon_bars,
        feature_schema_version=dataset["feature_schema_version"].iloc[0],
        label_schema_version=dataset["label_schema_version"].iloc[0],
        discovery_start=str(dataset["decision_timestamp"].min()),
        discovery_end=str(dataset["decision_timestamp"].max()),
        discovery_rows=100,
        discovery_sessions=8,
        leaf_probability=0.6,
        imputation_values=(
            FeatureImputation(feature="relative_volume_20", value=1.0),
        ),
    )
    assert candidate_mask(dataset.loc[[validation_index]], candidate).iloc[0]
    metrics = evaluate_candidate(dataset, candidate)
    assert metrics["trades"] > 0
    assert metrics["claim_boundary"] == "UNDERLYING_RESEARCH_LABELS_NOT_OPTION_PNL"
    assert "label_profit_factor" in metrics
    assert_rule_oracle_agreement(dataset, candidate)
    assert set(run_negative_controls(dataset, candidate)) == {
        "original",
        "label_permutation",
        "timestamp_shift",
        "condition_ablations",
    }
    stability_cases = parameter_stability(dataset, candidate)
    assert sum(1 for _ in stability_cases) == 4
    with pytest.raises(PermissionError):
        evaluate_locked_holdout_once(dataset, candidate, acknowledgement="NO")


def test_labels_enter_at_next_legal_bar_open() -> None:
    bars = pd.DataFrame(
        {
            "session_date": ["2026-01-05"] * 3,
            "open": [100.0, 110.0, 111.0],
            "high": [101.0, 111.2, 112.0],
            "low": [99.0, 109.8, 110.0],
            "close": [100.0, 111.0, 111.5],
        }
    )
    labels = compute_triple_barrier_labels(
        bars,
        pd.Series([1.0, 1.0, 1.0]),
        horizon_bars=1,
        target_atr=1.0,
        stop_atr=1.0,
        side="LONG",
    )
    assert labels.loc[0, "label_entry_price"] == 110.0
    assert labels.loc[0, "barrier_outcome"] == "TARGET_FIRST"
    assert labels.loc[0, "label_entry_semantics"] == "NEXT_LEGAL_BAR_OPEN"


def test_same_bar_collision_is_ambiguous_and_conservative() -> None:
    bars = pd.DataFrame(
        {
            "session_date": ["2026-01-05"] * 3,
            "open": [100.0, 100.0, 100.0],
            "close": [100.0, 100.0, 100.0],
            "high": [100.0, 102.0, 100.0],
            "low": [100.0, 98.0, 100.0],
        }
    )
    labels = compute_triple_barrier_labels(
        bars,
        pd.Series([1.0, 1.0, 1.0]),
        horizon_bars=1,
        target_atr=1.0,
        stop_atr=1.0,
        side="LONG",
    )
    assert labels.loc[0, "barrier_outcome"] == "AMBIGUOUS_SAME_BAR"
    assert labels.loc[0, "label_return_r"] == -1.0


def test_labels_never_cross_session_boundary_and_short_direction_is_correct() -> None:
    boundary = pd.DataFrame(
        {
            "session_date": ["2026-01-05", "2026-01-05", "2026-01-06"],
            "open": [100.0, 100.0, 120.0],
            "close": [100.0, 100.0, 120.0],
            "high": [100.0, 100.2, 125.0],
            "low": [100.0, 99.8, 119.0],
        }
    )
    labels = compute_triple_barrier_labels(
        boundary,
        pd.Series([1.0, 1.0, 1.0]),
        horizon_bars=1,
        target_atr=1.0,
        stop_atr=1.0,
        side="LONG",
    )
    assert labels.loc[1, "barrier_outcome"] == "UNAVAILABLE"
    assert labels.loc[1, "label_status"] == "SESSION_ENDED_BEFORE_HORIZON"

    short = pd.DataFrame(
        {
            "session_date": ["2026-01-05"] * 3,
            "open": [100.0, 100.0, 99.0],
            "close": [100.0, 99.0, 98.0],
            "high": [100.0, 100.2, 99.5],
            "low": [100.0, 98.5, 97.5],
        }
    )
    short_labels = compute_triple_barrier_labels(
        short,
        pd.Series([1.0, 1.0, 1.0]),
        horizon_bars=1,
        target_atr=1.0,
        stop_atr=1.0,
        side="SHORT",
    )
    assert short_labels.loc[0, "barrier_outcome"] == "TARGET_FIRST"
    assert short_labels.loc[0, "label_return_r"] == 1.0
