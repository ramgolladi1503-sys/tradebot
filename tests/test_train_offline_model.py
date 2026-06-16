from __future__ import annotations

import json

import joblib
import pandas as pd

from scripts.train_offline_model import train_offline_model


def test_train_offline_model_writes_artifacts(tmp_path):
    src = tmp_path / "labels.csv"
    pd.DataFrame(
        [
            {"timestamp": "2022-03-01T09:15:00+00:00", "open": 1, "high": 2, "low": 1, "close": 10, "volume": 100, "label_up": 1},
            {"timestamp": "2022-03-01T09:20:00+00:00", "open": 2, "high": 3, "low": 2, "close": 12, "volume": 120, "label_up": 1},
            {"timestamp": "2022-03-01T09:25:00+00:00", "open": 3, "high": 4, "low": 3, "close": 11, "volume": 130, "label_up": 0},
            {"timestamp": "2022-03-01T09:30:00+00:00", "open": 4, "high": 5, "low": 4, "close": 13, "volume": 140, "label_up": 1},
            {"timestamp": "2022-03-01T09:35:00+00:00", "open": 5, "high": 6, "low": 5, "close": 9, "volume": 150, "label_up": 0},
            {"timestamp": "2022-03-01T09:40:00+00:00", "open": 6, "high": 7, "low": 6, "close": 14, "volume": 160, "label_up": 1},
            {"timestamp": "2022-03-01T09:45:00+00:00", "open": 7, "high": 8, "low": 7, "close": 8, "volume": 170, "label_up": 0},
            {"timestamp": "2022-03-01T09:50:00+00:00", "open": 8, "high": 9, "low": 8, "close": 15, "volume": 180, "label_up": 1},
            {"timestamp": "2022-03-01T09:55:00+00:00", "open": 9, "high": 10, "low": 9, "close": 7, "volume": 190, "label_up": 0},
            {"timestamp": "2022-03-01T10:00:00+00:00", "open": 10, "high": 11, "low": 10, "close": 16, "volume": 200, "label_up": 1},
        ]
    ).to_csv(src, index=False)

    model_out = tmp_path / "model.joblib"
    metrics_out = tmp_path / "metrics.json"

    report = train_offline_model(
        input_csv=src,
        model_output=model_out,
        metrics_output=metrics_out,
        feature_columns=["open", "high", "low", "close", "volume"],
        label_column="label_up",
        test_fraction=0.2,
    )

    assert model_out.exists()
    assert metrics_out.exists()
    bundle = joblib.load(model_out)
    assert bundle["feature_columns"] == ["open", "high", "low", "close", "volume"]
    assert bundle["label_column"] == "label_up"
    assert list(bundle["model"].named_steps.keys()) == ["scaler", "classifier"]
    payload = json.loads(metrics_out.read_text())
    assert payload["model_type"] == "StandardScaledLogisticRegression"
    assert "reject_gate" in payload
    assert payload["reject_gate"].get("status") in {"missing_return_col", None}
    assert report["rows"] == 10
    assert "accuracy" in report
    assert report["train_rows"] == 8
    assert report["test_rows"] == 2


def test_train_offline_model_uses_engineered_features(tmp_path):
    src = tmp_path / "labels.csv"
    rows = []
    for idx in range(60):
        rows.append(
            {
                "timestamp": f"2022-03-01T09:{15 + idx:02d}:00+00:00",
                "open": 100 + idx,
                "high": 101 + idx,
                "low": 99 + idx,
                "close": 100.5 + idx,
                "volume": 1000 + idx * 10,
                "label_up": int(idx % 2 == 0),
            }
        )
    pd.DataFrame(rows).to_csv(src, index=False)

    model_out = tmp_path / "model.joblib"
    report = train_offline_model(
        input_csv=src,
        model_output=model_out,
        feature_columns=None,
        label_column="label_up",
        test_fraction=0.2,
    )

    bundle = joblib.load(model_out)
    assert list(bundle["model"].named_steps.keys()) == ["scaler", "classifier"]
    assert "sma_10" in bundle["feature_columns"]
    assert "atr_14" in bundle["feature_columns"]
    assert report["rows"] < 60
    assert report["train_rows"] + report["test_rows"] == report["rows"]


def test_train_offline_model_rejects_missing_label(tmp_path):
    src = tmp_path / "bad.csv"
    pd.DataFrame([{"timestamp": "2022-03-01T09:15:00+00:00", "open": 1, "high": 2, "low": 1, "close": 10, "volume": 100}]).to_csv(src, index=False)
    model_out = tmp_path / "model.joblib"

    try:
        train_offline_model(input_csv=src, model_output=model_out)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "missing_label_column" in str(exc)


def test_train_offline_model_supports_random_forest(tmp_path):
    src = tmp_path / "labels.csv"
    rows = []
    for idx in range(100):
        rows.append(
            {
                "timestamp": f"2022-03-01T09:{idx:02d}:00+00:00",
                "open": 100 + idx,
                "high": 101 + idx,
                "low": 99 + idx,
                "close": 100.5 + idx,
                "volume": 1000 + idx * 10,
                "label_up": int(idx % 3 == 0),
            }
        )
    pd.DataFrame(rows).to_csv(src, index=False)

    model_out = tmp_path / "rf.joblib"
    metrics_out = tmp_path / "rf.json"
    report = train_offline_model(
        input_csv=src,
        model_output=model_out,
        metrics_output=metrics_out,
        label_column="label_up",
        test_fraction=0.2,
        model_family="random_forest",
    )

    bundle = joblib.load(model_out)
    assert bundle["metrics"]["model_family"] == "random_forest"
    assert bundle["metrics"]["model_type"] == "RandomForestClassifier"
    assert "reject_gate" in bundle["metrics"]
    assert report["model_output"] == str(model_out)
    assert metrics_out.exists()
