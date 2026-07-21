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
            high = max(open_price, close_price) + abs(rng.normal(2.5, 1.0))
            low = min(open_price, close_price) - abs(rng.normal(2.5, 1.0))
            volume = (
                1000
                + 15 * bar
                + (1200 if bar < 20 else 0)
                + rng.integers(0, 500)
            )
            rows.append(
                {
                    "timestamp": start + pd.Timedelta(minutes=bar),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close_price,
                    "volume": float(volume),
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


def test_start_labelled_bar_is_available_only_at_bar_end() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-05 09:15:00")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10.0],
        }
    )
    normalized = normalize_bars(
        bars,
        DiscoveryConfig(
            instrument="NIFTY",
            timestamp_semantics="START",
            source_timezone="Asia/Kolkata",
            bar_interval_minutes=1,
        ),
    )
    assert normalized.loc[0, "bar_start_timestamp"] == pd.Timestamp(
        "2026-01-05 03:45:00+00:00"
    )
    assert normalized.loc[0, "bar_end_timestamp"] == pd.Timestamp(
        "2026-01-05 03:46:00+00:00"
    )
    assert normalized.loc[0, "timestamp"] == normalized.loc[0, "bar_end_timestamp"]


def test_end_labelled_bar_maps_to_same_completed_interval() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-05 09:16:00")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10.0],
        }
    )
    normalized = normalize_bars(
        bars,
        DiscoveryConfig(
            instrument="NIFTY",
            timestamp_semantics="END",
            source_timezone="Asia/Kolkata",
            bar_interval_minutes=1,
        ),
    )
    assert normalized.loc[0, "bar_start_timestamp"] == pd.Timestamp(
        "2026-01-05 03:45:00+00:00"
    )
    assert normalized.loc[0, "bar_end_timestamp"] == pd.Timestamp(
        "2026-01-05 03:46:00+00:00"
    )


def test_strict_cadence_fails_closed() -> None:
    bars = synthetic_bars(days=1, bars_per_day=80).drop(index=20).reset_index(drop=True)
    with pytest.raises(ValueError, match="strict bar cadence violated"):
        normalize_bars(bars, config())


def test_dataset_is_deterministic_and_marks_missing_option_data() -> None:
    bars = synthetic_bars()
    first = build_discovery_dataset(bars, config=config())
    second = build_discovery_dataset(
        bars.sample(frac=1.0, random_state=4),
        config=config(),
    )

    assert semantic_dataset_hash(first) == semantic_dataset_hash(second)
    assert set(first["option_data_availability"]) == {"UNAVAILABLE"}
    assert set(first["option_data_reason"]) == {
        "historical_bid_ask_path_not_supplied"
    }
    assert (first["source_data_max_timestamp"] <= first["decision_timestamp"]).all()
    assert (first["bar_start_timestamp"] < first["bar_end_timestamp"]).all()
    assert set(first["timestamp_semantics"]) == {"START"}
    assert first["feature_schema_version"].nunique() == 1
    assert first["label_schema_version"].nunique() == 1


def test_duplicate_timestamps_fail_closed() -> None:
    bars = synthetic_bars(days=2)
    duplicate = pd.concat([bars, bars.iloc[[10]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate timestamps fail closed"):
        build_discovery_dataset(duplicate, config=config())


def test_future_mutation_changes_labels_not_features() -> None:
    bars = synthetic_bars()
    evidence = assert_future_mutation_does_not_change_features(
        bars,
        decision_row=300,
        config=config(),
    )
    assert evidence["features_unchanged"] is True
    assert evidence["labels_changed"] is True
    assert evidence["feature_columns_checked"] >= 25


def test_chronological_split_locks_holdout() -> None:
    dataset = build_discovery_dataset(synthetic_bars(), config=config())
    split = chronological_split(dataset)
    dev_end = split.loc[
        split["split"] == "DEVELOPMENT", "decision_timestamp"
    ].max()
    validation_start = split.loc[
        split["split"] == "VALIDATION", "decision_timestamp"
    ].min()
    validation_end = split.loc[
        split["split"] == "VALIDATION", "decision_timestamp"
    ].max()
    holdout_start = split.loc[
        split["split"] == "HOLDOUT_LOCKED", "decision_timestamp"
    ].min()
    assert dev_end < validation_start
    assert validation_end < holdout_start
    dev_sessions = set(split.loc[split["split"] == "DEVELOPMENT", "session_date"])
    validation_sessions = set(
        split.loc[split["split"] == "VALIDATION", "session_date"]
    )
    holdout_sessions = set(
        split.loc[split["split"] == "HOLDOUT_LOCKED", "session_date"]
    )
    assert dev_sessions.isdisjoint(validation_sessions)
    assert dev_sessions.isdisjoint(holdout_sessions)
    assert validation_sessions.isdisjoint(holdout_sessions)


def test_training_does_not_fit_or_score_locked_holdout() -> None:
    dataset = build_discovery_dataset(synthetic_bars(), config=config())
    split = chronological_split(dataset)
    artifacts = train_discovery_models(
        split,
        config=config(),
        max_tree_depth=3,
        minimum_leaf_rows=10,
    )

    mutated = split.copy()
    holdout = mutated["split"] == "HOLDOUT_LOCKED"
    mutated.loc[holdout, "barrier_outcome"] = "TARGET_FIRST"
    mutated.loc[holdout, "label_return_r"] = 99.0
    second = train_discovery_models(
        mutated,
        config=config(),
        max_tree_depth=3,
        minimum_leaf_rows=10,
    )

    assert artifacts.validation_metrics == second.validation_metrics
    assert [candidate.candidate_id for candidate in artifacts.candidates] == [
        candidate.candidate_id for candidate in second.candidates
    ]
    assert artifacts.validation_metrics[
        "holdout_rows_excluded_from_fit_and_score"
    ] == int(holdout.sum())
    for candidate in artifacts.candidates:
        assert candidate.leaf_node_id >= 0
        assert candidate.source_dataset_hash
        assert candidate.imputation_values
        assert_rule_oracle_agreement(split, candidate)


def test_candidate_evaluation_preserves_frozen_imputation() -> None:
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

    selected = candidate_mask(dataset.loc[[validation_index]], candidate)
    assert selected.iloc[0]
    validation = evaluate_candidate(dataset, candidate)
    assert validation["trades"] > 0
    assert validation["claim_boundary"] == "UNDERLYING_RESEARCH_LABELS_NOT_OPTION_PNL"
    assert "label_profit_factor" in validation
    assert_rule_oracle_agreement(dataset, candidate)
    controls = run_negative_controls(dataset, candidate)
    assert set(controls) == {
        "original",
        "label_permutation",
        "timestamp_shift",
        "condition_ablations",
    }
    stability = parameter_stability(dataset, candidate)
    assert len(stability) == 4

    with pytest.raises(PermissionError):
        evaluate_locked_holdout_once(dataset, candidate, acknowledgement="NO")
    holdout = evaluate_locked_holdout_once(
        dataset,
        candidate,
        acknowledgement="EVALUATE_FROZEN_CANDIDATE_ONCE",
    )
    assert holdout["trades"] > 0


def test_same_bar_collision_is_ambiguous_and_conservative() -> None:
    bars = pd.DataFrame(
        {
            "close": [100.0, 100.0, 100.0],
            "high": [100.0, 102.0, 100.0],
            "low": [100.0, 98.0, 100.0],
        }
    )
    atr = pd.Series([1.0, 1.0, 1.0])
    labels = compute_triple_barrier_labels(
        bars,
        atr,
        horizon_bars=1,
        target_atr=1.0,
        stop_atr=1.0,
        side="LONG",
    )
    assert labels.loc[0, "barrier_outcome"] == "AMBIGUOUS_SAME_BAR"
    assert labels.loc[0, "label_return_r"] == -1.0


def test_barrier_labels_never_cross_session_boundary() -> None:
    bars = pd.DataFrame(
        {
            "session_date": [
                "2026-01-05",
                "2026-01-05",
                "2026-01-06",
                "2026-01-06",
            ],
            "close": [100.0, 100.0, 120.0, 120.0],
            "high": [100.0, 100.2, 125.0, 125.0],
            "low": [100.0, 99.8, 119.0, 119.0],
        }
    )
    labels = compute_triple_barrier_labels(
        bars,
        pd.Series([1.0, 1.0, 1.0, 1.0]),
        horizon_bars=1,
        target_atr=1.0,
        stop_atr=1.0,
        side="LONG",
    )
    assert labels.loc[1, "barrier_outcome"] == "UNAVAILABLE"
    assert labels.loc[1, "label_status"] == "SESSION_ENDED_BEFORE_HORIZON"


def test_short_side_labels_are_directionally_correct() -> None:
    bars = pd.DataFrame(
        {
            "session_date": ["2026-01-05"] * 3,
            "close": [100.0, 99.0, 98.0],
            "high": [100.0, 99.5, 98.5],
            "low": [100.0, 98.5, 97.5],
        }
    )
    labels = compute_triple_barrier_labels(
        bars,
        pd.Series([1.0, 1.0, 1.0]),
        horizon_bars=1,
        target_atr=1.0,
        stop_atr=1.0,
        side="SHORT",
    )
    assert labels.loc[0, "barrier_outcome"] == "TARGET_FIRST"
    assert labels.loc[0, "label_return_r"] == 1.0
