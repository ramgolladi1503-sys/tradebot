from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.ml_strategy_discovery_v2 import artifacts, pipeline
from research.ml_strategy_discovery_v2.contracts import (
    DEVELOPMENT,
    FRESH_CONSUMED,
    FRESH_LOCKED,
    HOLDOUT_LOCKED,
    VALIDATION_CONSUMED,
    StabilityConfig,
    canonical_hash,
    is_forbidden_feature,
    require_causal_features,
)
from research.ml_strategy_discovery_v2.controls import run_negative_controls
from research.ml_strategy_discovery_v2.data import (
    ConfirmationAuthorizationError,
    DatasetRegistryViolation,
    TokenReplayViolation,
    consume_confirmation_authorization,
    default_registry,
    issue_confirmation_authorization,
    load_development_for_selection,
    load_registry,
    locked_confirmation_metadata,
    select_development_bars,
)
from research.ml_strategy_discovery_v2.folds import (
    fold_manifest_hash,
    generate_anchored_folds,
    generate_nested_folds,
)
from research.ml_strategy_discovery_v2.freeze import (
    candidate_bundle,
    write_frozen_registry,
)
from research.ml_strategy_discovery_v2.gates import (
    base_rate_gate,
    bootstrap_gate,
    concentration_gate,
    concentration_metrics,
    fold_gate,
    imputation_dependence,
    performance_metrics,
    session_bootstrap_expectancy,
    support_gate,
)
from research.ml_strategy_discovery_v2.model import (
    RuleReproductionError,
    fit_imputer,
    generate_candidates,
    rule_mask,
    semantic_frame_hash,
)
from research.ml_strategy_discovery_v2.source import (
    SourceCertificationError,
    development_manifest_payload,
    load_and_verify_manifest,
    resolve_source_file,
    verify_manifest_sidecar,
    verify_record_file,
)
from research.ml_strategy_discovery_v2.stability import (
    benjamini_hochberg,
    jaccard_selected_rows,
    max_statistic_test,
    permuted_labels_by_session,
    recurrence_summary,
    rule_similarity,
)


def _registry_payload() -> dict:
    return {
        "ranges": [
            {"name": DEVELOPMENT, "start": None, "end": "2025-09-05", "status": "A"},
            {"name": VALIDATION_CONSUMED, "start": "2025-09-08", "end": "2026-02-05", "status": "B"},
            {"name": HOLDOUT_LOCKED, "start": "2026-02-06", "end": "2026-07-10", "status": "C"},
            {"name": FRESH_CONSUMED, "start": "2026-07-11", "end": "2026-07-21", "status": "D"},
            {"name": FRESH_LOCKED, "start": "2026-07-22", "end": None, "status": "E"},
        ]
    }


def _candidate(threshold: float = 0.5) -> dict:
    return {
        "conditions": [{"feature": "f1", "operator": ">", "threshold": threshold}],
        "imputation_values": {"f1": 0.0},
        "rule_hash": canonical_hash({"threshold": threshold}),
    }


def _frame(sessions: int = 20, rows_per_session: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-01", periods=sessions).strftime("%Y-%m-%d")
    records = []
    for session_index, session in enumerate(dates):
        for bar in range(rows_per_session):
            f1 = float(rng.normal())
            records.append(
                {
                    "session_date": session,
                    "decision_timestamp": pd.Timestamp(session) + pd.Timedelta(minutes=bar),
                    "f1": f1,
                    "f2": float(rng.normal()),
                    "label_return_r": 0.6 if f1 > 0.5 else -0.3,
                    "trend_regime": float(session_index % 3 - 1),
                    "volatility_regime": float(session_index % 2),
                    "gap_regime": float(session_index % 2),
                    "time_regime": float(bar // max(1, rows_per_session // 3)),
                }
            )
    return pd.DataFrame.from_records(records)


def _write_manifest(tmp_path: Path, records: list[dict], policies: list[dict] | None = None) -> Path:
    path = tmp_path / "manifest.json"
    payload = {
        "source_manifest_version": "v2",
        "record_count": len(records),
        "records": records,
        "special_session_policies": policies or [],
    }
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    Path(f"{path}.sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return path


# Model and exact rule oracle

def test_imputer_uses_development_median() -> None:
    frame = pd.DataFrame({"f1": [1.0, np.nan, 9.0]})
    imputer = fit_imputer(frame, ["f1"])
    assert imputer.values["f1"] == 5.0
    assert imputer.transform(frame, ["f1"])["f1"].tolist() == [1.0, 5.0, 9.0]


def test_rule_mask_reports_imputation_dependency() -> None:
    frame = pd.DataFrame({"f1": [np.nan, 1.0, -1.0]})
    mask, dependent = rule_mask(frame, _candidate(0.5), return_imputation_dependency=True)
    assert mask.tolist() == [False, True, False]
    assert dependent.sum() == 0


def test_rule_mask_rejects_missing_imputation_map() -> None:
    with pytest.raises(RuleReproductionError, match="imputation"):
        rule_mask(pd.DataFrame({"f1": [1.0]}), {"conditions": _candidate()["conditions"]})


def test_generated_tree_rules_reproduce_source_leaves() -> None:
    frame = _frame(sessions=16, rows_per_session=12)
    candidates = generate_candidates(frame, features=["f1", "f2"], min_samples_leaf=12)
    assert candidates
    for candidate in candidates:
        mask = rule_mask(frame, candidate)
        assert canonical_hash(mask.astype(int).tolist()) == candidate["selected_row_mask_hash"]


def test_candidate_generation_is_deterministic() -> None:
    frame = _frame(sessions=16, rows_per_session=12)
    first = generate_candidates(frame, features=["f1", "f2"], min_samples_leaf=12, seed=42)
    second = generate_candidates(frame, features=["f1", "f2"], min_samples_leaf=12, seed=42)
    assert first == second


def test_semantic_frame_hash_ignores_input_row_order() -> None:
    frame = _frame(sessions=5, rows_per_session=4)
    columns = ["session_date", "decision_timestamp", "label_return_r", "f1"]
    assert semantic_frame_hash(frame, columns) == semantic_frame_hash(
        frame.sample(frac=1.0, random_state=9), columns
    )


# Statistics and recurrence

def test_benjamini_hochberg_known_values() -> None:
    adjusted = benjamini_hochberg([0.01, 0.04, 0.03])
    assert adjusted == pytest.approx([0.03, 0.04, 0.04])


def test_session_permutation_preserves_label_multiset() -> None:
    frame = _frame(sessions=10, rows_per_session=5)
    permuted = permuted_labels_by_session(frame, rng=np.random.default_rng(2))
    assert sorted(permuted.tolist()) == sorted(frame["label_return_r"].tolist())


def test_max_statistic_test_is_deterministic() -> None:
    frame = _frame(sessions=12, rows_per_session=6)
    candidate = _candidate(0.5)
    first = max_statistic_test(frame, [candidate], iterations=100, seed=3)
    second = max_statistic_test(frame, [candidate], iterations=100, seed=3)
    assert first == second
    assert first["hypothesis_count"] == 1


def test_rule_similarity_and_jaccard_detect_equivalence() -> None:
    frame = _frame(sessions=5, rows_per_session=5)
    candidate = _candidate(0.5)
    assert rule_similarity(candidate, candidate) == pytest.approx(1.0)
    assert jaccard_selected_rows(frame, candidate, candidate) == pytest.approx(1.0)


def test_recurrence_requires_rule_and_selected_row_stability() -> None:
    frame = _frame(sessions=5, rows_per_session=5)
    candidate = _candidate(0.5)
    close = _candidate(0.51)
    far = _candidate(5.0)
    passed = recurrence_summary(frame, candidate, [[close], [candidate], [close]])
    failed = recurrence_summary(frame, candidate, [[far], [], [far]])
    assert passed["passes_recurrence"]
    assert not failed["passes_recurrence"]


# Gates and controls

def test_performance_metrics_are_real_and_finite() -> None:
    frame = _frame(sessions=5, rows_per_session=5)
    metrics = performance_metrics(frame, rule_mask(frame, _candidate()))
    assert metrics["rows"] > 0
    assert metrics["expectancy_r"] > 0
    assert metrics["label_pf"] is None
    assert metrics["label_pf_unbounded"]


def test_support_and_base_rate_gates_fail_expected_cases() -> None:
    config = StabilityConfig(min_rows=10, min_sessions=3, bootstrap_iterations=100, permutation_iterations=100)
    assert not support_gate({"rows": 2, "sessions": 1, "support_rate": 0.01}, config)[0]
    assert not base_rate_gate({"expectancy_r": 0.1}, {"expectancy_r": 0.2})[0]


def test_fold_gate_checks_coverage_expectancy_and_concentration() -> None:
    config = StabilityConfig(bootstrap_iterations=100, permutation_iterations=100)
    records = [
        {"metrics": {"rows": 10, "expectancy_r": 0.2, "total_r": 2.0}},
        {"metrics": {"rows": 10, "expectancy_r": 0.2, "total_r": 2.0}},
        {"metrics": {"rows": 0, "expectancy_r": 0.0, "total_r": 0.0}},
    ]
    passed, reasons, summary = fold_gate(records, config)
    assert not passed
    assert "INSUFFICIENT_FOLD_COVERAGE" in reasons
    assert summary["trade_bearing_fraction"] == pytest.approx(2 / 3)


def test_concentration_gate_requires_real_regime_and_diversification() -> None:
    frame = _frame(sessions=10, rows_per_session=5)
    values = concentration_metrics(frame, rule_mask(frame, _candidate()))
    config = StabilityConfig(bootstrap_iterations=100, permutation_iterations=100)
    assert values["regime_columns"]
    assert isinstance(concentration_gate(values, config)[0], bool)
    values["largest_regime_positive_contribution"] = None
    assert "MISSING_REGIME_CONCENTRATION" in concentration_gate(values, config)[1]


def test_bootstrap_gate_requires_positive_lower_bound() -> None:
    assert not bootstrap_gate({"lower_95": 0.0})[0]
    assert bootstrap_gate({"lower_95": 0.01})[0]


def test_session_bootstrap_is_deterministic() -> None:
    frame = _frame(sessions=10, rows_per_session=5)
    mask = rule_mask(frame, _candidate())
    first = session_bootstrap_expectancy(frame, mask, iterations=100, seed=4)
    second = session_bootstrap_expectancy(frame, mask, iterations=100, seed=4)
    assert first == second


def test_imputation_dependence_is_measured() -> None:
    frame = _frame(sessions=5, rows_per_session=5)
    frame.loc[frame.index[:3], "f1"] = np.nan
    values = imputation_dependence(frame, _candidate(-0.1))
    assert 0 <= values["any_feature_fraction"] <= 1


def test_negative_controls_are_deterministic_and_comprehensive() -> None:
    frame = _frame(sessions=12, rows_per_session=40)
    candidate = _candidate(0.5)
    first = run_negative_controls(frame, candidate, seed=5)
    second = run_negative_controls(frame, candidate, seed=5)
    assert first == second
    required = {
        "row_label_permutation",
        "whole_session_label_permutation",
        "timestamp_shift_one_session",
        "one_bar_signal_latency",
        "two_bar_signal_latency",
        "abstract_cost_stress",
    }
    assert required.issubset(first["controls"])
    assert first["threshold_variant_count"] == 6
