from __future__ import annotations

import numpy as np
import pandas as pd

from research.ml_strategy_discovery_v2.model import (
    finite_training_features,
    fit_imputer,
    generate_candidates,
)


def _training_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    sessions = pd.bdate_range("2024-01-01", periods=12).strftime("%Y-%m-%d")
    values = np.linspace(-2.0, 2.0, num=len(sessions) * 10)
    for index, value in enumerate(values):
        rows.append(
            {
                "session_date": sessions[index // 10],
                "f1": float(value),
                "f2": float(np.cos(value)),
                "all_missing": np.nan,
                "all_infinite": np.inf if index % 2 == 0 else -np.inf,
                "label_return_r": 0.8 if value > 0.25 else -0.4,
            }
        )
    return pd.DataFrame.from_records(rows)


def test_finite_training_features_excludes_only_fold_unusable_columns() -> None:
    frame = _training_frame()
    usable, excluded = finite_training_features(
        frame, ["f1", "all_missing", "f2", "all_infinite"]
    )
    assert usable == ("f1", "f2")
    assert excluded == ("all_missing", "all_infinite")


def test_training_imputer_treats_infinity_as_missing() -> None:
    frame = pd.DataFrame({"f1": [1.0, np.inf, np.nan, 3.0, -np.inf]})
    imputer = fit_imputer(frame, ["f1"])
    transformed = imputer.transform(frame, ["f1"])
    assert imputer.values == {"f1": 2.0}
    assert transformed["f1"].tolist() == [1.0, 2.0, 2.0, 3.0, 2.0]


def test_candidate_search_records_fold_local_feature_exclusions() -> None:
    frame = _training_frame()
    first = generate_candidates(
        frame,
        features=["f1", "all_missing", "f2", "all_infinite"],
        min_samples_leaf=10,
        seed=17,
    )
    second = generate_candidates(
        frame,
        features=["f1", "all_missing", "f2", "all_infinite"],
        min_samples_leaf=10,
        seed=17,
    )
    assert first == second
    assert first
    for candidate in first:
        assert candidate["feature_names"] == ["f1", "f2"]
        assert candidate["requested_feature_names"] == [
            "f1",
            "all_missing",
            "f2",
            "all_infinite",
        ]
        assert candidate["excluded_nonfinite_features"] == [
            "all_missing",
            "all_infinite",
        ]
        assert "all_missing" not in {
            condition["feature"] for condition in candidate["conditions"]
        }


def test_candidate_search_returns_no_hypotheses_when_no_feature_is_usable() -> None:
    frame = _training_frame()
    candidates = generate_candidates(
        frame,
        features=["all_missing", "all_infinite"],
        min_samples_leaf=10,
        seed=17,
    )
    assert candidates == []
