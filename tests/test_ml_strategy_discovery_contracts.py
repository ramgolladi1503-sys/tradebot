from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from research.ml_strategy_discovery.audit import (
    audit_candidate,
    audit_observations,
)
from research.ml_strategy_discovery.contracts import (
    CandidateStrategySpec,
    DiscoveryObservation,
    FeatureValue,
    SafetyEnvelope,
)
from research.ml_strategy_discovery.dataset import (
    LabeledObservation,
    build_feature_matrix,
)
from research.ml_strategy_discovery.registry import CandidateRegistry
from research.ml_strategy_discovery.splits import (
    make_anchored_walk_forward,
    make_chronological_partitions,
)

UTC = timezone.utc
T0 = datetime(2026, 1, 2, 9, 30, tzinfo=UTC)


def observation(
    observation_id: str,
    minute: int = 0,
    feature_order: tuple[str, ...] = ("a", "b"),
) -> DiscoveryObservation:
    decision_at = T0 + timedelta(minutes=minute)
    values = {
        "a": FeatureValue(
            "a",
            1.0 + minute,
            decision_at,
            "completed_bar",
        ),
        "b": FeatureValue(
            "b",
            2.0 + minute,
            decision_at - timedelta(seconds=1),
            "prior_state",
        ),
    }
    return DiscoveryObservation(
        observation_id=observation_id,
        instrument="NIFTY",
        session_id=f"2026-01-{minute + 2:02d}",
        decision_at=decision_at,
        features={name: values[name] for name in feature_order},
    )


def candidate(**overrides) -> CandidateStrategySpec:
    payload = dict(
        candidate_id="opening_momentum_001",
        family="opening_state_momentum",
        hypothesis=(
            "Moderate gaps with participation and acceptance may continue."
        ),
        regime_conditions=("moderate_gap", "liquid_options"),
        event_sequence=(
            "opening_range_complete",
            "breakout",
            "hold",
        ),
        entry_rule="next legal bar open after hold confirmation",
        invalidation_rule="completed close below hold level",
        exit_rule="frozen target, stop, or time exit",
        maximum_holding_minutes=30,
        development_observations=100,
        development_sessions=50,
        source_dataset_hash="a" * 64,
    )
    payload.update(overrides)
    return CandidateStrategySpec(**payload)


def test_feature_contract_rejects_future_availability() -> None:
    leaked = DiscoveryObservation(
        observation_id="leak",
        instrument="NIFTY",
        session_id="2026-01-02",
        decision_at=T0,
        features={
            "a": FeatureValue(
                "a",
                1.0,
                T0 + timedelta(seconds=1),
                "future",
            )
        },
    )
    with pytest.raises(ValueError, match="leaks future information"):
        leaked.validate()


def test_feature_contract_rejects_naive_timestamp() -> None:
    row = DiscoveryObservation(
        observation_id="naive",
        instrument="NIFTY",
        session_id="2026-01-02",
        decision_at=datetime(2026, 1, 2, 9, 30),
        features={
            "a": FeatureValue("a", 1.0, T0, "completed_bar")
        },
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        row.validate()


def test_semantic_hash_is_mapping_order_independent() -> None:
    assert observation(
        "same",
        feature_order=("a", "b"),
    ).evidence_hash == observation(
        "same",
        feature_order=("b", "a"),
    ).evidence_hash


def test_safety_envelope_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsafe discovery envelope"):
        SafetyEnvelope(allowed_for_live_execution=True).validate()


def test_matrix_is_chronological_and_schema_locked() -> None:
    feature_names, X, y, ids = build_feature_matrix(
        [
            LabeledObservation(observation("later", 1), 1),
            LabeledObservation(observation("earlier", 0), 0),
        ]
    )
    assert feature_names == ("a", "b")
    assert ids == ("earlier", "later")
    assert X == [[1.0, 2.0], [2.0, 3.0]]
    assert y == [0, 1]


def test_matrix_rejects_inconsistent_feature_schema() -> None:
    incomplete = DiscoveryObservation(
        observation_id="incomplete",
        instrument="NIFTY",
        session_id="2026-01-09",
        decision_at=T0 + timedelta(days=7),
        features={"a": FeatureValue("a", 1.0, T0, "prior")},
    )
    with pytest.raises(ValueError, match="inconsistent feature schema"):
        build_feature_matrix(
            [
                LabeledObservation(observation("full"), 1),
                LabeledObservation(incomplete, 0),
            ]
        )


def test_chronological_partitions_are_disjoint() -> None:
    sessions = tuple(
        f"2026-01-{day:02d}" for day in range(1, 11)
    )
    plan = make_chronological_partitions(sessions)
    assert plan.development == sessions[:6]
    assert plan.validation == sessions[6:8]
    assert plan.holdout == sessions[8:]


def test_walk_forward_has_explicit_purge_gap() -> None:
    sessions = tuple(
        f"2026-01-{day:02d}" for day in range(1, 13)
    )
    folds = make_anchored_walk_forward(
        sessions,
        minimum_train_sessions=5,
        purge_sessions=1,
        test_sessions=2,
        step_sessions=2,
    )
    assert folds[0].train_sessions == sessions[:5]
    assert folds[0].purge_sessions == sessions[5:6]
    assert folds[0].test_sessions == sessions[6:8]
    assert all(
        not (set(fold.train_sessions) & set(fold.test_sessions))
        for fold in folds
    )


def test_registry_has_no_live_transition_and_requires_evidence() -> None:
    registry = CandidateRegistry([candidate()])
    with pytest.raises(ValueError, match="SHA-256"):
        registry.transition(
            "opening_momentum_001",
            "VALIDATION_READY",  # type: ignore[arg-type]
            evidence_hash="weak",
        )
    assert "LIVE" not in registry.export_json()


def test_candidate_audit_rejects_holdout_consumption() -> None:
    report = audit_candidate(
        candidate(),
        development_sessions=("2026-01-01", "2026-01-02"),
        validation_sessions=("2026-01-03",),
        holdout_sessions=("2026-01-04",),
        holdout_consumed_during_discovery=True,
    )
    assert report.verdict == "FAIL"
    assert "locked holdout" in report.failures[-1]


def test_observation_audit_detects_duplicate_ids() -> None:
    report = audit_observations(
        [observation("dup", 0), observation("dup", 1)]
    )
    assert report.verdict == "FAIL"
    assert any(
        "duplicate observation_id" in failure
        for failure in report.failures
    )
